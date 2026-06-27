"""
03-react-agent 入口 —— 双模式切换 + 推理链可视化
================================================================

通过 AGENT_MODE 环境变量在两种模式间切换：
    - react（默认）：ReAct 模式，显式推理链（Thought/Action/Observation）
    - direct：直接工具调用模式（对照组，01/02 风格的 Function Calling）

用同一个问题跑两种模式，直观对比"有推理过程"和"没推理过程"的区别。
"""

import os
import json
from dotenv import load_dotenv

# 必须最先加载 .env（02 踩过的坑：晚于 import 就读不到）
load_dotenv()


# ============================================================
# ANSI 颜色定义 —— 让推理链在终端里一目了然
# ============================================================

class Colors:
    """终端颜色，用于推理链可视化。"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # ReAct 三要素各用一种颜色
    THOUGHT = "\033[36m"   # 青色 —— 思考
    ACTION = "\033[33m"    # 黄色 —— 行动
    OBSERVATION = "\033[32m"  # 绿色 —— 观察

    # 其他
    QUESTION = "\033[35m"  # 紫色 —— 用户问题
    ANSWER = "\033[34m"    # 蓝色 —— 最终答案
    ERROR = "\033[31m"     # 红色 —— 错误
    HEADER = "\033[37;1m"  # 白色粗体 —— 标题


def print_header():
    """打印启动信息。"""
    mode = os.environ.get("AGENT_MODE", "react").lower().strip()
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    print(f"\n{Colors.HEADER}{'═' * 60}{Colors.RESET}")
    print(f"{Colors.HEADER}  03-react-agent —— ReAct 推理链学习项目{Colors.RESET}")
    print(f"{Colors.HEADER}{'═' * 60}{Colors.RESET}")
    print(f"  模式：{Colors.BOLD}{mode.upper()}{Colors.RESET}")
    print(f"  模型：{model}")
    print(f"  输入 'exit' 退出 | 'switch' 切换模式 | 'compare' 双模式对比")
    print(f"{Colors.HEADER}{'═' * 60}{Colors.RESET}\n")


def print_react_result(result: dict):
    """
    彩色打印 ReAct 模式的推理链。

    这是 03 的核心学习输出——让推理过程可视化，
    能清晰看到 LM 每一步"在想什么→做了什么→看到了什么"。
    """
    print(f"\n{Colors.HEADER}{'─' * 60}{Colors.RESET}")
    print(f"{Colors.HEADER}  📋 ReAct 推理链回放{Colors.RESET}")
    print(f"{Colors.HEADER}{'─' * 60}{Colors.RESET}")

    for step in result["steps"]:
        step_num = step["step"]
        print(f"\n  {Colors.DIM}[Step {step_num}]{Colors.RESET}")

        if step.get("thought"):
            print(f"  {Colors.THOUGHT}💭 Thought: {step['thought']}{Colors.RESET}")

        if step.get("action"):
            action_input = step.get("action_input", "")
            print(f"  {Colors.ACTION}🔧 Action: {step['action']}[{action_input}]{Colors.RESET}")

        if step.get("observation"):
            obs = step["observation"]
            # 长结果截断显示
            if len(obs) > 200:
                obs = obs[:200] + "..."
            print(f"  {Colors.OBSERVATION}👁️ Observation: {obs}{Colors.RESET}")

        if step.get("error"):
            print(f"  {Colors.ERROR}❌ Error: {step['error']}{Colors.RESET}")

    print(f"\n  {Colors.HEADER}{'─' * 40}{Colors.RESET}")
    print(f"  {Colors.ANSWER}✅ Final Answer: {result['answer']}{Colors.RESET}")
    print(f"  {Colors.DIM}总步数: {result['total_steps']} | 终止: {result['terminated_by']}{Colors.RESET}")


def print_direct_result(result: dict):
    """打印 Direct 模式的调用链。"""
    print(f"\n{Colors.HEADER}{'─' * 60}{Colors.RESET}")
    print(f"{Colors.HEADER}  📋 Direct 模式调用链{Colors.RESET}")
    print(f"{Colors.HEADER}{'─' * 60}{Colors.RESET}")

    for step in result["steps"]:
        step_num = step["step"]
        if step.get("action"):
            action_input = json.dumps(step["action_input"], ensure_ascii=False) if step["action_input"] else ""
            print(f"  {Colors.DIM}[Step {step_num}]{Colors.RESET} "
                  f"{Colors.ACTION}🔧 {step['action']}({action_input}){Colors.RESET}")
            if step.get("observation"):
                obs = step["observation"]
                if len(obs) > 100:
                    obs = obs[:100] + "..."
                print(f"           {Colors.OBSERVATION}→ {obs}{Colors.RESET}")

    print(f"\n  {Colors.HEADER}{'─' * 40}{Colors.RESET}")
    print(f"  {Colors.ANSWER}✅ Final Answer: {result['answer']}{Colors.RESET}")
    print(f"  {Colors.DIM}总步数: {result['total_steps']} | 终止: {result['terminated_by']}{Colors.RESET}")


def compare_mode(question: str):
    """
    双模式对比：同一个问题分别跑 ReAct 和 Direct，并排展示。

    这是 03 最有学习价值的功能——同一输入、同一工具集，
    只是"有没有显式推理"的区别，直观看到差异。
    """
    from react_agent import ReactAgent
    from direct_agent import DirectAgent

    print(f"\n{Colors.HEADER}{'═' * 60}{Colors.RESET}")
    print(f"{Colors.HEADER}  🔬 双模式对比实验{Colors.RESET}")
    print(f"{Colors.QUESTION}  问题：{question}{Colors.RESET}")
    print(f"{Colors.HEADER}{'═' * 60}{Colors.RESET}")

    # 运行 ReAct
    print(f"\n{Colors.HEADER}  ▸ ReAct 模式{Colors.RESET}")
    react_agent = ReactAgent(max_steps=10, verbose=False)
    react_result = react_agent.run(question)
    print_react_result(react_result)

    # 运行 Direct
    print(f"\n\n{Colors.HEADER}  ▸ Direct 模式{Colors.RESET}")
    direct_agent = DirectAgent(max_steps=10, verbose=False)
    direct_result = direct_agent.run(question)
    print_direct_result(direct_result)

    # 汇总对比
    print(f"\n{Colors.HEADER}{'═' * 60}{Colors.RESET}")
    print(f"{Colors.HEADER}  📊 对比总结{Colors.RESET}")
    print(f"{Colors.HEADER}{'═' * 60}{Colors.RESET}")
    print(f"              {'ReAct':<20}{'Direct':<20}")
    print(f"  步数        {react_result['total_steps']:<20}{direct_result['total_steps']:<20}")
    print(f"  终止原因    {react_result['terminated_by']:<20}{direct_result['terminated_by']:<20}")
    print(f"  推理可见    {'✅ 有 Thought':<20}{'❌ 黑盒':<20}")
    print()


def run_interactive():
    """交互式主循环。"""
    mode = os.environ.get("AGENT_MODE", "react").lower().strip()

    # 延迟导入，避免两个 agent 都加载
    agent = None

    while True:
        try:
            user_input = input(f"{Colors.QUESTION}❓ 你的问题：{Colors.RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue

        if user_input.lower() == "exit":
            print("再见！")
            break

        if user_input.lower() == "switch":
            mode = "direct" if mode == "react" else "react"
            agent = None  # 重新加载
            print(f"  已切换到 {Colors.BOLD}{mode.upper()}{Colors.RESET} 模式\n")
            continue

        if user_input.lower().startswith("compare"):
            # compare 后面可以跟问题，也可以不跟（用默认问题）
            question = user_input[7:].strip()
            if not question:
                question = "星辰王国的面积是月影王国的多少倍？"
            compare_mode(question)
            continue

        # 按当前模式运行
        if agent is None:
            if mode == "react":
                from react_agent import ReactAgent
                agent = ReactAgent(max_steps=10, verbose=True)
            else:
                from direct_agent import DirectAgent
                agent = DirectAgent(max_steps=10, verbose=True)

        result = agent.run(user_input)

        # 打印结果
        if mode == "react":
            print_react_result(result)
        else:
            print_direct_result(result)

        print()


# ============================================================
# 测试用的预设问题（方便跑验证）
# ============================================================

DEMO_QUESTIONS = [
    # 单步：直接查一个字段
    "星辰王国的国王是谁？",
    # 两步：查面积 + 算比值
    "星辰王国的面积是月影王国的多少倍？",
    # 三步：查国王→查导师→查居住地（链式推理经典场景）
    "星辰王国国王的导师现在住在哪里？",
    # 比较：两个实体同一字段
    "艾瑞克三世和塞琳娜女王谁年龄更大？大多少岁？",
    # 多步混合：查+算+推理
    "翡翠联邦的人口密度（人口/面积）是多少？和星辰王国比谁更密集？",
]


def run_demo():
    """运行预设问题演示。"""
    from react_agent import ReactAgent

    print(f"\n{Colors.HEADER}{'═' * 60}{Colors.RESET}")
    print(f"{Colors.HEADER}  🎯 ReAct 演示 —— 预设问题{Colors.RESET}")
    print(f"{Colors.HEADER}{'═' * 60}{Colors.RESET}")

    agent = ReactAgent(max_steps=10, verbose=True)

    for i, q in enumerate(DEMO_QUESTIONS, 1):
        print(f"\n\n{'🔥' * 30}")
        print(f"  问题 {i}/{len(DEMO_QUESTIONS)}: {q}")
        print(f"{'🔥' * 30}")

        result = agent.run(q)
        print_react_result(result)

        if i < len(DEMO_QUESTIONS):
            try:
                input(f"\n  {Colors.DIM}按 Enter 继续下一题...{Colors.RESET}")
            except (EOFError, KeyboardInterrupt):
                print("\n演示中断。")
                break


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    import sys

    print_header()

    if "--demo" in sys.argv:
        run_demo()
    elif "--compare" in sys.argv:
        # 可指定问题：python main.py --compare "问题"
        question = sys.argv[sys.argv.index("--compare") + 1] if len(sys.argv) > sys.argv.index("--compare") + 1 else DEMO_QUESTIONS[1]
        compare_mode(question)
    else:
        run_interactive()
