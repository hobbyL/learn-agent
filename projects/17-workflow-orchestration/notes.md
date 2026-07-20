# 项目 17 实现笔记

## 开发过程

### 1. 需求脑暴（PRD 设计）

**核心决策：**
- **编排方式**：声明式 DSL（Python API）✓（而非 YAML 配置或可视化拖拽）
- **状态管理**：内存状态机 ✓（而非持久化到 Redis/DB）
- **场景**：星际研究站建设（5 任务链：地质勘探 → 选址 → 基建 → 能源 → 生命支持）

### 2. 实现顺序

```
knowledge_base.py (蓝晶星数据，复用项目 15)
    ↓
tools.py (5 个领域工具 + 工具路由)
    ↓
agents.py (5 个专家 Agent + 简化 ReAct 执行器)
    ↓
workflow.py (核心：Workflow + Task 类 + 拓扑排序)
    ↓
display.py (ASCII 流程图 + 进度展示)
    ↓
main.py (CLI 入口)
```

### 3. 核心代码设计

#### Workflow 类关键方法

```python
class Workflow:
    def add_task(name, agent_role, description, depends_on):
        # 创建 Task 对象
        # 更新双向链表（depends_on + downstream）
        
    def topological_sort():
        # Kahn 算法：入度表 + 队列
        # 环检测：result 数量 < 总任务数
        
    def run(client, model, on_task_start, on_task_complete):
        # 拓扑排序 → 按序执行
        # 收集上游输出作为 context
        # 调用 run_agent()
        # 回调通知
```

#### Context 注入机制

```python
def _format_context(task):
    for dep in task.depends_on:
        # 上游 Agent 名称 + 输出结果
        lines.append(f"### {emoji} {name}（{dep.name}）")
        lines.append(dep.result)
```

**为什么要 context 注入？**
- 建筑师需要看到地质学家的报告才能选址
- 工程师需要知道建筑师选的区域 ID 才能规划基建
- 每个 Agent 独立推理，但看到上游的完整输出

### 4. 拓扑排序算法复用

从项目 10 的 `goal_tree.py` 复用 Kahn 算法逻辑：

```python
# 项目 10：goal_tree.py
def get_ready_tasks():
    in_degree = {id: len(deps) for id, deps in graph.items()}
    return [id for id in graph if in_degree[id] == 0]

# 项目 17：workflow.py
def topological_sort():
    in_degree = {task: len(task.depends_on) for task in self.tasks}
    queue = [task for task in self.tasks if in_degree[task] == 0]
    # Kahn 算法主循环
```

**差异：**
- 项目 10 是运行时 DAG（可动态展开、重规划）
- 项目 17 是静态 DAG（声明后不变）

### 5. 踩坑记录

#### 坑 1：忘记维护 downstream

**问题：**
```python
task = Task(name, agent_role, description, depends_on)
# 只设置了 task.depends_on，忘记更新上游任务的 downstream
```

**解决：**
```python
if depends_on:
    for dep in depends_on:
        dep.downstream.append(task)  # 双向链表
```

**为什么需要 downstream？**
- 拓扑排序时需要更新下游任务的入度
- 如果只有 depends_on，无法反向查找"谁依赖我"

#### 坑 2：环检测的时机

**错误实现：**
```python
def add_task(...):
    # 每次 add_task 时检测环 → 性能浪费
    if self._has_cycle():
        raise CycleError()
```

**正确实现：**
```python
def topological_sort():
    # 排序结束后检测
    if len(result) != len(self.tasks):
        raise CycleError()
```

**原因：**
- Kahn 算法本身就能检测环（无需额外算法）
- 只需在排序结束时比较节点数

### 6. 可视化设计

#### ASCII 流程图设计

```
目标：展示任务节点 + 依赖关系 + 执行顺序

实现：
1. 拓扑排序获取执行顺序
2. 遍历每个任务，打印节点 + emoji + 角色
3. 如果有依赖，缩进打印 "└─ 依赖: ..."
4. 节点间用 "↓" 连接
```

#### 进度展示设计

```
目标：实时显示任务状态（pending/running/completed）

实现：
1. 定义 on_task_start / on_task_complete 回调
2. 任务开始时打印 "▶ 开始任务: ..."
3. 任务完成时打印 "✓ 完成任务: ..." + 输出摘要（前 200 字符）
```

### 7. CLI 设计

**三种模式：**
1. `--demo`：预定义 5 任务工作流，一键运行
2. `--interactive`：用户输入任务名称、角色、依赖，动态构建工作流
3. `--visualize`：只展示 DAG 结构，不执行（用于调试/展示）

**默认行为：**
- 不带参数 = `--demo`（最常用的场景）

## 难点突破

### 难点 1：如何让 Agent 看到上游输出？

**方案 1（手动）：** 在每个 Agent 的 prompt 里硬编码上游输出
```python
prompt = f"根据地质学家的报告：{t1.result}，选择最佳区域"
# ❌ 不可扩展，每个任务都要改代码
```

**方案 2（自动注入）：** Workflow 引擎自动收集上游输出
```python
context = self._format_context(task)  # 自动拼接所有 depends_on 的输出
user_prompt = f"{task.description}\n\n【上游任务输出】\n{context}"
# ✅ 通用，任何任务都适用
```

### 难点 2：如何支持用户自定义工作流？

**设计：**
- 交互式输入任务名称 → 角色 → 依赖（已创建的任务名）
- 用 `tasks = ` 字典存储已创建的任务，供后续任务依赖引用

**实现细节：**
```python
tasks = {}
while True:
    task_name = input("任务名称: ")
    depends_on_input = input("依赖任务（逗号分隔）: ")
    depends_on = [tasks[name] for name in depends_on_input.split(",") if name in tasks]
    task = workflow.add_task(...)
    tasks[task_name] = task  # 存储供后续引用
```

### 难点 3：如何测试拓扑排序的正确性？

**测试用例：**
1. 正常链式：A → B → C（应该返回 [A, B, C]）
2. 并行分支：A → B, A → C（应该返回 [A, B, C] 或 [A, C, B]）
3. 依赖环：A → B → C → A（应该抛 CycleError）

**验证方式：**
```python
# 不用写单元测试，用 --visualize 模式直接看 DAG 结构
python3 main.py --visualize
```

## 与已有项目的对比

| 维度 | 项目 10 | 项目 15 | 项目 17 |
|------|---------|---------|---------|
| 主题 | 任务分解与目标树 | 多 Agent 辩论 | 工作流编排 |
| 结构 | 嵌套树 + 运行时 DAG | 无依赖关系 | 静态 DAG |
| Agent 数量 | 1（Planner + Executor 同一个） | 3（独立推理） | 5（协作推理） |
| 信息流 | 父任务 → 子任务 | 隔离 → 交叉质疑 | 上游 → 下游 |
| 动态性 | 高（重规划） | 低（固定三阶段） | 低（静态工作流） |
| 失败处理 | 局部重规划 | 无（全通过） | 失败即终止 |

## 可复用的设计模式

### 模式 1：双向链表表达 DAG

```python
class Task:
    depends_on: List[Task]    # 我依赖谁
    downstream: List[Task]    # 谁依赖我
```

**好处：**
- 正向遍历：从根节点找到所有叶子
- 反向遍历：从叶子节点找到所有依赖
- 拓扑排序：更新下游入度时需要 downstream

### 模式 2：回调 > 硬编码日志

```python
def run(..., on_task_start=None, on_task_complete=None):
    for task in tasks:
        if on_task_start:
            on_task_start(task)
        # 执行任务
        if on_task_complete:
            on_task_complete(task)
```

**好处：**
- 引擎不关心展示逻辑，只负责编排
- 调用方可以自定义展示（终端 / Web / 日志文件）

### 模式 3：声明式 API 设计

```python
# 命令式（繁琐）
workflow = Workflow()
t1 = Task("t1", "geologist")
t2 = Task("t2", "architect")
t2.depends_on.append(t1)
workflow.tasks.append(t1)
workflow.tasks.append(t2)

# 声明式（简洁）
workflow = Workflow()
t1 = workflow.add_task("t1", "geologist")
t2 = workflow.add_task("t2", "architect", depends_on=[t1])
```

**好处：**
- 用户只关心"是什么"，不关心"怎么做"
- 引擎负责维护内部状态（双向链表、拓扑排序）

## 总结

### 项目亮点

1. **代码复用**：从项目 10 复用拓扑排序，从项目 15 复用知识库
2. **架构清晰**：5 层分离（知识库/工具/Agent/引擎/展示）
3. **可扩展性强**：新增 Agent 只需改 agents.py + tools.py，引擎无需改动

### 如果重做会改进什么？

1. **并行执行**：同一层级的独立任务可并发（用 asyncio.gather）
2. **失败重试**：单任务失败后自动重试 N 次（而非直接终止）
3. **条件分支**：根据上游结果动态选择分支（if/else 逻辑）
4. **持久化**：保存工作流状态到 JSON，支持断点恢复

### 核心收获

- **拓扑排序 = DAG 编排的基础**：无论是任务调度、依赖管理、还是构建系统，都离不开拓扑排序
- **Context 注入 = 协作的本质**：Agent 不需要知道上游是谁，引擎负责串联信息流
- **声明式 > 命令式**：用户只需声明"要什么"，引擎负责"怎么做"，降低心智负担
