"""
HITL 数据模型 —— Pydantic schema + JSON Schema 生成
====================================================

定义 HITL 交互相关的结构化数据：
- HITLRequest：Agent 发起的人类审批请求
- HITLResponse：人类回复（approve / reject / provide_info）
- ActionResult：工具执行结果

复用 09 的 get_json_schema() + _enforce_strict_schema() 模式。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HITL 交互模型
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ApprovalType(str, Enum):
    """HITL 审批类型。"""

    LIFE_RISK = "life_risk"  # 人命风险
    IRREVERSIBLE = "irreversible"  # 不可逆操作
    RESOURCE_CONFLICT = "resource_conflict"  # 资源冲突
    HIGH_RISK = "high_risk"  # 超阈值风险


class HITLRequest(BaseModel):
    """Agent 发起的 HITL 审批请求。"""

    tool_name: str = Field(description="触发审批的工具名称")
    tool_args: dict[str, Any] = Field(description="工具调用参数")
    reason: str = Field(description="为什么需要人类确认（Agent 的说明）")
    approval_type: ApprovalType = Field(description="审批类型分类")
    risk_description: str = Field(description="风险描述：如果执行，可能的后果")
    current_situation: str = Field(description="当前态势摘要")


class FeedbackType(str, Enum):
    """人类反馈类型。"""

    APPROVE = "approve"  # 批准执行
    REJECT = "reject"  # 否决 + 替代指令
    PROVIDE_INFO = "provide_info"  # 补充信息


class HITLResponse(BaseModel):
    """人类对 HITL 请求的回复。"""

    feedback_type: FeedbackType = Field(description="反馈类型")
    message: str = Field(default="", description="人类的回复内容（reject 时为替代指令，provide_info 时为补充信息）")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 工具执行结果
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ActionResult(BaseModel):
    """工具执行结果。"""

    success: bool = Field(description="是否成功")
    message: str = Field(description="执行结果描述")
    alerts: list[str] = Field(default_factory=list, description="本步产生的警报")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# JSON Schema 工具（复用 09 模式）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _enforce_strict_schema(schema: dict) -> None:
    """递归修改 JSON Schema 以满足 OpenAI strict 模式要求。"""
    if "$defs" in schema:
        for def_schema in schema["$defs"].values():
            _enforce_strict_schema(def_schema)

    if schema.get("type") == "object" and "properties" in schema:
        schema["additionalProperties"] = False
        schema["required"] = list(schema["properties"].keys())
        for prop_schema in schema["properties"].values():
            _enforce_strict_schema(prop_schema)

    if schema.get("type") == "array" and "items" in schema:
        _enforce_strict_schema(schema["items"])


def get_json_schema(model_class: type[BaseModel], name: str | None = None) -> dict:
    """
    从 Pydantic Model 生成 OpenAI Structured Outputs 兼容的 JSON Schema。

    返回格式：{"name": "...", "strict": True, "schema": {...}}
    """
    schema = model_class.model_json_schema()
    _enforce_strict_schema(schema)

    return {
        "name": name or model_class.__name__,
        "strict": True,
        "schema": schema,
    }
