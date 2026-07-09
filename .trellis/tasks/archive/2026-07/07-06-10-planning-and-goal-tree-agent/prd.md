# 10-planning-and-goal-tree：任务分解与目标树 Agent

## Goal

学习 LLM 驱动的任务规划与分解能力：将复杂目标拆解为子任务 DAG（有向无环图），按依赖顺序执行，并在子任务失败时触发局部 re-planning。核心区别于 03-ReAct（单步推理）和 04-Reflexion（重试修正）——本项目聚焦"先规划再执行"的认知架构层，实现 **Plan → Execute → Re-plan** 双层循环。

## Requirements

### 场景：太空基地建设

虚构世界"太空基地建设"，天然具备多步骤、强依赖、易失败的特性，适合演示规划与重规划。

**知识库规模：丰富版 ~35 实体**，包含：
- **资源**（钛矿、硅晶、氦-3、水冰、碳纤维、稀土…）— 有存量、采集难度
- **模块**（居住舱、太阳能板、推进器、通信塔、实验室、温室、维修坞…）— 有材料需求、建造时间、前置依赖
- **设备/工具**（采矿机器人、3D打印机、运输飞船、机械臂…）— 执行任务的前置条件
- **人员/团队**（工程队、科研组、运输队…）— 增加调度复杂度
- **环境事件**（太阳风暴、轨道窗口、陨石预警…）— 制造失败场景的触发器

**关键关系（支撑 DAG）：**
- 模块需要资源（居住舱需要钛矿×5 + 碳纤维×3）
- 模块需要设备（组装需要 3D 打印机 / 机械臂）
- 模块有前置依赖（实验室必须在居住舱之后）
- 环境事件打断执行（太阳风暴 → 舱外作业失败）

### 规划方式：混合模式（初始全计划 + 执行中动态调整）

1. **初始规划**：Agent 拿到高层目标后，用 LLM + json_schema 强制模式一次性生成完整目标树（DAG）
2. **执行中动态调整**：执行某子任务时若发现需要进一步拆解，动态展开子树
3. 复用 09 的 `get_json_schema()` + `_enforce_strict_schema()` 保证计划可解析

### 目标树数据结构：DAG 树形 + 依赖边

每个节点：
```
TaskNode {
  id: str
  name: str
  description: str
  status: Literal["pending", "in_progress", "done", "failed"]
  depends_on: list[str]      # 依赖的其他节点 id（跨分支依赖）
  subtasks: list[str]        # 子节点 id（层级拆解）
  estimated_steps: int
}
```
- 用 Pydantic 定义，json_schema 强制模式生成
- 可视化：终端 ASCII 树 + 依赖关系箭头 + 拓扑序标注

### 执行引擎：LLM 驱动执行（ReAct 内层循环）

- 每个叶子子任务由 LLM 通过 ReAct 推理 + Function Calling 完成
- 工具直接操作知识库状态（资源扣减、模块状态变更、环境检查）
- 工具示例：`mine_resource(resource, amount)`、`build_module(module)`、`check_environment()`、`transport(item, from, to)`、`query_inventory()`
- 双层结构：外层 Plan（规划器）+ 内层 Execute（每个子任务一个 ReAct 循环）

### Re-planning：失败即触发 + 局部重规划

- 子任务执行失败 → 将失败原因 + 当前状态反馈给规划 LLM
- 只重新规划受影响的子树，未受影响的已完成任务保留不动
- 学习重点：识别"影响范围" + 把部分完成状态编码给 LLM
- 最多 re-plan N 次（默认 3），避免无限循环

### 运行模式：--demo + --interactive

- **--demo**：预设完整目标（如"建造载人空间站 Phase-1"），自动跑完整 Plan→Execute→Re-plan 流程，实时展示目标树状态变化
- **--interactive**：用户输入自定义建设目标，Agent 规划并执行
- ANSI 着色沿用前序项目风格（不同状态不同颜色）

## Acceptance Criteria

* [ ] 知识库包含 ~35 个实体，覆盖资源/模块/设备/人员/环境事件，关系支撑多层依赖
* [ ] schemas.py 用 Pydantic 定义 TaskNode + Plan 结构，json_schema 强制模式生成
* [ ] 初始规划：能将复杂目标分解为 3+ 层的子任务 DAG
* [ ] 执行中动态调整：叶子任务可按需进一步拆解
* [ ] 执行引擎：每个子任务通过 LLM ReAct + Function Calling 完成，工具操作知识库状态
* [ ] 依赖顺序：按拓扑序执行子任务，依赖未完成则不执行
* [ ] 失败检测：环境事件/资源不足导致子任务失败可被正确捕获
* [ ] 局部 re-planning：失败时只重规划受影响子树，保留已完成任务，最多 3 次
* [ ] 可视化：目标树 ASCII 展示 + 依赖箭头 + 状态着色 + 拓扑序
* [ ] --demo 模式跑完整流程，--interactive 支持自定义目标
* [ ] 所有依赖在 requirements.txt 中列出

## Definition of Done

* 代码实现完整，--demo / --interactive 均可运行
* notes.md 记录踩坑点（规划 prompt 设计、DAG 校验、局部重规划状态编码等）
* README.md 含用法说明 + 状态标记 + 架构图
* .env.example 提供配置模板
* 主 README.md 更新进度（10/18，阶段 2 进度 6/8）
* notes/ 目录新增 planning-and-goal-tree.md 主题笔记

## Technical Approach

**双层架构：**
```
main.py (--demo / --interactive)
  ↓
planner_agent.py (外层：Plan → Execute → Re-plan 循环)
  ├─ planner.py     生成/重规划目标树（LLM + json_schema）
  ├─ executor.py    执行单个叶子任务（ReAct 内层循环）
  ├─ goal_tree.py   DAG 数据结构 + 拓扑排序 + 影响范围分析
  ├─ tools.py       操作知识库状态的工具（Function Calling）
  ├─ knowledge_base.py  太空基地世界（~35 实体 + 状态）
  ├─ schemas.py     Pydantic：TaskNode / Plan / ReplanRequest
  └─ display.py     ASCII 目标树 + 依赖箭头 + 状态着色
```

**Plan → Execute → Re-plan 循环伪码：**
```python
plan = planner.create_plan(goal)           # 初始全计划
while not plan.all_done() and replans < MAX:
    task = plan.next_executable_task()      # 拓扑序取可执行叶子
    if task.needs_decomposition():
        plan.expand(task, planner.decompose(task))  # 动态展开
        continue
    result = executor.run(task)             # ReAct 内层执行
    if result.failed:
        affected = plan.affected_subtree(task)
        new_subtree = planner.replan(goal, plan.state(), task, result.reason)
        plan.replace_subtree(affected, new_subtree)
        replans += 1
    else:
        task.mark_done()
```

## Decision (ADR-lite)

**Context**: 需要在"规划复杂度"与"学习聚焦度"间平衡。规划方式、执行方式、重规划粒度三个维度各有多种选择。

**Decision**:
- 规划：混合模式（初始全计划 + 动态调整）——兼顾目标树可视化与真实 Agent 灵活性
- 执行：LLM 驱动 ReAct 内层——完整覆盖 Plan+Execute 双层结构（区别于纯模拟执行）
- 重规划：局部重规划——学习"影响范围识别"与"部分状态编码"，比全局重规划更有价值
- 数据结构：DAG 树形+依赖边——支持跨分支依赖，适合目标树教学

**Consequences**:
- Token 消耗较高（每个子任务一轮 ReAct），--demo 需控制规模
- 实现量中等偏大（双层循环 + DAG 操作 + 动态展开），但学习覆盖面完整
- 局部重规划的"影响范围分析"是最难点，需要仔细设计 DAG 依赖追踪

## Out of Scope (explicit)

* 不做多 Agent 协作（留给阶段 3）
* 不做并发子任务执行（顺序执行即可，但按 DAG 拓扑序）
* 不做持久化存储（内存中完成）
* 不做 Human-in-the-Loop（留给 11-hitl）
* 不做 --compare 模式（本项目重点是展示完整流程，非方法对比）

## Technical Notes

* 项目结构沿用：main.py + agent 层 + knowledge_base.py + display.py + schemas.py 模式
* 可复用 09 的 `get_json_schema()` 和 `_enforce_strict_schema()` 工具函数
* 执行层 ReAct 可参考 03-react-agent 的推理链实现
* ANSI 着色沿用之前项目风格（pending=灰 / in_progress=黄 / done=绿 / failed=红）
* 环境事件作为失败触发器：执行前 check_environment()，风暴期舱外作业失败
