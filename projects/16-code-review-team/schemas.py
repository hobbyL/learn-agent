"""
代码审查团队 —— Pydantic Schema 定义
====================================

定义审查员输出的结构化 schema（复用项目 09 的 strict 模式经验）。
"""

from pydantic import BaseModel, Field


class Finding(BaseModel):
    """单个审查发现"""
    file: str = Field(description="文件名")
    line: int = Field(description="行号")
    severity: str = Field(description="严重级别：P0（致命）/P1（严重）/P2（建议）")
    category: str = Field(description="问题分类")
    description: str = Field(description="问题描述")
    suggestion: str = Field(description="修复建议")


class ReviewResult(BaseModel):
    """审查员输出结果"""
    reviewer: str = Field(description="审查员名称")
    findings: list[Finding] = Field(description="发现的问题列表")
    summary: str = Field(description="审查总结")
    pass_review: bool = Field(description="是否通过审查")


def get_json_schema(model: type[BaseModel]) -> dict:
    """
    获取 Pydantic 模型的 JSON Schema（OpenAI strict 模式）。
    复用项目 09 的经验。
    """
    schema = model.model_json_schema()
    return _enforce_strict_schema(schema)


def _enforce_strict_schema(schema: dict) -> dict:
    """
    递归处理 schema，确保符合 OpenAI strict 模式要求：
    - 所有对象都有 additionalProperties: false
    - 所有属性都在 required 里
    """
    if isinstance(schema, dict):
        # 处理当前层级
        if schema.get("type") == "object":
            schema["additionalProperties"] = False
            if "properties" in schema:
                schema["required"] = list(schema["properties"].keys())

        # 递归处理所有子字段
        for key, value in schema.items():
            if isinstance(value, dict):
                schema[key] = _enforce_strict_schema(value)
            elif isinstance(value, list):
                schema[key] = [_enforce_strict_schema(item) if isinstance(item, dict) else item for item in value]

    return schema
