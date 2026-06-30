"""
06-streaming-react 入口
========================

运行模式：
  python main.py              → 交互模式（流式 ReAct + 实时推理链展示）
  python main.py --demo       → 预设问题演示
  python main.py --compare    → 非流式 ReAct vs 流式 ReAct 对比
  python main.py --compare "问题"  → 指定问题对比
"""

import argparse
import os
import sys

from dotenv import load_dotenv

# 在所有 import 之前加载环境变量（01 的教训）
load_dotenv()

from streaming_react_agent import StreamingReActAgent
from non_streaming_react_agent import NonStreamingReActAgent
from display import (
    print_session_header, print_agent_answer,
    print_compare_header, print_compare_result, print_error,
)


# ============================================================
# 预设演示问题（太空站联盟）
# ============================================================

DEMO_QUESTIONS = [
    # 单步：直接查一个字段
    "极光站的站长是谁？",
    # 两步：查站长 → 查年龄
    "天琴站站长的年龄是多少？",
    # 三步链式：查站长 → 查导师 → 查导师驻站
    "深红站站长的导师现在驻扎在哪个站？",
    # 比较+计算
    "极光站和深红站的人口相差多少？",
    # 跨类型查询
    "天琴号的操作员驻扎在哪个站？",
]


# ============================================================
# 运行模式
# ============================================================

def run_interactive():
    """交互模式：流式 ReAct，实时展示推理链。"""
    print_session_header("streaming")
    print("输入问题开始对话（输入 exit 退出，输入 reset 重置对话）\n")

    agent = StreamingReActAgent()

    while True:
        try:
            user_input = input("\033[1m你: \033[0m").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() == "exit":
            print("再见！")
            break
        if user_input.lower() == "reset":
            agent.reset()
            print("\033[90m[对话已重置]\033[0m\n")
            continue

        answer = agent.run(user_input, show_realtime=True)
        print_agent_answer(answer)
        print(f"\033[90m共 {agent.get_step_count()} 步，耗时 {agent.get_total_time_ms():.0f}ms\033[0m\n")
        agent.reset()  # 每次问题独立（不保留对话历史）


def run_demo():
    """演示模式：用预设问题展示流式 ReAct 推理过程。"""
    print_session_header("demo")
    print(f"📋 演示模式：{len(DEMO_QUESTIONS)} 个预设问题\n")

    agent = StreamingReActAgent()

    for i, question in enumerate(DEMO_QUESTIONS, 1):
        print(f"\033[1m{'─'*60}\033[0m")
        print(f"\033[1m问题 {i}/{len(DEMO_QUESTIONS)}: {question}\033[0m")

        answer = agent.run(question, show_realtime=True)
        print_agent_answer(answer)
        print(f"\033[90m共 {agent.get_step_count()} 步，耗时 {agent.get_total_time_ms():.0f}ms\033[0m")

        agent.reset()

        if i < len(DEMO_QUESTIONS):
            try:
                input("\n\033[90m[按 Enter 继续下一题...]\033[0m")
            except (KeyboardInterrupt, EOFError):
                print("\n演示结束。")
                return


def run_compare(question: str = ""):
    """
    对比模式：同一问题分别跑非流式 ReAct 和流式 ReAct。

    对比维度：
    - 推理步数是否一致（检验两者逻辑等价性）
    - 总耗时差异
    - 流式体验 vs 非流式等待
    """
    if not question:
        question = DEMO_QUESTIONS[2]  # 默认用三步链式题

    print_compare_header(question)

    # ─── 非流式 ReAct ───
    print_session_header("non-streaming")
    print("\033[90m[等待完整响应...]\033[0m\n")
    nonstream_agent = NonStreamingReActAgent()
    nonstream_answer = nonstream_agent.run(question)
    print_agent_answer(nonstream_answer)
    print(f"\033[90m共 {nonstream_agent.get_step_count()} 步，耗时 {nonstream_agent.get_total_time_ms():.0f}ms\033[0m\n")

    # ─── 流式 ReAct ───
    print_session_header("streaming")
    stream_agent = StreamingReActAgent()
    stream_answer = stream_agent.run(question, show_realtime=True)
    print_agent_answer(stream_answer)
    print(f"\033[90m共 {stream_agent.get_step_count()} 步，耗时 {stream_agent.get_total_time_ms():.0f}ms\033[0m\n")

    # ─── 对比结果 ───
    print_compare_result(
        stream_answer=stream_answer,
        stream_ms=stream_agent.get_total_time_ms(),
        stream_steps=stream_agent.get_step_count(),
        nonstream_answer=nonstream_answer,
        nonstream_ms=nonstream_agent.get_total_time_ms(),
        nonstream_steps=nonstream_agent.get_step_count(),
    )


# ============================================================
# 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="06-streaming-react：流式 ReAct Agent")
    parser.add_argument("--demo", action="store_true", help="运行预设问题演示")
    parser.add_argument("--compare", nargs="?", const="", help="非流式 vs 流式 ReAct 对比")
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print_error("请设置 OPENAI_API_KEY 环境变量（参考 .env.example）")
        sys.exit(1)

    if args.demo:
        run_demo()
    elif args.compare is not None:
        run_compare(args.compare)
    else:
        run_interactive()


if __name__ == "__main__":
    main()
