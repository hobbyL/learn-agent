"""
Demo 预设剧本
=============

定义完整演示流程：一个救援调度任务目标 + 每个 HITL 检查点的预设人类回答。
剧本设计覆盖三种反馈类型：

1. approve   — 批准撤离操作
2. reject    — 否决危险派遣，给出替代指令
3. provide_info — 补充上游降雨量信息影响决策

目标：让 demo 模式无人值守跑完，同时展示 HITL 的全部能力。
"""

from __future__ import annotations

from schemas import FeedbackType, HITLResponse


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Demo 目标
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DEMO_GOAL = (
    "明川市刚发生 6.8 级地震，震中位于老城区。目前已知：\n"
    "1. 老城区明川小学有约 200 名师生被困\n"
    "2. 城北化工厂次生火灾正在蔓延\n"
    "3. 堰塞湖水位持续上涨，距警戒线仅 2 米\n\n"
    "请制定并执行救援调度方案，在有限资源下最大程度减少人员伤亡。"
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 预设反馈剧本
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 每个条目是一个 HITLResponse，按触发顺序消费。
# 用完后 fallback 到默认 approve。

DEMO_SCRIPT: list[HITLResponse] = [
    # 第 1 次 HITL：Agent 要派搜救队进危楼 → approve（学校师生优先）
    HITLResponse(
        feedback_type=FeedbackType.APPROVE,
        message="同意，学校师生是最高优先级，立即派遣搜救队。",
    ),

    # 第 2 次 HITL：Agent 要派消防队去化工厂 → provide_info（补充风储罐信息）
    HITLResponse(
        feedback_type=FeedbackType.PROVIDE_INFO,
        message="补充情报：化工厂 3 号储罐内是丙烷，泄漏量约 2 吨，风向为东南风，下风向 500 米有居民区。请据此调整消防方案。",
    ),

    # 第 3 次 HITL：Agent 要撤离老城区居民 → reject（改为先加固堰塞湖）
    HITLResponse(
        feedback_type=FeedbackType.REJECT,
        message="暂缓老城区大规模撤离。当前堰塞湖水位上升过快，优先派工程队加固坝体，撤离方案待水位稳定后再执行。",
    ),

    # 第 4 次 HITL：Agent 根据 reject 改为派工程队加固 → approve
    HITLResponse(
        feedback_type=FeedbackType.APPROVE,
        message="同意，工程队立即前往堰塞湖坝体加固。",
    ),

    # 第 5 次 HITL：如果触发泄洪决策 → approve
    HITLResponse(
        feedback_type=FeedbackType.APPROVE,
        message="同意控制性泄洪，已通知下游农田区居民转移。",
    ),
]

# 默认反馈：剧本用完后全部 approve
DEFAULT_RESPONSE = HITLResponse(
    feedback_type=FeedbackType.APPROVE,
    message="同意执行。",
)


def get_demo_script() -> list[HITLResponse]:
    """获取 demo 剧本（返回副本，避免状态污染）。"""
    return list(DEMO_SCRIPT)
