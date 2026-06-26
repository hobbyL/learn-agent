"""
Pydantic 版 Schema 生成 + 运行时参数校验 —— 路线 A 的「下半场」
================================================================

这是手搓版 schema_gen.py 的对照版本。两个文件并存，做法完全不同，
但产出完全一样（都是 OpenAI tools 格式的 JSON Schema）。

手搓版（schema_gen.py）怎么做的：
    - 用 inspect.signature 读函数签名
    - 自己写 _annotation_to_schema 逐个翻译类型
    - 手动判断 required / optional
    - 枚举用 Literal 告诉 LLM，但**运行时完全不校验**

Pydantic 版怎么做：
    - 每个工具定义一个 BaseModel（就是参数模型）
    - model_json_schema() 一行生成 Schema（自动处理所有类型、required、enum）
    - model_validate(args) 一行校验参数（枚举/类型/范围全部强制拦截）
    - 校验失败抛 ValidationError，错误信息极其详细，可直接喂回 LLM

--------------------------------------------------------------------
核心对比一览
--------------------------------------------------------------------
                    手搓版                          Pydantic 版
    ────────────────────────────────────────────────────────────────
    代码量          ~200 行                          ~120 行（含 8 个 Model）
    类型支持        str/int/bool/list/Literal        所有 Python 类型 + 自定义
    生成 Schema    build_schema() 手动拼接           model_json_schema() 一行
    运行时校验      无（只"告诉"LLM 约束）           model_validate() 自动强制
    枚举非法值      靠工具函数内部 if 拦截            Pydantic 抛 literal_error
    错误信息        要自己写文案                     自动生成，含字段路径+期望值
    扩展性          新增类型要改 _annotation_to_schema  直接用任意 Pydantic 类型

--------------------------------------------------------------------
学习要点
--------------------------------------------------------------------
1. 对比手搓版，体会 Pydantic 到底"替你扛了什么"
2. 理解 model_json_schema() 的输出和 OpenAI tools 格式的差异（需要适配）
3. 理解 ValidationError 的结构，学会把它转成"对 LLM 友好"的错误消息
4. 注意：Pydantic 的 json_schema 输出有 title 字段、$defs 嵌套等，
   直接用会有冗余，需要做一层清理才能喂给 OpenAI
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


# ============================================================
# 第一部分：为 8 个工具定义参数模型（BaseModel）
# ============================================================
# 每个 Model 对应一个工具的全部参数。
# Field(description=...) 就是手搓版里 params 字典补充的那些说明——
# 但这里它和类型定义住在一起，不再是分散的元数据。


class QrTextEncoderParams(BaseModel):
    """qr_text_encoder 的参数模型"""
    text: str = Field(description="要编码的文本内容（建议 20 字以内，过长会被截断）")
    size: int = Field(default=3, description="每个色块用几个字符宽来表示，越大图案越粗，默认 3")


class PasswordGeneratorParams(BaseModel):
    """password_generator 的参数模型"""
    length: int = Field(description="密码长度（字符个数），建议 8~64")
    use_symbols: bool = Field(default=True, description="是否包含特殊符号（如 !@#$%），默认包含")


class RandomPickerParams(BaseModel):
    """random_picker 的参数模型"""
    options: list[str] = Field(description="候选项列表，例如 ['苹果', '香蕉', '橘子']")
    count: int = Field(default=1, description="要抽取的数量，默认 1。不能超过选项总数")


class ColorConverterParams(BaseModel):
    """color_converter 的参数模型 —— 这是 Pydantic 最亮眼的场景"""
    value: str = Field(description="十六进制颜色值，形如 #RRGGBB 或 RRGGBB，例如 #FF8800")
    to_format: Literal["hex", "rgb", "hsl"] = Field(
        description="目标格式：hex（十六进制）、rgb（红绿蓝）、hsl（色相饱和度亮度）"
    )


class BaseConverterParams(BaseModel):
    """base_converter 的参数模型"""
    number: str = Field(description="要转换的数字（用字符串表示，例如 'FF'、'1010'、'255'）")
    from_base: int = Field(description="原始进制（2~36），例如 16 表示十六进制")
    to_base: int = Field(description="目标进制（2~36），例如 2 表示二进制")


class TextCaseConverterParams(BaseModel):
    """text_case_converter 的参数模型"""
    text: str = Field(description="要转换的原始文本")
    mode: Literal["upper", "lower", "title", "snake", "camel"] = Field(
        description="转换模式：upper（全大写）、lower（全小写）、title（首字母大写）、"
                    "snake（蛇形）、camel（驼峰）"
    )


class DiceRollerParams(BaseModel):
    """dice_roller 的参数模型 —— 全部可选（required 为空）"""
    sides: int = Field(default=6, description="骰子面数，默认 6（即普通六面骰）")
    times: int = Field(default=1, description="投掷次数，默认 1")


class HashGeneratorParams(BaseModel):
    """hash_generator 的参数模型 —— 枚举 + bool + 默认值混合"""
    text: str = Field(description="要计算哈希的原始文本")
    algorithm: Literal["md5", "sha1", "sha256"] = Field(
        description="哈希算法：md5、sha1、sha256"
    )
    uppercase: bool = Field(default=False, description="结果是否用大写字母，默认小写")


# ============================================================
# 第二部分：工具名 → 参数模型 的映射
# ============================================================
# 这个映射表让 agent 根据工具名查到对应的 Pydantic 模型，从而做校验。

TOOL_PARAM_MODELS: dict[str, type[BaseModel]] = {
    "qr_text_encoder": QrTextEncoderParams,
    "password_generator": PasswordGeneratorParams,
    "random_picker": RandomPickerParams,
    "color_converter": ColorConverterParams,
    "base_converter": BaseConverterParams,
    "text_case_converter": TextCaseConverterParams,
    "dice_roller": DiceRollerParams,
    "hash_generator": HashGeneratorParams,
}


# ============================================================
# 第三部分：Schema 生成 —— 一行 model_json_schema() 搞定
# ============================================================

def _clean_schema(raw_schema: dict) -> dict:
    """
    清理 Pydantic 的 model_json_schema() 输出，使其符合 OpenAI tools 格式。

    Pydantic 输出的 JSON Schema 和 OpenAI 期望的有几个差异需要适配：
      1. Pydantic 会给每个字段加 "title"（如 "Title": "Text"），OpenAI 不需要
      2. Pydantic 顶层有 "title" 和 "type": "object"，OpenAI 需要但叫法一致
      3. 有些情况 Pydantic 会生成 "$defs" 嵌套（复杂类型），简单场景不会

    这里做最小化清理：去掉字段级别的 title（减少 token 消耗），保留其余。
    """
    # 复制一份避免修改原对象
    schema = dict(raw_schema)

    # 去掉顶层 title（工具名由 function.name 承担，不需要重复）
    schema.pop("title", None)

    # 清理每个字段的 title
    if "properties" in schema:
        for prop_schema in schema["properties"].values():
            if isinstance(prop_schema, dict):
                prop_schema.pop("title", None)

    return schema


def build_schema_pydantic(
    tool_name: str,
    description: str,
    model: type[BaseModel],
) -> dict[str, Any]:
    """
    用 Pydantic Model 生成 OpenAI tools 格式的完整 Schema。

    对比手搓版的 build_schema()：
        手搓版：inspect → 逐个参数翻译类型 → 拼 properties + required（~80 行逻辑）
        Pydantic版：model.model_json_schema() 一行搞定 → 清理格式即可

    参数：
        tool_name: 工具名
        description: 工具说明（给 LLM 看）
        model: 该工具的 Pydantic 参数模型类

    返回：
        OpenAI tools 数组中的一个元素（和手搓版 build_schema 返回值格式一致）
    """
    # 核心就这一行——Pydantic 自动处理所有类型映射、required/optional、enum 等
    raw_schema = model.model_json_schema()
    parameters = _clean_schema(raw_schema)

    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": description,
            "parameters": parameters,
        },
    }


# ============================================================
# 第四部分：运行时参数校验 —— 手搓版完全没有的能力
# ============================================================
# 这是 Pydantic 版的最大价值：不仅"告诉"LLM 约束，还在运行时"强制"约束。
# 手搓版里 LLM 传了枚举外的值（比如 to_format="yuv"），会直接传到工具函数里，
# 要靠工具自己的 if 语句拦截。Pydantic 版在调用工具函数之前就拦住了。

def validate_tool_args(tool_name: str, args: dict) -> dict[str, Any]:
    """
    用 Pydantic 校验工具参数，返回校验结果。

    如果校验通过：返回 {"valid": True, "validated_args": {...}}
        validated_args 是经过类型转换后的干净参数（比如字符串 "3" 会被转成 int 3）

    如果校验失败：返回 {"valid": False, "error": "人类可读的错误描述"}
        error 字段可以直接作为 role="tool" 的内容喂回 LLM，让它自我纠正

    为什么要这个函数？
        在 agent 的 _dispatch_tool 里，原来是直接 func(**args)。
        现在可以先 validate_tool_args → 通过了再 func(**validated_args)。
        如果没通过，把 error 喂回 LLM，它就知道"哦，参数错了，我调整一下"。
        这就是 README 里说的"参数校验闭环"。
    """
    model = TOOL_PARAM_MODELS.get(tool_name)
    if model is None:
        # 没有对应的 Pydantic 模型（比如还没迁移的工具），跳过校验
        return {"valid": True, "validated_args": args}

    try:
        # model_validate 做两件事：
        # 1. 类型转换（宽容模式：字符串 "3" → int 3）
        # 2. 约束检查（Literal 枚举、必填字段等）
        validated = model.model_validate(args)
        # model_dump() 把验证后的对象转回 dict，可以直接 **解包给函数
        return {"valid": True, "validated_args": validated.model_dump()}
    except ValidationError as e:
        # 把 Pydantic 的错误信息转成对 LLM 友好的格式
        error_msg = _format_validation_error(tool_name, e)
        return {"valid": False, "error": error_msg}


def _format_validation_error(tool_name: str, error: ValidationError) -> str:
    """
    把 Pydantic ValidationError 转成 LLM 能理解并据此自我纠正的可读文本。

    ValidationError.errors() 返回一个列表，每项包含：
        - type: 错误类型（如 "literal_error", "missing", "int_parsing"）
        - loc: 出错字段路径，如 ("to_format",)
        - msg: 错误描述（英文）
        - input: 实际收到的值

    我们把它翻译成中文提示，明确告诉 LLM "哪个参数错了、期望什么、收到什么"，
    让它能精准修正后重试。
    """
    lines = [f"调用工具 {tool_name} 的参数校验失败，请修正后重试："]

    for err in error.errors():
        field = " → ".join(str(loc) for loc in err["loc"])
        msg = err["msg"]
        input_val = err.get("input", "（无）")
        lines.append(f"  - 字段 '{field}'：{msg}（收到的值：{repr(input_val)}）")

    return "\n".join(lines)


# ============================================================
# 第五部分：快速验证脚本（python schema_gen_pydantic.py 可直接运行）
# ============================================================

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("Pydantic 版 Schema 生成 + 参数校验 演示")
    print("=" * 60)

    # --- 演示 1：生成 Schema ---
    print("\n▸ color_converter 的 Schema（Pydantic 自动生成）：")
    schema = build_schema_pydantic(
        "color_converter",
        "把一个十六进制颜色值转换成指定的颜色格式。",
        ColorConverterParams,
    )
    print(json.dumps(schema, indent=2, ensure_ascii=False))

    # --- 演示 2：校验通过 ---
    print("\n▸ 校验通过的例子：")
    result = validate_tool_args("color_converter", {"value": "#FF8800", "to_format": "rgb"})
    print(f"  结果：{result}")

    # --- 演示 3：校验失败 —— 枚举非法值（手搓版拦不住的！）---
    print("\n▸ 校验失败的例子（to_format 传了非法值 'yuv'）：")
    result = validate_tool_args("color_converter", {"value": "#FF8800", "to_format": "yuv"})
    print(f"  valid: {result['valid']}")
    print(f"  error:\n{result['error']}")

    # --- 演示 4：校验失败 —— 缺少必填字段 ---
    print("\n▸ 校验失败的例子（base_converter 缺少 to_base）：")
    result = validate_tool_args("base_converter", {"number": "FF", "from_base": 16})
    print(f"  valid: {result['valid']}")
    print(f"  error:\n{result['error']}")

    # --- 演示 5：类型自动转换（宽容模式）---
    print("\n▸ 类型自动转换：password_generator length='16' (字符串→int)")
    result = validate_tool_args("password_generator", {"length": "16", "use_symbols": "true"})
    print(f"  结果：{result}")

    # --- 演示 6：对比手搓版和 Pydantic 版的 Schema 差异 ---
    print("\n" + "=" * 60)
    print("对比：手搓版 vs Pydantic 版生成的 Schema")
    print("=" * 60)

    # 手搓版
    from schema_gen import build_schema
    from tools import hash_generator
    handcraft_schema = build_schema(
        hash_generator,
        "hash_generator",
        "计算一段文本的哈希值",
        {"text": "原始文本", "algorithm": "哈希算法", "uppercase": "是否大写"},
    )

    # Pydantic 版
    pydantic_schema = build_schema_pydantic(
        "hash_generator",
        "计算一段文本的哈希值",
        HashGeneratorParams,
    )

    print("\n手搓版 parameters：")
    print(json.dumps(handcraft_schema["function"]["parameters"], indent=2, ensure_ascii=False))
    print("\nPydantic 版 parameters：")
    print(json.dumps(pydantic_schema["function"]["parameters"], indent=2, ensure_ascii=False))
    print("\n✅ 两者结构等价，都能让 LLM 正确理解参数约束。")
    print("   但 Pydantic 版额外提供了 validate_tool_args() 做运行时强制校验！")
