"""
入口脚本 —— 长期记忆 Agent
============================

三种运行模式：

1. --demo         自动演示 3 个模拟 session：
                    Session 1：询问星际学院信息（建立记忆）
                    Session 2：清空短期，测试跨 session 回忆
                    Session 3：深层追问，验证长期记忆检索
                  结束后打印短期 vs 长期记忆对比表

2. --interactive  交互式对话，每轮自动存入长期记忆
                  命令：reset / clear-memory / exit

3. --clear-memory 清空 ChromaDB 持久化数据（需确认）

用法：
    python3 main.py --demo
    python3 main.py --interactive
    python3 main.py --clear-memory
"""

import argparse
import os
import sys

# 将当前目录加入 sys.path，确保能导入同目录模块
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv

from agent import LongMemoryAgent, create_agent, SYSTEM_PROMPT
from display import (
    print_answer,
    print_comparison_table,
    print_info,
    print_injection_summary,
    print_interactive_help,
    print_memory_stats,
    print_retrieved_memories,
    print_session_header,
    print_turn_header,
    print_warning,
    print_error,
    print_separator,
)


# ============================================================
# Demo 模式数据
# ============================================================

# 3 个模拟 session，覆盖建立→跨 session 回忆→深层追问的完整流程
DEMO_SESSIONS = [
    {
        "session_id": "session_1",
        "desc": "建立记忆：询问星际学院信息",
        "questions": [
            "林晨是哪个院系的学员？",
            "量子院的院长是谁？",
            "林晨的导师是谁？",
            "苏明哲的研究方向是什么？",
        ],
    },
    {
        "session_id": "session_2",
        "desc": "跨 session 回忆：清空短期记忆，测试长期记忆检索",
        "questions": [
            "上次我们聊了什么关于量子院的内容？",
            "之前提到的林晨的导师叫什么名字？",
        ],
    },
    {
        "session_id": "session_3",
        "desc": "深层追问：基于长期记忆继续探索",
        "questions": [
            "苏明哲所在院系的合作机构是哪个？",
            "林晨入学多少年了？（当前2026年）",
        ],
    },
]


# ============================================================
# 公共对话轮次执行函数
# ============================================================

def run_turn(
    agent: LongMemoryAgent,
    question: str,
    turn_num: int,
    session_id: str,
    top_k: int,
    threshold: float,
) -> None:
    """
    执行单轮对话并展示完整信息（检索记忆 + 注入摘要 + 回答）。

    参数：
        agent      — LongMemoryAgent 实例
        question   — 用户问题
        turn_num   — 当前轮次编号
        session_id — 当前 session ID
        top_k      — 检索条数（用于展示）
        threshold  — 相似度阈值（用于展示）
    """
    # 打印轮次标题和用户问题
    print_turn_header(turn_num, session_id, question)

    # 执行问答（内部自动检索长期记忆并存入）
    answer, memories = agent.ask(question)

    # 展示检索到的记忆
    print_retrieved_memories(memories, top_k, threshold)
    print_injection_summary(memories)

    # 展示最终回答
    print_answer(answer)


# ============================================================
# Demo 模式
# ============================================================

def run_demo(agent: LongMemoryAgent, top_k: int, threshold: float) -> None:
    """
    自动运行 3 个模拟 session，演示跨 session 长期记忆效果。

    核心演示点：
    - Session 1 → Session 2：清空短期记忆后，长期记忆仍能检索到 Session 1 内容
    - Session 2 → Session 3：更深层的追问也能从长期记忆中找到相关内容
    """
    print(f"\n{'═' * 60}")
    print(f"  🧠 长期记忆 Agent —— 跨 Session 演示")
    print(f"{'═' * 60}")
    print(f"\n当前长期记忆条数：{agent.long_term_memory.count()}")
    print(f"将依次运行 {len(DEMO_SESSIONS)} 个模拟 session...\n")

    for session_data in DEMO_SESSIONS:
        session_id = session_data["session_id"]
        desc = session_data["desc"]
        questions = session_data["questions"]

        # 开始新 session（清空短期记忆，长期记忆保留）
        agent.new_session(session_id)
        print_session_header(session_id, desc)

        # 依次执行每个问题
        for i, question in enumerate(questions, start=1):
            run_turn(agent, question, i, session_id, top_k, threshold)

        # 每个 session 结束后展示当前长期记忆总数
        print_memory_stats(agent.long_term_memory.count())
        print_separator()

    # 所有 session 结束后打印对比表
    print_comparison_table()


# ============================================================
# Interactive 模式
# ============================================================

def run_interactive(agent: LongMemoryAgent, top_k: int, threshold: float) -> None:
    """
    交互式对话模式。

    功能：
    - 每轮自动存入长期记忆
    - 启动时展示当前记忆条数
    - 支持命令：reset / clear-memory / exit

    命令说明：
        reset        — 清空短期 messages（不清长期记忆），模拟新 session 开始
        clear-memory — 清空所有 ChromaDB 数据（需要确认）
        exit/quit    — 退出
    """
    # 使用一个递增的 session counter
    session_counter = 1
    session_id = f"interactive_{session_counter}"
    agent.new_session(session_id)

    print(f"\n{'═' * 60}")
    print(f"  🧠 长期记忆 Agent —— 交互模式")
    print(f"{'═' * 60}")
    print(f"\n当前长期记忆条数：{agent.long_term_memory.count()}")
    print_interactive_help()

    turn_num = 0

    while True:
        try:
            user_input = input(f"\n{session_id} > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n再见！")
            break

        if not user_input:
            continue

        # ── 命令处理 ──

        if user_input.lower() in ("exit", "quit"):
            print("\n再见！")
            break

        elif user_input.lower() == "reset":
            # 清空短期记忆，开始新 session（保留长期记忆）
            session_counter += 1
            session_id = f"interactive_{session_counter}"
            agent.new_session(session_id)
            turn_num = 0
            print_info(f"短期记忆已清空，开始新 Session：{session_id}")
            print_memory_stats(agent.long_term_memory.count())
            continue

        elif user_input.lower() == "clear-memory":
            # 二次确认后清空长期记忆
            confirm = input("  确认清空所有长期记忆？输入 yes 确认：").strip().lower()
            if confirm == "yes":
                agent.clear_long_term()
                print_info("长期记忆已清空")
            else:
                print_info("已取消")
            continue

        # ── 正常对话 ──
        turn_num += 1
        print_turn_header(turn_num, session_id, user_input)

        answer, memories = agent.ask(user_input)

        print_retrieved_memories(memories, top_k, threshold)
        print_injection_summary(memories)
        print_answer(answer)


# ============================================================
# 入口
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="长期记忆 Agent —— ChromaDB 跨 session 语义记忆",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
模式说明：
  --demo          自动演示 3 个 session（建立→回忆→追问）
  --interactive   交互式对话，支持 reset / clear-memory 命令
  --clear-memory  清空 ChromaDB 持久化数据
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo",         action="store_true", help="自动演示模式")
    group.add_argument("--interactive",  action="store_true", help="交互式对话模式")
    group.add_argument("--clear-memory", action="store_true", help="清空长期记忆")

    args = parser.parse_args()

    # 加载 .env
    load_dotenv()

    # 读取记忆参数（用于展示）
    top_k = int(os.environ.get("MEMORY_TOP_K", "3"))
    threshold = float(os.environ.get("MEMORY_THRESHOLD", "0.7"))

    # --clear-memory 模式：不需要完整 agent，直接操作 ChromaDB
    if args.clear_memory:
        _handle_clear_memory(top_k, threshold)
        return

    # 创建 Agent（会验证所有环境变量配置）
    try:
        agent = create_agent(session_id="demo_init")
    except ValueError as e:
        print_error(str(e))
        sys.exit(1)

    if args.demo:
        run_demo(agent, top_k, threshold)
    elif args.interactive:
        run_interactive(agent, top_k, threshold)


def _handle_clear_memory(top_k: int, threshold: float) -> None:
    """
    独立处理 --clear-memory 模式。

    需要初始化 ChromaDB 客户端，但不需要创建完整 Agent，
    因此单独处理以提供更清晰的错误提示。
    """
    from dotenv import load_dotenv
    load_dotenv()

    # 只需要 Embedding 配置和 ChromaDB 路径
    emb_base_url = os.environ.get("EMBEDDING_BASE_URL", "").strip()
    emb_api_key = os.environ.get("EMBEDDING_API_KEY", "").strip()
    emb_model = os.environ.get("EMBEDDING_MODEL", "").strip()
    persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_db").strip()

    if not all([emb_base_url, emb_api_key, emb_model]):
        print_error(
            "清空记忆需要 Embedding 配置，请在 .env 中设置：\n"
            "  EMBEDDING_BASE_URL, EMBEDDING_API_KEY, EMBEDDING_MODEL"
        )
        sys.exit(1)

    from long_term_memory import LongTermMemory, OpenAICompatibleEF

    embedding_fn = OpenAICompatibleEF(
        base_url=emb_base_url,
        api_key=emb_api_key,
        model=emb_model,
    )
    ltm = LongTermMemory(
        persist_dir=persist_dir,
        collection_name="conversation_memory",
        embedding_fn=embedding_fn,
    )

    count = ltm.count()
    print(f"\n当前长期记忆条数：{count}")

    if count == 0:
        print_info("长期记忆已经为空，无需清除")
        return

    confirm = input(f"\n确认清空 {count} 条记忆？输入 yes 确认：").strip().lower()
    if confirm == "yes":
        ltm.clear()
        print_info(f"已清空 {count} 条长期记忆")
    else:
        print_info("已取消")


if __name__ == "__main__":
    main()
