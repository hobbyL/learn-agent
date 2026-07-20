"""
可视化展示模块
============

功能：
- ASCII 流程图：展示 DAG 结构
- 执行进度：实时显示任务状态
- 结果汇总：最终输出所有任务结果
"""

from workflow import Workflow, Task, TaskStatus
from agents import get_agent_info


# ============================================================
# ANSI 颜色
# ============================================================

class Color:
    BLUE = "\033[34m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def colorize(text: str, color: str) -> str:
    """给文本添加颜色。"""
    return f"{color}{text}{Color.RESET}"


# ============================================================
# ASCII 流程图
# ============================================================

def print_workflow_dag(workflow: Workflow):
    """打印工作流 DAG 结构。"""
    print(f"\n{colorize('=' * 60, Color.BOLD)}")
    print(colorize(f"工作流：{workflow.name}", Color.BOLD))
    print(colorize('=' * 60, Color.RESET))
    print()

    # 拓扑排序获取执行顺序
    sorted_tasks = workflow.topological_sort()

    # 打印每个任务节点
    for i, task in enumerate(sorted_tasks):
        agent_info = get_agent_info(task.agent_role)

        # 任务节点
        node_text = f"{agent_info['emoji']} {task.name} ({agent_info['name']})"
        print(colorize(node_text, Color.CYAN))

        # 依赖关系
        if task.depends_on:
            dep_names = [f"'{dep.name}'" for dep in task.depends_on]
            deps_text = f"   └─ 依赖: {', '.join(dep_names)}"
            print(colorize(deps_text, Color.BLUE))

        # 箭头（除了最后一个任务）
        if i < len(sorted_tasks) - 1:
            print(colorize("   ↓", Color.BLUE))

    print()


# ============================================================
# 任务状态展示
# ============================================================

def print_task_status(task: Task):
    """打印任务状态（单行）。"""
    agent_info = get_agent_info(task.agent_role)

    # 状态颜色
    status_colors = {
        TaskStatus.PENDING: Color.BLUE,
        TaskStatus.READY: Color.CYAN,
        TaskStatus.RUNNING: Color.YELLOW,
        TaskStatus.COMPLETED: Color.GREEN,
        TaskStatus.FAILED: Color.RED,
    }
    status_color = status_colors.get(task.status, Color.RESET)

    # 状态符号
    status_symbols = {
        TaskStatus.PENDING: "⏸",
        TaskStatus.READY: "⏯",
        TaskStatus.RUNNING: "▶",
        TaskStatus.COMPLETED: "✓",
        TaskStatus.FAILED: "✗",
    }
    status_symbol = status_symbols.get(task.status, "?")

    # 打印
    status_text = f"{status_symbol} {task.status.value.upper()}"
    task_text = f"{agent_info['emoji']} {task.name}"

    print(f"{colorize(status_text, status_color):30s} {task_text}")


def print_execution_progress(workflow: Workflow):
    """打印工作流执行进度。"""
    print(f"\n{colorize('─' * 60, Color.BOLD)}")
    print(colorize("执行进度", Color.BOLD))
    print(colorize('─' * 60, Color.RESET))
    print()

    for task in workflow.tasks:
        print_task_status(task)

    # 统计信息
    summary = workflow.get_status_summary()
    total = len(workflow.tasks)
    completed = summary["completed"]
    progress = f"{completed}/{total}"

    print()
    print(colorize(f"进度：{progress} 任务完成", Color.GREEN if completed == total else Color.YELLOW))
    print()


# ============================================================
# 任务开始/完成回调
# ============================================================

def make_task_callbacks():
    """创建任务回调函数（用于实时展示）。"""

    def on_task_start(task: Task):
        """任务开始回调。"""
        agent_info = get_agent_info(task.agent_role)
        print(f"\n{colorize('─' * 60, Color.YELLOW)}")
        print(colorize(f"▶ 开始任务: {agent_info['emoji']} {task.name}", Color.YELLOW + Color.BOLD))
        print(colorize('─' * 60, Color.RESET))
        print()

    def on_task_complete(task: Task):
        """任务完成回调。"""
        agent_info = get_agent_info(task.agent_role)
        if task.status == TaskStatus.COMPLETED:
            print(f"\n{colorize('─' * 60, Color.GREEN)}")
            print(colorize(f"✓ 完成任务: {agent_info['emoji']} {task.name}", Color.GREEN + Color.BOLD))
            print(colorize('─' * 60, Color.RESET))
            print()
            # 打印结果摘要（前 200 字符）
            if task.result:
                summary = task.result[:200] + "..." if len(task.result) > 200 else task.result
                print(colorize("输出摘要:", Color.CYAN))
                print(summary)
                print()
        else:
            print(f"\n{colorize('─' * 60, Color.RED)}")
            print(colorize(f"✗ 任务失败: {agent_info['emoji']} {task.name}", Color.RED + Color.BOLD))
            print(colorize('─' * 60, Color.RESET))
            print()
            if task.result:
                print(colorize("错误信息:", Color.RED))
                print(task.result)
                print()

    return on_task_start, on_task_complete


# ============================================================
# 结果汇总
# ============================================================

def print_results_summary(workflow: Workflow):
    """打印工作流结果汇总。"""
    print(f"\n{colorize('=' * 60, Color.BOLD)}")
    print(colorize("工作流执行完成 - 结果汇总", Color.BOLD))
    print(colorize('=' * 60, Color.RESET))
    print()

    sorted_tasks = workflow.topological_sort()

    for task in sorted_tasks:
        agent_info = get_agent_info(task.agent_role)

        print(colorize(f"{agent_info['emoji']} {task.name} ({agent_info['name']})", Color.CYAN + Color.BOLD))
        print(colorize('─' * 60, Color.BLUE))

        if task.status == TaskStatus.COMPLETED:
            print(task.result)
        else:
            print(colorize(f"状态: {task.status.value}", Color.RED))
            if task.result:
                print(task.result)

        print()


# ============================================================
# 工作流可视化（只展示结构，不执行）
# ============================================================

def visualize_workflow(workflow: Workflow):
    """可视化工作流结构（不执行）。"""
    print_workflow_dag(workflow)

    # 打印任务详情
    print(colorize("任务详情", Color.BOLD))
    print(colorize('─' * 60, Color.RESET))
    print()

    for task in workflow.tasks:
        agent_info = get_agent_info(task.agent_role)
        print(f"{colorize(task.name, Color.CYAN + Color.BOLD)} - {agent_info['emoji']} {agent_info['name']}")
        if task.description and task.description != task.name:
            print(f"  描述: {task.description}")
        if task.depends_on:
            dep_names = [dep.name for dep in task.depends_on]
            print(f"  依赖: {', '.join(dep_names)}")
        print()
