# 17-workflow-orchestration：工作流编排引擎

声明式工作流编排引擎，通过 Python DSL 定义任务 DAG，自动拓扑排序并执行，支持多 Agent 协作。

## 核心特性

- **声明式 DSL**：简洁的 Python API 定义工作流
- **自动依赖管理**：DAG 拓扑排序 + 环检测
- **多 Agent 协作**：任务输出自动注入下游 context
- **实时可视化**：ASCII 流程图 + 执行进度
- **内存状态机**：轻量级，无需数据库

## 场景：蓝晶星研究站建设

5 个阶段任务链：

```
地质勘探 (Geologist) → 选址分析 (Architect) → 基础建设 (Engineer)
                                                        ↓
                                                  能源系统 (Energy)
                                                        ↓
                                                  生命支持 (Life Support)
```

## 文件结构

```
projects/17-workflow-orchestration/
├── knowledge_base.py    # 蓝晶星数据（地质/环境/资源）
├── tools.py             # 5 个领域工具（每 Agent 1 个工具）
├── agents.py            # 5 个专家 Agent + 简化 ReAct 执行器
├── workflow.py          # 核心：Workflow + Task 类 + 拓扑排序
├── display.py           # ASCII 流程图 + 进度展示 + 结果汇总
├── main.py              # CLI: --demo / --interactive / --visualize
├── README.md
└── notes.md
```

## 快速开始

### 1. Demo 模式（预定义 5 任务工作流）

```bash
cd projects/17-workflow-orchestration
python3 main.py --demo
```

### 2. 可视化模式（只展示 DAG，不执行）

```bash
python3 main.py --visualize
```

### 3. 交互模式（自定义工作流）

```bash
python3 main.py --interactive
```

## 核心 API

### 定义工作流

```python
from workflow import Workflow

# 创建工作流
workflow = Workflow("建设蓝晶星研究站")

# 添加任务（按依赖关系）
t1 = workflow.add_task("地质勘探", "geologist", "分析地质数据")
t2 = workflow.add_task("选址分析", "architect", "选择建设区域", depends_on=[t1])
t3 = workflow.add_task("基础建设", "engineer", "规划基础设施", depends_on=[t2])

# 拓扑排序（自动检测环）
sorted_tasks = workflow.topological_sort()

# 执行工作流
results = workflow.run(client, model)
```

### 任务状态

| 状态 | 描述 |
|------|------|
| PENDING | 等待依赖完成 |
| READY | 依赖已满足，可执行 |
| RUNNING | 正在执行 |
| COMPLETED | 执行成功 |
| FAILED | 执行失败 |

### Agent 角色

| 角色 | 名称 | 工具 | 职责 |
|------|------|------|------|
| geologist | 地质学家 🔬 | scan_geology | 分析地质数据，评估建设可行性 |
| architect | 建筑师 🏗️ | evaluate_site | 评估候选区域，选择最佳位置 |
| engineer | 工程师 ⚙️ | plan_infrastructure | 规划基础设施建设方案 |
| energy_specialist | 能源专家 ⚡ | design_energy_system | 设计能源系统（太阳能/核聚变） |
| life_support_specialist | 生命支持专家 🌱 | configure_life_support | 配置生命支持系统 |

## 工作流可视化

运行 `--demo` 或 `--visualize` 会展示 ASCII 流程图：

```
============================================================
工作流：建设蓝晶星研究站
============================================================

🔬 地质勘探 (地质学家)
   ↓
🏗️ 选址分析 (建筑师)
   └─ 依赖: '地质勘探'
   ↓
⚙️ 基础建设 (工程师)
   └─ 依赖: '选址分析'
   ↓
⚡ 能源系统 (能源专家)
   └─ 依赖: '基础建设'
   ↓
🌱 生命支持 (生命支持专家)
   └─ 依赖: '能源系统'
```

## 技术亮点

### 1. 拓扑排序（Kahn 算法）

```python
def topological_sort(self) -> List[Task]:
    in_degree = {task: len(task.depends_on) for task in self.tasks}
    queue = [task for task in self.tasks if in_degree[task] == 0]
    result = []
    
    while queue:
        task = queue.pop(0)
        result.append(task)
        
        for downstream in task.downstream:
            in_degree[downstream] -= 1
            if in_degree[downstream] == 0:
                queue.append(downstream)
    
    if len(result) != len(self.tasks):
        raise CycleError("检测到依赖环！")
    
    return result
```

### 2. Context 自动注入

上游任务的输出自动格式化为下游 Agent 的 context：

```python
def _format_context(self, task: Task) -> str:
    lines = []
    for dep in task.depends_on:
        agent_info = get_agent_info(dep.agent_role)
        lines.append(f"### {agent_info['emoji']} {agent_info['name']}（{dep.name}）")
        lines.append(dep.result or "(无输出)")
    return "\n".join(lines)
```

### 3. 实时进度展示

```python
on_task_start, on_task_complete = make_task_callbacks()

workflow.run(
    client=client,
    model=model,
    on_task_start=on_task_start,
    on_task_complete=on_task_complete,
)
```

## 验收确认

- [x] Workflow 类支持 add_task / topological_sort / run
- [x] Task 类有 5 种状态（pending/ready/running/completed/failed）
- [x] Kahn 算法检测依赖环并抛 CycleError
- [x] 上游输出自动注入下游 context
- [x] 5 个 Agent 角色各有专属工具
- [x] ASCII 流程图展示 DAG 结构
- [x] 实时进度展示（on_task_start / on_task_complete 回调）
- [x] --demo 运行 5 任务预定义工作流
- [x] --interactive 支持用户自定义工作流
- [x] --visualize 只展示结构不执行

## 项目复盘

### 学到的内容

- **声明式 vs 命令式编排**：add_task 定义"是什么"，引擎负责"怎么做"
- **DAG 双向链表**：除了 depends_on 还需 downstream，方便拓扑排序时更新入度
- **Kahn 算法天然带环检测**：排序节点数 < 总节点数即存在环
- **Context 注入是编排的核心价值**：Agent 不需要知道上游是谁，引擎自动串联
- **回调机制 > 日志**：on_task_start/complete 让调用方控制展示，而非引擎内部硬编码 print

### 与项目 10 的差异

| 维度 | 项目 10 (planning-and-goal-tree) | 项目 17 (workflow-orchestration) |
|------|--------------------------------|--------------------------------|
| 用途 | 单 Agent 任务分解 + 动态重规划 | 多 Agent 协作编排 |
| 结构 | 嵌套树 + 运行时 DAG | 静态 DAG |
| 执行模式 | Plan→Execute→Re-plan 循环 | 一次性顺序执行 |
| 失败处理 | 局部重规划（子树替换） | 失败即终止 |
| 动态性 | 高（运行时展开/重规划） | 低（声明后不变） |

## 下一步扩展

- [ ] 并行执行：同一层级的独立任务可并发
- [ ] 失败重试：单任务失败后自动重试 N 次
- [ ] 条件分支：根据上游结果选择不同分支
- [ ] 持久化：保存工作流状态到 JSON/DB，支持断点恢复
- [ ] 可视化 Web UI：实时展示 DAG 执行状态

## 参考资料

- 项目 10 (`planning-and-goal-tree`)：DAG 拓扑排序的代码基础
- 项目 15 (`multi-agent-debate`)：多 Agent 协作的经验
- Kahn 拓扑排序算法：[维基百科](https://en.wikipedia.org/wiki/Topological_sorting#Kahn's_algorithm)
