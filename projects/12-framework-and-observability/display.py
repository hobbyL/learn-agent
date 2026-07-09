"""
display.py —— ANSI 着色输出，三路实现对比渲染
==============================================

颜色方案：
- v1 手写：蓝色（\033[34m）
- v2 StateGraph：绿色（\033[32m）
- v3 prebuilt：青色（\033[36m）
- 标题/分隔线：粗体白色
- 工具调用：黄色
- 答案：粗体绿色
"""

import time
from typing import Optional


# ============================================================
# ANSI 颜色常量
# ============================================================

class C:
    """ANSI 颜色代码。"""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"

    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"

    # 实现颜色
    V1_COLOR = "\033[34m"   # 蓝色
    V2_COLOR = "\033[32m"   # 绿色
    V3_COLOR = "\033[36m"   # 青色

    @staticmethod
    def colored(text: str, color: str) -> str:
        return f"{color}{text}{C.RESET}"

    @staticmethod
    def bold(text: str) -> str:
        return f"{C.BOLD}{text}{C.RESET}"


# 版本元信息
VERSION_META = {
    "v1": {
        "color": C.V1_COLOR,
        "label": "v1 手写纯文本 ReAct",
        "short": "v1",
        "desc": "纯文本格式 + 正则解析 + 手写循环",
    },
    "v2": {
        "color": C.V2_COLOR,
        "label": "v2 手动 StateGraph",
        "short": "v2",
        "desc": "Function Calling + ToolNode + InMemorySaver",
    },
    "v3": {
        "color": C.V3_COLOR,
        "label": "v3 create_react_agent",
        "short": "v3",
        "desc": "5 行 prebuilt，结构隐藏",
    },
}


# ============================================================
# 通用工具函数
# ============================================================

def print_separator(char: str = "─", width: int = 60, color: str = C.DIM) -> None:
    print(C.colored(char * width, color))


def print_header(title: str, color: str = C.WHITE) -> None:
    print()
    print_separator("═", 60, C.BOLD)
    print(C.colored(f"  {title}", C.BOLD))
    print_separator("═", 60, C.BOLD)


def print_version_header(version: str) -> None:
    meta = VERSION_META[version]
    color = meta["color"]
    print()
    print(C.colored(f"┌─ {meta['label']} ─────────────────────────────────", color))
    print(C.colored(f"│  {meta['desc']}", C.DIM))
    print(C.colored("└" + "─" * 50, color))


# ============================================================
# v1 输出渲染（手写 ReAct，含 Thought/Action/Observation）
# ============================================================

def render_v1_step(step: dict, step_num: int, color: str = C.V1_COLOR) -> None:
    """渲染 v1 的单步推理。"""
    print(C.colored(f"\n  步骤 {step_num}", C.DIM))

    if step.get("thought"):
        thought_preview = step["thought"][:120].replace("\n", " ")
        print(C.colored(f"  Thought: {thought_preview}", color))

    action = step.get("action")
    if action and not action.startswith("_"):
        import json
        args_str = json.dumps(step.get("action_input", {}), ensure_ascii=False)
        print(C.colored(f"  Action:  {action}({args_str})", C.YELLOW))

        obs = step.get("observation", "")
        obs_preview = str(obs)[:120].replace("\n", " ")
        print(C.colored(f"  Obs:     {obs_preview}", C.DIM))
    elif action == "_unfinished_plan_rejected":
        print(C.colored("  [跳步检测] 计划未完成，拒绝 Final Answer", C.RED))
    elif action == "_format_error":
        print(C.colored("  [格式错误] 提示重试", C.RED))
    elif action is None and step.get("thought"):
        # Final Answer 步
        pass


def render_v1_result(result: dict, elapsed: float) -> None:
    """渲染 v1 的完整结果。"""
    color = C.V1_COLOR
    print_version_header("v1")

    for step in result["steps"]:
        render_v1_step(step, step["step"], color)

    print()
    print(C.colored(f"  答案:    {result['answer']}", C.GREEN + C.BOLD))
    print(C.colored(f"  步数:    {result['total_steps']}  耗时: {elapsed:.1f}s  终止: {result['terminated_by']}", C.DIM))


# ============================================================
# v2/v3 输出渲染（LangGraph，解析 messages 列表）
# ============================================================

def render_langgraph_result(result: dict, version: str, elapsed: float) -> None:
    """
    渲染 v2 或 v3 的完整结果。

    从 messages 列表中提取 AI 消息和工具调用信息展示。
    """
    meta = VERSION_META[version]
    color = meta["color"]
    print_version_header(version)

    messages = result.get("messages", [])

    from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

    step_num = 0
    for msg in messages:
        if isinstance(msg, HumanMessage):
            # 只显示用户的新问题，不显示 tool observation（那是 ToolMessage）
            content_preview = str(msg.content)[:80].replace("\n", " ")
            print(C.colored(f"\n  User: {content_preview}", C.DIM))

        elif isinstance(msg, AIMessage):
            step_num += 1
            print(C.colored(f"\n  [agent_node 执行 {step_num}]", C.DIM))

            if msg.tool_calls:
                for tc in msg.tool_calls:
                    import json
                    args_str = json.dumps(tc.get("args", {}), ensure_ascii=False)
                    print(C.colored(f"  工具调用: {tc['name']}({args_str})", C.YELLOW))
            elif msg.content:
                content_preview = msg.content[:120].replace("\n", " ")
                print(C.colored(f"  AI 回复: {content_preview}", color))

        elif isinstance(msg, ToolMessage):
            obs_preview = str(msg.content)[:120].replace("\n", " ")
            print(C.colored(f"  工具返回: [{msg.name}] {obs_preview}", C.DIM))

    print()
    print(C.colored(f"  答案:    {result['answer']}", C.GREEN + C.BOLD))
    print(C.colored(
        f"  步数:    {result['total_steps']}  耗时: {elapsed:.1f}s",
        C.DIM
    ))


# ============================================================
# compare 模式对比表格
# ============================================================

def render_compare_table(results: dict[str, dict], elapsed: dict[str, float]) -> None:
    """
    渲染三路实现的对比表格。

    results: {"v1": {...}, "v2": {...}, "v3": {...}}
    elapsed: {"v1": 1.2, "v2": 0.8, "v3": 0.7}
    """
    print_header("对比结果")

    # 表头
    col_w = [8, 20, 8, 8, 50]
    header = f"{'版本':<{col_w[0]}} {'实现方式':<{col_w[1]}} {'步数':>{col_w[2]}} {'耗时':>{col_w[3]}} {'答案':<{col_w[4]}}"
    print(C.bold(header))
    print_separator("─", sum(col_w) + len(col_w))

    for version, meta in VERSION_META.items():
        result = results.get(version)
        color = meta["color"]

        if result is None:
            row = f"{version:<{col_w[0]}} {meta['short']:<{col_w[1]}} {'ERR':>{col_w[2]}} {'—':>{col_w[3]}} {'运行失败':<{col_w[4]}}"
            print(C.colored(row, C.RED))
            continue

        steps = result.get("total_steps", "?")
        t = elapsed.get(version, 0)
        answer = result.get("answer", "")
        # 截断答案显示
        answer_preview = answer[:47] + "..." if len(answer) > 50 else answer

        row = f"{version:<{col_w[0]}} {meta['short']:<{col_w[1]}} {steps:>{col_w[2]}} {t:>{col_w[3]-1}.1f}s {answer_preview:<{col_w[4]}}"
        print(C.colored(row, color))

    print()


# ============================================================
# LangSmith 状态提示
# ============================================================

def print_langsmith_status() -> None:
    """在 demo 启动时打印 LangSmith tracing 状态。"""
    import os
    tracing = os.environ.get("LANGSMITH_TRACING", "").lower()
    api_key = os.environ.get("LANGSMITH_API_KEY", "")
    project = os.environ.get("LANGSMITH_PROJECT", "12-framework-and-observability")

    print()
    if tracing in ("true", "1", "yes") and api_key:
        print(C.colored("LangSmith Tracing: 已开启", C.GREEN))
        print(C.colored(f"  项目: {project}", C.DIM))
        print(C.colored("  在 https://smith.langchain.com 查看 trace", C.DIM))
    else:
        print(C.colored("LangSmith Tracing: 未开启（可选）", C.DIM))
        print(C.colored("  开启方法：设置环境变量 LANGSMITH_TRACING=true 和 LANGSMITH_API_KEY", C.DIM))


# ============================================================
# 多轮对话分隔
# ============================================================

def print_turn_separator(turn: int, question: str) -> None:
    """打印多轮对话的轮次分隔。"""
    print()
    print(C.colored(f"── 第 {turn} 轮对话 ─────────────────────────────────────────", C.YELLOW))
    print(C.colored(f"  问题: {question}", C.BOLD))
