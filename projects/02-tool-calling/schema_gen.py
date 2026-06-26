"""
手搓 Schema 生成器 —— 路线 A 的「上半场」
================================================

这个文件是 02 学习路径里最能锻炼理解的部分。

它要回答一个问题：
    LLM 需要一份 JSON Schema 才知道"工具叫什么、有哪些参数、参数什么类型"。
    01 里这份 Schema 是我们手写的（写一遍函数签名，再手写一遍 Schema）。
    那能不能"只写函数，Schema 自动长出来"？

答案：能。Python 的函数自带签名信息（参数名、类型注解、默认值），
我们用标准库 inspect 把这些信息读出来，再翻译成 JSON Schema 的格式即可。
这就是所谓的「代码即 Schema」——函数本身就是唯一信息源，不再有第二份手写副本。

--------------------------------------------------------------------
这是「手搓版」，故意不依赖 Pydantic
--------------------------------------------------------------------
学习路线 A：先手搓（理解原理）→ 再换 Pydantic（学框架做法）。
手搓的意义在于：你会亲眼看到"从函数签名生成 Schema"要处理多少琐碎的事——
类型映射、可选 vs 必填、list 怎么办、枚举怎么办……
等你被这些细节折磨过一遍，再看 Pydantic 一行 model_json_schema() 搞定，
就能真正体会到框架到底替你扛了什么。

本文件支持的类型（够覆盖我们 8 个工具的参数）：
    str / int / float / bool        → 基础标量
    list[str] / list[int] 等         → 数组
    Literal["a", "b", "c"]           → 枚举（这是表达"只能从几个值里选"的标准方式）

不支持的（手搓版的边界，正是 Pydantic 的价值所在）：
    嵌套对象、Union、Optional[X] 的复杂组合、自定义校验规则……
"""

import inspect
import typing
from typing import Any, Callable, Literal, Optional, get_args, get_origin


# ============================================================
# 第一块：把 Python 类型「翻译」成 JSON Schema 的类型描述
# ============================================================
# JSON Schema 用字符串描述类型："string" / "integer" / "number" / "boolean" / "array"
# 我们要做的就是把 Python 的 str/int/float/bool/list[...] 映射过去。

# Python 基础类型 -> JSON Schema 的 "type" 字段
_BASIC_TYPE_MAP: dict[type, str] = {
    str:   "string",
    int:   "integer",
    float: "number",
    bool:  "boolean",
}


def _annotation_to_schema(annotation: Any) -> dict[str, Any]:
    """
    把单个参数的「类型注解」翻译成一段 JSON Schema 片段。

    例子：
        str                  -> {"type": "string"}
        int                  -> {"type": "integer"}
        list[str]            -> {"type": "array", "items": {"type": "string"}}
        Literal["a", "b"]    -> {"type": "string", "enum": ["a", "b"]}

    这是整个手搓过程的核心难点：要分情况讨论各种类型形态。
    """

    # ---- 情况 1：没写类型注解 ----
    # inspect 用 Parameter.empty 表示"这个参数没有类型注解"。
    # 没注解我们就无法判断类型，退而求其次当成 string（LLM 通常也能处理）。
    if annotation is inspect.Parameter.empty:
        return {"type": "string"}

    # ---- 情况 2：基础标量类型（str/int/float/bool）----
    # 注意 bool 要放在 int 之前判断——但用字典精确匹配 type，所以无所谓顺序。
    if annotation in _BASIC_TYPE_MAP:
        return {"type": _BASIC_TYPE_MAP[annotation]}

    # 接下来处理「带参数的泛型类型」，比如 list[str]、Literal["a","b"]。
    # get_origin / get_args 是标准库 typing 提供的工具：
    #   get_origin(list[str])        -> list
    #   get_args(list[str])          -> (str,)
    #   get_origin(Literal["a","b"]) -> Literal
    #   get_args(Literal["a","b"])   -> ("a", "b")
    origin = get_origin(annotation)
    args = get_args(annotation)

    # ---- 情况 3：Literal[...] 枚举 ----
    # Literal["hex", "rgb", "hsl"] 表示"这个参数只能取这几个值之一"。
    # 在 JSON Schema 里用 enum 字段表达。
    # 枚举值的类型（这里都是字符串）决定 "type"，我们取第一个值的类型。
    if origin is Literal:
        enum_values = list(args)
        # 推断枚举元素的 JSON 类型（我们的工具里枚举都是字符串，但顺手做通用些）
        elem_type = type(enum_values[0]) if enum_values else str
        json_type = _BASIC_TYPE_MAP.get(elem_type, "string")
        return {"type": json_type, "enum": enum_values}

    # ---- 情况 4：list[X] 数组 ----
    # JSON Schema 用 {"type": "array", "items": {...}} 描述数组，
    # items 描述"数组里每个元素长什么样"——这里递归调用自己来生成。
    if origin in (list, typing.List):
        # list[str] 的 args 是 (str,)；如果写的是裸 list（无元素类型），args 为空
        item_annotation = args[0] if args else str
        return {
            "type": "array",
            "items": _annotation_to_schema(item_annotation),
        }

    # ---- 情况 5：兜底 ----
    # 遇到手搓版不认识的类型（嵌套对象、Union 等），不报错，
    # 退化成 string 并留个记号。真实项目里你可能想抛错，但学习版里宽容处理，
    # 同时这也正好暴露"手搓版的能力边界"——这是 Pydantic 要来解决的。
    return {"type": "string"}


# ============================================================
# 第二块：读取函数签名，拼出完整的工具 Schema
# ============================================================

def build_schema(
    func: Callable,
    name: str,
    description: str,
    params: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """
    读取一个函数的签名，生成 OpenAI tools 格式的完整 Schema。

    参数：
        func (Callable): 被 @tool 装饰的工具函数
        name (str): 工具名
        description (str): 工具说明（给 LLM 看的整体描述）
        params (dict, optional): {参数名: 该参数的中文说明}，
                                 用来补充每个参数的 description——
                                 函数签名只有类型，没有"这个参数干嘛的"，靠它补上。

    返回（OpenAI tools 数组里的一个元素的格式）：
        {
            "type": "function",
            "function": {
                "name": "...",
                "description": "...",
                "parameters": {
                    "type": "object",
                    "properties": { 参数名: {类型描述...}, ... },
                    "required": [必填参数名, ...],
                },
            },
        }

    「必填 vs 可选」怎么判断？
        看函数参数有没有默认值：
            def f(a, b=1)  ->  a 必填，b 可选
        inspect 用 Parameter.empty 表示"没有默认值"。没默认值 = 必填。
    """
    params = params or {}

    # inspect.signature 拿到函数的参数列表（顺序、默认值、注解都在里面）
    sig = inspect.signature(func)

    properties: dict[str, Any] = {}  # 每个参数的类型描述
    required: list[str] = []         # 必填参数名列表

    for param_name, param in sig.parameters.items():
        # 跳过 *args / **kwargs 这类可变参数——它们无法用 JSON Schema 干净表达，
        # 我们的工具也不该用它们。
        if param.kind in (inspect.Parameter.VAR_POSITIONAL,
                           inspect.Parameter.VAR_KEYWORD):
            continue

        # 1) 把类型注解翻译成 Schema 片段
        prop_schema = _annotation_to_schema(param.annotation)

        # 2) 补上这个参数的自然语言说明（如果 @tool 的 params 里提供了）
        if param_name in params:
            prop_schema["description"] = params[param_name]

        # 3) 如果参数有默认值，把默认值也写进 Schema（对 LLM 是有用的提示）
        if param.default is not inspect.Parameter.empty:
            prop_schema["default"] = param.default
        else:
            # 没有默认值 = 必填
            required.append(param_name)

        properties[param_name] = prop_schema

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }
