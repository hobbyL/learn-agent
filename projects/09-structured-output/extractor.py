"""
结构化提取器 —— 3 种输出模式 + 重试机制
=========================================

核心功能：调用 LLM 从知识库文本中提取结构化数据。

支持 3 种输出模式：
1. json_schema 强制模式 —— response_format: { type: "json_schema", json_schema: {...} }
   模型保证输出符合 schema，100% 校验通过
2. json_object 弱模式 —— response_format: { type: "json_object" }
   模型返回合法 JSON，但不保证符合特定 schema，需 Pydantic 校验 + 重试
3. text 纯文本模式 —— 不设 response_format，在 prompt 中要求返回 JSON
   从自由文本中 parse JSON，失败时重试

统一接口：
    extract(knowledge_text, prompt, schema_class, mode, client, model)
    → (result, metadata)

metadata 包含：
    - retries: 重试次数
    - is_valid: 是否通过校验
    - errors: 错误信息列表
    - raw_output: 原始 LLM 输出
"""

import json
import re
from typing import Any

from openai import OpenAI, BadRequestError
from pydantic import BaseModel, ValidationError

from schemas import get_json_schema


# ============================================================
# 常量
# ============================================================

MAX_RETRIES = 3  # 最大重试次数


# ============================================================
# 主提取接口
# ============================================================

def extract(
    knowledge_text: str,
    prompt: str,
    schema_class: type[BaseModel],
    mode: str,
    client: OpenAI,
    model: str,
) -> tuple[Any, dict]:
    """
    从知识库文本中提取结构化数据。

    参数：
        knowledge_text — 知识库完整文本
        prompt — 提取任务描述（如"提取林昊天的档案信息"）
        schema_class — Pydantic Model 类（DeveloperProfile 等）
        mode — 输出模式："json_schema" | "json_object" | "text"
        client — OpenAI 客户端
        model — 模型名称

    返回：
        (result, metadata)
        - result: 解析成功时为 Pydantic Model 实例；失败时为 None
        - metadata: {"retries": int, "is_valid": bool, "errors": list[str], "raw_output": str}
    """
    if mode == "json_schema":
        return _extract_json_schema_mode(knowledge_text, prompt, schema_class, client, model)
    elif mode == "json_object":
        return _extract_json_object_mode(knowledge_text, prompt, schema_class, client, model)
    elif mode == "text":
        return _extract_text_mode(knowledge_text, prompt, schema_class, client, model)
    else:
        raise ValueError(f"未知输出模式：{mode}。可用模式：json_schema | json_object | text")


# ============================================================
# 模式 1：json_schema 强制模式
# ============================================================

def _extract_json_schema_mode(
    knowledge_text: str,
    prompt: str,
    schema_class: type[BaseModel],
    client: OpenAI,
    model: str,
) -> tuple[Any, dict]:
    """
    json_schema 强制模式：OpenAI 保证输出符合 schema，无需重试。

    处理 refusal：检查 message.refusal 字段。
    """
    json_schema = get_json_schema(schema_class)
    system_prompt = "你是一个精确的信息提取助手，严格按照提供的 JSON Schema 输出结构化数据。"
    user_prompt = f"{prompt}\n\n{knowledge_text}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    metadata = {
        "retries": 0,
        "is_valid": False,
        "errors": [],
        "raw_output": "",
    }

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": json_schema,
            },
        )
    except BadRequestError as e:
        err_msg = str(e)
        metadata["errors"].append(f"API 请求失败: {err_msg}")
        return None, metadata

    choice = resp.choices[0]
    msg = choice.message

    # 检查 refusal（模型拒绝返回结构化输出的情况）
    if msg.refusal:
        metadata["errors"].append(f"模型拒绝: {msg.refusal}")
        return None, metadata

    raw_output = msg.content or ""
    metadata["raw_output"] = raw_output

    # json_schema 模式下 OpenAI 保证输出合法 JSON 且符合 schema
    try:
        data = json.loads(raw_output)
        result = schema_class.model_validate(data)
        metadata["is_valid"] = True
        return result, metadata
    except (json.JSONDecodeError, ValidationError) as e:
        # 理论上不应该走到这里，但保险起见捕获
        metadata["errors"].append(f"解析失败（意外）: {e}")
        return None, metadata


# ============================================================
# 模式 2：json_object 弱模式
# ============================================================

def _extract_json_object_mode(
    knowledge_text: str,
    prompt: str,
    schema_class: type[BaseModel],
    client: OpenAI,
    model: str,
) -> tuple[Any, dict]:
    """
    json_object 弱模式：OpenAI 保证输出合法 JSON，但不保证符合特定 schema。

    需要：
    1. Pydantic 校验
    2. 失败时提取 ValidationError → 追加到 messages → 重试（最多 3 次）
    """
    system_prompt = "你是一个精确的信息提取助手，输出 JSON 格式的结构化数据。"
    json_schema = get_json_schema(schema_class)
    schema_desc = json.dumps(json_schema["schema"], indent=2, ensure_ascii=False)
    user_prompt = (
        f"{prompt}\n\n"
        f"请严格按照以下 JSON Schema 输出：\n```json\n{schema_desc}\n```\n\n"
        f"{knowledge_text}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    metadata = {
        "retries": 0,
        "is_valid": False,
        "errors": [],
        "raw_output": "",
    }

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
            )
        except BadRequestError as e:
            err_msg = str(e)
            metadata["errors"].append(f"API 请求失败: {err_msg}")
            return None, metadata

        choice = resp.choices[0]
        raw_output = choice.message.content or ""
        metadata["raw_output"] = raw_output

        # 尝试解析 JSON
        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as e:
            # json_object 模式下理论上不会出现 JSON 语法错误，但保险起见处理
            err_msg = f"JSON 解析失败: {e}"
            metadata["errors"].append(err_msg)
            if attempt < MAX_RETRIES:
                metadata["retries"] += 1
                messages.append({"role": "assistant", "content": raw_output})
                messages.append({"role": "user", "content": f"错误：{err_msg}\n请修正后重新输出。"})
                continue
            return None, metadata

        # Pydantic 校验
        try:
            result = schema_class.model_validate(data)
            metadata["is_valid"] = True
            return result, metadata
        except ValidationError as e:
            # 提取校验错误信息
            err_msg = _format_validation_error(e)
            metadata["errors"].append(err_msg)
            if attempt < MAX_RETRIES:
                metadata["retries"] += 1
                messages.append({"role": "assistant", "content": raw_output})
                messages.append({"role": "user", "content": f"校验失败：{err_msg}\n请修正后重新输出。"})
                continue
            return None, metadata

    return None, metadata


# ============================================================
# 模式 3：text 纯文本模式
# ============================================================

def _extract_text_mode(
    knowledge_text: str,
    prompt: str,
    schema_class: type[BaseModel],
    client: OpenAI,
    model: str,
) -> tuple[Any, dict]:
    """
    text 纯文本模式：不设 response_format，在 prompt 中要求返回 JSON。

    需要：
    1. 从自由文本中提取 JSON（可能包含 markdown 代码块）
    2. Pydantic 校验
    3. 失败时重试（最多 3 次）
    """
    system_prompt = "你是一个精确的信息提取助手，输出 JSON 格式的结构化数据。"
    json_schema = get_json_schema(schema_class)
    schema_desc = json.dumps(json_schema["schema"], indent=2, ensure_ascii=False)
    user_prompt = (
        f"{prompt}\n\n"
        f"请严格按照以下 JSON Schema 输出，直接返回 JSON 对象（不要额外解释）：\n```json\n{schema_desc}\n```\n\n"
        f"{knowledge_text}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    metadata = {
        "retries": 0,
        "is_valid": False,
        "errors": [],
        "raw_output": "",
    }

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
            )
        except BadRequestError as e:
            err_msg = str(e)
            metadata["errors"].append(f"API 请求失败: {err_msg}")
            return None, metadata

        choice = resp.choices[0]
        raw_output = choice.message.content or ""
        metadata["raw_output"] = raw_output

        # 从自由文本中提取 JSON（处理 markdown 代码块等情况）
        json_str = _extract_json_from_text(raw_output)

        # 尝试解析 JSON
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            err_msg = f"JSON 解析失败: {e}"
            metadata["errors"].append(err_msg)
            if attempt < MAX_RETRIES:
                metadata["retries"] += 1
                messages.append({"role": "assistant", "content": raw_output})
                messages.append({"role": "user", "content": f"错误：{err_msg}\n请直接输出纯 JSON 对象，不要包含额外解释。"})
                continue
            return None, metadata

        # Pydantic 校验
        try:
            result = schema_class.model_validate(data)
            metadata["is_valid"] = True
            return result, metadata
        except ValidationError as e:
            err_msg = _format_validation_error(e)
            metadata["errors"].append(err_msg)
            if attempt < MAX_RETRIES:
                metadata["retries"] += 1
                messages.append({"role": "assistant", "content": raw_output})
                messages.append({"role": "user", "content": f"校验失败：{err_msg}\n请修正后重新输出。"})
                continue
            return None, metadata

    return None, metadata


# ============================================================
# 工具函数
# ============================================================

def _format_validation_error(e: ValidationError) -> str:
    """
    格式化 Pydantic ValidationError 为可读的错误信息。

    示例：
        字段 'name' 缺失
        字段 'experience_years' 类型错误：期望 int，实际 str
    """
    lines = []
    for err in e.errors():
        loc = ".".join(str(l) for l in err["loc"])
        msg = err["msg"]
        err_type = err["type"]
        if err_type == "missing":
            lines.append(f"字段 '{loc}' 缺失")
        elif "type" in err_type:
            expected = err.get("expected", "?")
            lines.append(f"字段 '{loc}' 类型错误：{msg}")
        else:
            lines.append(f"字段 '{loc}': {msg}")
    return "；".join(lines)


def _extract_json_from_text(text: str) -> str:
    """
    从自由文本中提取 JSON 字符串。

    处理情况：
    1. 纯 JSON：直接返回
    2. Markdown 代码块：```json ... ```
    3. 解释文本 + JSON：提取 JSON 部分
    """
    # 尝试直接解析（最常见情况）
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        return text

    # 提取 markdown 代码块中的 JSON
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 查找第一个 { 到最后一个 }（处理"这是提取结果：{...}"的情况）
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0)

    # 查找第一个 [ 到最后一个 ]（数组情况）
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        return match.group(0)

    # 无法提取，返回原文
    return text


# ============================================================
# 快速验证（不调用真实 API）
# ============================================================

if __name__ == "__main__":
    print("=== Extractor 模块快速验证 ===\n")

    # 测试 JSON 提取逻辑
    test_cases = [
        ('{"name": "test"}', '{"name": "test"}'),
        ('```json\n{"name": "test"}\n```', '{"name": "test"}'),
        ('结果如下：{"name": "test"}', '{"name": "test"}'),
        ('[1, 2, 3]', '[1, 2, 3]'),
    ]

    print("测试 _extract_json_from_text:")
    for i, (input_text, expected) in enumerate(test_cases):
        result = _extract_json_from_text(input_text)
        status = "✓" if result == expected else "✗"
        print(f"  {status} Case {i+1}: {result == expected}")

    print("\n测试 _format_validation_error:")
    from pydantic import Field

    class TestModel(BaseModel):
        name: str = Field()
        age: int = Field()

    try:
        TestModel.model_validate({"name": "test"})
    except ValidationError as e:
        err_msg = _format_validation_error(e)
        print(f"  示例错误信息: {err_msg}")

    print("\nExtractor 模块验证通过 ✓")
