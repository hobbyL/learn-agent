"""
展示模块 —— ANSI 着色 + 并排策略输出
======================================

负责 compare / demo 模式的可视化展示。

颜色方案：
- BaselineMemory:      白色  —— 基准，无特殊标记
- SlidingWindowMemory: 黄色  —— 滑动窗口，容易截断
- TokenLimitMemory:    青色  —— Token 精确控制
- SummaryMemory:       绿色  —— 摘要压缩，信息保留最好

每轮展示格式：
    ══════════════════════════
    第 N 轮：<问题>
    ══════════════════════════
    [baseline] <回答>
    [sliding ] <回答>
    [token   ] <回答>
    [summary ] <回答>
    ──────────────────────────
    📊 指标汇总：
    [baseline] messages: XX | tokens: ~XXXX | 本轮: ✓/✗
    ...
"""

import sys
import textwrap

# ============================================================
# ANSI 颜色常量
# ============================================================

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

WHITE  = "\033[37m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
GREEN  = "\033[32m"
RED    = "\033[31m"
GRAY   = "\033[90m"
BRIGHT_WHITE = "\033[97m"

# 各策略对应的颜色
STRATEGY_COLORS = {
    "BaselineMemory":      WHITE,
    "SlidingWindowMemory": YELLOW,
    "TokenLimitMemory":    CYAN,
    "SummaryMemory":       GREEN,
}

# 各策略的简洁标签（固定宽度，对齐用）
STRATEGY_LABELS = {
    "BaselineMemory":      "baseline",
    "SlidingWindowMemory": "sliding ",
    "TokenLimitMemory":    "token   ",
    "SummaryMemory":       "summary ",
}

# 溢出标记文本
OVERFLOW_MARKER = "⚠️ context 溢出，本轮跳过"


# ============================================================
# 工具函数
# ============================================================

def _color(strategy_name: str) -> str:
    """返回策略对应的 ANSI 颜色码。"""
    return STRATEGY_COLORS.get(strategy_name, RESET)


def _label(strategy_name: str) -> str:
    """返回策略对应的对齐标签。"""
    return STRATEGY_LABELS.get(strategy_name, strategy_name[:8].ljust(8))


def _wrap_answer(text: str, width: int = 70, indent: str = "    ") -> str:
    """
    将回答文本折行，使长回答不会撑破对齐格式。
    第一行无缩进，后续行加 indent 缩进。
    """
    if not text:
        return "(无回答)"
    # textwrap.fill 将文本折行到指定宽度
    wrapped = textwrap.fill(text.strip(), width=width, subsequent_indent=indent)
    return wrapped


# ============================================================
# 会话级标题
# ============================================================

def print_session_header(mode: str, strategy: str = "") -> None:
    """打印会话开始标题。"""
    mode_labels = {
        "compare": "🔬 4 策略对比模式 (compare)",
        "demo":    "🎬 演示模式 (demo)",
        "interactive": f"💬 交互模式 —— 策略: {strategy}",
    }
    label = mode_labels.get(mode, mode)
    print(f"\n{BOLD}{'═' * 62}{RESET}")
    print(f"{BOLD}  星际学院短期记忆 Agent{RESET}")
    print(f"{BOLD}  {label}{RESET}")
    print(f"{BOLD}{'═' * 62}{RESET}\n")


# ============================================================
# 每轮对话展示
# ============================================================

def print_round_header(round_num: int, question: str) -> None:
    """打印轮次开始分隔线 + 问题。"""
    print(f"\n{BOLD}{'─' * 62}{RESET}")
    print(f"{BOLD}第 {round_num} 轮：{question}{RESET}")
    print(f"{BOLD}{'─' * 62}{RESET}")


def print_strategy_answer(strategy_name: str, answer: str) -> None:
    """
    打印单个策略的回答内容，带颜色标签。

    格式示例：
        [summary ] 林晨是量子院的学员，导师是苏明哲...
    """
    color = _color(strategy_name)
    label = _label(strategy_name)
    is_overflow = OVERFLOW_MARKER in answer

    # 溢出时用红色特殊展示
    if is_overflow:
        print(f"{RED}{BOLD}[{label}]{RESET} {RED}{answer}{RESET}")
        return

    # 正常回答
    wrapped = _wrap_answer(answer, width=65, indent=" " * 12)
    print(f"{color}{BOLD}[{label}]{RESET} {wrapped}")


def print_round_metrics(results: list[dict]) -> None:
    """
    打印轮次结束后的指标汇总行。

    results 格式：
        [
            {
                "strategy": "BaselineMemory",
                "answer": "...",
                "messages": 5,
                "tokens": 320,
                "correct": True,   # 是否答对（可选）
            },
            ...
        ]

    输出示例：
        📊 context 指标：
        [baseline] messages:  5 | tokens: ~  320 | 本轮: ✓ 答对
        [sliding ] messages:  5 | tokens: ~  320 | 本轮: ✓ 答对
    """
    print(f"\n{DIM}{'·' * 62}{RESET}")
    print(f"{BOLD}📊 context 指标：{RESET}")

    for r in results:
        strategy = r.get("strategy", "")
        messages = r.get("messages", 0)
        tokens   = r.get("tokens", 0)
        correct  = r.get("correct", None)
        answer   = r.get("answer", "")

        color = _color(strategy)
        label = _label(strategy)

        # 是否答对标记
        if OVERFLOW_MARKER in answer:
            result_mark = f"{RED}✗ 溢出{RESET}"
        elif correct is None:
            result_mark = f"{GRAY}— 未检测{RESET}"
        elif correct:
            result_mark = f"{GREEN}✓ 答对{RESET}"
        else:
            result_mark = f"{YELLOW}✗ 答错{RESET}"

        print(
            f"  {color}[{label}]{RESET} "
            f"messages: {messages:3d} | "
            f"tokens: ~{tokens:5d} | "
            f"本轮: {result_mark}"
        )


def print_round_separator() -> None:
    """轮次结束分隔线。"""
    print(f"\n{DIM}{'═' * 62}{RESET}")


# ============================================================
# compare 模式专用
# ============================================================

def print_compare_final_summary(all_results: list[list[dict]]) -> None:
    """
    打印 compare 模式结束后的整体汇总。

    all_results: 每轮的 results 列表组成的列表
    """
    print(f"\n{BOLD}{'═' * 62}{RESET}")
    print(f"{BOLD}📋 整体汇总{RESET}")
    print(f"{BOLD}{'═' * 62}{RESET}\n")

    if not all_results:
        print("  (无数据)")
        return

    # 收集各策略的最终指标（最后一轮）
    last_round = all_results[-1]
    strategy_correct = {}
    strategy_total = {}

    for round_results in all_results:
        for r in round_results:
            s = r.get("strategy", "")
            correct = r.get("correct", None)
            strategy_total[s] = strategy_total.get(s, 0) + 1
            if correct is True:
                strategy_correct[s] = strategy_correct.get(s, 0) + 1

    print(f"  {'策略':<18} {'最终消息数':>8} {'最终Token':>10} {'答对率':>8}")
    print(f"  {'─' * 50}")
    for r in last_round:
        s = r.get("strategy", "")
        color = _color(s)
        label = _label(s)
        messages = r.get("messages", 0)
        tokens = r.get("tokens", 0)
        total = strategy_total.get(s, 0)
        correct = strategy_correct.get(s, 0)
        rate = f"{correct}/{total}" if total > 0 else "N/A"

        print(
            f"  {color}[{label}]{RESET} "
            f"{messages:>8} 条  "
            f"~{tokens:>8} tokens  "
            f"{rate:>6}"
        )

    print(f"\n{DIM}提示：baseline 消息数最多、summary 信息保留最完整{RESET}\n")


# ============================================================
# 交互模式专用
# ============================================================

def print_interactive_answer(strategy_name: str, answer: str, messages: int, tokens: int) -> None:
    """交互模式：打印回答 + 简洁指标。"""
    color = _color(strategy_name)
    label = _label(strategy_name)

    print(f"\n{color}{BOLD}[{label}] 回答：{RESET}")
    wrapped = _wrap_answer(answer, width=70, indent="  ")
    print(f"  {color}{wrapped}{RESET}")
    print(f"\n{DIM}  messages: {messages} | tokens: ~{tokens}{RESET}\n")


def print_interactive_prompt(strategy_name: str) -> None:
    """交互模式：打印输入提示符。"""
    color = _color(strategy_name)
    print(f"{color}你({strategy_name}){RESET}> ", end="", flush=True)


def print_reset_notice() -> None:
    """打印 reset 成功提示。"""
    print(f"{GREEN}✓ 对话已重置，记忆清空。{RESET}\n")


# ============================================================
# 错误/提示输出
# ============================================================

def print_error(msg: str) -> None:
    """红色错误信息输出到 stderr。"""
    print(f"\n{RED}❌ 错误：{msg}{RESET}", file=sys.stderr)


def print_info(msg: str) -> None:
    """灰色信息提示。"""
    print(f"{GRAY}ℹ  {msg}{RESET}")


def print_overflow_warning(strategy_name: str) -> None:
    """context 溢出时的特殊提示。"""
    label = _label(strategy_name)
    print(f"{RED}{BOLD}⚠️  [{label}] context 溢出，本轮跳过{RESET}")


# ============================================================
# 快速验证
# ============================================================

if __name__ == "__main__":
    print_session_header("compare")

    print_round_header(1, "林晨是哪个院系的学员？")

    print_strategy_answer("BaselineMemory",      "林晨是量子院的学员，导师是苏明哲，专长是量子纠缠通信协议设计。")
    print_strategy_answer("SlidingWindowMemory", "林晨是量子院的学员，导师是苏明哲。")
    print_strategy_answer("TokenLimitMemory",    "林晨是量子院的学员。")
    print_strategy_answer("SummaryMemory",       "林晨是量子院的学员，导师是苏明哲，专长是量子纠缠通信。")

    sample_results = [
        {"strategy": "BaselineMemory",      "answer": "量子院", "messages": 3,  "tokens": 250, "correct": True},
        {"strategy": "SlidingWindowMemory", "answer": "量子院", "messages": 3,  "tokens": 250, "correct": True},
        {"strategy": "TokenLimitMemory",    "answer": "量子院", "messages": 3,  "tokens": 250, "correct": True},
        {"strategy": "SummaryMemory",       "answer": "量子院", "messages": 3,  "tokens": 250, "correct": True},
    ]
    print_round_metrics(sample_results)

    print_round_separator()
    print("\n展示模块验证通过 ✓")
