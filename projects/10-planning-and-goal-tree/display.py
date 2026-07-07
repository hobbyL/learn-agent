"""
展示模块 —— ASCII 目标树可视化 + ANSI 着色
============================================

把 GoalTree 的运行时状态渲染成终端可读的目标树，并统一负责规划 Agent
过程中的所有视觉输出（头部 / 子任务 ReAct 执行 / 重规划事件 / 收尾汇总）。

设计原则（对齐 06-streaming-react/display.py）：
- 只依赖 goal_tree 暴露的纯数据（to_display_rows / get_progress），
  不 import planner_agent，避免循环依赖。
- ANSI 颜色码只用于"上色"，不参与宽度对齐计算（见 09 notes.md 的踩坑：
  ANSI 码会被计入字符串宽度导致列错乱）。因此对齐用的缩进全部由纯文本构成，
  颜色码只在最后拼接到已排好版的文本两侧。

状态配色（对齐 PRD）：
    pending  ○ 灰    ready  ◎ 青    running ▶ 黄
    done     ✓ 绿    failed ✗ 红    skipped ⊘ 紫（被重规划替换的废弃分支）
"""

from goal_tree import GoalTree


# ============================================================
# ANSI 颜色定义（沿用项目约定）
# ============================================================

class Colors:
    """ANSI 转义码集合。用类命名空间收敛，避免散落的裸字符串。"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    GRAY = "\033[90m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    BRIGHT_WHITE = "\033[97m"


# 状态 → (图标, 颜色) 映射。
# 键用 TaskStatus.value（字符串），这样 display 无需 import 枚举本身。
_STATUS_STYLE: dict[str, tuple[str, str]] = {
    "pending":   ("○", Colors.GRAY),
    "ready":     ("◎", Colors.CYAN),
    "running":   ("▶", Colors.YELLOW),
    "done":      ("✓", Colors.GREEN),
    "failed":    ("✗", Colors.RED),
    "skipped":   ("⊘", Colors.MAGENTA),
    "replanned": ("↻", Colors.MAGENTA),  # 兜底：当前 GoalTree 用 skipped 表达，保留以防扩展
}


def _style_for(status: str) -> tuple[str, str]:
    """返回状态对应的 (图标, 颜色)，未知状态回退为灰点。"""
    return _STATUS_STYLE.get(status, ("·", Colors.GRAY))


# ============================================================
# 目标树渲染
# ============================================================

def _tree_prefix(depth: int, is_last: bool) -> str:
    """
    生成某一行的树形前缀（纯文本，不含颜色）。

    depth 来自 GoalTree._compute_depths（最长依赖链长度）：
        depth=0 的是"根"（无前置），不加连接符。
        depth>0 的用 │ 维持父层竖线，末端用 └─，中间用 ├─。

    注意：这是 DAG 被拓扑序压平后的近似树形——同一 depth 的节点
    可能来自不同分支，这里以"缩进 + 连接符"给出层级直觉，而非严格父子边。
    真正的跨分支依赖用每行后面的 "← deps" 标注补全。
    """
    if depth <= 0:
        return ""
    guide = f"{Colors.DIM}│{Colors.RESET}  " * (depth - 1)
    connector = "└─ " if is_last else "├─ "
    return guide + f"{Colors.DIM}{connector}{Colors.RESET}"


def _render_progress_bar(progress: dict, width: int = 24) -> str:
    """
    用 get_progress() 的统计画一条进度条。

    进度条按 done 占比填充；后面追加各状态计数，失败/跳过非零时着色提示。
    """
    total = max(progress["total"], 1)
    done = progress["done"]
    filled = int(width * done / total)
    bar = (
        f"{Colors.GREEN}{'█' * filled}{Colors.RESET}"
        f"{Colors.GRAY}{'░' * (width - filled)}{Colors.RESET}"
    )

    parts = [f"{Colors.GREEN}完成 {done}{Colors.RESET}"]
    if progress["running"]:
        parts.append(f"{Colors.YELLOW}进行 {progress['running']}{Colors.RESET}")
    if progress["failed"]:
        parts.append(f"{Colors.RED}失败 {progress['failed']}{Colors.RESET}")
    if progress["skipped"]:
        parts.append(f"{Colors.MAGENTA}跳过 {progress['skipped']}{Colors.RESET}")
    parts.append(f"{Colors.GRAY}待办 {progress['pending']}{Colors.RESET}")

    return f"{bar} {done}/{total}  " + "  ".join(parts)


def print_goal_tree(tree: GoalTree, title: str = "目标树") -> None:
    """
    打印完整目标树（ASCII 树 + 依赖箭头 + 状态着色）+ 进度条。

    数据来源：
        tree.to_display_rows() → [{id, name, status, depends_on, depth, target_module}]
        tree.get_progress()    → {total, done, failed, running, pending, skipped}

    渲染顺序即拓扑序，缩进由 depth 决定。
    """
    rows = tree.to_display_rows()

    print(f"\n{Colors.BOLD}{Colors.CYAN}┌─ {title}{Colors.RESET}")
    if tree.goal:
        print(f"{Colors.DIM}│  🎯 {tree.goal}{Colors.RESET}")

    for i, row in enumerate(rows):
        depth = row["depth"]
        # 判断是否是该缩进块的末端：下一行 depth 更浅（或没有下一行）
        is_last = (i == len(rows) - 1) or (rows[i + 1]["depth"] < depth)
        prefix = _tree_prefix(depth, is_last)

        icon, color = _style_for(row["status"])
        # 依赖箭头标注（跨分支依赖靠这个补全，弥补压平树的信息损失）
        deps = row["depends_on"]
        dep_text = (
            f"  {Colors.DIM}← {', '.join(deps)}{Colors.RESET}" if deps else ""
        )
        module = row["target_module"]
        module_text = (
            f"  {Colors.DIM}[{module}]{Colors.RESET}" if module and module != "无" else ""
        )

        print(
            f"{Colors.DIM}│{Colors.RESET}  {prefix}"
            f"{color}{icon} {row['id']} {row['name']}{Colors.RESET}"
            f"{module_text}{dep_text}"
        )

    progress = tree.get_progress()
    print(f"{Colors.DIM}│{Colors.RESET}")
    print(f"{Colors.DIM}│  {Colors.RESET}{_render_progress_bar(progress)}")
    print(f"{Colors.BOLD}{Colors.CYAN}└{'─' * 40}{Colors.RESET}")


# ============================================================
# 头部 / 收尾
# ============================================================

def print_plan_header(goal: str) -> None:
    """打印本次规划任务的头部（高层目标）。"""
    print(f"\n{Colors.BOLD}{Colors.BRIGHT_WHITE}{'═' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_WHITE}🛰  新曙光基地 · 任务规划 Agent{Colors.RESET}")
    print(f"{Colors.BOLD}{'═' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}🎯 建设目标：{Colors.RESET}{goal}")
    print(f"{Colors.DIM}   规划模式：混合（初始全计划 + 执行中动态展开），"
          f"失败触发局部重规划{Colors.RESET}")


def print_planning_start(goal: str) -> None:
    """LLM 初始规划开始前的提示（规划调用可能较慢，给用户反馈）。"""
    print(f"\n{Colors.CYAN}🧭 正在为目标生成子任务 DAG：{goal}{Colors.RESET}")


def print_final_summary(result: dict) -> None:
    """
    打印收尾汇总。

    result 为 PlanningAgent.run() 的返回结构：
        {goal, goal_tree, execution_log, replan_count, replan_history,
         success, terminated_by, ...}
    """
    success = result["success"]
    replan_count = result["replan_count"]
    terminated_by = result["terminated_by"]
    exec_count = len(result["execution_log"])

    print(f"\n{Colors.BOLD}{'═' * 60}{Colors.RESET}")
    if success:
        print(f"{Colors.BOLD}{Colors.GREEN}🎉 目标达成！{Colors.RESET}")
    else:
        print(f"{Colors.BOLD}{Colors.RED}🛑 未完全达成目标{Colors.RESET}")
    print(f"{Colors.BOLD}{'═' * 60}{Colors.RESET}")

    term_labels = {
        "all_done": "所有子任务完成",
        "max_replans": "达到最大重规划次数",
        "safeguard": "触发兜底保护（无法继续推进）",
    }
    term_text = term_labels.get(terminated_by, terminated_by)

    print(f"  执行子任务：{Colors.BOLD}{exec_count}{Colors.RESET} 次")
    print(f"  局部重规划：{Colors.BOLD}{replan_count}{Colors.RESET} 次")
    print(f"  终止原因：  {term_text}")

    # 收尾再打一次最终目标树，直观展示所有状态变化的落点
    print_goal_tree(result["goal_tree"], "最终目标树")


# ============================================================
# 子任务 ReAct 执行过程（沿用 06 的 Thought/Action/Observation 分色）
# ============================================================

def print_subtask_execution(subtask_name: str, exec_result: dict) -> None:
    """
    展示单个子任务的内层 ReAct 执行过程。

    exec_result 为 executor.execute_subtask 的返回结构：
        {success, subtask_id, steps:[{step, thought, action, action_input, observation}],
         final_message, failure_reason}

    分色约定（对齐 06-streaming-react）：
        Thought 灰 / Action 黄 / Action Input 黄 / Observation 绿 /
        report_result 收尾按成败绿或红。
    """
    subtask_id = exec_result.get("subtask_id", "?")
    steps = exec_result.get("steps", [])

    print(f"\n{Colors.BOLD}{Colors.BLUE}▷ 执行子任务 [{subtask_id}] {subtask_name}{Colors.RESET}")

    for step in steps:
        thought = (step.get("thought") or "").strip()
        action = step.get("action")
        action_input = step.get("action_input")
        observation = step.get("observation")

        if thought:
            print(f"  {Colors.GRAY}🧠 Thought: {thought}{Colors.RESET}")

        # 收尾工具单独高亮
        if action == "report_result":
            success = bool(action_input.get("success")) if isinstance(action_input, dict) else False
            reason = action_input.get("reason", "") if isinstance(action_input, dict) else ""
            if success:
                print(f"  {Colors.GREEN}🏁 report_result → 成功：{reason}{Colors.RESET}")
            else:
                print(f"  {Colors.RED}🏁 report_result → 失败：{reason}{Colors.RESET}")
            continue

        if action:
            arg_text = _fmt_args(action_input)
            print(f"  {Colors.YELLOW}⚡ Action: {action}{arg_text}{Colors.RESET}")
        if observation is not None:
            print(f"  {Colors.GREEN}👁 Observation: {observation}{Colors.RESET}")

    # 若步骤里没有 report_result（自然语言收尾或超步数），补一行结果
    has_report = any(s.get("action") == "report_result" for s in steps)
    if not has_report:
        if exec_result.get("success"):
            print(f"  {Colors.GREEN}🏁 结果：成功 —— "
                  f"{exec_result.get('final_message', '')}{Colors.RESET}")
        else:
            print(f"  {Colors.RED}🏁 结果：失败 —— "
                  f"{exec_result.get('failure_reason') or exec_result.get('final_message', '')}"
                  f"{Colors.RESET}")


def _fmt_args(action_input) -> str:
    """把工具参数格式化为紧凑可读文本，如 (module=居住舱)。"""
    if not isinstance(action_input, dict) or not action_input:
        return ""
    inner = ", ".join(f"{k}={v}" for k, v in action_input.items())
    return f"({inner})"


# ============================================================
# 重规划事件
# ============================================================

def print_replan_event(
    failed_task_name: str,
    failure_reason: str,
    analysis: str = "",
    affected_ids: list | None = None,
    replacement_ids: list | None = None,
    replan_index: int | None = None,
) -> None:
    """
    高亮展示一次局部重规划事件。

    对应 PlanningAgent.run() 主循环失败分支：某子任务失败后，
    规划器给出影响范围（affected_ids）与替换子任务（replacement_ids）。
    """
    affected_ids = affected_ids or []
    replacement_ids = replacement_ids or []

    idx_text = f" #{replan_index}" if replan_index is not None else ""
    print(f"\n{Colors.BOLD}{Colors.MAGENTA}╭─ ↻ 局部重规划{idx_text}{Colors.RESET}")
    print(f"{Colors.MAGENTA}│  失败任务：{failed_task_name}{Colors.RESET}")
    print(f"{Colors.RED}│  失败原因：{failure_reason}{Colors.RESET}")
    if analysis:
        print(f"{Colors.MAGENTA}│  根因分析：{analysis}{Colors.RESET}")
    print(f"{Colors.MAGENTA}│  受影响任务：{Colors.RESET}"
          f"{', '.join(affected_ids) if affected_ids else '（无）'}")
    print(f"{Colors.MAGENTA}│  替换为新任务：{Colors.RESET}"
          f"{', '.join(replacement_ids) if replacement_ids else '（无）'}")
    print(f"{Colors.BOLD}{Colors.MAGENTA}╰{'─' * 40}{Colors.RESET}")


# ============================================================
# 通用信息 / 错误
# ============================================================

def print_info(msg: str) -> None:
    """灰色提示信息。"""
    print(f"{Colors.GRAY}ℹ  {msg}{Colors.RESET}")


def print_error(msg: str) -> None:
    """红色错误信息（输出到 stderr）。"""
    import sys
    print(f"\n{Colors.RED}❌ 错误：{msg}{Colors.RESET}", file=sys.stderr)


# ============================================================
# 快速验证（不依赖 openai/pydantic，用 mock 节点跑通渲染）
# ============================================================

if __name__ == "__main__":
    from dataclasses import dataclass
    from goal_tree import GoalTree, TaskStatus

    print("=== display 模块渲染验证（mock 数据）===")

    @dataclass
    class MockSubTask:
        id: str
        name: str
        description: str
        depends_on: list
        target_module: str
        estimated_steps: int

    subtasks = [
        MockSubTask("t1", "采集钛矿×6", "从矿区采集钛矿", [], "钛矿", 2),
        MockSubTask("t2", "采集碳纤维×4", "从合成车间调取碳纤维", [], "碳纤维", 1),
        MockSubTask("t3", "建造居住舱", "组装居住舱", ["t1", "t2"], "居住舱", 3),
        MockSubTask("t4", "建造实验室", "在居住舱后建实验室", ["t3"], "实验室", 3),
    ]

    class MockPlan:
        goal = "建造载人基地 Phase-1"
        subtasks = subtasks

    tree = GoalTree(MockPlan())

    # 头部
    print_plan_header(MockPlan.goal)

    # 初始树
    print_goal_tree(tree, "初始目标树")

    # 模拟推进：t1、t2 完成，t3 运行中
    tree.mark_status("t1", TaskStatus.DONE)
    tree.mark_status("t2", TaskStatus.DONE)
    tree.mark_status("t3", TaskStatus.RUNNING)
    print_goal_tree(tree, "执行中目标树")

    # 模拟一次子任务执行记录
    exec_result = {
        "success": True,
        "subtask_id": "t1",
        "steps": [
            {"step": 1, "thought": "先看看库存够不够", "action": "check_inventory",
             "action_input": {}, "observation": "钛矿×4，需要×6，缺口 2"},
            {"step": 2, "thought": "库存不足，去采集", "action": "mine_resource",
             "action_input": {"resource": "钛矿", "amount": 2}, "observation": "采集成功，钛矿×6"},
            {"step": 3, "thought": "已达标，收尾", "action": "report_result",
             "action_input": {"success": True, "reason": "钛矿采集完成，库存充足"},
             "observation": "成功：钛矿采集完成，库存充足"},
        ],
        "final_message": "钛矿采集完成，库存充足",
        "failure_reason": None,
    }
    print_subtask_execution("采集钛矿×6", exec_result)

    # 模拟一次重规划事件
    print_replan_event(
        failed_task_name="建造居住舱",
        failure_reason="太阳风暴，舱外作业被禁止",
        analysis="居住舱是舱外作业，当前环境事件为太阳风暴，需先等待环境恢复",
        affected_ids=["t3"],
        replacement_ids=["r1", "r2"],
        replan_index=1,
    )

    # 收尾汇总
    tree.mark_status("t3", TaskStatus.DONE)
    tree.mark_status("t4", TaskStatus.DONE)
    result = {
        "goal": MockPlan.goal,
        "goal_tree": tree,
        "execution_log": [1, 2, 3, 4],
        "replan_count": 1,
        "replan_history": [],
        "success": True,
        "terminated_by": "all_done",
    }
    print_final_summary(result)

    print("\ndisplay 模块渲染验证通过 ✓")
