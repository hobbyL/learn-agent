"""
main.py —— CLI 入口（--compare / --demo / --version）
======================================================

用法：
    python main.py --demo              # 跑 v2，展示完整流程 + 多轮对话
    python main.py --compare           # 三路并跑，输出对比表格
    python main.py --version v1        # 单独运行 v1，交互式输入
    python main.py --version v2        # 单独运行 v2
    python main.py --version v3        # 单独运行 v3

环境变量（.env 或 shell 中设置）：
    OPENAI_API_KEY=...
    OPENAI_BASE_URL=...       # 自定义端点（可选）
    OPENAI_MODEL=...          # 默认 gpt-4o-mini
    LANGSMITH_TRACING=true    # 开启 LangSmith tracing（可选）
    LANGSMITH_API_KEY=...     # LangSmith API key（可选）
    LANGSMITH_PROJECT=...     # LangSmith 项目名（可选）
"""

import argparse
import sys
import time
import os
import traceback

from dotenv import load_dotenv

load_dotenv()


# ============================================================
# 演示问题
# ============================================================

DEMO_QUESTION_1 = "星辰王国和月影王国，哪个人口更多？多多少？"
DEMO_QUESTION_2 = "那它们的面积差是多少？"  # 第二轮，利用 checkpointer 上下文

COMPARE_QUESTION = "星辰王国和月影王国，哪个人口更多？多多少？"


# ============================================================
# 各版本运行封装（含异常捕获）
# ============================================================

def run_v1_safe(question: str, verbose: bool = True) -> tuple[dict | None, float]:
    """安全运行 v1，返回 (result, elapsed)，失败返回 (None, 0)。"""
    try:
        from agent_v1_handwritten import ReactAgent
        agent = ReactAgent(max_steps=10, verbose=verbose)
        t0 = time.time()
        result = agent.run(question)
        return result, time.time() - t0
    except Exception as e:
        print(f"  [v1 错误] {e}")
        if verbose:
            traceback.print_exc()
        return None, 0.0


def run_v2_safe(question: str, thread_id: str = "demo-v2", verbose: bool = True) -> tuple[dict | None, float]:
    """安全运行 v2，返回 (result, elapsed)，失败返回 (None, 0)。"""
    try:
        from agent_v2_stategraph import run_v2
        t0 = time.time()
        result = run_v2(question, thread_id=thread_id, verbose=verbose)
        return result, time.time() - t0
    except Exception as e:
        print(f"  [v2 错误] {e}")
        if verbose:
            traceback.print_exc()
        return None, 0.0


def run_v3_safe(question: str, thread_id: str = "demo-v3", verbose: bool = True) -> tuple[dict | None, float]:
    """安全运行 v3，返回 (result, elapsed)，失败返回 (None, 0)。"""
    try:
        from agent_v3_prebuilt import run_v3
        t0 = time.time()
        result = run_v3(question, thread_id=thread_id, verbose=verbose)
        return result, time.time() - t0
    except Exception as e:
        print(f"  [v3 错误] {e}")
        if verbose:
            traceback.print_exc()
        return None, 0.0


# ============================================================
# demo 模式
# ============================================================

def cmd_demo():
    """
    demo 模式：跑 v2（手动 StateGraph）。

    展示内容：
    1. 图结构（Mermaid 格式）
    2. 第一轮对话：完整节点/边/状态流转
    3. 第二轮对话：复用同一 thread_id，展示 checkpointer 多轮记忆
    """
    from display import (
        print_header, print_langsmith_status, print_version_header,
        render_langgraph_result, print_turn_separator, C, print_separator,
    )

    print_header("12 · Framework & Observability · Demo 模式（v2 StateGraph）")
    print_langsmith_status()

    # 显示图结构
    print()
    print(C.bold("图结构（Mermaid）："))
    try:
        from agent_v2_stategraph import get_graph_for_display
        graph = get_graph_for_display()
        mermaid = graph.get_graph().draw_mermaid()
        print(C.colored(mermaid, C.DIM))
    except Exception as e:
        print(C.colored(f"  （无法生成图：{e}）", C.DIM))

    # 第一轮对话
    thread_id = "demo-thread-001"
    print_turn_separator(1, DEMO_QUESTION_1)
    result1, elapsed1 = run_v2_safe(DEMO_QUESTION_1, thread_id=thread_id, verbose=True)

    if result1:
        render_langgraph_result(result1, "v2", elapsed1)
    else:
        print(C.colored("  v2 运行失败", C.RED))
        return

    # 第二轮对话（复用同一 thread_id）
    print()
    print(C.colored("  复用同一 thread_id 的第二轮对话（checkpointer 保留上文）：", C.DIM))
    print_turn_separator(2, DEMO_QUESTION_2)

    # 第二轮：直接 invoke 到同一个已有 thread（需要重用已构建的 graph）
    # 注意：run_v2_safe 每次都 build_graph()，会创建新的 InMemorySaver（内存丢失）
    # 正确做法：在同一个 graph 对象上两次 invoke
    try:
        from agent_v2_stategraph import build_graph
        from display import render_langgraph_result as render_v2
        graph = build_graph(verbose=True)
        config = {"configurable": {"thread_id": thread_id}}

        t0 = time.time()
        r1 = graph.invoke(
            {"messages": [{"role": "user", "content": DEMO_QUESTION_1}]},
            config=config,
        )
        elapsed_r1 = time.time() - t0

        from langchain_core.messages import AIMessage
        answer1 = ""
        for msg in reversed(r1["messages"]):
            if isinstance(msg, AIMessage) and msg.content and not getattr(msg, "tool_calls", None):
                answer1 = msg.content
                break

        result1_obj = {
            "answer": answer1,
            "total_steps": len([m for m in r1["messages"] if isinstance(m, AIMessage)]),
            "thread_id": thread_id,
            "messages": r1["messages"],
        }
        render_v2(result1_obj, "v2", elapsed_r1)

        print_turn_separator(2, DEMO_QUESTION_2)
        t0 = time.time()
        r2 = graph.invoke(
            {"messages": [{"role": "user", "content": DEMO_QUESTION_2}]},
            config=config,
        )
        elapsed_r2 = time.time() - t0

        # 第二轮只显示新的消息（从第一轮结束后的位置开始）
        new_messages = r2["messages"][len(r1["messages"]):]
        answer2 = ""
        for msg in reversed(new_messages):
            if isinstance(msg, AIMessage) and msg.content and not getattr(msg, "tool_calls", None):
                answer2 = msg.content
                break

        result2_obj = {
            "answer": answer2,
            "total_steps": len([m for m in new_messages if isinstance(m, AIMessage)]),
            "thread_id": thread_id,
            "messages": new_messages,
        }
        render_v2(result2_obj, "v2", elapsed_r2)

        print()
        print(C.colored(
            "  checkpointer 演示完成：第二轮利用了第一轮的上下文（无需重复查询人口数据）",
            C.GREEN,
        ))

    except Exception as e:
        print(C.colored(f"  多轮对话演示失败：{e}", C.RED))
        if os.environ.get("DEBUG"):
            traceback.print_exc()


# ============================================================
# compare 模式
# ============================================================

def cmd_compare():
    """
    compare 模式：用同一个问题跑三路实现，并排展示结果。
    """
    from display import (
        print_header, render_v1_result, render_langgraph_result,
        render_compare_table, C,
    )

    print_header(f"12 · Framework & Observability · 对比模式")
    print(f"  问题: {COMPARE_QUESTION}")
    print()

    results = {}
    elapsed = {}

    # v1
    print(C.colored("  运行 v1 手写 ReAct...", C.V1_COLOR))
    r1, t1 = run_v1_safe(COMPARE_QUESTION, verbose=False)
    results["v1"] = r1
    elapsed["v1"] = t1
    if r1:
        render_v1_result(r1, t1)

    # v2
    print(C.colored("\n  运行 v2 手动 StateGraph...", C.V2_COLOR))
    r2, t2 = run_v2_safe(COMPARE_QUESTION, thread_id="compare-v2", verbose=False)
    results["v2"] = r2
    elapsed["v2"] = t2
    if r2:
        render_langgraph_result(r2, "v2", t2)

    # v3
    print(C.colored("\n  运行 v3 prebuilt...", C.V3_COLOR))
    r3, t3 = run_v3_safe(COMPARE_QUESTION, thread_id="compare-v3", verbose=False)
    results["v3"] = r3
    elapsed["v3"] = t3
    if r3:
        render_langgraph_result(r3, "v3", t3)

    # 对比表格
    render_compare_table(results, elapsed)


# ============================================================
# version 模式（单独运行）
# ============================================================

def cmd_version(version: str):
    """单独运行某一路实现，交互式输入问题。"""
    from display import print_header, render_v1_result, render_langgraph_result, C

    labels = {
        "v1": "手写纯文本 ReAct",
        "v2": "手动 StateGraph",
        "v3": "create_react_agent prebuilt",
    }
    print_header(f"12 · Framework & Observability · {version} {labels.get(version, '')}")

    thread_id = f"version-{version}-session"

    while True:
        try:
            question = input(C.colored("\n请输入问题（Ctrl+C 退出）：", C.BOLD)).strip()
        except KeyboardInterrupt:
            print("\n已退出。")
            break

        if not question:
            continue

        if version == "v1":
            result, elapsed = run_v1_safe(question, verbose=True)
            if result:
                render_v1_result(result, elapsed)

        elif version == "v2":
            result, elapsed = run_v2_safe(question, thread_id=thread_id, verbose=True)
            if result:
                render_langgraph_result(result, "v2", elapsed)

        elif version == "v3":
            result, elapsed = run_v3_safe(question, thread_id=thread_id, verbose=True)
            if result:
                render_langgraph_result(result, "v3", elapsed)

        else:
            print(f"未知版本: {version}，可选：v1 / v2 / v3")
            break


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="12-framework-and-observability：LangGraph 三路 ReAct 对比",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python main.py --demo              # v2 完整演示 + 多轮对话
  python main.py --compare           # 三路并跑对比
  python main.py --version v1        # 单独运行 v1
  python main.py --version v2        # 单独运行 v2（交互）
  python main.py --version v3        # 单独运行 v3（交互）
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true", help="v2 完整演示（推荐首次运行）")
    group.add_argument("--compare", action="store_true", help="三路实现并排对比")
    group.add_argument("--version", choices=["v1", "v2", "v3"], help="单独运行某路实现")

    args = parser.parse_args()

    if args.demo:
        cmd_demo()
    elif args.compare:
        cmd_compare()
    elif args.version:
        cmd_version(args.version)


if __name__ == "__main__":
    main()
