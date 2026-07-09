"""
ANSI 着色展示层
===============

职责：所有终端输出的渲染，与业务逻辑解耦。
核心区分：Agent 自主执行（绿色）vs ⏸ 等待人类（黄色闪烁）。

对齐系列风格：03/04/10 display.py 的着色 + 状态图标设计。
"""

from __future__ import annotations

from schemas import FeedbackType, HITLResponse


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ANSI 颜色常量
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"

_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_BLUE = "\033[34m"
_CYAN = "\033[36m"
_MAGENTA = "\033[35m"
_WHITE = "\033[37m"

_BG_YELLOW = "\033[43m"
_BG_RED = "\033[41m"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 头部 / 任务目标
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_header(goal: str) -> None:
    """打印任务启动头部。"""
    print()
    print(f"{_BOLD}{_CYAN}{'═' * 60}{_RESET}")
    print(f"{_BOLD}{_CYAN}  🏢 明川市应急指挥中心 — HITL Agent{_RESET}")
    print(f"{_BOLD}{_CYAN}{'═' * 60}{_RESET}")
    print()
    print(f"{_BOLD}📋 任务目标：{_RESET}")
    for line in goal.strip().split("\n"):
        print(f"   {line}")
    print()
    print(f"{_DIM}{'─' * 60}{_RESET}")
    print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ReAct 步骤展示
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_thought(step: int, thought: str) -> None:
    """打印 Agent 思考步骤。"""
    print(f"  {_BLUE}🧠 Step {step} Thought:{_RESET}")
    for line in thought.strip().split("\n"):
        print(f"     {_DIM}{line}{_RESET}")
    print()


def print_action(tool_name: str, args: dict) -> None:
    """打印 Agent 工具调用。"""
    args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
    print(f"  {_GREEN}⚡ Action:{_RESET} {tool_name}({args_str})")


def print_observation(result: str) -> None:
    """打印工具执行结果。"""
    # 截断过长结果
    display_result = result if len(result) < 200 else result[:200] + "..."
    print(f"  {_CYAN}👁 Observation:{_RESET} {display_result}")
    print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HITL 交互展示（核心区分点）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_hitl_request(checkpoint) -> None:
    """打印 HITL 暂停请求——黄色高亮，视觉上与自主执行明显区分。"""
    print()
    print(f"  {_BOLD}{_YELLOW}╭{'─' * 56}╮{_RESET}")
    print(f"  {_BOLD}{_YELLOW}│  ⏸  HITL 检查点 — 需要指挥官确认{' ' * 20}│{_RESET}")
    print(f"  {_BOLD}{_YELLOW}╰{'─' * 56}╯{_RESET}")
    print()
    print(f"  {_YELLOW}📍 触发工具：{_RESET}{checkpoint.tool_name}")
    print(f"  {_YELLOW}⚠️  触发原因：{_RESET}{checkpoint.reason}")
    approval = checkpoint.approval_type
    if approval:
        risk_color = _RED if "life" in str(approval) or "irreversible" in str(approval) else _YELLOW
        print(f"  {_YELLOW}🔴 审批类型：{_RESET}{risk_color}{approval}{_RESET}")
    if checkpoint.tool_args:
        import json as _json
        args_str = _json.dumps(checkpoint.tool_args, ensure_ascii=False)
        print(f"  {_YELLOW}📝 操作参数：{_RESET}{args_str}")
    print()


def print_hitl_response(response: HITLResponse, is_demo: bool = False) -> None:
    """打印人类反馈结果。"""
    source_tag = f"{_DIM}[demo 剧本]{_RESET} " if is_demo else ""

    if response.feedback_type == FeedbackType.APPROVE:
        icon = "✅"
        color = _GREEN
        label = "批准"
    elif response.feedback_type == FeedbackType.REJECT:
        icon = "❌"
        color = _RED
        label = "否决"
    else:
        icon = "ℹ️"
        color = _BLUE
        label = "补充信息"

    print(f"  {source_tag}{color}{icon} 指挥官反馈（{label}）：{_RESET}{response.message}")
    print()


def print_hitl_reject_retry(attempt: int, max_attempts: int, reason: str) -> None:
    """打印 reject 后指令不可执行的重试提示。"""
    print(f"  {_RED}⚠️  替代指令不可执行（尝试 {attempt}/{max_attempts}）：{reason}{_RESET}")
    print(f"  {_YELLOW}    正在再次请求指挥官指示...{_RESET}")
    print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 灾害状态展示
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_disaster_update(tick: int, changes: list[str]) -> None:
    """打印灾害状态恶化更新。"""
    if not changes:
        return
    print(f"  {_RED}{_BOLD}⏰ 灾害态势更新 [T+{tick}]{_RESET}")
    for change in changes:
        print(f"     {_RED}▲ {change}{_RESET}")
    print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 最终总结
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_final_summary(
    total_steps: int,
    hitl_count: int,
    approve_count: int,
    reject_count: int,
    info_count: int,
    final_message: str,
) -> None:
    """打印任务结束总结。"""
    print()
    print(f"{_BOLD}{_CYAN}{'═' * 60}{_RESET}")
    print(f"{_BOLD}{_CYAN}  📊 任务执行总结{_RESET}")
    print(f"{_BOLD}{_CYAN}{'═' * 60}{_RESET}")
    print()
    print(f"  总执行步数：{total_steps}")
    print(f"  HITL 交互次数：{_YELLOW}{hitl_count}{_RESET}")
    print(f"    ├─ ✅ approve：{_GREEN}{approve_count}{_RESET}")
    print(f"    ├─ ❌ reject：{_RED}{reject_count}{_RESET}")
    print(f"    └─ ℹ️  provide_info：{_BLUE}{info_count}{_RESET}")
    print()
    print(f"  {_BOLD}最终结论：{_RESET}")
    for line in final_message.strip().split("\n"):
        print(f"    {line}")
    print()
    print(f"{_DIM}{'─' * 60}{_RESET}")
    print()


def print_abort(reason: str) -> None:
    """打印任务中止信息。"""
    print()
    print(f"  {_BG_RED}{_WHITE}{_BOLD} ⛔ 任务中止 {_RESET}")
    print(f"  {_RED}原因：{reason}{_RESET}")
    print()


def print_step_divider() -> None:
    """步骤间分隔线。"""
    print(f"  {_DIM}{'·' * 40}{_RESET}")
    print()
