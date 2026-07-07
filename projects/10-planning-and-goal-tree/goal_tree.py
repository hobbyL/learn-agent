"""
目标树 GoalTree —— 运行时 DAG 数据结构 + 拓扑排序 + 状态管理
=============================================================

这是执行引擎的核心数据结构，负责管理子任务 DAG 的运行时状态：
    - 从 schemas.Plan 构建（也接受任何带 .subtasks 的对象或 SubTask 列表）
    - 按依赖关系做拓扑排序（Kahn 算法，检测环）
    - 追踪每个节点的状态（pending / ready / running / done / failed / skipped）
    - 支持动态展开（add_subtasks）和局部重规划（replace_subtree）

设计原则：纯 Python，不依赖 openai/pydantic。
    只依赖节点对象暴露的属性（id / name / depends_on），
    这样单元测试可以用最简单的 mock 节点跑通，无需真跑 LLM。

为什么依赖用 depends_on 扁平表达而非嵌套树？
    见 schemas.py 的说明——扁平列表能表达跨分支依赖（t5 同时依赖 t2、t3），
    而嵌套树只能表达父子层级。GoalTree 在这基础上做拓扑排序即可。
"""

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ============================================================
# 任务状态枚举
# ============================================================

class TaskStatus(str, Enum):
    """
    子任务生命周期状态。

    继承 str 是为了 JSON 序列化和 display 层拼接时更方便
    （TaskStatus.DONE == "done" 直接成立）。
    """
    PENDING = "pending"     # 待执行（依赖未满足或未轮到）
    READY = "ready"         # 依赖已满足，可执行
    RUNNING = "running"     # 执行中
    DONE = "done"           # 已完成
    FAILED = "failed"       # 执行失败
    SKIPPED = "skipped"     # 因重规划被跳过/替换


# ============================================================
# 运行时节点
# ============================================================

@dataclass
class TaskNode:
    """
    运行时子任务节点。

    从 SubTask（Pydantic）拷贝核心字段而来，额外维护可变的 status。
    我们不直接持有 Pydantic 对象，是为了让 GoalTree 保持"纯 Python、可独立测试"，
    也避免执行过程中意外污染原始 Plan 数据。
    """
    id: str
    name: str
    description: str
    depends_on: list[str] = field(default_factory=list)
    target_module: str = "无"
    estimated_steps: int = 1
    status: TaskStatus = TaskStatus.PENDING

    @classmethod
    def from_subtask(cls, subtask: Any) -> "TaskNode":
        """
        从 schemas.SubTask（或任何具备同名属性的对象）构建运行时节点。

        用 getattr 带默认值，既兼容 Pydantic 对象，也兼容测试用的鸭子类型 mock。
        """
        return cls(
            id=subtask.id,
            name=subtask.name,
            description=getattr(subtask, "description", ""),
            depends_on=list(getattr(subtask, "depends_on", []) or []),
            target_module=getattr(subtask, "target_module", "无"),
            estimated_steps=getattr(subtask, "estimated_steps", 1),
            status=TaskStatus.PENDING,
        )


# ============================================================
# 目标树
# ============================================================

class GoalTree:
    """
    运行时目标树：管理子任务 DAG 的状态、依赖、拓扑排序。

    从 Plan 构建后，执行器循环调用：
        get_ready_tasks() → 取可执行节点 → mark_status(RUNNING/DONE/FAILED)
    失败时执行器调用 replace_subtree() 做局部重规划，
    需要动态细化时调用 add_subtasks() 展开。
    """

    def __init__(self, plan: Any):
        """
        从 Plan 对象（或 SubTask 列表）构建目标树。

        参数：
            plan: 具备 .subtasks 属性的对象（如 schemas.Plan），
                  或直接传入 SubTask 列表。
        """
        # 兼容两种入参：Plan 对象 或 直接的子任务列表
        if hasattr(plan, "subtasks"):
            self.goal: str = getattr(plan, "goal", "")
            subtasks = plan.subtasks
        else:
            self.goal = ""
            subtasks = plan

        # 用有序 dict 保存节点，保留 LLM 生成顺序（影响同层展示顺序）
        self._nodes: dict[str, TaskNode] = {}
        for st in subtasks:
            node = TaskNode.from_subtask(st)
            self._nodes[node.id] = node

        # 构建时即校验一次拓扑序（尽早暴露环）
        self.topological_order()

    # ── 基础访问 ──────────────────────────────────────────

    def get_task(self, task_id: str) -> Optional[TaskNode]:
        """按 id 获取节点，不存在返回 None。"""
        return self._nodes.get(task_id)

    def all_tasks(self) -> list[TaskNode]:
        """返回全部节点（含各种状态）。"""
        return list(self._nodes.values())

    def mark_status(self, task_id: str, status: TaskStatus) -> None:
        """更新指定节点状态。id 不存在则静默忽略（重规划后可能已被移除）。"""
        node = self._nodes.get(task_id)
        if node is not None:
            node.status = status

    # ── 拓扑排序（Kahn 算法）────────────────────────────

    def topological_order(self) -> list[str]:
        """
        返回满足依赖约束的拓扑执行顺序（子任务 id 列表）。

        使用 Kahn 算法：
            1. 统计每个节点的入度（有多少个未处理的前置依赖）
            2. 入度为 0 的入队
            3. 出队一个节点，把它从图里"删除"，其后继入度减 1
            4. 后继入度归零则入队
            5. 若最终排序出的节点数 < 总节点数，说明存在环 → 报错

        只统计"图内存在"的依赖：depends_on 里指向不存在节点的悬空依赖会被忽略
        （重规划/展开过程中可能临时出现无效引用，不应因此崩溃）。
        """
        # 入度表 + 邻接表（前置 → 后继）
        in_degree: dict[str, int] = {tid: 0 for tid in self._nodes}
        successors: dict[str, list[str]] = {tid: [] for tid in self._nodes}

        for tid, node in self._nodes.items():
            for dep in node.depends_on:
                if dep in self._nodes:          # 忽略悬空依赖
                    in_degree[tid] += 1
                    successors[dep].append(tid)

        # 入度为 0 的初始入队（保持插入顺序，展示更直观）
        queue = deque(tid for tid in self._nodes if in_degree[tid] == 0)
        order: list[str] = []

        while queue:
            tid = queue.popleft()
            order.append(tid)
            for succ in successors[tid]:
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        if len(order) != len(self._nodes):
            # 剩余未排序的节点即处于环中
            remaining = [tid for tid in self._nodes if tid not in set(order)]
            raise ValueError(f"目标树存在循环依赖，涉及节点：{remaining}")

        return order

    # ── 可执行任务筛选 ──────────────────────────────────

    def get_ready_tasks(self) -> list[TaskNode]:
        """
        返回当前所有"依赖已满足且自身为 PENDING"的子任务。

        依赖满足 = depends_on 里所有存在的前置节点状态均为 DONE。
        被 SKIPPED 的前置视为"不阻塞"（它已被重规划替换掉，不应无限等待）。
        按拓扑序返回，让执行器优先处理更靠前的任务。
        """
        ready: list[TaskNode] = []
        order = self.topological_order()
        for tid in order:
            node = self._nodes[tid]
            if node.status != TaskStatus.PENDING:
                continue
            if self._dependencies_satisfied(node):
                ready.append(node)
        return ready

    def _dependencies_satisfied(self, node: TaskNode) -> bool:
        """判断某节点的所有前置依赖是否都已完成（DONE）或已被跳过（SKIPPED）。"""
        for dep in node.depends_on:
            dep_node = self._nodes.get(dep)
            if dep_node is None:
                continue  # 悬空依赖不阻塞
            if dep_node.status not in (TaskStatus.DONE, TaskStatus.SKIPPED):
                return False
        return True

    # ── 完成判定 / 进度 ─────────────────────────────────

    def all_done(self) -> bool:
        """
        是否所有非 SKIPPED 子任务都已 DONE。

        SKIPPED 节点是被重规划替换掉的"废弃分支"，不计入完成判定，
        否则被替换的旧任务会永远卡住 all_done。
        """
        for node in self._nodes.values():
            if node.status == TaskStatus.SKIPPED:
                continue
            if node.status != TaskStatus.DONE:
                return False
        return True

    def has_failed(self) -> bool:
        """是否存在处于 FAILED 状态的节点（供外层决定是否触发重规划）。"""
        return any(n.status == TaskStatus.FAILED for n in self._nodes.values())

    def get_progress(self) -> dict:
        """返回进度统计：{total, done, failed, running, pending, skipped}。"""
        stats = {
            "total": len(self._nodes),
            "done": 0,
            "failed": 0,
            "running": 0,
            "pending": 0,
            "skipped": 0,
        }
        for node in self._nodes.values():
            if node.status == TaskStatus.DONE:
                stats["done"] += 1
            elif node.status == TaskStatus.FAILED:
                stats["failed"] += 1
            elif node.status == TaskStatus.RUNNING:
                stats["running"] += 1
            elif node.status == TaskStatus.SKIPPED:
                stats["skipped"] += 1
            else:  # PENDING / READY 都归入待办
                stats["pending"] += 1
        return stats

    # ── 动态展开 ────────────────────────────────────────

    def add_subtasks(self, new_subtasks: list, parent_id: str) -> None:
        """
        动态展开：在 parent 之后插入新子任务。

        语义：parent 被拆解成若干更细的步骤，这些新步骤先执行，
        parent 变成"汇聚点"——依赖所有新子任务完成后才轮到它。
        因此：
            1. 新子任务加入图中（保持它们自带的相互依赖）
            2. 把新子任务的 id 追加到 parent 的 depends_on，让 parent 等它们完成
            3. parent 若已是 READY/RUNNING，回退为 PENDING（依赖又变多了）
        """
        parent = self._nodes.get(parent_id)
        new_ids: list[str] = []

        for st in new_subtasks:
            node = TaskNode.from_subtask(st)
            self._nodes[node.id] = node
            new_ids.append(node.id)

        if parent is not None:
            # parent 现在要等这些新子任务先完成
            for nid in new_ids:
                if nid not in parent.depends_on:
                    parent.depends_on.append(nid)
            # 依赖增加了，parent 重新回到待定状态
            if parent.status in (TaskStatus.READY, TaskStatus.RUNNING):
                parent.status = TaskStatus.PENDING

        # 插入后重新校验拓扑序，及时发现展开引入的环
        self.topological_order()

    # ── 局部重规划 ──────────────────────────────────────

    def replace_subtree(self, affected_ids: list[str], replacements: list) -> None:
        """
        局部重规划：将受影响子任务标记 SKIPPED，插入替换子任务。

        影响面处理：
            1. 受影响的旧节点全部标记为 SKIPPED（保留在图里供展示"被替换"轨迹，
               但不计入 all_done、不阻塞后继）
            2. 插入 replacement 新节点
            3. 原先依赖"受影响节点"的其它节点，把这些依赖重定向到替换任务
               —— 否则下游会永远等一个已 SKIPPED 的节点
               （简化策略：让下游依赖所有新替换任务，保证在其之后执行）

        未列入 affected_ids 的已完成任务保持不动，实现"局部"而非"全局"重规划。
        """
        affected_set = set(affected_ids)

        # 1. 旧节点标记 SKIPPED
        for tid in affected_ids:
            node = self._nodes.get(tid)
            if node is not None:
                node.status = TaskStatus.SKIPPED

        # 2. 插入替换节点
        new_ids: list[str] = []
        for st in replacements:
            node = TaskNode.from_subtask(st)
            self._nodes[node.id] = node
            new_ids.append(node.id)

        # 3. 下游依赖重定向：把指向"被跳过节点"的依赖替换为"新替换任务"
        for node in self._nodes.values():
            if node.id in new_ids or node.id in affected_set:
                continue
            # 该节点是否依赖了被跳过的任务？
            if any(dep in affected_set for dep in node.depends_on):
                # 移除对被跳过节点的依赖，改为依赖全部新替换任务
                node.depends_on = [d for d in node.depends_on if d not in affected_set]
                for nid in new_ids:
                    if nid not in node.depends_on:
                        node.depends_on.append(nid)

        # 重新校验拓扑序
        self.topological_order()

    # ── 展示辅助 ────────────────────────────────────────

    def _compute_depths(self) -> dict[str, int]:
        """
        计算每个节点的深度 = 最长依赖链长度。

        depth(node) = 0                       （无依赖）
        depth(node) = 1 + max(depth(前置))     （有依赖）
        沿拓扑序正向递推即可保证前置已算好。供 display 做缩进。
        """
        depth: dict[str, int] = {}
        for tid in self.topological_order():
            node = self._nodes[tid]
            valid_deps = [d for d in node.depends_on if d in self._nodes]
            if not valid_deps:
                depth[tid] = 0
            else:
                depth[tid] = 1 + max(depth[d] for d in valid_deps)
        return depth

    def to_display_rows(self) -> list[dict]:
        """
        返回供 display 模块渲染的行数据（按拓扑序排列）：
            [{id, name, status, depends_on, depth, target_module}]
        depth 用于缩进展示（依赖链越深缩进越多）。
        """
        depths = self._compute_depths()
        rows: list[dict] = []
        for tid in self.topological_order():
            node = self._nodes[tid]
            rows.append({
                "id": node.id,
                "name": node.name,
                "status": node.status.value,
                "depends_on": list(node.depends_on),
                "depth": depths[tid],
                "target_module": node.target_module,
            })
        return rows


# ============================================================
# 快速验证（不依赖 openai/pydantic，用 mock 节点跑通）
# ============================================================

if __name__ == "__main__":
    from dataclasses import dataclass as _dc

    # 用最简单的 mock 节点模拟 schemas.SubTask（鸭子类型）
    @_dc
    class MockSubTask:
        id: str
        name: str
        description: str
        depends_on: list
        target_module: str
        estimated_steps: int

    # 硬编码一个 mock 计划：
    #   t1(采钛矿) → t3(建居住舱)
    #   t2(采碳纤维) → t3
    #   t3 → t4(建实验室)
    mock_subtasks = [
        MockSubTask("t1", "采集钛矿×6", "从矿区采集钛矿", [], "钛矿", 2),
        MockSubTask("t2", "采集碳纤维×3", "从仓库调取碳纤维", [], "碳纤维", 1),
        MockSubTask("t3", "建造居住舱", "组装居住舱", ["t1", "t2"], "居住舱", 3),
        MockSubTask("t4", "建造实验室", "在居住舱后建实验室", ["t3"], "实验室", 3),
    ]

    class MockPlan:
        goal = "建造载人基地 Phase-1"
        subtasks = mock_subtasks

    print("=== GoalTree 快速验证 ===\n")
    tree = GoalTree(MockPlan())

    print(f"目标: {tree.goal}")
    print(f"拓扑序: {tree.topological_order()}\n")

    print("初始可执行任务（应只有 t1、t2，无依赖）:")
    for t in tree.get_ready_tasks():
        print(f"  - {t.id} {t.name}")

    print("\n展示行（depth 缩进）:")
    for row in tree.to_display_rows():
        indent = "  " * row["depth"]
        print(f"  {indent}[{row['status']}] {row['id']} {row['name']} "
              f"(deps={row['depends_on']}, depth={row['depth']})")

    # 模拟执行：完成 t1、t2，t3 应变为可执行
    print("\n完成 t1、t2 后，可执行任务应出现 t3:")
    tree.mark_status("t1", TaskStatus.DONE)
    tree.mark_status("t2", TaskStatus.DONE)
    for t in tree.get_ready_tasks():
        print(f"  - {t.id} {t.name}")

    print(f"\n进度: {tree.get_progress()}")

    # 模拟局部重规划：t3 失败，用 t3a/t3b 替换
    print("\n模拟 t3 失败 → 局部重规划（t3 → t3a, t3b）:")
    tree.mark_status("t3", TaskStatus.FAILED)
    replacements = [
        MockSubTask("t3a", "打印居住舱外壳", "用 3D 打印机打印外壳", [], "居住舱", 2),
        MockSubTask("t3b", "焊接组装居住舱", "机械臂焊接组装", ["t3a"], "居住舱", 2),
    ]
    tree.replace_subtree(["t3"], replacements)
    print(f"  重规划后拓扑序: {tree.topological_order()}")
    print(f"  t4 的依赖已重定向为: {tree.get_task('t4').depends_on}")
    print(f"  进度: {tree.get_progress()}")

    # 环检测验证
    print("\n环检测验证（构造 a→b→a）:")
    cyclic = [
        MockSubTask("a", "A", "", ["b"], "无", 1),
        MockSubTask("b", "B", "", ["a"], "无", 1),
    ]

    class CyclicPlan:
        goal = "环测试"
        subtasks = cyclic

    try:
        GoalTree(CyclicPlan())
        print("  ✗ 未检测到环（预期应报错）")
    except ValueError as e:
        print(f"  ✓ 正确检测到环: {e}")

    print("\nGoalTree 模块验证通过 ✓")
