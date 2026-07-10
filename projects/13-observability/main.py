"""
main.py —— CLI 入口（--trace / --eval / --compare / --demo）
=============================================================

用法：
    python main.py --demo              # 默认模式：trace → eval → 对比总结
    python main.py --trace             # 运行手写 Agent，展示自定义 tracer 输出
    python main.py --eval              # 跑手写 Agent 的 eval，输出评分表格
    python main.py --compare           # 对比两个 Agent 的 eval 结果

环境变量（.env 或 shell 中设置）：
    OPENAI_API_KEY=...
    OPENAI_BASE_URL=...               # 自定义端点（可选）
    OPENAI_MODEL=...                  # 默认 gpt-4o-mini
    LANGSMITH_TRACING=true            # 开启 LangSmith tracing（可选）
    LANGSMITH_API_KEY=...             # LangSmith API key（可选）
    LANGSMITH_PROJECT=...             # LangSmith 项目名（可选）
"""

import argparse
import os

from dotenv import load_dotenv

load_dotenv()


# ============================================================
# 演示问题
# ============================================================

TRACE_QUESTION = "星辰王国的面积是月影王国的多少倍？"


# ============================================================
# --trace 模式
# ============================================================

def cmd_trace():
    """
    运行手写 Agent 回答一个问题，展示自定义 tracer 的完整输出。
    包括：实时 ANSI 着色 + 汇总 + JSON 导出。
    """
    from display import print_header, print_langsmith_status, C
    from custom_tracer import AgentTracer
    from agent_handwritten import HandwrittenAgent

    print_header("13 · Observability · Trace 模式（手写 Agent + 自定义 Tracer）")
    print_langsmith_status()

    print()
    print(C.colored(f"  问题: {TRACE_QUESTION}", C.BOLD))
    print()

    # 创建 tracer（verbose=True 开启实时终端输出）
    tracer = AgentTracer(verbose=True)

    # 运行 Agent
    agent = HandwrittenAgent(max_steps=10, verbose=False)
    result = agent.run(TRACE_QUESTION, tracer=tracer)

    # 打印汇总
    tracer.print_summary()

    # 导出 JSON
    json_path = os.path.join(os.path.dirname(__file__), "trace_output.json")
    tracer.to_json(json_path)
    print()
    print(C.colored(f"  Trace JSON 已导出: {json_path}", C.DIM))

    # 打印答案
    print()
    print(C.colored(f"  最终答案: {result['answer']}", C.GREEN + C.BOLD))
    print(C.colored(f"  步数: {result['total_steps']}  终止: {result['terminated_by']}", C.DIM))


# ============================================================
# --eval 模式
# ============================================================

def cmd_eval():
    """
    加载 eval_dataset.json，跑手写 Agent 的 eval，输出评分表格。
    """
    from display import print_header, print_langsmith_status, print_eval_table, C
    from eval_runner import run_eval, load_dataset
    from agent_handwritten import run_handwritten

    print_header("13 · Observability · Eval 模式（手写 Agent）")
    print_langsmith_status()

    dataset = load_dataset()
    print()
    print(C.colored(f"  数据集: {len(dataset)} 个问题", C.DIM))
    print()

    results = run_eval(
        agent_fn=run_handwritten,
        dataset=dataset,
        use_llm_judge=True,
        agent_name="手写Agent",
    )

    print_eval_table(results, agent_name="手写 Agent")


# ============================================================
# --compare 模式
# ============================================================

def cmd_compare():
    """
    对比 LangGraph Agent vs 手写 Agent 的 eval 结果。
    """
    from display import (
        print_header, print_langsmith_status, print_eval_table,
        print_compare_table, C,
    )
    from eval_runner import run_eval, load_dataset
    from agent_handwritten import run_handwritten
    from agent_langgraph import run_langgraph

    print_header("13 · Observability · Compare 模式（手写 vs LangGraph）")
    print_langsmith_status()

    dataset = load_dataset()
    print()
    print(C.colored(f"  数据集: {len(dataset)} 个问题", C.DIM))
    print()

    # 手写 Agent
    print(C.colored("  ── 手写 Agent ──", C.BLUE + C.BOLD))
    results_hw = run_eval(
        agent_fn=run_handwritten,
        dataset=dataset,
        use_llm_judge=True,
        agent_name="手写Agent",
    )

    # LangGraph Agent
    print()
    print(C.colored("  ── LangGraph Agent ──", C.GREEN + C.BOLD))
    results_lg = run_eval(
        agent_fn=run_langgraph,
        dataset=dataset,
        use_llm_judge=True,
        agent_name="LangGraph",
    )

    # 各自的表格
    print_eval_table(results_hw, agent_name="手写 Agent")
    print_eval_table(results_lg, agent_name="LangGraph Agent")

    # 对比表格
    print_compare_table(results_hw, results_lg)


# ============================================================
# --demo 模式（默认）
# ============================================================

def cmd_demo():
    """
    默认模式：依次演示 trace → eval → 简要对比总结。
    """
    from display import (
        print_header, print_langsmith_status, print_section,
        print_eval_table, print_compare_table, C,
    )
    from custom_tracer import AgentTracer
    from agent_handwritten import HandwrittenAgent, run_handwritten
    from eval_runner import run_eval, load_dataset

    print_header("13 · Observability · Demo 模式")
    print_langsmith_status()

    # ── Part 1: Trace 演示 ──
    print_section("Part 1: 自定义 Tracer 演示（手写 Agent）")
    print(C.colored(f"  问题: {TRACE_QUESTION}", C.BOLD))
    print()

    tracer = AgentTracer(verbose=True)
    agent = HandwrittenAgent(max_steps=10, verbose=False)
    result = agent.run(TRACE_QUESTION, tracer=tracer)

    tracer.print_summary()

    json_path = os.path.join(os.path.dirname(__file__), "trace_output.json")
    tracer.to_json(json_path)
    print(C.colored(f"\n  Trace JSON 已导出: {json_path}", C.DIM))
    print(C.colored(f"  答案: {result['answer']}", C.GREEN))

    # ── Part 2: Eval 演示（精简版：只跑前 4 个问题）──
    print_section("Part 2: Eval 演示（手写 Agent，精简版）")

    dataset = load_dataset()
    demo_dataset = dataset[:4]  # demo 模式只跑前 4 个
    print(C.colored(f"  数据集: {len(demo_dataset)}/{len(dataset)} 个问题（demo 精简版）", C.DIM))
    print()

    results = run_eval(
        agent_fn=run_handwritten,
        dataset=demo_dataset,
        use_llm_judge=True,
        agent_name="手写Agent",
    )

    print_eval_table(results, agent_name="手写 Agent")

    # ── Part 3: 总结 ──
    print_section("Part 3: 总结")
    print(f"""
  本项目展示了三层 Agent 可观测性：

  {C.CYAN}1. Tracing（链路追踪）{C.RESET}
     - LangGraph Agent: LangSmith 零代码追踪（设置环境变量即可）
     - 手写 Agent: wrap_openai + @traceable（手动接入 LangSmith）
     - 自定义 Tracer: 不依赖 LangSmith，终端 ANSI + JSON 文件输出

  {C.CYAN}2. Eval（效果评估）{C.RESET}
     - 规则匹配评分器: 快速、确定性、适合事实型问题
     - LLM-as-Judge: 灵活、主观、适合开放型问题
     - 双评分器并用，互相补充

  {C.CYAN}3. 对比分析{C.RESET}
     - python main.py --compare 可并排对比两种 Agent
     - 同一数据集，不同实现，结果可量化对比

  {C.DIM}完整评估请运行: python main.py --eval 或 python main.py --compare{C.RESET}
""")


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="13-observability：Agent 可观测性（tracing + eval + 自定义 tracer）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python main.py --demo              # 默认模式（推荐首次运行）
  python main.py --trace             # 手写 Agent + 自定义 tracer
  python main.py --eval              # 手写 Agent 完整 eval
  python main.py --compare           # 手写 vs LangGraph 对比
        """,
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--demo", action="store_true", help="默认模式：trace → eval → 总结（推荐）")
    group.add_argument("--trace", action="store_true", help="运行手写 Agent，展示自定义 tracer")
    group.add_argument("--eval", action="store_true", help="手写 Agent 完整 eval")
    group.add_argument("--compare", action="store_true", help="手写 vs LangGraph 对比 eval")

    args = parser.parse_args()

    if args.trace:
        cmd_trace()
    elif args.eval:
        cmd_eval()
    elif args.compare:
        cmd_compare()
    else:
        # 默认 demo
        cmd_demo()


if __name__ == "__main__":
    main()
