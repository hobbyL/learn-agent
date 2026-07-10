"""
display.py —— ANSI 渲染（trace 视图 + eval 表格 + 对比）
=========================================================

颜色方案：
- 手写 Agent：蓝色
- LangGraph Agent：绿色
- 标题/分隔线：粗体白色
- 工具调用：黄色
- 通过/高分：绿色
- 失败/低分：红色
"""


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

    HANDWRITTEN_COLOR = "\033[34m"  # 蓝色
    LANGGRAPH_COLOR   = "\033[32m"  # 绿色

    @staticmethod
    def colored(text: str, color: str) -> str:
        return f"{color}{text}{C.RESET}"

    @staticmethod
    def bold(text: str) -> str:
        return f"{C.BOLD}{text}{C.RESET}"


# ============================================================
# 通用工具函数
# ============================================================

def print_separator(char: str = "-", width: int = 70, color: str = C.DIM) -> None:
    print(C.colored(char * width, color))


def print_header(title: str) -> None:
    print()
    print_separator("=", 70, C.BOLD)
    print(C.colored(f"  {title}", C.BOLD))
    print_separator("=", 70, C.BOLD)


def print_section(title: str) -> None:
    print()
    print_separator("-", 70, C.DIM)
    print(C.colored(f"  {title}", C.BOLD))
    print_separator("-", 70, C.DIM)


# ============================================================
# LangSmith 状态提示
# ============================================================

def print_langsmith_status() -> None:
    """打印 LangSmith tracing 状态。"""
    import os
    tracing = os.environ.get("LANGSMITH_TRACING", "").lower()
    api_key = os.environ.get("LANGSMITH_API_KEY", "")
    project = os.environ.get("LANGSMITH_PROJECT", "13-observability")

    print()
    if tracing in ("true", "1", "yes") and api_key:
        print(C.colored("  LangSmith Tracing: 已开启", C.GREEN))
        print(C.colored(f"    项目: {project}", C.DIM))
        print(C.colored("    在 https://smith.langchain.com 查看 trace", C.DIM))
    else:
        print(C.colored("  LangSmith Tracing: 未开启（可选）", C.DIM))
        print(C.colored("    开启方法：设置 LANGSMITH_TRACING=true 和 LANGSMITH_API_KEY", C.DIM))


# ============================================================
# Trace 视图渲染
# ============================================================

def print_trace_summary(tracer) -> None:
    """打印 tracer 的汇总信息（调用 tracer 自身的 print_summary）。"""
    tracer.print_summary()


# ============================================================
# Eval 表格渲染
# ============================================================

def print_eval_table(results: list[dict], agent_name: str = "Agent") -> None:
    """
    打印评分表格。

    格式：
    编号 | 类型    | 问题              | 规则  | LLM | 耗时
    1    | factual | 星辰王国的人口... | PASS  | 4/5 | 1.2s
    """
    print_section(f"{agent_name} 评估结果")

    # 表头
    header = f"  {'#':<3} {'类型':<8} {'问题':<30} {'规则':<6} {'LLM':<5} {'耗时':<8}"
    print(C.bold(header))
    print(C.colored("  " + "-" * 65, C.DIM))

    for i, r in enumerate(results, 1):
        q_type = r["type"]
        question = r["question"][:28]
        if len(r["question"]) > 28:
            question += ".."

        # 规则评分
        if r["rule_eval"]:
            rule_passed = r["rule_eval"]["pass"]
            rule_str = C.colored("PASS", C.GREEN) if rule_passed else C.colored("FAIL", C.RED)
        else:
            rule_str = C.colored("  - ", C.DIM)

        # LLM 评分
        if r["llm_eval"] and r["llm_eval"]["score"] > 0:
            score = r["llm_eval"]["score"]
            score_color = C.GREEN if score >= 4 else (C.YELLOW if score >= 3 else C.RED)
            llm_str = C.colored(f"{score}/5", score_color)
        else:
            llm_str = C.colored(" - ", C.DIM)

        # 耗时
        elapsed = r["elapsed_ms"] / 1000  # 转换为秒
        elapsed_str = f"{elapsed:.1f}s"

        # 构建行（需要手动对齐因为有 ANSI 码）
        print(f"  {i:<3} {q_type:<8} {question:<30} {rule_str}  {llm_str}  {elapsed_str:<8}")

    # 汇总行
    from eval_runner import summarize_eval
    summary = summarize_eval(results)
    print(C.colored("  " + "-" * 65, C.DIM))
    print(f"  {C.BOLD}汇总{C.RESET}  "
          f"规则: {summary['rule_pass']} pass / {summary['rule_fail']} fail  "
          f"LLM 均分: {summary['avg_llm_score']:.1f}/5  "
          f"平均耗时: {summary['avg_elapsed_ms']/1000:.1f}s")


# ============================================================
# 对比表格
# ============================================================

def print_compare_table(
    results_handwritten: list[dict],
    results_langgraph: list[dict],
) -> None:
    """
    两个 Agent 的 eval 结果对比表格。

    格式：
    编号 | 问题              | 手写规则 | 手写LLM | LG规则 | LG-LLM
    """
    print_section("Agent 对比")

    header = (
        f"  {'#':<3} {'问题':<28} "
        f"{'手写-规则':<10} {'手写-LLM':<9} "
        f"{'LG-规则':<10} {'LG-LLM':<9}"
    )
    print(C.bold(header))
    print(C.colored("  " + "-" * 72, C.DIM))

    for i, (rh, rl) in enumerate(zip(results_handwritten, results_langgraph), 1):
        question = rh["question"][:26]
        if len(rh["question"]) > 26:
            question += ".."

        # 手写 Agent
        hw_rule = _format_rule(rh["rule_eval"])
        hw_llm = _format_llm(rh["llm_eval"])

        # LangGraph Agent
        lg_rule = _format_rule(rl["rule_eval"])
        lg_llm = _format_llm(rl["llm_eval"])

        print(f"  {i:<3} {question:<28} {hw_rule:<16} {hw_llm:<15} {lg_rule:<16} {lg_llm:<15}")

    # 汇总对比
    from eval_runner import summarize_eval
    sh = summarize_eval(results_handwritten)
    sl = summarize_eval(results_langgraph)
    print(C.colored("  " + "-" * 72, C.DIM))
    print(f"  {C.BOLD}手写 Agent{C.RESET}  "
          f"规则: {sh['rule_pass']}p/{sh['rule_fail']}f  "
          f"LLM: {sh['avg_llm_score']:.1f}/5  "
          f"耗时: {sh['avg_elapsed_ms']/1000:.1f}s")
    print(f"  {C.BOLD}LangGraph {C.RESET}  "
          f"规则: {sl['rule_pass']}p/{sl['rule_fail']}f  "
          f"LLM: {sl['avg_llm_score']:.1f}/5  "
          f"耗时: {sl['avg_elapsed_ms']/1000:.1f}s")


def _format_rule(rule_eval: dict | None) -> str:
    """格式化规则评分。"""
    if not rule_eval:
        return C.colored("-", C.DIM)
    if rule_eval["pass"]:
        return C.colored("PASS", C.GREEN)
    return C.colored("FAIL", C.RED)


def _format_llm(llm_eval: dict | None) -> str:
    """格式化 LLM 评分。"""
    if not llm_eval or llm_eval.get("score", 0) <= 0:
        return C.colored("-", C.DIM)
    score = llm_eval["score"]
    color = C.GREEN if score >= 4 else (C.YELLOW if score >= 3 else C.RED)
    return C.colored(f"{score}/5", color)
