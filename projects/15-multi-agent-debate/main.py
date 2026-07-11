"""
多 Agent 辩论决策系统 — CLI 入口
================================

Usage:
    python main.py --demo        # 一键运行完整辩论
    python main.py --interactive # 自定义议题
"""

import sys
import os
import argparse

# 同目录 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from openai import OpenAI

from display import print_header, print_interactive_prompt, print_info, c
from orchestrator import DebateOrchestrator


def create_client() -> tuple[OpenAI, str]:
    """创建 OpenAI 客户端，返回 (client, model)。"""
    load_dotenv()
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
    )
    model = os.getenv("OPENAI_MODEL", "deepseek-v4-flash")
    return client, model


def run_demo():
    """Demo 模式：一键运行完整辩论。"""
    print_header()
    print_info("模式：Demo（完整三阶段辩论）")
    print_info("议题：从蓝晶星、赤焰星、翡翠星中选择最佳殖民地")
    print()

    client, model = create_client()
    print_info(f"模型：{model}")
    print()

    orchestrator = DebateOrchestrator(client, model)
    orchestrator.run_debate()


def run_interactive():
    """交互模式：自定义议题。"""
    print_header()
    print_interactive_prompt()

    client, model = create_client()
    print_info(f"模型：{model}")
    print()

    while True:
        try:
            topic = input(c("system", "  🎯 输入议题（回车用默认 / quit 退出）：")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print_info("再见！")
            break

        if topic.lower() in ("quit", "exit", "q"):
            print_info("再见！")
            break

        if not topic:
            topic = None  # 使用默认

        orchestrator = DebateOrchestrator(client, model)
        orchestrator.run_debate(topic=topic)

        print()
        print_info("辩论结束。输入新议题继续，或 'quit' 退出。")


def main():
    parser = argparse.ArgumentParser(description="多 Agent 辩论决策系统")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true", help="Demo 模式：完整辩论")
    group.add_argument("--interactive", action="store_true", help="交互模式：自定义议题")
    args = parser.parse_args()

    if args.demo:
        run_demo()
    elif args.interactive:
        run_interactive()


if __name__ == "__main__":
    main()
