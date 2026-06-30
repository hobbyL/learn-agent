"""
展示模块 —— 流式 ReAct 着色输出
=================================

ANSI 颜色方案：
- Thought：灰色（\033[90m）—— 推理是"内心独白"，低调展示
- Action / Action Input：黄色（\033[33m）—— 行动需要突出
- Observation：绿色（\033[32m）—— 工具结果，正面反馈色
- Final Answer：亮白（\033[97m）—— 最终答案最显眼
- 跳步警告：红色（\033[31m）—— 错误/警告
- Section 标题：加粗

与 05 的 display.py 的区别：
- 05 = Function Calling 流式，展示 delta 事件和 timeline
- 06 = ReAct 文本流式，按段落着色，展示推理链结构
"""

import sys

# ANSI 转义码
_RESET = "\033[0m"
_BOLD = "\033[1m"
_GRAY = "\033[90m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_BRIGHT_WHITE = "\033[97m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_DIM = "\033[2m"

from stream_parser import Section


def _color_for_section(section: Section) -> str:
    """返回对应 section 的 ANSI 颜色码。"""
    return {
        Section.IDLE: _RESET,
        Section.THOUGHT: _GRAY,
        Section.ACTION: _YELLOW,
        Section.ACTION_INPUT: _YELLOW,
        Section.FINAL_ANSWER: _BRIGHT_WHITE,
    }.get(section, _RESET)


def print_section_header(section: Section) -> None:
    """打印 section 开始标题（加粗 + 着色）。"""
    titles = {
        Section.THOUGHT: "🧠 Thought:",
        Section.ACTION: "⚡ Action:",
        Section.ACTION_INPUT: "📥 Action Input:",
        Section.FINAL_ANSWER: "✅ Final Answer:",
    }
    title = titles.get(section)
    if title is None:
        return
    color = _color_for_section(section)
    print(f"\n{_BOLD}{color}{title}{_RESET} ", end="", flush=True)


def print_streaming_char(text: str, section: Section) -> None:
    """
    实时打印文本片段（无换行），根据 section 着色。

    这是 streaming 体验的核心：字符边到达边展示。
    """
    color = _color_for_section(section)
    print(f"{color}{text}{_RESET}", end="", flush=True)


def print_observation(tool_name: str, result: str) -> None:
    """绿色展示工具执行结果（Observation）。"""
    print(f"\n{_BOLD}{_GREEN}👁 Observation [{tool_name}]:{_RESET}")
    print(f"{_GREEN}{result}{_RESET}")


def print_final_answer(text: str) -> None:
    """亮白色展示最终答案（Final Answer 段落完整后调用）。"""
    print(f"\n{_BOLD}{_BRIGHT_WHITE}💬 Agent 最终答案:{_RESET}")
    print(f"{_BRIGHT_WHITE}{text.strip()}{_RESET}\n")


def print_skip_warning(thought_text: str) -> None:
    """
    红色展示跳步警告。

    跳步：Thought 包含"接下来要查 X"等未完成计划，却直接给 Final Answer。
    streaming 下实时检测，比 03 的非流式版更即时。
    """
    print(f"\n{_BOLD}{_RED}⚠️  检测到跳步！{_RESET}")
    print(f"{_RED}Thought 中有未完成计划，但 LLM 试图给出 Final Answer。")
    print(f"已拦截，要求 LLM 补完工具调用。{_RESET}\n")


def print_session_header(mode: str) -> None:
    """打印会话标题。"""
    mode_labels = {
        "streaming": "🌊 Streaming ReAct 模式",
        "non-streaming": "📦 Non-Streaming ReAct 模式",
        "demo": "📋 演示模式",
        "compare": "⚡ Streaming vs Non-Streaming ReAct 对比",
    }
    label = mode_labels.get(mode, mode)
    print(f"\n{_BOLD}{'═'*60}{_RESET}")
    print(f"{_BOLD}{label}{_RESET}")
    print(f"{_BOLD}{'═'*60}{_RESET}\n")


def print_step_header(step: int) -> None:
    """打印 ReAct 步骤编号（每次 LLM 调用一步）。"""
    print(f"\n{_DIM}── 第 {step} 步 ──{_RESET}")


def print_compare_header(question: str) -> None:
    """compare 模式：问题标题。"""
    print(f"\n{_BOLD}{'═'*60}{_RESET}")
    print(f"{_BOLD}⚡ Streaming vs Non-Streaming ReAct 对比{_RESET}")
    print(f"{_BOLD}{'═'*60}{_RESET}")
    print(f"问题: {question}\n")


def print_compare_result(
    stream_answer: str,
    stream_ms: float,
    stream_steps: int,
    nonstream_answer: str,
    nonstream_ms: float,
    nonstream_steps: int,
) -> None:
    """打印对比结果总结。"""
    print(f"\n{_BOLD}{'─'*60}{_RESET}")
    print(f"{_BOLD}📊 对比结果{_RESET}")
    print(f"{_BOLD}{'─'*60}{_RESET}\n")

    print(f"  {'模式':<18} {'耗时':>10}  {'步数':>6}")
    print(f"  {'─'*40}")
    print(f"  {'Streaming ReAct':<18} {stream_ms:>8.0f}ms  {stream_steps:>4} 步")
    print(f"  {'Non-Stream ReAct':<18} {nonstream_ms:>8.0f}ms  {nonstream_steps:>4} 步")

    steps_match = stream_steps == nonstream_steps
    if steps_match:
        print(f"\n  {_GREEN}✓ 步数一致（{stream_steps} 步）{_RESET}")
    else:
        print(f"\n  {_YELLOW}△ 步数不同（Streaming: {stream_steps} 步 | Non-Streaming: {nonstream_steps} 步）{_RESET}")

    faster = "Streaming" if stream_ms < nonstream_ms else "Non-Streaming"
    diff_ms = abs(stream_ms - nonstream_ms)
    print(f"  {_DIM}{faster} 总耗时少 {diff_ms:.0f}ms{_RESET}")

    print(f"\n  {_BOLD}Streaming 答案:{_RESET}")
    print(f"  {stream_answer.strip()[:200]}")
    print(f"\n  {_BOLD}Non-Stream 答案:{_RESET}")
    print(f"  {nonstream_answer.strip()[:200]}")


def print_error(msg: str) -> None:
    """红色错误信息。"""
    print(f"\n{_RED}❌ 错误：{msg}{_RESET}", file=sys.stderr)


def print_format_retry(attempt: int, max_attempts: int) -> None:
    """格式错误重试提示。"""
    print(f"\n{_YELLOW}⚠️  格式解析失败（第 {attempt}/{max_attempts} 次重试）{_RESET}")


def print_agent_answer(answer: str) -> None:
    """展示 Agent 最终答案（与 05 风格一致）。"""
    print(f"\n{_BOLD}{_GREEN}💬 Agent 最终答案:{_RESET}")
    print(f"{_GREEN}{answer.strip()}{_RESET}\n")
