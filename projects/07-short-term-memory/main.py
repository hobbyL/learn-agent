"""
主入口 —— 短期记忆 Agent 运行模式
====================================

支持 4 种运行模式：

1. --compare  (默认核心模式)
   预设 8 轮追问序列，4 种记忆策略并排运行，每轮展示回答 + 指标。
   用于直观对比各策略在记忆保留上的差异。

2. --demo
   同 compare，但使用精简 5 轮序列，快速体验效果。

3. --strategy <name>  交互模式
   单策略交互对话，支持 reset 命令清空记忆。
   name 可选：baseline / sliding / token / summary

4. 无参数（默认）
   等同于 --strategy summary（默认策略）

环境变量（.env 文件）：
    OPENAI_API_KEY=your-key
    MODEL_NAME=gpt-4o-mini
    MEMORY_STRATEGY=summary
    SLIDING_WINDOW_TURNS=6
    TOKEN_LIMIT=3000
    SUMMARY_THRESHOLD_RATIO=0.7

使用示例：
    python3 main.py --compare
    python3 main.py --demo
    python3 main.py --strategy sliding
    python3 main.py
"""

import argparse
import os
import sys

# 确保运行目录在 import 路径中
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
from openai import OpenAI

from agent import SYSTEM_PROMPT, MemoryAgent
from display import (
    print_compare_final_summary,
    print_error,
    print_info,
    print_interactive_answer,
    print_interactive_prompt,
    print_reset_notice,
    print_round_header,
    print_round_metrics,
    print_round_separator,
    print_session_header,
    print_strategy_answer,
)
from memory_manager import create_memory_manager
from tools import TOOLS_SCHEMA

# ============================================================
# 追问序列定义
# ============================================================

# --compare 模式：8 轮追问，刻意构造跨轮依赖
# 设计原理：
#   轮 1-3：建立基础信息（问林晨、问导师）
#   轮 4-5：引用早轮（问导师的院系、院系的院长）
#   轮 6：  引用轮 4-5（问院长相关的合作机构）—— 此时滑动窗口开始丢失轮 1 信息
#   轮 7：  深层引用（问合作机构负责人）
#   轮 8：  跨轮计算（引用轮 1 的入学年份 + 计算工具）
COMPARE_QUESTIONS = [
    "林晨是哪个院系的学员？",                          # 轮1：建立基础（林晨→量子院）
    "林晨的导师是谁？",                                # 轮2：建立基础（导师→苏明哲）
    "林晨的导师在哪个院系任职？",                       # 轮3：引用轮2（苏明哲→量子院）
    "那个院系的院长是谁？",                            # 轮4：隐式引用轮3（量子院→方若冰）
    "林晨的专长是什么？",                              # 轮5：回头引用轮1（检验早期信息）
    "刚才提到的那位院长，他们院系的合作机构是哪个？",    # 轮6：引用轮4（方若冰→量子院→量子动力研究所）
    "那个合作机构的负责人是谁？",                      # 轮7：引用轮6（量子动力研究所→黎远征）
    "林晨是 2026 年入学多少年了？请计算一下。",         # 轮8：引用轮1入学年份 + calculate
]

# --demo 模式：精简 5 轮，快速演示核心效果
DEMO_QUESTIONS = [
    "林晨是哪个院系的学员？",         # 轮1
    "林晨的导师是谁？",               # 轮2
    "那位导师在哪个院系？",           # 轮3：引用轮2
    "那个院系的院长是谁？",           # 轮4：引用轮3
    "林晨的专长是什么？",             # 轮5：回头引用轮1（测试早期记忆保留）
]

# 每轮的关键词检测（用于判断是否"答对"）
# 格式：{ 轮次索引: [正确答案关键词] }
# 只要回答中包含任意一个关键词即视为答对
ANSWER_KEYWORDS = {
    0: ["量子院", "量子物理"],
    1: ["苏明哲"],
    2: ["量子院", "量子物理"],
    3: ["方若冰"],
    4: ["量子纠缠", "通信协议"],
    5: ["量子动力研究所"],
    6: ["黎远征"],
    7: ["4", "四", "2022"],  # 2026-2022=4年
}

DEMO_ANSWER_KEYWORDS = {
    0: ["量子院", "量子物理"],
    1: ["苏明哲"],
    2: ["量子院", "量子物理"],
    3: ["方若冰"],
    4: ["量子纠缠", "通信协议"],
}


# ============================================================
# 工具函数
# ============================================================

def check_answer(answer: str, keywords: list[str]) -> bool:
    """
    检测回答是否包含期望关键词（任一命中即为答对）。
    溢出答案直接判为错。
    """
    if "⚠️ context 溢出" in answer:
        return False
    answer_lower = answer.lower()
    return any(kw.lower() in answer_lower for kw in keywords)


def load_env_config() -> tuple[OpenAI, str]:
    """
    加载环境变量，返回 (OpenAI client, model_name)。
    找不到 API key 时直接退出。
    """
    load_dotenv()

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    model = (
        os.environ.get("OPENAI_MODEL")
        or os.environ.get("MODEL_NAME", "gpt-4o-mini")
    ).strip()

    if not api_key:
        print_error("未找到 OPENAI_API_KEY 环境变量。请创建 .env 文件并配置 API Key。")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url=base_url)
    return client, model


def create_all_agents(client: OpenAI, model: str) -> dict[str, MemoryAgent]:
    """
    创建 4 种策略的 MemoryAgent 字典。
    每个 agent 独立拥有自己的 MemoryManager 实例。
    """
    sliding_turns = int(os.environ.get("SLIDING_WINDOW_TURNS", "6"))
    token_limit = int(os.environ.get("TOKEN_LIMIT", "3000"))
    summary_ratio = float(os.environ.get("SUMMARY_THRESHOLD_RATIO", "0.7"))

    agents = {}
    for strategy_name in ["baseline", "sliding", "token", "summary"]:
        memory = create_memory_manager(
            strategy_name,
            SYSTEM_PROMPT,
            client=client,
            model=model,
            max_turns=sliding_turns,
            max_tokens=token_limit,
            threshold_ratio=summary_ratio,
        )
        agents[strategy_name] = MemoryAgent(memory, client, model, TOOLS_SCHEMA)
    return agents


# ============================================================
# 运行模式：compare / demo
# ============================================================

def run_compare_mode(questions: list[str], answer_keywords: dict, mode: str = "compare") -> None:
    """
    核心对比模式：4 策略并排，按轮次展示。

    每轮：
    1. 打印轮次标题和问题
    2. 4 种策略依次调用 API（顺序调用，非并发）
    3. 收集每个策略的 (answer, messages_count, token_count)
    4. 打印回答内容 + 指标汇总
    5. 轮次结束后分隔线

    参数：
        questions: 追问序列
        answer_keywords: 轮次索引 -> 关键词列表
        mode: "compare" | "demo"（用于标题显示）
    """
    client, model = load_env_config()
    agents = create_all_agents(client, model)
    strategy_order = ["baseline", "sliding", "token", "summary"]
    # 策略简称 -> memory.name（用于 display 层颜色匹配）
    strategy_class_names = {
        "baseline": "BaselineMemory",
        "sliding":  "SlidingWindowMemory",
        "token":    "TokenLimitMemory",
        "summary":  "SummaryMemory",
    }

    print_session_header(mode)
    all_round_results = []

    for round_idx, question in enumerate(questions):
        round_num = round_idx + 1
        print_round_header(round_num, question)

        round_results = []

        for strategy_name in strategy_order:
            agent = agents[strategy_name]
            class_name = strategy_class_names[strategy_name]

            # 调用 API，获取回答和指标
            try:
                answer, msg_cnt, tok_cnt = agent.ask(question)
            except Exception as e:
                answer = f"(API 错误: {e})"
                msg_cnt = agent.memory.messages_count()
                tok_cnt = agent.memory.token_count()

            # 打印回答
            print_strategy_answer(class_name, answer)

            # 检测是否答对
            keywords = answer_keywords.get(round_idx, [])
            correct = check_answer(answer, keywords) if keywords else None

            round_results.append({
                "strategy": class_name,
                "answer":   answer,
                "messages": msg_cnt,
                "tokens":   tok_cnt,
                "correct":  correct,
            })

        # 打印本轮指标汇总
        print_round_metrics(round_results)
        print_round_separator()
        all_round_results.append(round_results)

    # 打印整体汇总
    print_compare_final_summary(all_round_results)


# ============================================================
# 运行模式：单策略交互
# ============================================================

def run_interactive_mode(strategy: str) -> None:
    """
    单策略交互模式。

    用户逐轮输入问题，支持：
    - 直接输入问题
    - 输入 "reset" 清空记忆
    - Ctrl+C / Ctrl+D / 输入 "exit" 退出
    """
    client, model = load_env_config()

    # 从环境变量读取策略参数
    sliding_turns = int(os.environ.get("SLIDING_WINDOW_TURNS", "6"))
    token_limit = int(os.environ.get("TOKEN_LIMIT", "3000"))
    summary_ratio = float(os.environ.get("SUMMARY_THRESHOLD_RATIO", "0.7"))

    memory = create_memory_manager(
        strategy,
        SYSTEM_PROMPT,
        client=client,
        model=model,
        max_turns=sliding_turns,
        max_tokens=token_limit,
        threshold_ratio=summary_ratio,
    )
    agent = MemoryAgent(memory, client, model, TOOLS_SCHEMA)
    class_name = memory.name

    print_session_header("interactive", strategy=strategy)
    print_info("输入问题与 Agent 对话。输入 reset 清空记忆，输入 exit 退出。")
    print()

    while True:
        # 打印输入提示符
        print_interactive_prompt(class_name)

        try:
            user_input = input().strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q"):
            print("再见！")
            break

        if user_input.lower() == "reset":
            agent.reset()
            print_reset_notice()
            continue

        # 调用 Agent
        try:
            answer, msg_cnt, tok_cnt = agent.ask(user_input)
        except Exception as e:
            print_error(str(e))
            continue

        # 打印回答和指标
        print_interactive_answer(class_name, answer, msg_cnt, tok_cnt)


# ============================================================
# 命令行参数解析
# ============================================================

def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="星际学院短期记忆 Agent —— 4 种记忆策略对比",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python3 main.py --compare           # 8 轮完整对比
  python3 main.py --demo              # 5 轮快速演示
  python3 main.py --strategy sliding  # 滑动窗口交互模式
  python3 main.py                     # 默认：summary 策略交互
        """,
    )

    parser.add_argument(
        "--compare",
        action="store_true",
        help="4 策略并排对比模式（8 轮追问序列）",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="演示模式（5 轮精简序列）",
    )
    parser.add_argument(
        "--strategy",
        choices=["baseline", "sliding", "token", "summary"],
        help="单策略交互模式，指定策略名",
    )

    return parser.parse_args()


# ============================================================
# 主函数
# ============================================================

def main() -> None:
    """程序入口，根据命令行参数分发到对应运行模式。"""
    args = parse_args()

    if args.compare:
        # 完整 8 轮对比
        run_compare_mode(COMPARE_QUESTIONS, ANSWER_KEYWORDS, mode="compare")

    elif args.demo:
        # 精简 5 轮演示
        run_compare_mode(DEMO_QUESTIONS, DEMO_ANSWER_KEYWORDS, mode="demo")

    elif args.strategy:
        # 单策略交互
        run_interactive_mode(args.strategy)

    else:
        # 默认：从环境变量读取策略，交互模式
        load_dotenv()
        default_strategy = os.environ.get("MEMORY_STRATEGY", "summary").lower().strip()
        # 验证策略名
        valid_strategies = ["baseline", "sliding", "token", "summary"]
        if default_strategy not in valid_strategies:
            default_strategy = "summary"
        run_interactive_mode(default_strategy)


if __name__ == "__main__":
    main()
