"""
展示模块 —— Raw Timeline + Final Output 双视角
================================================

C2 展示策略：
- 先打印 raw delta 时间线（每个 chunk 编号 + 类型 + 内容）
- 再打印合成的最终输出

ANSI 颜色约定：
- 灰色：chunk 编号 / 元信息
- 青色：content delta
- 黄色：tool_call delta
- 绿色：合成结果 / 工具执行结果
- 红色：错误信息
- 品红：finish 事件
"""

import sys
from stream_collector import StreamResult, TimelineEntry


# ============================================================
# ANSI 颜色
# ============================================================

_GRAY = "\033[90m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_MAGENTA = "\033[35m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


# ============================================================
# 实时输出（streaming 进行中）
# ============================================================

def print_streaming_char(text: str) -> None:
    """实时打印流式文本片段（不换行）"""
    sys.stdout.write(text)
    sys.stdout.flush()


def print_tool_call_start(name: str, arguments: dict) -> None:
    """打印工具调用开始"""
    args_str = ", ".join(f'{k}="{v}"' for k, v in arguments.items())
    print(f"\n{_YELLOW}🔧 调用工具: {name}({args_str}){_RESET}")


def print_tool_result(name: str, result: str) -> None:
    """打印工具执行结果"""
    # 截断过长结果
    display = result if len(result) <= 200 else result[:200] + "..."
    print(f"{_GREEN}📋 结果: {display}{_RESET}\n")


# ============================================================
# Raw Delta Timeline 展示
# ============================================================

def print_raw_timeline(result: StreamResult) -> None:
    """
    打印原始 delta 时间线。

    展示每个 chunk 的编号、类型和原始内容，
    让学习者直观看到 streaming 协议的底层细节。
    """
    print(f"\n{_BOLD}{'='*60}{_RESET}")
    print(f"{_BOLD}📡 原始 Delta 时间线（共 {len(result.timeline)} 个事件）{_RESET}")
    print(f"{_BOLD}{'='*60}{_RESET}")
    print(f"{_GRAY}总耗时: {result.duration_ms:.0f}ms{_RESET}\n")

    _COLOR_MAP = {
        "content": _CYAN,
        "tool_call_delta": _YELLOW,
        "finish": _MAGENTA,
    }

    _ICON_MAP = {
        "content": "📝",
        "tool_call_delta": "🔧",
        "finish": "🏁",
    }

    base_time = result.start_time

    for entry in result.timeline:
        color = _COLOR_MAP.get(entry.event_type, _GRAY)
        icon = _ICON_MAP.get(entry.event_type, "  ")
        elapsed = (entry.timestamp - base_time) * 1000
        print(
            f"{_GRAY}[{entry.chunk_index:3d}]{_RESET} "
            f"{_GRAY}{elapsed:6.0f}ms{_RESET} "
            f"{icon} {color}{entry.event_type:16s}{_RESET} "
            f"{color}{entry.content}{_RESET}"
        )

    print()


# ============================================================
# Final Output 展示
# ============================================================

def print_final_output(result: StreamResult) -> None:
    """打印合成的最终输出"""
    print(f"{_BOLD}{'='*60}{_RESET}")
    print(f"{_BOLD}✅ 合成最终输出{_RESET}")
    print(f"{_BOLD}{'='*60}{_RESET}\n")

    if result.content:
        print(f"{_GREEN}{result.content}{_RESET}")
    elif result.has_tool_calls:
        print(f"{_YELLOW}[本轮输出为工具调用，无文本内容]{_RESET}")
        for tc in result.tool_calls:
            print(f"  🔧 {tc['function']['name']}({tc['function']['arguments']})")
    else:
        print(f"{_RED}[无输出]{_RESET}")

    print()


# ============================================================
# 完整 Agent 会话展示
# ============================================================

def print_session_header(mode: str) -> None:
    """打印会话头"""
    mode_label = "🌊 Streaming 模式" if mode == "streaming" else "📦 Non-Streaming 模式"
    print(f"\n{_BOLD}{'─'*60}{_RESET}")
    print(f"{_BOLD}{mode_label}{_RESET}")
    print(f"{_BOLD}{'─'*60}{_RESET}\n")


def print_iteration_header(iteration: int) -> None:
    """打印循环轮次头"""
    print(f"{_GRAY}── 第 {iteration} 轮 API 调用 ──{_RESET}")


def print_agent_answer(answer: str) -> None:
    """打印 Agent 最终答案"""
    print(f"\n{_BOLD}{_GREEN}💬 Agent 最终答案:{_RESET}")
    print(f"{_GREEN}{answer}{_RESET}\n")


def print_error(msg: str) -> None:
    """打印错误信息"""
    print(f"{_RED}❌ {msg}{_RESET}")


# ============================================================
# Compare 模式展示
# ============================================================

def print_compare_header(question: str) -> None:
    """打印对比模式头"""
    print(f"\n{_BOLD}{'═'*60}{_RESET}")
    print(f"{_BOLD}⚡ Streaming vs Non-Streaming 对比{_RESET}")
    print(f"{_BOLD}{'═'*60}{_RESET}")
    print(f"问题: {question}\n")


def print_compare_result(
    stream_answer: str, stream_time_ms: float,
    normal_answer: str, normal_time_ms: float,
) -> None:
    """打印对比结果"""
    print(f"\n{_BOLD}{'─'*60}{_RESET}")
    print(f"{_BOLD}📊 对比结果{_RESET}")
    print(f"{_BOLD}{'─'*60}{_RESET}\n")

    print(f"  {'模式':<12} {'耗时':>10} {'首字节':>10}")
    print(f"  {'─'*36}")
    print(f"  {'Streaming':<12} {stream_time_ms:>8.0f}ms {'(实时)':>10}")
    print(f"  {'Non-Stream':<12} {normal_time_ms:>8.0f}ms {'(等完)':>10}")
    print()

    if abs(stream_time_ms - normal_time_ms) < 100:
        print(f"  {_GRAY}总耗时相近（预期）——streaming 的优势在于首字节更快{_RESET}")
    elif stream_time_ms < normal_time_ms:
        saved = normal_time_ms - stream_time_ms
        print(f"  {_GREEN}Streaming 总耗时少 {saved:.0f}ms{_RESET}")
    else:
        diff = stream_time_ms - normal_time_ms
        print(f"  {_YELLOW}Streaming 总耗时多 {diff:.0f}ms（chunk 处理开销）{_RESET}")

    print(f"\n  {_BOLD}Streaming 答案:{_RESET}")
    print(f"  {stream_answer}")
    print(f"\n  {_BOLD}Non-Stream 答案:{_RESET}")
    print(f"  {normal_answer}")
    print()
