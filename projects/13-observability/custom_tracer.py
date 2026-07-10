"""
custom_tracer.py —— 自定义 Tracer（不依赖 LangSmith）
=====================================================

核心思想：tracer 的本质就是在代码关键点插入记录调用。
不需要任何框架，一个类 + 几个 on_* 方法就够了。

输出两种格式：
1. 终端 ANSI 着色实时展示（verbose=True 时在 on_* 方法内立即打印）
2. JSON 文件持久化（to_json() 导出，可离线分析）

使用方式：
    tracer = AgentTracer(verbose=True)
    tracer.on_llm_start("系统消息...", "gpt-4o-mini")
    # ... LLM 调用 ...
    tracer.on_llm_end("回复内容...", tokens=150, duration_ms=1200)
    tracer.on_tool_start("lookup", {"entity": "星辰王国", "field": "人口"})
    # ... 工具执行 ...
    tracer.on_tool_end("lookup", "120000", duration_ms=5)
    tracer.on_agent_step(1, "我需要查找人口", "lookup")

    # 导出
    tracer.to_json("trace_output.json")
    tracer.print_summary()
"""

import json
import time
from datetime import datetime, timezone


# ============================================================
# ANSI 颜色（轻量版，不依赖 display.py）
# ============================================================

class _C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"


# ============================================================
# AgentTracer
# ============================================================

class AgentTracer:
    """
    不依赖 LangSmith 的轻量 tracer。

    在 Agent 代码的关键位置手动调用 on_* 方法，
    记录每个 span 到内存，可选实时打印到终端。
    """

    def __init__(self, verbose: bool = True):
        """
        参数：
            verbose: 是否在每个 on_* 调用时实时打印 ANSI 着色输出
        """
        self._spans: list[dict] = []
        self._verbose = verbose
        self._start_time = time.time()
        self._total_tokens = 0
        self._llm_calls = 0
        self._tool_calls_count = 0

    def on_llm_start(self, prompt_summary: str, model: str) -> None:
        """记录 LLM 调用开始。"""
        span = {
            "type": "llm_start",
            "timestamp": _now_iso(),
            "model": model,
            "prompt_summary": _truncate(prompt_summary, 200),
        }
        self._spans.append(span)

        if self._verbose:
            print(f"  {_C.BLUE}{_C.BOLD}[LLM]{_C.RESET} "
                  f"{_C.BLUE}调用 {model}{_C.RESET}")
            print(f"        {_C.DIM}prompt: {_truncate(prompt_summary, 100)}{_C.RESET}")

    def on_llm_end(self, response_summary: str, tokens: int = 0, duration_ms: float = 0) -> None:
        """记录 LLM 调用结束。"""
        self._llm_calls += 1
        self._total_tokens += tokens

        span = {
            "type": "llm_end",
            "timestamp": _now_iso(),
            "response_summary": _truncate(response_summary, 200),
            "tokens": tokens,
            "duration_ms": round(duration_ms, 1),
        }
        self._spans.append(span)

        if self._verbose:
            print(f"  {_C.BLUE}{_C.BOLD}[LLM]{_C.RESET} "
                  f"{_C.BLUE}完成{_C.RESET} "
                  f"{_C.DIM}tokens={tokens} {duration_ms:.0f}ms{_C.RESET}")
            print(f"        {_C.DIM}response: {_truncate(response_summary, 100)}{_C.RESET}")

    def on_tool_start(self, tool_name: str, args: dict) -> None:
        """记录工具调用开始。"""
        span = {
            "type": "tool_start",
            "timestamp": _now_iso(),
            "tool_name": tool_name,
            "args": args,
        }
        self._spans.append(span)

        if self._verbose:
            args_str = json.dumps(args, ensure_ascii=False)
            print(f"  {_C.GREEN}{_C.BOLD}[TOOL]{_C.RESET} "
                  f"{_C.GREEN}{tool_name}({args_str}){_C.RESET}")

    def on_tool_end(self, tool_name: str, result_summary: str, duration_ms: float = 0) -> None:
        """记录工具调用结束。"""
        self._tool_calls_count += 1

        span = {
            "type": "tool_end",
            "timestamp": _now_iso(),
            "tool_name": tool_name,
            "result_summary": _truncate(result_summary, 200),
            "duration_ms": round(duration_ms, 1),
        }
        self._spans.append(span)

        if self._verbose:
            print(f"  {_C.GREEN}{_C.BOLD}[TOOL]{_C.RESET} "
                  f"{_C.GREEN}{tool_name}{_C.RESET} "
                  f"{_C.DIM}→ {_truncate(result_summary, 80)} ({duration_ms:.0f}ms){_C.RESET}")

    def on_agent_step(self, step_num: int, thought: str, action: str | None) -> None:
        """记录 Agent 步骤（Thought + Action 决策）。"""
        span = {
            "type": "agent_step",
            "timestamp": _now_iso(),
            "step_num": step_num,
            "thought": _truncate(thought, 300),
            "action": action,
        }
        self._spans.append(span)

        if self._verbose:
            print(f"\n  {_C.YELLOW}{_C.BOLD}[STEP {step_num}]{_C.RESET}")
            if thought:
                print(f"  {_C.YELLOW}Thought: {_truncate(thought, 120)}{_C.RESET}")
            if action:
                print(f"  {_C.YELLOW}Action:  {action}{_C.RESET}")

    # ── 汇总与导出 ────────────────────────────────────────────

    def get_summary(self) -> dict:
        """统计汇总：总步数、总耗时、总 token、工具调用分布。"""
        total_duration = (time.time() - self._start_time) * 1000  # ms

        # 工具调用分布
        tool_distribution: dict[str, int] = {}
        for span in self._spans:
            if span["type"] == "tool_end":
                name = span["tool_name"]
                tool_distribution[name] = tool_distribution.get(name, 0) + 1

        # LLM 总耗时
        llm_total_ms = sum(
            s.get("duration_ms", 0) for s in self._spans if s["type"] == "llm_end"
        )

        # 工具总耗时
        tool_total_ms = sum(
            s.get("duration_ms", 0) for s in self._spans if s["type"] == "tool_end"
        )

        # Agent 步数
        agent_steps = sum(1 for s in self._spans if s["type"] == "agent_step")

        return {
            "agent_steps": agent_steps,
            "llm_calls": self._llm_calls,
            "tool_calls": self._tool_calls_count,
            "total_tokens": self._total_tokens,
            "llm_total_ms": round(llm_total_ms, 1),
            "tool_total_ms": round(tool_total_ms, 1),
            "total_duration_ms": round(total_duration, 1),
            "tool_distribution": tool_distribution,
        }

    def to_json(self, filepath: str | None = None) -> dict:
        """
        导出为 JSON 格式。

        参数：
            filepath: 如果提供，写入文件；否则只返回 dict

        返回：
            包含所有 spans 和 summary 的完整 trace 数据
        """
        data = {
            "trace_id": f"trace-{int(self._start_time)}",
            "start_time": datetime.fromtimestamp(self._start_time, tz=timezone.utc).isoformat(),
            "summary": self.get_summary(),
            "spans": self._spans,
        }

        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        return data

    def print_summary(self) -> None:
        """终端汇总打印。"""
        summary = self.get_summary()

        print()
        print(f"  {_C.CYAN}{_C.BOLD}Trace 汇总{_C.RESET}")
        print(f"  {_C.DIM}{'─' * 40}{_C.RESET}")
        print(f"  {_C.CYAN}Agent 步数  : {summary['agent_steps']}{_C.RESET}")
        print(f"  {_C.CYAN}LLM 调用    : {summary['llm_calls']} 次 ({summary['llm_total_ms']:.0f}ms){_C.RESET}")
        print(f"  {_C.CYAN}工具调用    : {summary['tool_calls']} 次 ({summary['tool_total_ms']:.0f}ms){_C.RESET}")
        print(f"  {_C.CYAN}总 Token    : {summary['total_tokens']}{_C.RESET}")
        print(f"  {_C.CYAN}总耗时      : {summary['total_duration_ms']:.0f}ms{_C.RESET}")

        if summary["tool_distribution"]:
            print(f"  {_C.CYAN}工具分布    : {_C.RESET}", end="")
            parts = [f"{k}({v})" for k, v in summary["tool_distribution"].items()]
            print(f"{_C.DIM}{', '.join(parts)}{_C.RESET}")


# ============================================================
# 工具函数
# ============================================================

def _now_iso() -> str:
    """返回 ISO 格式当前时间。"""
    return datetime.now(tz=timezone.utc).isoformat()


def _truncate(text: str, max_len: int) -> str:
    """截断文本。"""
    text = text.replace("\n", " ")
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text
