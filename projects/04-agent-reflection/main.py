"""
04-agent-reflection 入口 —— Reflexion 自我反思 Agent
====================================================

三种运行模式：
    --demo    : 运行预设测试问题，展示完整反思循环
    --compare : 对比"无反思（单轮）" vs "有反思（多轮）"的效果差异
    交互模式   : 自由提问（默认用 Ground Truth 评估器，需手动输入标准答案）

核心学习价值：
    观察 Agent 如何从错误中学习——
    第 1 轮犯错 → 评估器指出问题 → 反思器总结教训 →
    第 2 轮带着教训重试 → 答案改善。

和 03 的区别：
    03 关注"单轮推理链的可审计性"（ReAct 内部循环）
    04 关注"多轮试错的自我改进"（ReAct 外层的 Reflexion 循环）
"""

import os
import sys
import json
from dotenv import load_dotenv

# 必须最先加载 .env
load_dotenv()


# ============================================================
# ANSI 颜色定义 —— 分层可视化（比 03 多了 Reflection 层的颜色）
# ============================================================

class Colors:
    """终端颜色，用于多层推理可视化。"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # ReAct 内层
    THOUGHT = "\033[36m"       # 青色 —— 思考
    ACTION = "\033[33m"        # 黄色 —— 行动
    OBSERVATION = "\033[32m"   # 绿色 —— 观察

    # Reflexion 外层
    TRIAL = "\033[35m"         # 紫色 —— 试验轮次
    EVALUATION = "\033[31m"    # 红色 —— 评估（失败时醒目）
    EVAL_PASS = "\033[32m"     # 绿色 —— 评估通过
    REFLECTION = "\033[34m"    # 蓝色 —— 反思

    # 通用
    QUESTION = "\033[35;1m"    # 紫色粗体 —— 用户问题
    ANSWER = "\033[34;1m"      # 蓝色粗体 —— 最终答案
    ERROR = "\033[31m"         # 红色 —— 错误
    HEADER = "\033[37;1m"      # 白色粗体 —— 标题
    SUCCESS = "\033[32;1m"     # 绿色粗体 —— 成功


def print_header():
    """打印启动信息。"""
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    max_trials = os.environ.get("MAX_TRIALS", "3")
    evaluator = os.environ.get("EVALUATOR_MODE", "ground_truth")

    print(f"\n{Colors.HEADER}{'═' * 60}{Colors.RESET}")
    print(f"{Colors.HEADER}  04-agent-reflection —— Reflexion 自我反思 Agent{Colors.RESET}")
    print(f"{Colors.HEADER}{'═' * 60}{Colors.RESET}")
    print(f"  模型：{model}")
    print(f"  最大反思轮数：{max_trials}")
    print(f"  评估器：{evaluator}")
    print(f"  输入 'exit' 退出 | 'list' 查看测试问题")
    print(f"{Colors.HEADER}{'═' * 60}{Colors.RESET}\n")


def print_trial_result(trial_num: int, max_trials: int, result: dict):
    """打印单轮试验结果（内层 ReAct 的推理链）。"""
    print(f"\n  {Colors.TRIAL}{'─' * 50}{Colors.RESET}")
    print(f"  {Colors.TRIAL}  Trial {trial_num}/{max_trials} —— ReAct 推理链{Colors.RESET}")
    print(f"  {Colors.TRIAL}{'─' * 50}{Colors.RESET}")

    for step in result.get("steps", []):
        step_num = step["step"]
        print(f"\n    {Colors.DIM}[Step {step_num}]{Colors.RESET}")

        if step.get("thought"):
            # 截断过长的 thought
            thought = step["thought"]
            if len(thought) > 150:
                thought = thought[:150] + "..."
            print(f"    {Colors.THOUGHT}💭 {thought}{Colors.RESET}")

        if step.get("action") and not step["action"].startswith("_"):
            action_input = json.dumps(step.get("action_input", {}), ensure_ascii=False)
            print(f"    {Colors.ACTION}🔧 {step['action']}({action_input}){Colors.RESET}")

        if step.get("observation") and not step.get("action", "").startswith("_"):
            obs = step["observation"]
            if len(obs) > 120:
                obs = obs[:120] + "..."
            print(f"    {Colors.OBSERVATION}👁️ {obs}{Colors.RESET}")

    print(f"\n    {Colors.DIM}答案：{result.get('answer', '无')}{Colors.RESET}")
    print(f"    {Colors.DIM}步数：{result.get('total_steps', 0)} | 终止：{result.get('terminated_by', '?')}{Colors.RESET}")


def print_evaluation(eval_result: dict):
    """打印评估结果。"""
    is_correct = eval_result.get("is_correct", False)
    feedback = eval_result.get("feedback", "")
    confidence = eval_result.get("confidence", 0)

    if is_correct:
        print(f"\n  {Colors.EVAL_PASS}✅ 评估通过！{Colors.RESET}")
        print(f"  {Colors.EVAL_PASS}   置信度：{confidence:.0%} | {feedback}{Colors.RESET}")
    else:
        print(f"\n  {Colors.EVALUATION}❌ 评估未通过{Colors.RESET}")
        print(f"  {Colors.EVALUATION}   置信度：{confidence:.0%} | {feedback}{Colors.RESET}")


def print_reflection(reflection: str, trial_num: int):
    """打印反思摘要。"""
    print(f"\n  {Colors.REFLECTION}{'─' * 50}{Colors.RESET}")
    print(f"  {Colors.REFLECTION}🪞 第 {trial_num} 轮反思摘要{Colors.RESET}")
    print(f"  {Colors.REFLECTION}{'─' * 50}{Colors.RESET}")
    # 缩进反思内容
    for line in reflection.split("\n"):
        print(f"  {Colors.REFLECTION}  {line}{Colors.RESET}")


def print_final_result(run_result: dict):
    """打印最终运行结果。"""
    print(f"\n{Colors.HEADER}{'═' * 60}{Colors.RESET}")
    print(f"{Colors.HEADER}  📊 最终结果{Colors.RESET}")
    print(f"{Colors.HEADER}{'═' * 60}{Colors.RESET}")

    answer = run_result.get("answer", "无")
    total_trials = run_result.get("total_trials", 0)
    success = run_result.get("is_correct", False)
    terminated_by = run_result.get("terminated_by", "?")

    if success:
        print(f"  {Colors.SUCCESS}✅ 成功！{Colors.RESET}")
    else:
        print(f"  {Colors.ERROR}❌ 未能得出正确答案{Colors.RESET}")

    print(f"  {Colors.ANSWER}答案：{answer}{Colors.RESET}")
    print(f"  总试验轮数：{total_trials}")
    print(f"  终止原因：{terminated_by}")

    # 打印反思历程
    reflections = run_result.get("reflections", [])
    if reflections:
        print(f"\n  {Colors.REFLECTION}📝 反思历程摘要：{Colors.RESET}")
        for i, ref in enumerate(reflections, 1):
            short = ref[:100] + "..." if len(ref) > 100 else ref
            print(f"  {Colors.REFLECTION}  [{i}] {short}{Colors.RESET}")

    print()


# ============================================================
# 运行模式
# ============================================================

def run_demo():
    """
    运行预设测试问题演示。

    选取覆盖不同难度和类别的问题，展示 Reflexion 完整循环。
    """
    from reflexion_agent import ReflexionAgent
    from test_questions import get_demo_questions

    print(f"\n{Colors.HEADER}{'═' * 60}{Colors.RESET}")
    print(f"{Colors.HEADER}  🎯 Reflexion 演示 —— 预设问题{Colors.RESET}")
    print(f"{Colors.HEADER}{'═' * 60}{Colors.RESET}")

    agent = ReflexionAgent(verbose=True)
    demo_questions = get_demo_questions()

    for i, q in enumerate(demo_questions, 1):
        stars = {"easy": "★☆☆", "medium": "★★☆", "hard": "★★★"}[q["difficulty"]]
        print(f"\n\n{'🔥' * 30}")
        print(f"  问题 {i}/{len(demo_questions)} {stars} [{q['category']}]")
        print(f"  {Colors.QUESTION}{q['question']}{Colors.RESET}")
        print(f"  {Colors.DIM}标准答案：{q['ground_truth']}{Colors.RESET}")
        print(f"  {Colors.DIM}设计意图：{q['description']}{Colors.RESET}")
        print(f"{'🔥' * 30}")

        result = agent.run(
            question=q["question"],
            ground_truth=q["ground_truth"],
        )
        print_final_result(result)

        if i < len(demo_questions):
            try:
                input(f"\n  {Colors.DIM}按 Enter 继续下一题...{Colors.RESET}")
            except (EOFError, KeyboardInterrupt):
                print("\n演示中断。")
                break


def run_compare():
    """
    对比模式：同一问题跑"无反思（单轮）" vs "有反思（多轮）"。

    直观展示反思带来的改进效果——
    无反思就是只跑一轮 ReAct，答错了也不重试。
    有反思则可以在错误后调整策略重试。
    """
    from reflexion_agent import ReflexionAgent
    from react_loop import ReactLoop
    from evaluator import get_evaluator
    from test_questions import get_questions_by_difficulty

    print(f"\n{Colors.HEADER}{'═' * 60}{Colors.RESET}")
    print(f"{Colors.HEADER}  🔬 对比实验：无反思 vs 有反思{Colors.RESET}")
    print(f"{Colors.HEADER}{'═' * 60}{Colors.RESET}")

    # 选困难题来对比（更容易看出差异）
    hard_questions = get_questions_by_difficulty("hard")
    # 也加一道中等陷阱题
    from test_questions import get_question_by_id
    trap_q = get_question_by_id("q05")
    compare_questions = [trap_q] + hard_questions[:2] if trap_q else hard_questions[:3]

    evaluator = get_evaluator()
    react_loop = ReactLoop(max_steps=8, verbose=False)
    reflexion_agent = ReflexionAgent(verbose=False)

    results_table = []

    for i, q in enumerate(compare_questions, 1):
        print(f"\n{'─' * 60}")
        print(f"  问题 {i}: {Colors.QUESTION}{q['question']}{Colors.RESET}")
        print(f"  标准答案：{q['ground_truth']}")
        print(f"{'─' * 60}")

        # ── 无反思：单轮 ReAct ──
        print(f"\n  {Colors.DIM}▸ 无反思模式（单轮 ReAct）...{Colors.RESET}")
        no_ref_result = react_loop.run(q["question"])
        no_ref_eval = evaluator.evaluate(
            question=q["question"],
            agent_answer=no_ref_result["answer"],
            ground_truth=q["ground_truth"],
        )

        # ── 有反思：Reflexion 多轮 ──
        print(f"  {Colors.DIM}▸ 有反思模式（Reflexion）...{Colors.RESET}")
        ref_result = reflexion_agent.run(
            question=q["question"],
            ground_truth=q["ground_truth"],
        )

        # 展示对比
        no_ref_status = "✅" if no_ref_eval.is_correct else "❌"
        ref_status = "✅" if ref_result["is_correct"] else "❌"

        print(f"\n  {'无反思':<10} {no_ref_status} 答案：{no_ref_result['answer'][:50]}")
        print(f"  {'有反思':<10} {ref_status} 答案：{ref_result['answer'][:50]}（{ref_result['total_trials']}轮）")

        if ref_result.get("reflections"):
            print(f"  {Colors.REFLECTION}反思次数：{len(ref_result['reflections'])}{Colors.RESET}")

        results_table.append({
            "question": q["question"][:30],
            "no_reflection": no_ref_eval.is_correct,
            "with_reflection": ref_result["is_correct"],
            "trials_needed": ref_result["total_trials"],
        })

    # 汇总表
    print(f"\n\n{Colors.HEADER}{'═' * 60}{Colors.RESET}")
    print(f"{Colors.HEADER}  📊 对比汇总{Colors.RESET}")
    print(f"{Colors.HEADER}{'═' * 60}{Colors.RESET}")
    print(f"  {'问题':<32} {'无反思':<8} {'有反思':<8} {'轮数':<6}")
    print(f"  {'─' * 54}")
    for r in results_table:
        s1 = "✅" if r["no_reflection"] else "❌"
        s2 = "✅" if r["with_reflection"] else "❌"
        print(f"  {r['question']:<30} {s1:<8} {s2:<8} {r['trials_needed']:<6}")

    no_ref_correct = sum(1 for r in results_table if r["no_reflection"])
    ref_correct = sum(1 for r in results_table if r["with_reflection"])
    total = len(results_table)
    print(f"\n  正确率：无反思 {no_ref_correct}/{total} vs 有反思 {ref_correct}/{total}")
    print()


def run_interactive():
    """交互式模式：自由提问。"""
    from reflexion_agent import ReflexionAgent
    from test_questions import TEST_QUESTIONS

    agent = ReflexionAgent(verbose=True)

    while True:
        try:
            user_input = input(f"{Colors.QUESTION}❓ 你的问题（或输入题号如 q01）：{Colors.RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue

        if user_input.lower() == "exit":
            print("再见！")
            break

        if user_input.lower() == "list":
            print(f"\n  {'ID':<5} {'难度':<5} {'类别':<10} {'问题'}")
            print(f"  {'─' * 60}")
            for q in TEST_QUESTIONS:
                stars = {"easy": "★☆☆", "medium": "★★☆", "hard": "★★★"}[q["difficulty"]]
                print(f"  {q['id']:<5} {stars:<5} {q['category']:<10} {q['question']}")
            print()
            continue

        # 检查是否是题号
        question = user_input
        ground_truth = None

        if user_input.lower().startswith("q"):
            from test_questions import get_question_by_id
            test_q = get_question_by_id(user_input.lower())
            if test_q:
                question = test_q["question"]
                ground_truth = test_q["ground_truth"]
                print(f"  {Colors.DIM}问题：{question}{Colors.RESET}")
                print(f"  {Colors.DIM}标准答案：{ground_truth}{Colors.RESET}")
            else:
                print(f"  {Colors.ERROR}未找到题号 {user_input}{Colors.RESET}")
                continue
        else:
            # 自由提问时，询问标准答案（可选）
            gt_input = input(f"  {Colors.DIM}标准答案（可选，直接回车跳过）：{Colors.RESET}").strip()
            if gt_input:
                ground_truth = gt_input

        print(f"\n{Colors.HEADER}  开始 Reflexion 循环...{Colors.RESET}")
        result = agent.run(question=question, ground_truth=ground_truth)
        print_final_result(result)


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    print_header()

    if "--demo" in sys.argv:
        run_demo()
    elif "--compare" in sys.argv:
        run_compare()
    else:
        run_interactive()
