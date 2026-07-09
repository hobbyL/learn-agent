"""
HITL 核心模块 —— 检查点拦截 + 反馈处理 + 容错
================================================

本模块是 11 项目的核心新知识点：实现"Agent 在工具调用前主动暂停"机制。

设计：
- HITLCheckpoint：检查点数据结构（当前要执行什么、为什么暂停、上下文）
- HITLHandler（协议类）：定义人类交互接口，有两个实现：
    - InteractiveHandler：从 stdin 获取真实人类输入
    - ScriptedHandler：从预设剧本自动应答（demo 模式）
- check_and_pause()：核心函数，判断工具是否需审批，暂停并获取反馈

容错设计：
- 连续 reject 上限（默认 3），超限后 Agent 优雅终止
- reject 后指令不可执行 → 报告不可行并二次请求
- 输入校验：空白/无效输入重新提示
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from schemas import ApprovalType, HITLRequest, HITLResponse, FeedbackType
from tools import get_approval_type, requires_approval


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 检查点数据结构
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class HITLCheckpoint:
    """一次 HITL 检查点的完整记录。"""

    tool_name: str
    tool_args: dict
    approval_type: str  # life_risk / irreversible / resource_conflict
    reason: str  # 为什么需要审批的自然语言说明
    context_summary: str  # 当前态势摘要
    response: HITLResponse | None = None
    attempt: int = 1  # 第几次请求（容错重试）


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 人类交互接口（协议类）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class HITLHandler(ABC):
    """HITL 交互处理器基类。"""

    @abstractmethod
    def request_feedback(self, checkpoint: HITLCheckpoint) -> HITLResponse:
        """请求人类反馈，返回结构化响应。"""
        ...


class InteractiveHandler(HITLHandler):
    """交互模式：从 stdin 获取真实人类输入。"""

    def request_feedback(self, checkpoint: HITLCheckpoint) -> HITLResponse:
        """通过 stdin 交互获取人类反馈。"""
        print()
        print("=" * 60)
        print(f"⏸  HITL 检查点 —— 需要指挥官确认")
        print("=" * 60)
        print(f"  操作：{checkpoint.tool_name}")
        print(f"  参数：{json.dumps(checkpoint.tool_args, ensure_ascii=False, indent=4)}")
        print(f"  风险类型：{_approval_type_desc(checkpoint.approval_type)}")
        print(f"  原因：{checkpoint.reason}")
        print()
        print(f"  当前态势：{checkpoint.context_summary}")
        print()
        print("─" * 60)
        print("  请选择操作：")
        print("    [1] approve  — 批准执行")
        print("    [2] reject   — 否决并给出替代指令")
        print("    [3] info     — 补充信息")
        print("─" * 60)

        while True:
            choice = input("  您的选择 (1/2/3): ").strip()

            if choice == "1":
                return HITLResponse(
                    feedback_type=FeedbackType.APPROVE,
                    message="批准执行",
                )

            elif choice == "2":
                instruction = ""
                while not instruction.strip():
                    instruction = input("  请输入替代指令: ").strip()
                return HITLResponse(
                    feedback_type=FeedbackType.REJECT,
                    message=instruction,
                )

            elif choice == "3":
                info = ""
                while not info.strip():
                    info = input("  请输入补充信息: ").strip()
                return HITLResponse(
                    feedback_type=FeedbackType.PROVIDE_INFO,
                    message=info,
                )

            else:
                print("  ⚠️ 无效输入，请输入 1、2 或 3")


class ScriptedHandler(HITLHandler):
    """
    脚本模式：从预设剧本自动应答（demo 模式）。

    剧本是一个列表，按顺序消费：每次 request_feedback 取下一个预设回答。
    如果剧本耗尽，默认 approve。
    """

    def __init__(self, script: list[HITLResponse]):
        self._script = list(script)  # 深拷贝
        self._index = 0

    def request_feedback(self, checkpoint: HITLCheckpoint) -> HITLResponse:
        """从预设剧本获取下一个回答。"""
        if self._index < len(self._script):
            response = self._script[self._index]
            self._index += 1
            return response
        # 剧本耗尽，默认批准
        return HITLResponse(
            feedback_type=FeedbackType.APPROVE,
            message="(剧本耗尽，自动批准)",
        )

    @property
    def remaining(self) -> int:
        """剩余剧本条目数。"""
        return max(0, len(self._script) - self._index)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 核心拦截逻辑
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


MAX_REJECT_RETRIES = 3


def should_pause(tool_name: str) -> bool:
    """判断工具调用是否需要暂停等待人类审批。"""
    return requires_approval(tool_name)


def build_checkpoint(
    tool_name: str,
    tool_args: dict,
    context_summary: str,
    attempt: int = 1,
) -> HITLCheckpoint:
    """构建 HITL 检查点。"""
    approval_type = get_approval_type(tool_name) or "unknown"

    # 根据审批类型和参数生成暂停原因
    reason = _generate_reason(tool_name, tool_args, approval_type)

    return HITLCheckpoint(
        tool_name=tool_name,
        tool_args=tool_args,
        approval_type=approval_type,
        reason=reason,
        context_summary=context_summary,
        attempt=attempt,
    )


def _generate_reason(tool_name: str, tool_args: dict, approval_type: str) -> str:
    """根据工具和参数生成暂停原因说明。"""
    reasons = {
        "dispatch_team": lambda a: f"将派遣 {a.get('team', '?')} 前往 {a.get('destination', '?')} 执行{a.get('mission', '?')}任务，队员面临人身安全风险",
        "evacuate": lambda a: f"将撤离 {a.get('area', '?')} 的 {a.get('population', '?')} 名居民至 {a.get('destination', '?')}，操作不可逆",
        "allocate_resource": lambda a: f"将分配 {a.get('amount', '?')}{a.get('resource', '?')} 至 {a.get('destination', '?')}，可能导致其他区域资源不足",
        "release_flood": lambda a: f"将对 {a.get('dam', '?')} 执行泄洪，{a.get('flood_zone', '?')} 将被淹没，操作不可逆",
    }

    generator = reasons.get(tool_name)
    if generator:
        return generator(tool_args)
    return f"工具 {tool_name} 标记为需审批（类型：{approval_type}）"


def _approval_type_desc(approval_type: str) -> str:
    """审批类型的中文描述。"""
    descs = {
        "life_risk": "🔴 人命风险",
        "irreversible": "⚠️ 不可逆操作",
        "resource_conflict": "🟡 资源冲突",
    }
    return descs.get(approval_type, f"❓ {approval_type}")
