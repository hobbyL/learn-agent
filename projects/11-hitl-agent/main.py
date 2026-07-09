"""
11-hitl-agent CLI 入口
======================

双模式：
    --demo        预设剧本模式，无人值守跑完（默认）
    --interactive 交互模式，真实人类 stdin 输入

配置通过 .env 文件读取：
    OPENAI_API_KEY   — API 密钥（必填）
    OPENAI_BASE_URL  — 可选自定义端点
    MODEL_NAME       — 模型名（默认 gpt-4o-mini）
    MAX_STEPS        — ReAct 最大步数（默认 15）
    RANDOM_SEED      — 随机种子（可选，控制灾害恶化随机性）
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

# 先加载 .env，再 import 依赖 env 的模块
load_dotenv()


def _build_agent(mode: str):
    """构建 Agent 实例。"""
    from openai import OpenAI

    from agent import HITLAgent
    from hitl import ScriptedHandler, InteractiveHandler
    from scenarios import DEMO_GOAL, get_demo_script

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("❌ 请在 .env 中设置 OPENAI_API_KEY")
        sys.exit(1)

    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    model = os.environ.get("MODEL_NAME", "gpt-4o-mini")
    max_steps = int(os.environ.get("MAX_STEPS", "15"))

    client = OpenAI(api_key=api_key, base_url=base_url)

    # 根据模式选择 HITL handler
    if mode == "demo":
        handler = ScriptedHandler(get_demo_script())
    else:
        handler = InteractiveHandler()

    agent = HITLAgent(
        handler=handler,
        client=client,
        model=model,
        max_steps=max_steps,
    )

    return agent, DEMO_GOAL if mode == "demo" else None


def main():
    parser = argparse.ArgumentParser(
        description="11-hitl-agent：Human-in-the-Loop 灾害应急指挥 Agent"
    )
    parser.add_argument(
        "--demo",
        action="store_const",
        const="demo",
        dest="mode",
        help="演示模式：预设剧本，无人值守（默认）",
    )
    parser.add_argument(
        "--interactive",
        action="store_const",
        const="interactive",
        dest="mode",
        help="交互模式：真实人类 stdin 输入",
    )
    parser.set_defaults(mode="demo")

    args = parser.parse_args()

    agent, goal = _build_agent(args.mode)

    if args.mode == "interactive":
        print("\n🏢 明川市应急指挥中心 — 交互模式")
        print("请输入救援任务目标（或按 Enter 使用默认目标）：\n")
        user_input = input("> ").strip()
        if not user_input:
            from scenarios import DEMO_GOAL
            goal = DEMO_GOAL
            print(f"\n使用默认目标。\n")
        else:
            goal = user_input

    agent.run(goal)


if __name__ == "__main__":
    main()
