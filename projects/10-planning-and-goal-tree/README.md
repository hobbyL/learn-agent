# 10-planning-and-goal-tree：任务分解与目标树 Agent

**状态**: ✅ 已完成

学习 LLM 驱动的**任务规划与分解**能力：把一个复杂的高层目标拆解为子任务 DAG（有向无环图），按依赖顺序执行，并在子任务失败时触发**局部 re-planning**。核心区别于 03-ReAct（单步推理）和 04-Reflexion（重试修正）——本项目聚焦"先规划再执行"的认知架构层，实现 **Plan → Execute → Re-plan** 双层循环。

## 核心特性

### 混合规划模式（初始全计划 + 执行中动态展开）
- **初始规划**：Agent 拿到高层目标后，用 LLM + `json_schema` 强制模式一次性生成完整目标树（DAG）
- **执行中动态展开**：执行某子任务时若发现它其实包含多个独立步骤，可动态展开成更细的子树（可选，`ENABLE_EXPANSION=true` 开启）
- 复用 09 的 `get_json_schema()` + `_enforce_strict_schema()` 保证计划 100% 可解析为 Pydantic 对象

### DAG 目标树（扁平节点 + depends_on 依赖边）
- 每个 `SubTask` 节点用 `depends_on` 表达跨分支依赖（如"建实验室"同时依赖"居住舱"和"太阳能阵列"）
- `goal_tree.py` 用 **Kahn 拓扑排序**求可执行顺序，构建时即检测循环依赖
- 状态机：`pending → ready → running → done / failed`，被重规划替换的旧节点标记 `skipped`

### LLM 驱动执行（内层 ReAct 循环）
- 每个叶子子任务由 LLM 通过 Function Calling（ReAct 内层循环）自主完成
- 工具直接操作**有状态的世界**：`mine_resource`（采集资源）、`build_module`（建造模块）、`check_environment`（环境检查）、`transport`（运输）、`check_inventory`（查库存）、`lookup`（查询知识库）
- 收尾用 `report_result(success, reason)` 结构化工具判定成败——而非解析自然语言，避免"我觉得完成了"这类歧义

### 局部重规划（失败即触发 + 影响范围分析）
- 子任务失败 → 把失败原因 + 当前树状态 + 库存快照反馈给规划 LLM
- 只重新规划受影响的子树（`affected_task_ids`），未受影响的已完成任务保留不动
- 下游依赖自动重定向到替换任务，最多 re-plan N 次（默认 3）

## 太空基地世界：新曙光基地

虚构月球背面「新曙光基地」，**32 个实体**天然具备多步骤、强依赖、易失败的特性：

| 类别 | 数量 | 示例 | 作用 |
|------|------|------|------|
| 资源 | 8 | 钛矿、硅晶、氦-3、水冰、碳纤维、稀土、铝合金、聚合物 | 有库存/采集难度，模块建造的消耗品 |
| 模块 | 8 | 居住舱、太阳能阵列、实验室、通信塔、生命维持系统、储物仓、对接口、推进器 | 有材料需求 + 前置依赖，构成 DAG 主干 |
| 设备 | 6 | 采矿机器人、3D打印机、机械臂、焊接单元、运输飞船、诊断仪 | 模块建造的前置工具 |
| 团队 | 5 | 工程队、采矿队、科研组、后勤组、指挥中心 | 调度维度 |
| 环境事件 | 5 | 太阳风暴、流星雨、轨道窗口、温度骤降、通信中断 | **失败触发器**（太阳风暴 → 舱外作业失败） |

**关键依赖示例**：
- 居住舱需要 钛矿×6 + 碳纤维×4 + 铝合金×3，用 3D打印机 + 机械臂
- 实验室必须在 居住舱 + 太阳能阵列 之后建造
- 太阳风暴期间所有"舱外"作业失败 → 触发局部重规划

## 架构

```
main.py (--demo / --interactive)
  ↓
planner_agent.py (外层：Plan → Execute → Re-plan 循环)
  ├─ planner.py         生成 / 重规划 / 动态展开目标树（LLM + json_schema）
  ├─ executor.py        执行单个叶子任务（ReAct 内层循环 + report_result 收尾）
  ├─ goal_tree.py       DAG 数据结构 + Kahn 拓扑排序 + 影响范围分析
  ├─ tools.py           操作有状态世界的工具（Function Calling）
  ├─ knowledge_base.py  新曙光基地世界（32 实体 + 可变状态）
  ├─ schemas.py         Pydantic：SubTask / Plan / ReplanResult / SubTaskExpansion
  └─ display.py         ASCII 目标树 + 依赖箭头 + 状态着色 + 进度条
```

**Plan → Execute → Re-plan 主循环**：
```python
plan = generate_plan(goal)           # 初始全计划 → 构建 GoalTree
while not tree.all_done():
    task = tree.get_ready_tasks()[0]      # 拓扑序取可执行叶子
    result = execute_subtask(task)        # 内层 ReAct 执行
    if result.success:
        tree.mark_status(task, DONE)
        # 可选：expand_subtask 动态展开
    else:
        tree.mark_status(task, FAILED)
        replan = replan_subtree(goal, tree, task, reason)  # 局部重规划
        tree.replace_subtree(replan.affected_ids, replan.replacements)
```

## 使用方法

### 安装依赖

如果使用 uv（推荐）：
```bash
cd projects/10-planning-and-goal-tree
uv venv
source .venv/bin/activate  # macOS/Linux
# 或 .venv\Scripts\activate  # Windows
uv pip install -r requirements.txt
```

如果使用 pip：
```bash
cd projects/10-planning-and-goal-tree
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 或 venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 配置环境变量
```bash
cp .env.example .env
# 编辑 .env，填入你的 OPENAI_API_KEY
```

### 运行模式

#### 1. 演示模式（默认）
```bash
python3 main.py --demo
# 或
python3 main.py
```
用预设目标"建造载人空间站 Phase-1"自动跑完整 Plan → Execute → Re-plan 流程，实时展示目标树状态变化。

#### 2. 交互模式
```bash
python3 main.py --interactive
```
输入自定义建设目标（如"建造一座带通信塔和实验室的科研基地"），Agent 规划并执行。

## 输出示例

### 目标树 ASCII 展示
```
┌─ 初始目标树
│  🎯 建造载人空间站 Phase-1
│  ○ t1 采集钛矿×6  [钛矿]
│  ○ t2 采集碳纤维×4  [碳纤维]
│  ├─ ○ t3 建造居住舱  [居住舱]  ← t1, t2
│  │  └─ ○ t4 建造生命维持系统  [生命维持系统]  ← t3
│
│  ░░░░░░░░░░░░░░░░░░░░░░░░ 0/4  完成 0  待办 4
└────────────────────────────────────────
```

### 子任务 ReAct 执行
```
▷ 执行子任务 [t1] 采集钛矿×6
  🧠 Thought: 先看看库存够不够
  ⚡ Action: check_inventory()
  👁 Observation: 钛矿×4，需要×6
  ⚡ Action: mine_resource(resource=钛矿, amount=2)
  👁 Observation: 采集成功，钛矿×6
  🏁 report_result → 成功：钛矿采集完成，库存充足
```

### 局部重规划事件
```
╭─ ↻ 局部重规划 #1
│  失败任务：建造居住舱
│  失败原因：太阳风暴，舱外作业被禁止
│  根因分析：居住舱是舱外作业，当前环境事件为太阳风暴，需先等待环境恢复
│  受影响任务：t3
│  替换为新任务：r1, r2
╰────────────────────────────────────────
```

## 文件结构

```
projects/10-planning-and-goal-tree/
├── knowledge_base.py    # 新曙光基地世界（32 实体 + 可变状态）
├── schemas.py           # Pydantic schema（SubTask/Plan/ReplanResult/SubTaskExpansion）
├── tools.py             # 有状态世界的 Function Calling 工具
├── goal_tree.py         # DAG 数据结构 + 拓扑排序 + 影响范围分析
├── executor.py          # 内层 ReAct 执行器（单个子任务）
├── planner.py           # 规划器（生成/重规划/动态展开）
├── planner_agent.py     # 外层编排（Plan→Execute→Re-plan 主循环）
├── display.py           # ANSI 着色展示（ASCII 目标树 + 进度条）
├── main.py              # CLI 入口（--demo/--interactive）
├── requirements.txt     # 依赖列表
├── .env.example         # 环境变量模板
├── notes.md             # 踩坑记录
└── README.md            # 本文件
```

## 学习收获

1. **Plan → Execute 双层架构**：外层规划器负责"拆解 + 排序 + 重规划"，内层执行器负责"用工具真正把单步做完"，职责清晰分离
2. **DAG 比线性列表更贴近真实任务**：`depends_on` 扁平依赖能表达跨分支依赖，配合 Kahn 拓扑排序天然求解执行顺序
3. **局部重规划的核心是"影响范围识别"**：不是失败就推倒重来，而是只作废受影响子树、保留已完成成果，把"部分完成状态"编码给 LLM 是关键难点
4. **结构化收尾信号 > 自然语言解析**：用 `report_result(success, reason)` 工具让执行器给出可靠的成败信号，reason 直接喂给重规划 LLM
5. **json_schema 强制模式是规划的可靠基座**：目标树的 id/depends_on 引用必须精确，强制模式把格式约束交给 API，prompt 专注讲清"依赖语义"

## 下一步

- 项目 11：human-in-the-loop（HITL）—— 在规划/执行的关键节点引入人工确认与干预
- 阶段 3：多 Agent 协作 —— 规划器与执行器拆成独立 Agent，通过结构化消息通信

## 相关资源

- [OpenAI Structured Outputs 文档](https://platform.openai.com/docs/guides/structured-outputs)
- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)
- [Kahn's Algorithm（拓扑排序）](https://en.wikipedia.org/wiki/Topological_sorting)
- 本项目参考：03-react-agent（内层推理链）、04-agent-reflection（外层循环结构）、09-structured-output（json_schema 强制模式 + schema 复用）
