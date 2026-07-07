"""
主入口 —— 任务规划与目标树 Agent 运行模式
==========================================

支持 2 种运行模式（本项目不做 --compare，见 PRD Out of Scope）：

1. --demo（默认）
   预设高层目标"建造载人空间站 Phase-1"，自动跑完整 Plan → Execute → Re-plan
   流程，用 display 实时展示目标树状态变化。

2. --interactive
   用户输入自定义建设目标，Agent 规划并执行。

环境变量（.env 文件）：
    OPENAI_API_KEY=your-key
    OPENAI_BASE_URL=https://api.openai.com/v1   （可选）
    MODEL_NAME=gpt-4o-mini
    MAX_REPLANS=3                                （可选，最大局部重规划次数）
    MAX_STEPS=8                                  （可选，内层 ReAct 每子任务最大步数）
    ENABLE_EXPANSION=false                       （可选，是否启用动态展开判断）
    RANDOM_SEED=42                               （可选，固定环境事件随机性便于复现）

使用示例：
    python3 main.py --demo
    python3 main.py --interactive
    python3 main.py                 # 默认 --demo
"""

import argparse
import os
import sys

# load_dotenv 必须在导入自研模块前最先调用（对齐项目约定）
from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI  # noqa: E402

import display  # noqa: E402
from planner_agent import PlanningAgent  # noqa: E402


# ============================================================
# 预设 demo 目标
# ============================================================
# 选"建造载人空间站 Phase-1"作为默认目标：它天然需要多个模块（居住舱、
# 太阳能阵列、生命维持系统…），模块之间有前置依赖，且部分是舱外作业——
# 恰好能触发资源采集 → 依赖排序 → 环境事件失败 → 局部重规划的完整链路。
DEMO_GOAL = "建造载人空间站 Phase-1：完成居住舱、太阳能阵列、生命维持系统三个核心模块"


# ============================================================
# 配置加载
# ============================================================

def load_config() -> tuple[OpenAI, str]:
    """
    加载环境变量，返回 (OpenAI client, model_name)。

    找不到 API key 时打印错误并退出（对齐 09 的做法）。
    load_dotenv 已在模块顶部调用，这里只读取。
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    model = (
        os.environ.get("OPENAI_MODEL")
        or os.environ.get("MODEL_NAME", "gpt-4o-mini")
    ).strip()

    if not api_key:
        display.print_error(
            "未找到 OPENAI_API_KEY 环境变量。请复制 .env.example 为 .env 并填入 API Key。"
        )
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url=base_url)
    return client, model


def build_agent(client: OpenAI, model: str) -> PlanningAgent:
    """
    从环境变量读取运行参数，构建 PlanningAgent。

    MAX_REPLANS / MAX_STEPS / ENABLE_EXPANSION 均可通过 .env 覆盖默认值。
    RANDOM_SEED 若设置，则固定 tools 层的环境事件随机性，便于复现 demo 结果。
    """
    max_replans = int(os.environ.get("MAX_REPLANS", "3"))
    max_steps = int(os.environ.get("MAX_STEPS", "8"))
    enable_expansion = os.environ.get("ENABLE_EXPANSION", "false").strip().lower() in (
        "1", "true", "yes", "on"
    )

    # 可选：固定随机种子，让环境事件触发在多次运行间可复现
    seed_raw = os.environ.get("RANDOM_SEED", "").strip()
    if seed_raw:
        try:
            from tools import set_random_seed
            set_random_seed(int(seed_raw))
        except (ImportError, ValueError):
            # 种子设置是可选优化，失败不影响主流程
            pass

    return PlanningAgent(
        max_replans=max_replans,
        max_steps=max_steps,
        enable_expansion=enable_expansion,
        client=client,
        model=model,
        verbose=True,
    )


# ============================================================
# 运行模式：demo
# ============================================================

def run_demo_mode() -> None:
    """
    演示模式：用预设目标自动跑完整 Plan → Execute → Re-plan 流程。

    PlanningAgent 在 verbose=True 下已经通过 display 渲染全过程
    （头部 / 目标树 / 子任务执行 / 重规划事件 / 收尾汇总），
    因此这里只需驱动它跑起来。
    """
    client, model = load_config()
    display.print_info(f"模型：{model}｜模式：demo（预设目标）")

    agent = build_agent(client, model)
    agent.run(DEMO_GOAL)


# ============================================================
# 运行模式：interactive
# ============================================================

def run_interactive_mode() -> None:
    """
    交互模式：用户输入自定义建设目标，Agent 规划并执行。

    支持连续输入多个目标；输入 exit / quit / q 退出。
    每个目标都会 reset 基地状态从干净世界开始（PlanningAgent.run 内部处理）。
    """
    client, model = load_config()
    agent = build_agent(client, model)

    display.print_info(f"模型：{model}｜模式：interactive（自定义目标）")
    print()
    display.print_info(
        "输入你的太空基地建设目标，Agent 会规划并执行。输入 exit 退出。"
    )
    display.print_info(
        "示例：建造一座带通信塔和实验室的科研基地"
    )
    print()

    while True:
        try:
            goal = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not goal:
            continue

        if goal.lower() in ("exit", "quit", "q"):
            print("再见！")
            break

        try:
            agent.run(goal)
        except Exception as e:
            display.print_error(f"规划执行失败：{e}")


# ============================================================
# 命令行参数解析
# ============================================================

def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="新曙光基地 · 任务规划与目标树 Agent（Plan → Execute → Re-plan）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python3 main.py --demo          # 预设目标，自动跑完整流程（默认）
  python3 main.py --interactive   # 自定义建设目标
  python3 main.py                 # 等同 --demo
        """,
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="演示模式：预设目标自动跑完整 Plan→Execute→Re-plan 流程（默认）",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="交互模式：用户输入自定义建设目标",
    )

    return parser.parse_args()


# ============================================================
# 主函数
# ============================================================

def main() -> None:
    """程序入口，根据命令行参数分发到对应运行模式。"""
    args = parse_args()

    if args.interactive:
        run_interactive_mode()
    else:
        # --demo 或无参数：均走演示模式
        run_demo_mode()


if __name__ == "__main__":
    main()
