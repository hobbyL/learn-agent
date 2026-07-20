"""
工作流编排引擎
============

核心组件：
- Task: 任务节点（name, agent, depends_on, status, result）
- Workflow: 工作流管理器（DAG 构建 + 拓扑排序 + 执行调度）
"""

from typing import List, Dict, Optional
from enum import Enum
from agents import run_agent, get_agent_info


# ============================================================
# 任务状态
# ============================================================

class TaskStatus(Enum):
    PENDING = "pending"      # 等待依赖完成
    READY = "ready"          # 依赖已满足，可执行
    RUNNING = "running"      # 正在执行
    COMPLETED = "completed"  # 执行成功
    FAILED = "failed"        # 执行失败


# ============================================================
# Task 类
# ============================================================

class Task:
    """任务节点。"""

    def __init__(
        self,
        name: str,
        agent_role: str,
        description: str = "",
        depends_on: Optional[List["Task"]] = None,
    ):
        self.name = name
        self.agent_role = agent_role
        self.description = description or name
        self.depends_on: List[Task] = depends_on or []
        self.downstream: List[Task] = []  # 依赖本任务的下游任务
        self.status = TaskStatus.PENDING
        self.result: Optional[str] = None

    def __repr__(self):
        return f"Task({self.name}, {self.status.value})"

    def is_ready(self) -> bool:
        """检查任务是否就绪（所有依赖都已完成）。"""
        return all(dep.status == TaskStatus.COMPLETED for dep in self.depends_on)

    def mark_running(self):
        """标记为运行中。"""
        self.status = TaskStatus.RUNNING

    def mark_completed(self, result: str):
        """标记为已完成。"""
        self.status = TaskStatus.COMPLETED
        self.result = result

    def mark_failed(self, error: str):
        """标记为失败。"""
        self.status = TaskStatus.FAILED
        self.result = f"ERROR: {error}"


# ============================================================
# Workflow 类
# ============================================================

class CycleError(Exception):
    """依赖环错误。"""
    pass


class Workflow:
    """工作流管理器。"""

    def __init__(self, name: str):
        self.name = name
        self.tasks: List[Task] = []
        self._task_map: Dict[str, Task] = {}

    def add_task(
        self,
        name: str,
        agent_role: str,
        description: str = "",
        depends_on: Optional[List[Task]] = None,
    ) -> Task:
        """
        添加任务到工作流。

        Args:
            name: 任务名称
            agent_role: Agent 角色（如 'geologist'）
            description: 任务描述
            depends_on: 依赖的任务列表

        Returns:
            创建的 Task 对象
        """
        task = Task(name, agent_role, description, depends_on)
        self.tasks.append(task)
        self._task_map[name] = task

        # 更新下游任务列表
        if depends_on:
            for dep in depends_on:
                dep.downstream.append(task)

        return task

    def topological_sort(self) -> List[Task]:
        """
        拓扑排序（Kahn 算法）。

        Returns:
            排序后的任务列表

        Raises:
            CycleError: 检测到依赖环
        """
        # 计算入度
        in_degree = {task: len(task.depends_on) for task in self.tasks}

        # 找到所有入度为 0 的任务
        queue = [task for task in self.tasks if in_degree[task] == 0]
        result = []

        while queue:
            # 取出一个入度为 0 的任务
            task = queue.pop(0)
            result.append(task)

            # 更新下游任务的入度
            for downstream in task.downstream:
                in_degree[downstream] -= 1
                if in_degree[downstream] == 0:
                    queue.append(downstream)

        # 如果结果数量 < 总任务数，说明有环
        if len(result) != len(self.tasks):
            raise CycleError(f"检测到依赖环！已排序 {len(result)} 个任务，总共 {len(self.tasks)} 个任务。")

        return result

    def run(self, client, model: str, on_task_start=None, on_task_complete=None):
        """
        执行工作流。

        Args:
            client: OpenAI 客户端
            model: 模型名称
            on_task_start: 任务开始回调 (task: Task) -> None
            on_task_complete: 任务完成回调 (task: Task) -> None

        Returns:
            所有任务的结果字典 {task_name: result}
        """
        # 拓扑排序
        sorted_tasks = self.topological_sort()

        # 按顺序执行任务
        results = {}
        for task in sorted_tasks:
            # 任务开始回调
            if on_task_start:
                on_task_start(task)

            task.mark_running()

            try:
                # 收集上游任务的输出作为 context
                context = self._format_context(task)

                # 执行 Agent
                result = run_agent(
                    role=task.agent_role,
                    task_description=task.description,
                    context=context,
                    client=client,
                    model=model,
                )

                # 标记完成
                task.mark_completed(result)
                results[task.name] = result

                # 任务完成回调
                if on_task_complete:
                    on_task_complete(task)

            except Exception as e:
                # 标记失败
                task.mark_failed(str(e))
                results[task.name] = task.result

                # 任务完成回调（即使失败也调用）
                if on_task_complete:
                    on_task_complete(task)

                # 失败即终止工作流
                raise RuntimeError(f"任务 '{task.name}' 执行失败: {e}")

        return results

    def _format_context(self, task: Task) -> str:
        """格式化上游任务的输出作为 context。"""
        if not task.depends_on:
            return ""

        lines = []
        for dep in task.depends_on:
            agent_info = get_agent_info(dep.agent_role)
            lines.append(f"### {agent_info['emoji']} {agent_info['name']}（{dep.name}）")
            lines.append(dep.result or "(无输出)")
            lines.append("")

        return "\n".join(lines)

    def get_task(self, name: str) -> Optional[Task]:
        """根据名称获取任务。"""
        return self._task_map.get(name)

    def get_status_summary(self) -> Dict[str, int]:
        """获取任务状态统计。"""
        summary = {
            "pending": 0,
            "ready": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
        }
        for task in self.tasks:
            summary[task.status.value] += 1
        return summary
