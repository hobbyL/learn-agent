"""
05-streaming-agent 入口
========================

运行模式：
  python main.py              → 交互模式（streaming + raw timeline）
  python main.py --demo       → 预设问题演示
  python main.py --compare    → Streaming vs Non-Streaming 对比
  python main.py --compare "问题"  → 指定问题对比
"""

import argparse
import os
import sys

from dotenv import load_dotenv

# 在所有 import 之前加载环境变量（01 的教训）
load_dotenv()

from streaming_agent import StreamingAgent
from non_streaming_agent import NonStreamingAgent
from display import (
    print_session_header,
    print_raw_timeline,
    print_final_output,
    print_agent_answer,
    print_compare_header,
    print_compare_result,
    print_error,
)


# ============================================================
# 预设演示问题
# ============================================================

DEMO_QUESTIONS = [
    # 单步：直接查一个字段
    "极光站的站长是谁？",
    # 两步：查站长 → 查站长年龄
    "天琴站站长的年龄是多少？",
    # 三步链式：查站长 → 查导师 → 查导师驻站
    "深红站站长的导师现在驻扎在哪个站？",
    # 比较 + 计算
    "极光站和深红站的人口相差多少？",
    # 多步混合：需要查两个站的人口和面积再计算
    "天琴站的人口密度（人口/面积）是多少？",
]


# ============================================================
# 运行模式
# ============================================================

def run_interactive():
    """交互模式：streaming + 每次问答后展示 raw timeline"""
    print_session_header("streaming")
    print("输入问题开始对话（输入 exit 退出，输入 reset 重置对话）\n")

    agent = StreamingAgent()

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

        # 执行 streaming Agent
        answer = agent.run(user_input, show_realtime=True)

        # 展示最终答案
        print_agent_answer(answer)

        # C2 双视角：展示 raw delta timeline
        for i, result in enumerate(agent.get_all_timelines(), 1):
            if len(agent.get_all_timelines()) > 1:
                print(f"\033[90m── 第 {i} 轮 API 调用 timeline ──\033[0m")
            print_raw_timeline(result)

        # 重置 timeline（保留对话历史）
        agent._all_timelines = []
        print()


def run_demo():
    """演示模式：用预设问题展示 streaming 效果"""
    print_session_header("streaming")
    print(f"📋 演示模式：{len(DEMO_QUESTIONS)} 个预设问题\n")

    agent = StreamingAgent()

    for i, question in enumerate(DEMO_QUESTIONS, 1):
        print(f"\033[1m{'─'*60}\033[0m")
        print(f"\033[1m问题 {i}/{len(DEMO_QUESTIONS)}: {question}\033[0m\n")

        answer = agent.run(question, show_realtime=True)
        print_agent_answer(answer)

        # 展示 raw timeline
        for result in agent.get_all_timelines():
            print_raw_timeline(result)

        # 每个问题独立（重置对话）
        agent.reset()
        print()

        # 问题之间暂停
        if i < len(DEMO_QUESTIONS):
            try:
                input("\033[90m[按 Enter 继续下一题...]\033[0m")
            except (KeyboardInterrupt, EOFError):
                print("\n演示结束。")
                return


def run_compare(question: str = ""):
    """对比模式：同一问题跑 streaming 和 non-streaming"""
    if not question:
        question = DEMO_QUESTIONS[2]  # 默认用三步链式题

    print_compare_header(question)

    # ─── Streaming 模式 ───
    print_session_header("streaming")
    stream_agent = StreamingAgent()
    stream_answer = stream_agent.run(question, show_realtime=True)
    print_agent_answer(stream_answer)

    # 计算 streaming 总耗时
    stream_time_ms = sum(r.duration_ms for r in stream_agent.get_all_timelines())

    # 展示 raw timeline
    for result in stream_agent.get_all_timelines():
        print_raw_timeline(result)

    # ─── Non-Streaming 模式 ───
    print_session_header("non-streaming")
    print("\033[90m[等待完整响应...]\033[0m")
    normal_agent = NonStreamingAgent()
    normal_answer = normal_agent.run(question)
    print_agent_answer(normal_answer)

    normal_time_ms = normal_agent.total_time_ms

    # ─── 对比结果 ───
    print_compare_result(
        stream_answer, stream_time_ms,
        normal_answer, normal_time_ms,
    )


# ============================================================
# 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="05-streaming-agent：流式输出 Agent")
    parser.add_argument("--demo", action="store_true", help="运行预设问题演示")
    parser.add_argument("--compare", nargs="?", const="", help="Streaming vs Non-Streaming 对比")
    args = parser.parse_args()

    # 检查 API Key
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
