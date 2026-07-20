"""
主程序 —— 工作流编排引擎演示
==========================

CLI 模式：
- --demo: 运行预定义的 5 任务工作流
- --interactive: 用户自定义工作流
- --visualize: 只展示 DAG 结构，不执行
"""

import argparse
import os
from dotenv import load_dotenv
from openai import OpenAI

from workflow import Workflow
from display import (
    print_workflow_dag,
    print_execution_progress,
    make_task_callbacks,
    print_results_summary,
    visualize_workflow,
)


# ============================================================
# 初始化
# ============================================================

def init_client():
    """初始化 OpenAI 客户端。"""
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        raise ValueError("缺少 OPENAI_API_KEY 环境变量")

    client = OpenAI(api_key=api_key, base_url=base_url)
    return client, model


# ============================================================
# Demo 模式：预定义工作流
# ============================================================

def run_demo():
    """运行预定义的 5 任务工作流。"""
    print("\n🚀 星际研究站建设工作流 - Demo 模式\n")

    client, model = init_client()

    # 创建工作流
    workflow = Workflow("建设蓝晶星研究站")

    # 添加任务（按依赖关系）
    t1 = workflow.add_task(
        name="地质勘探",
        agent_role="geologist",
        description="分析蓝晶星的地质数据，评估建设可行性",
    )

    t2 = workflow.add_task(
        name="选址分析",
        agent_role="architect",
        description="基于地质报告，选择最佳建设区域",
        depends_on=[t1],
    )

    t3 = workflow.add_task(
        name="基础建设",
        agent_role="engineer",
        description="规划基础设施建设方案",
        depends_on=[t2],
    )

    t4 = workflow.add_task(
        name="能源系统",
        agent_role="energy_specialist",
        description="设计研究站能源系统",
        depends_on=[t3],
    )

    t5 = workflow.add_task(
        name="生命支持",
        agent_role="life_support_specialist",
        description="配置生命支持系统",
        depends_on=[t4],
    )

    # 展示工作流结构
    print_workflow_dag(workflow)

    # 执行工作流
    print("🔄 开始执行工作流...\n")

    on_task_start, on_task_complete = make_task_callbacks()

    try:
        results = workflow.run(
            client=client,
            model=model,
            on_task_start=on_task_start,
            on_task_complete=on_task_complete,
        )

        # 打印结果汇总
        print_results_summary(workflow)

        print("✅ 工作流执行成功！")

    except Exception as e:
        print(f"\n❌ 工作流执行失败: {e}")
        print_execution_progress(workflow)


# ============================================================
# Interactive 模式：用户自定义工作流
# ============================================================

def run_interactive():
    """交互式模式：用户自定义工作流。"""
    print("\n🛠️ 星际研究站建设工作流 - 交互模式\n")
    print("可用的 Agent 角色：")
    print("  1. geologist       - 地质学家")
    print("  2. architect       - 建筑师")
    print("  3. engineer        - 工程师")
    print("  4. energy_specialist - 能源专家")
    print("  5. life_support_specialist - 生命支持专家")
    print()

    client, model = init_client()

    # 创建工作流
    workflow_name = input("工作流名称: ").strip() or "自定义工作流"
    workflow = Workflow(workflow_name)

    tasks = {}

    print("\n添加任务（输入空行结束）：")
    while True:
        task_name = input("\n任务名称: ").strip()
        if not task_name:
            break

        agent_role = input("Agent 角色 (如 geologist): ").strip()
        if agent_role not in ["geologist", "architect", "engineer", "energy_specialist", "life_support_specialist"]:
            print(f"  ⚠️  未知角色 '{agent_role}'，跳过")
            continue

        description = input("任务描述（可选）: ").strip() or task_name

        depends_on_input = input("依赖任务（用逗号分隔，可选）: ").strip()
        depends_on = []
        if depends_on_input:
            dep_names = [name.strip() for name in depends_on_input.split(",")]
            for dep_name in dep_names:
                if dep_name in tasks:
                    depends_on.append(tasks[dep_name])
                else:
                    print(f"  ⚠️  未知依赖 '{dep_name}'，忽略")

        task = workflow.add_task(task_name, agent_role, description, depends_on)
        tasks[task_name] = task
        print(f"  ✓ 任务 '{task_name}' 已添加")

    if not workflow.tasks:
        print("\n❌ 没有添加任何任务，退出。")
        return

    # 展示工作流结构
    print_workflow_dag(workflow)

    # 确认执行
    confirm = input("\n是否执行工作流？(y/n): ").strip().lower()
    if confirm != "y":
        print("已取消执行。")
        return

    # 执行工作流
    print("\n🔄 开始执行工作流...\n")

    on_task_start, on_task_complete = make_task_callbacks()

    try:
        results = workflow.run(
            client=client,
            model=model,
            on_task_start=on_task_start,
            on_task_complete=on_task_complete,
        )

        # 打印结果汇总
        print_results_summary(workflow)

        print("✅ 工作流执行成功！")

    except Exception as e:
        print(f"\n❌ 工作流执行失败: {e}")
        print_execution_progress(workflow)


# ============================================================
# Visualize 模式：只展示结构
# ============================================================

def run_visualize():
    """可视化模式：只展示预定义工作流的 DAG 结构。"""
    print("\n📊 星际研究站建设工作流 - 可视化模式\n")

    # 创建工作流（不执行）
    workflow = Workflow("建设蓝晶星研究站")

    t1 = workflow.add_task("地质勘探", "geologist", "分析蓝晶星的地质数据")
    t2 = workflow.add_task("选址分析", "architect", "选择最佳建设区域", depends_on=[t1])
    t3 = workflow.add_task("基础建设", "engineer", "规划基础设施", depends_on=[t2])
    t4 = workflow.add_task("能源系统", "energy_specialist", "设计能源系统", depends_on=[t3])
    t5 = workflow.add_task("生命支持", "life_support_specialist", "配置生命支持", depends_on=[t4])

    # 可视化
    visualize_workflow(workflow)


# ============================================================
# 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="工作流编排引擎 - 星际研究站建设")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="运行预定义的 5 任务工作流",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="交互式模式：用户自定义工作流",
    )
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="可视化模式：只展示 DAG 结构，不执行",
    )

    args = parser.parse_args()

    if args.demo:
        run_demo()
    elif args.interactive:
        run_interactive()
    elif args.visualize:
        run_visualize()
    else:
        # 默认运行 demo
        run_demo()


if __name__ == "__main__":
    main()
