"""
外层规划 Agent —— Plan → Execute → Re-plan 编排核心
=====================================================

这是把所有部件串起来的主循环，对齐 04-agent-reflection/reflexion_agent.py 的
"外层循环 + 内层执行"结构：
    04：外层 Reflexion（评估→反思→重试）+ 内层 ReAct
    10：外层 Planning（规划→执行→重规划）+ 内层 ReAct（executor）

核心循环（对应 PRD 伪码）：
    plan = generate_plan(goal)          # 初始全计划 → 构建 GoalTree
    while not tree.all_done() and replan_count < max_replans:
        for task in tree.get_ready_tasks():      # 拓扑序取可执行叶子
            result = execute_subtask(task)       # 内层 ReAct 执行
            if result.success:
                tree.mark DONE
                expansion = expand_subtask(...)  # 动态展开判断（可选）
                if needs_expansion: tree.add_subtasks(...)
            else:
                tree.mark FAILED
                replan = replan_subtree(...)     # 局部重规划
                tree.replace_subtree(...)
                replan_count += 1

设计约束：
    - verbose 下把所有过程渲染委托给 display 模块（ASCII 目标树 + 状态着色 +
      子任务 ReAct 执行链 + 重规划事件），本模块只负责编排逻辑与状态数据。
      display 只依赖 goal_tree 的纯数据（to_display_rows/get_progress），不反向依赖本模块，
      因此这里 import display 不会产生循环依赖。
    - 执行前 reset_base_state()，保证每次 run 从干净世界开始。
    - execution_log / replan_history 结构清晰，既供 display 实时渲染，也供调用方复盘。
"""

import os

from dotenv import load_dotenv
from openai import OpenAI

import display
from executor import execute_subtask
from goal_tree import GoalTree, TaskStatus
from knowledge_base import reset_base_state
from planner import expand_subtask, generate_plan, replan_subtree

# load_dotenv 必须在 import 后最先调用（对齐项目约定）
load_dotenv()


class PlanningAgent:
    """
    Plan → Execute → Re-plan 规划 Agent。

    编排 planner（规划）+ executor（执行）+ GoalTree（DAG 状态），
    跑完整的"先规划再执行、失败就局部重规划"流程。
    """

    def __init__(
        self,
        max_replans: int = 3,
        max_steps: int = 8,
        enable_expansion: bool = False,
        client: OpenAI | None = None,
        model: str | None = None,
        verbose: bool = True,
    ):
        """
        参数：
            max_replans     — 最大局部重规划次数（默认 3，避免无限循环）
            max_steps       — 内层 ReAct 每个子任务的最大步数
            enable_expansion— 是否启用动态展开判断（每个成功子任务后额外调一次 LLM，
                              默认关闭以控制 token；--demo 可按需打开演示）
            client/model    — 可注入；不传则从 .env 读取自动构建
            verbose         — 是否打印过程（由 display 模块渲染 ASCII 目标树 + 着色）
        """
        self._max_replans = max_replans
        self._max_steps = max_steps
        self._enable_expansion = enable_expansion
        self._verbose = verbose

        if client is None:
            client, model = self._build_client_from_env(model)
        self._client = client
        self._model = model

        # 防御：外层"总步数"上限，避免 ready 任务反复插入导致的极端死循环。
        # 正常流程有 all_done / max_replans 双重保护，这是最后一道兜底。
        self._max_total_iterations = 200

    @staticmethod
    def _build_client_from_env(model: str | None) -> tuple[OpenAI, str]:
        """从环境变量构建 OpenAI 客户端与模型名（对齐 08/09 的读取方式）。"""
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
        resolved_model = (
            model
            or os.environ.get("OPENAI_MODEL")
            or os.environ.get("MODEL_NAME", "gpt-4o-mini")
        ).strip()

        if not api_key:
            raise ValueError("未找到 OPENAI_API_KEY，请配置 .env 文件")

        client = OpenAI(api_key=api_key, base_url=base_url)
        return client, resolved_model

    # ── 主流程 ──────────────────────────────────────────────

    def run(self, goal: str) -> dict:
        """
        执行完整规划流程。

        参数：
            goal — 高层建设目标

        返回：
            {
                "goal": str,
                "final_plan": Plan,        # 初始计划
                "goal_tree": GoalTree,     # 最终树状态（含所有状态变更）
                "execution_log": [...],    # 每个子任务的执行记录
                "replan_count": int,
                "replan_history": [...],   # 每次重规划的记录
                "success": bool,           # 整体是否达成目标
                "terminated_by": "all_done" | "max_replans" | "safeguard",
            }
        """
        # 1. 干净世界 —— 每次 run 从初始状态开始
        reset_base_state()

        if self._verbose:
            display.print_plan_header(goal)

        # 2. 初始规划 → 构建目标树
        plan = generate_plan(goal, self._client, self._model, verbose=self._verbose)
        tree = GoalTree(plan)

        if self._verbose:
            display.print_goal_tree(tree, "初始目标树")

        execution_log: list[dict] = []
        replan_history: list[dict] = []
        replan_count = 0
        terminated_by = "all_done"
        iterations = 0

        # 3. Plan → Execute → Re-plan 主循环
        while not tree.all_done():
            # 兜底：总迭代上限
            iterations += 1
            if iterations > self._max_total_iterations:
                terminated_by = "safeguard"
                if self._verbose:
                    print("⚠️ 达到总迭代上限，强制终止（可能存在无法推进的死结）")
                break

            ready = tree.get_ready_tasks()
            if not ready:
                # 没有可执行任务但又没全完成：可能被失败/跳过卡住
                if self._verbose:
                    print("⚠️ 无可执行任务且未全部完成，流程停止")
                terminated_by = "safeguard"
                break

            # 取拓扑序最靠前的一个可执行任务
            task = ready[0]
            tree.mark_status(task.id, TaskStatus.RUNNING)

            # ── 内层 ReAct 执行 ──
            result = execute_subtask(
                task,
                self._client,
                self._model,
                max_steps=self._max_steps,
                verbose=False,  # 执行细节交给 display 统一渲染，避免 executor 内部占位打印重复
            )
            if self._verbose:
                display.print_subtask_execution(task.name, result)
            execution_log.append({
                "subtask_id": task.id,
                "name": task.name,
                "success": result["success"],
                "steps": result["steps"],
                "final_message": result["final_message"],
                "failure_reason": result["failure_reason"],
            })

            if result["success"]:
                tree.mark_status(task.id, TaskStatus.DONE)

                # ── 动态展开判断（可选）──
                if self._enable_expansion:
                    expansion = expand_subtask(
                        task, result, self._client, self._model, verbose=self._verbose
                    )
                    if expansion.needs_expansion and expansion.new_subtasks:
                        # parent 变汇聚点：新子任务先执行，parent 依赖它们
                        # （add_subtasks 会把 parent 回退为 PENDING）
                        tree.mark_status(task.id, TaskStatus.PENDING)
                        tree.add_subtasks(expansion.new_subtasks, task.id)
                        if self._verbose:
                            display.print_goal_tree(tree, f"动态展开 {task.id} 后")

            else:
                # ── 失败 → 局部重规划 ──
                tree.mark_status(task.id, TaskStatus.FAILED)

                if replan_count >= self._max_replans:
                    terminated_by = "max_replans"
                    if self._verbose:
                        display.print_info(
                            f"已达最大重规划次数 {self._max_replans}，停止"
                        )
                    break

                replan = replan_subtree(
                    goal,
                    tree,
                    task,
                    result["failure_reason"] or "未说明原因",
                    self._client,
                    self._model,
                    verbose=self._verbose,
                )

                # 确保失败任务本身也在受影响集合里（防 LLM 漏列）
                affected = list(replan.affected_task_ids)
                if task.id not in affected:
                    affected.append(task.id)

                tree.replace_subtree(affected, replan.replacement_subtasks)
                replan_count += 1

                replacement_ids = [
                    getattr(st, "id", "?") for st in replan.replacement_subtasks
                ]
                replan_history.append({
                    "replan_index": replan_count,
                    "failed_task_id": task.id,
                    "failed_task_name": task.name,
                    "failure_reason": result["failure_reason"],
                    "analysis": replan.analysis,
                    "affected_task_ids": affected,
                    "replacement_ids": replacement_ids,
                })

                if self._verbose:
                    display.print_replan_event(
                        failed_task_name=task.name,
                        failure_reason=result["failure_reason"] or "未说明原因",
                        analysis=replan.analysis,
                        affected_ids=affected,
                        replacement_ids=replacement_ids,
                        replan_index=replan_count,
                    )
                    display.print_goal_tree(tree, f"第 {replan_count} 次重规划后")

        # 4. 汇总结果
        success = tree.all_done()

        out = {
            "goal": goal,
            "final_plan": plan,
            "goal_tree": tree,
            "execution_log": execution_log,
            "replan_count": replan_count,
            "replan_history": replan_history,
            "success": success,
            "terminated_by": terminated_by,
        }

        if self._verbose:
            # display.print_final_summary 内部会再打一次"最终目标树"并输出收尾统计
            display.print_final_summary(out)

        return out


# ============================================================
# 快速验证（结构验证，不调真实 API）
# ============================================================

if __name__ == "__main__":
    print("=== PlanningAgent 结构验证（mock LLM）===\n")

    # 用 mock client 跑通一次极简流程：规划返回 2 个子任务，执行全部成功。
    import json as _json

    class _MockToolCall:
        def __init__(self, cid, fname, args):
            self.id = cid
            self.function = type("F", (), {"name": fname, "arguments": _json.dumps(args)})()

    class _MockMsg:
        def __init__(self, content, tool_calls=None, refusal=None):
            self.content = content
            self.tool_calls = tool_calls
            self.refusal = refusal
            self.role = "assistant"

    class _MockChoice:
        def __init__(self, finish_reason, message):
            self.finish_reason = finish_reason
            self.message = message

    class _MockResp:
        def __init__(self, choice):
            self.choices = [choice]

    class _MockCompletions:
        """按调用意图分派：带 response_format 的是规划调用，否则是执行调用。"""
        def __init__(self):
            self._exec_turn = 0

        def create(self, **kwargs):
            # 规划调用（json_schema 强制模式）
            if "response_format" in kwargs:
                plan_json = _json.dumps({
                    "goal": "建造储物仓",
                    "reasoning": "储物仓无前置、资源充足，直接建造即可。",
                    "subtasks": [
                        {
                            "id": "t1",
                            "name": "建造储物仓",
                            "description": "用现有资源建造储物仓",
                            "depends_on": [],
                            "target_module": "储物仓",
                            "estimated_steps": 2,
                        }
                    ],
                })
                return _MockResp(_MockChoice("stop", _MockMsg(plan_json)))

            # 执行调用（Function Calling）
            self._exec_turn += 1
            if self._exec_turn == 1:
                mc = _MockMsg("建造储物仓", [_MockToolCall("c1", "build_module", {"module": "储物仓"})])
                return _MockResp(_MockChoice("tool_calls", mc))
            mc = _MockMsg("", [_MockToolCall("c2", "report_result", {"success": True, "reason": "储物仓建成"})])
            return _MockResp(_MockChoice("tool_calls", mc))

    class _MockClient:
        def __init__(self):
            self.chat = type("C", (), {"completions": _MockCompletions()})()

    agent = PlanningAgent(
        max_replans=3,
        max_steps=5,
        enable_expansion=False,
        client=_MockClient(),
        model="mock-model",
        verbose=True,
    )
    out = agent.run("建造储物仓")

    print(f"\n结果 success={out['success']}, terminated_by={out['terminated_by']}")
    print(f"execution_log 条数={len(out['execution_log'])}, replan_count={out['replan_count']}")

    print("\nPlanningAgent 结构验证通过 ✓")
