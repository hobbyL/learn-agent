# 工作流编排模式知识笔记

> 基于项目 17 实践整理

---

## 1. 工作流编排的核心概念

### 什么是工作流编排？

将多个独立任务按**依赖关系**组织成有向无环图（DAG），由引擎负责：
1. 依赖解析（拓扑排序）
2. 执行调度（按序执行）
3. 状态管理（pending/running/completed）
4. 数据流转（上游输出 → 下游输入）

### 为什么需要工作流编排？

**问题场景：**
```python
# 硬编码的任务链（不可扩展）
result1 = task_a()
result2 = task_b(result1)
result3 = task_c(result2)
result4 = task_d(result2)  # task_d 也依赖 task_b
# 依赖关系隐式，无法复用，难以可视化
```

**工作流编排方案：**
```python
# 声明式定义依赖关系
workflow = Workflow()
t1 = workflow.add_task("A", ...)
t2 = workflow.add_task("B", ..., depends_on=[t1])
t3 = workflow.add_task("C", ..., depends_on=[t2])
t4 = workflow.add_task("D", ..., depends_on=[t2])  # 自动支持分支
workflow.run()
# 依赖关系显式，可复用，可可视化
```

---

## 2. 核心数据结构：DAG

### 什么是 DAG？

**Directed Acyclic Graph**（有向无环图）：
- **有向**：任务 A → 任务 B 有方向（A 必须先于 B）
- **无环**：不能有循环依赖（A → B → C → A 是错误的）

### 如何表达 DAG？

**方式 1：邻接表（单向）**
```python
graph = {
    "A": [],           # A 无依赖
    "B": ["A"],        # B 依赖 A
    "C": ["B"],        # C 依赖 B
    "D": ["B"],        # D 依赖 B
}
```

**方式 2：双向链表（推荐）**
```python
class Task:
    depends_on: List[Task]  # 我依赖谁（上游）
    downstream: List[Task]  # 谁依赖我（下游）
```

**为什么需要双向？**
- 拓扑排序时需要**反向查找**："谁依赖我" → 更新下游入度
- 只有单向链表无法高效反向遍历

---

## 3. 拓扑排序：Kahn 算法

### 算法原理

1. 计算每个任务的**入度**（被多少个任务依赖）
2. 找到所有入度为 0 的任务（无依赖，可立即执行）
3. 从队列中取出一个任务，将其下游任务的入度 -1
4. 如果下游任务入度变为 0，加入队列
5. 重复 3-4，直到队列为空

### 代码实现

```python
def topological_sort(tasks):
    # 1. 计算入度
    in_degree = {task: len(task.depends_on) for task in tasks}
    
    # 2. 找到入度为 0 的任务
    queue = [task for task in tasks if in_degree[task] == 0]
    result = []
    
    # 3. Kahn 算法主循环
    while queue:
        task = queue.pop(0)
        result.append(task)
        
        # 4. 更新下游任务的入度
        for downstream in task.downstream:
            in_degree[downstream] -= 1
            if in_degree[downstream] == 0:
                queue.append(downstream)
    
    # 5. 环检测
    if len(result) != len(tasks):
        raise CycleError("检测到依赖环！")
    
    return result
```

### 环检测原理

如果 DAG 中存在环，某些任务的入度永远无法降为 0，导致：
```
排序结果数量 < 总任务数
```

**例子：**
```
A → B → C → A（环）
入度：A=1, B=1, C=1
队列：[] （无入度为 0 的任务）
结果：[] （0 < 3，检测到环）
```

---

## 4. Context 注入机制

### 为什么需要 Context？

多 Agent 协作时，下游 Agent 需要看到上游的输出才能做决策：
- 建筑师需要看到地质学家的报告才能选址
- 工程师需要知道建筑师选的区域 ID 才能规划基建

### 自动 Context 注入

```python
def _format_context(task: Task) -> str:
    """收集上游任务的输出。"""
    lines = []
    for dep in task.depends_on:
        lines.append(f"### {dep.name}")
        lines.append(dep.result)
    return "\n".join(lines)

# 执行任务时自动注入
context = _format_context(task)
user_prompt = f"{task.description}\n\n【上游任务输出】\n{context}"
```

### 手动 vs 自动 Context

| 方式 | 实现 | 优点 | 缺点 |
|------|------|------|------|
| 手动 | 在 prompt 里硬编码上游输出 | 完全控制 | 不可扩展，每个任务都要改代码 |
| 自动 | 引擎收集 depends_on 的输出 | 通用，任何任务都适用 | 可能注入冗余信息 |

**最佳实践：**
- 简单工作流：自动注入（引擎负责）
- 复杂工作流：自动注入 + 手动过滤（Agent 自行筛选关键信息）

---

## 5. 工作流编排 vs 其他模式

### vs ReAct（项目 3）

| 维度 | ReAct | Workflow |
|------|-------|----------|
| 任务结构 | 单任务（单 Agent） | 多任务（多 Agent） |
| 执行模式 | 循环（Thought → Action → Observation） | DAG 顺序执行 |
| 依赖关系 | 无（每步依赖上一步） | 显式声明 |
| 适用场景 | 单一目标，多步推理 | 复杂项目，多角色协作 |

### vs 任务分解（项目 10）

| 维度 | 项目 10 (goal-tree) | 项目 17 (workflow) |
|------|--------------------|--------------------|
| 结构 | 嵌套树 + 运行时 DAG | 静态 DAG |
| Agent 数量 | 1（Planner + Executor） | 多个（独立角色） |
| 动态性 | 高（重规划） | 低（声明后不变） |
| 失败处理 | 局部重规划 | 失败即终止 |

### vs 多 Agent 辩论（项目 15）

| 维度 | 项目 15 (debate) | 项目 17 (workflow) |
|------|------------------|--------------------|
| Agent 关系 | 平行（互相质疑） | 串行（上下游协作） |
| 信息流 | 隔离 → 交叉质疑 | 上游输出 → 下游输入 |
| 决策方式 | 投票 | 无（每个 Agent 独立决策） |
| 适用场景 | 需要多视角评估 | 需要流程化执行 |

---

## 6. 声明式 API 设计

### 什么是声明式？

**命令式**：告诉计算机"怎么做"（步骤）
```python
t1 = Task("A", "geologist")
t2 = Task("B", "architect")
t2.depends_on.append(t1)
t1.downstream.append(t2)
workflow.tasks.append(t1)
workflow.tasks.append(t2)
```

**声明式**：告诉计算机"要什么"（目标）
```python
t1 = workflow.add_task("A", "geologist")
t2 = workflow.add_task("B", "architect", depends_on=[t1])
# 引擎负责维护双向链表、拓扑排序
```

### 声明式的好处

1. **降低心智负担**：用户不需要关心实现细节
2. **减少错误**：引擎负责维护内部状态（双向链表、环检测）
3. **提高可读性**：代码即文档，一眼看出依赖关系

### 声明式的代价

- 灵活性降低：无法精细控制每个步骤
- 调试困难：出错时需要理解引擎内部逻辑

**最佳实践：**
- 常见场景用声明式（简单易用）
- 特殊场景提供命令式接口（手动控制）

---

## 7. 回调机制 vs 硬编码日志

### 问题：硬编码日志

```python
def run(tasks):
    for task in tasks:
        print(f"开始任务: {task.name}")  # 硬编码
        result = execute(task)
        print(f"完成任务: {task.name}")  # 硬编码
```

**缺点：**
- 引擎和展示逻辑耦合
- 无法自定义展示（终端 / Web / 日志文件）

### 解决：回调机制

```python
def run(tasks, on_task_start=None, on_task_complete=None):
    for task in tasks:
        if on_task_start:
            on_task_start(task)  # 调用方控制展示
        result = execute(task)
        if on_task_complete:
            on_task_complete(task)  # 调用方控制展示
```

**好处：**
- 引擎只负责编排，不关心展示
- 调用方可自定义展示逻辑

### 常见回调类型

| 回调 | 触发时机 | 用途 |
|------|----------|------|
| on_task_start | 任务开始前 | 打印日志、更新 UI |
| on_task_complete | 任务完成后 | 打印结果、发送通知 |
| on_task_error | 任务失败后 | 记录错误、触发重试 |
| on_workflow_complete | 工作流完成后 | 汇总统计、清理资源 |

---

## 8. 工作流编排的典型应用

### 1. CI/CD 流水线

```
拉代码 → 安装依赖 → 运行测试 → 构建镜像 → 部署到 K8s
```

**特点：**
- 严格的线性依赖
- 失败即终止（不能部署失败的代码）

### 2. 数据处理管道

```
抽取数据 (Extract) → 转换数据 (Transform) → 加载数据 (Load)
```

**特点：**
- 可能有并行分支（多个数据源同时抽取）
- 需要数据血缘追踪（哪个任务产生了哪些数据）

### 3. 机器学习训练

```
数据预处理 → 特征工程 → 模型训练 → 模型评估 → 模型部署
```

**特点：**
- 可能有超参数搜索（并行训练多个模型）
- 需要版本管理（记录每次训练的参数和结果）

### 4. 多 Agent 协作（本项目）

```
地质勘探 → 选址分析 → 基础建设 → 能源系统 → 生命支持
```

**特点：**
- 每个任务由不同 Agent 执行
- 上游输出自动注入下游 context

---

## 9. 扩展方向

### 1. 并行执行

**当前实现：** 顺序执行（即使任务之间无依赖）
```python
for task in sorted_tasks:
    result = run_agent(task)
```

**改进：** 同一层级的独立任务可并发
```python
import asyncio

async def run(tasks):
    while tasks:
        ready_tasks = [t for t in tasks if t.is_ready()]
        results = await asyncio.gather(*[run_agent(t) for t in ready_tasks])
```

### 2. 失败重试

**当前实现：** 失败即终止
```python
try:
    result = run_agent(task)
except Exception as e:
    task.mark_failed(str(e))
    raise  # 终止工作流
```

**改进：** 自动重试 N 次
```python
for retry in range(max_retries):
    try:
        result = run_agent(task)
        break
    except Exception as e:
        if retry == max_retries - 1:
            task.mark_failed(str(e))
            raise
        time.sleep(2 ** retry)  # 指数退避
```

### 3. 条件分支

**当前实现：** 静态依赖（声明后不变）
```python
t2 = workflow.add_task("B", ..., depends_on=[t1])
```

**改进：** 根据上游结果动态选择分支
```python
t2a = workflow.add_task("B_success", ..., condition=lambda: t1.result.success)
t2b = workflow.add_task("B_failure", ..., condition=lambda: not t1.result.success)
```

### 4. 持久化

**当前实现：** 内存状态（进程退出即丢失）

**改进：** 保存到 JSON/DB，支持断点恢复
```python
workflow.save("workflow_state.json")
# 进程崩溃后
workflow = Workflow.load("workflow_state.json")
workflow.resume()
```

---

## 10. 与开源工具的对比

| 工具 | 语言 | 定义方式 | 状态管理 | 适用场景 |
|------|------|----------|----------|----------|
| Airflow | Python | Python DAG | 数据库 | 数据管道 |
| Prefect | Python | Python 装饰器 | 数据库/内存 | 数据管道 + ML |
| Argo Workflows | YAML | YAML | K8s CRD | K8s 原生工作流 |
| Temporal | Go/Java/Python | 代码 | 持久化 | 微服务编排 |
| **本项目** | Python | Python DSL | 内存 | 多 Agent 协作 |

**本项目的定位：**
- 轻量级（无需数据库/K8s）
- 专注多 Agent 协作（自动 Context 注入）
- 适合学习和原型验证

---

## 参考资料

- [Kahn 拓扑排序算法](https://en.wikipedia.org/wiki/Topological_sorting#Kahn's_algorithm)
- [Apache Airflow](https://airflow.apache.org/)
- [Prefect](https://www.prefect.io/)
- 项目 10 (`planning-and-goal-tree`)：拓扑排序的代码基础
- 项目 15 (`multi-agent-debate`)：多 Agent 协作的经验
