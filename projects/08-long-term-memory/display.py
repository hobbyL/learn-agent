"""
展示模块 —— 长期记忆 Agent 输出格式化
=======================================

负责将 LongMemoryAgent 的输出以清晰的格式呈现给用户，
包括检索到的记忆条目、相似度分数、注入摘要、最终回答等。

与 07-short-term-memory/display.py 的区别：
- 07：展示记忆策略指标（token 数、messages 数、策略名称）
- 08：展示长期记忆检索结果（相似度、session 信息、注入条数）

ANSI 颜色方案：
- Session 标题：蓝色加粗
- 用户问题：正常白色
- 检索记忆：黄色（引起注意）
- 注入摘要：青色
- Agent 回答：绿色
- 统计信息：灰色
- 错误信息：红色
"""

import sys

# ANSI 转义码
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_BLUE   = "\033[34m"
_CYAN   = "\033[36m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_GRAY   = "\033[90m"
_RED    = "\033[31m"
_WHITE  = "\033[97m"


def print_separator(char: str = "─", width: int = 60) -> None:
    """打印分隔线。"""
    print(f"{_GRAY}{char * width}{_RESET}")


def print_session_header(session_id: str, desc: str) -> None:
    """
    打印 session 开始标题。

    格式：
        ══════════════════════════════════════════
        Session 1 · 建立记忆：询问星际学院信息
        ══════════════════════════════════════════
    """
    print(f"\n{_BOLD}{_BLUE}{'═' * 60}{_RESET}")
    print(f"{_BOLD}{_BLUE}  {session_id}  ·  {desc}{_RESET}")
    print(f"{_BOLD}{_BLUE}{'═' * 60}{_RESET}\n")


def print_turn_header(turn_num: int, session_id: str, question: str) -> None:
    """
    打印每轮对话标题和用户问题。

    格式：
        ── Session 1 · 第 1 轮 ──
        📤 用户：林晨是哪个院系的学员？
    """
    print(f"\n{_GRAY}── {session_id} · 第 {turn_num} 轮 ──{_RESET}")
    print(f"{_BOLD}📤 用户：{_RESET}{question}")


def print_retrieved_memories(memories: list[dict], top_k: int, threshold: float) -> None:
    """
    打印检索到的长期记忆条目。

    格式：
        🔍 检索长期记忆（top-3，阈值0.7）：
          [相似度 0.92] Session 1 · 第2轮：用户问"..."，助手答"..."
          [相似度 0.87] Session 1 · 第1轮：用户问"..."，助手答"..."
        （无记忆时）：  暂无相关记忆
    """
    print(f"\n{_YELLOW}🔍 检索长期记忆（top-{top_k}，阈值{threshold}）：{_RESET}")

    if not memories:
        print(f"  {_GRAY}暂无相关记忆（collection 为空或无超过阈值的结果）{_RESET}")
        return

    for m in memories:
        meta = m["metadata"]
        sim = m["similarity"]
        session_id = meta["session_id"]
        turn_id = meta["turn_id"]
        # 截断过长的问答以保持展示简洁
        q = meta["user_query"][:30] + ("..." if len(meta["user_query"]) > 30 else "")
        a = meta["assistant_answer"][:30] + ("..." if len(meta["assistant_answer"]) > 30 else "")
        line = (
            f"  {_YELLOW}[相似度 {sim:.2f}]{_RESET}"
            f" {session_id} · 第{turn_id}轮："
            f" 用户问「{q}」，助手答「{a}」"
        )
        print(line)


def print_injection_summary(memories: list[dict]) -> None:
    """
    打印注入 context 的摘要。

    格式：
        💉 注入 context：2 条记忆
        （无记忆时）：💉 注入 context：0 条记忆（未超过相似度阈值）
    """
    count = len(memories)
    if count > 0:
        print(f"\n{_CYAN}💉 注入 context：{count} 条记忆{_RESET}")
    else:
        print(f"\n{_GRAY}💉 注入 context：0 条记忆（未超过相似度阈值）{_RESET}")


def print_answer(answer: str) -> None:
    """
    打印 Agent 回答。

    格式：
        🤖 回答：根据我们之前的对话...
    """
    print(f"\n{_BOLD}{_GREEN}🤖 回答：{_RESET}{_GREEN}{answer}{_RESET}")


def print_memory_stats(total_memories: int) -> None:
    """
    打印当前长期记忆总条数（每个 session 结束后展示）。

    格式：
        📊 当前长期记忆总条数：4
    """
    print(f"\n{_GRAY}📊 当前长期记忆总条数：{total_memories}{_RESET}")


def print_comparison_table() -> None:
    """
    打印短期记忆（07）vs 长期记忆（08）对比表。

    在 --demo 模式结束后调用，直观对比两种记忆机制的差异。
    """
    print(f"\n{_BOLD}{'═' * 60}{_RESET}")
    print(f"{_BOLD}  📊 短期记忆（07）vs 长期记忆（08）对比{_RESET}")
    print(f"{_BOLD}{'═' * 60}{_RESET}\n")

    # 表格数据
    rows = [
        ("存储位置",  "内存 messages 列表",    "ChromaDB 磁盘"),
        ("跨session", "❌ 清空即失",           "✅ 持久化"),
        ("检索方式",  "全量截断/压缩",          "语义相似度检索"),
        ("记忆容量",  "受 context 窗口限制",    "理论无上限"),
        ("首轮延迟",  "无（直接截断）",          "有（embedding API 调用）"),
        ("记忆精度",  "按时序保留近期对话",      "按语义相关性检索"),
    ]

    # 表头
    col0_w = 12
    col1_w = 22
    col2_w = 22
    header = (
        f"  {_BOLD}{'维度':<{col0_w}}{_RESET}"
        f"  {_BOLD}{_CYAN}{'短期记忆（07）':<{col1_w}}{_RESET}"
        f"  {_BOLD}{_GREEN}{'长期记忆（08）':<{col2_w}}{_RESET}"
    )
    print(header)
    print(f"  {_GRAY}{'─' * (col0_w + col1_w + col2_w + 4)}{_RESET}")

    for dim, short_val, long_val in rows:
        print(
            f"  {dim:<{col0_w}}"
            f"  {_CYAN}{short_val:<{col1_w}}{_RESET}"
            f"  {_GREEN}{long_val:<{col2_w}}{_RESET}"
        )

    print(f"\n{_GRAY}{'─' * 60}{_RESET}\n")


def print_interactive_help() -> None:
    """打印 interactive 模式的命令说明。"""
    print(f"\n{_GRAY}命令提示：")
    print(f"  reset        — 清空短期记忆（保留长期记忆，开始新 session）")
    print(f"  clear-memory — 清空所有长期记忆（ChromaDB 数据）")
    print(f"  exit / quit  — 退出程序{_RESET}\n")


def print_error(msg: str) -> None:
    """打印错误信息。"""
    print(f"\n{_RED}❌ 错误：{msg}{_RESET}", file=sys.stderr)


def print_info(msg: str) -> None:
    """打印一般提示信息。"""
    print(f"\n{_CYAN}ℹ️  {msg}{_RESET}")


def print_warning(msg: str) -> None:
    """打印警告信息。"""
    print(f"\n{_YELLOW}⚠️  {msg}{_RESET}")
