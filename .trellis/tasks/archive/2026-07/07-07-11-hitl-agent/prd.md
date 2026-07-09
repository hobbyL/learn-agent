# 11-hitl-agent：Human-in-the-Loop Agent

## Goal

学习 Agent 的**人机协作**模式：Agent 在执行过程中**主动识别需要人类介入的时机**，暂停执行、请求人类反馈，然后根据反馈恢复/调整执行。这是从"全自动 Agent"到"可控 Agent"的关键一步——让人类在关键决策点拥有否决权和引导权，同时不退化为纯手动操作。

区别于前序项目：
- 03-ReAct：全自动单步推理
- 04-Reflexion：全自动自我反思重试
- 10-Planning：全自动规划→执行→重规划

11 的核心新能力：**Agent 知道何时该停下来问人**。

## What I already know

* README 描述："Human-in-the-Loop：主动中断 + 人类反馈 + 恢复执行"
* 原始定位从"错误处理"重定位为 HITL（人机协作更有学习价值）
* 系列模式：每个项目有独立虚构知识库/世界观 + CLI demo/interactive 双模式
* 技术栈：OpenAI Function Calling + Pydantic + dotenv，复用 09 的 schema 工具链
* 10 的 planner_agent 已有完整的 Plan→Execute→Re-plan 循环可作为基座

## 场景世界观

**灾害应急指挥中心「明川市」**

虚构城市明川市遭遇复合灾害（地震 + 次生火灾 + 堰塞湖），Agent 作为指挥中心 AI 助手调度救援。
天然存在高风险决策点——资源分配、撤离决策、风险评估——Agent 不应独断，必须请求人类指挥官确认。

预计实体（~30 个）：
- 救援队（消防/医疗/搜救/工程/民兵）~5 支
- 灾区（震中/火灾区/堰塞湖/老城区/学校）~5 处
- 物资（帐篷/食品/医疗包/重型设备/通信设备）~5 类
- 基础设施（桥梁/医院/水电站/通信塔/避难所）~5 处
- 灾害事件（余震/火势蔓延/水位上涨/道路塌方/通信中断）~5 种
- 通信/天气/时间状态 ~5 项

**关键 HITL 触发示例**：
- 撤离老城区 5000 居民 vs 先加固堰塞湖坝体 → 资源冲突，需人类判断优先级
- 余震预警中是否派搜救队进入危楼 → 人命风险，Agent 不应独断
- 堰塞湖水位超警戒线，是否主动泄洪（淹没下游农田保住城区）→ 重大取舍

## 核心设计决策

### HITL 触发机制：规则触发
- 工具层标记 `requires_approval: true`，调用前自动暂停
- 预定义条件列表：人命风险、不可逆操作、资源冲突、超阈值风险
- 优点：可预测、可测试、学习者容易理解触发逻辑

### 架构基座：纯 ReAct + HITL 检查点
- 内层是 ReAct 循环（对齐 03），在特定工具调用前插入审批检查点
- 不做任务分解/DAG，聚焦学习 HITL 本身，不与 10 重复
- 新知识点集中在 HITL 机制设计，而非重复规划架构

## Assumptions (temporary)

* 交互方式是 CLI stdin/stdout（不涉及 Web UI）
* HITL 的"人类"在 demo 模式下可以用预设回答模拟

## Open Questions

* ~~虚构场景/世界观选择~~ → ✅ 灾害应急指挥中心「明川市」
* ~~HITL 介入触发机制~~ → ✅ 规则触发：工具/决策标记 `requires_approval`，预定义条件列表触发暂停
* ~~架构基座~~ → ✅ 纯 ReAct + HITL 检查点（不复用 10 的 Plan→Execute）
* ~~人类反馈的粒度和形式~~ → ✅ 三档选择：approve / reject+替代指令 / provide info
* ~~demo 模式如何模拟人类交互~~ → ✅ 预设剧本（scenarios.py），覆盖 approve/reject/provide_info 三种路径

### 人类反馈形式：三档选择
- **approve**：批准执行原方案
- **reject + 替代指令**：否决并给出自然语言指令，Agent 据此调整行动
- **provide info**：补充 Agent 缺少的信息（如"上游实际降雨量 80mm"）

### Demo 模式：预设剧本
- `scenarios.py` 定义完整演示剧本，每个 HITL 检查点对应预设回答
- 剧本覆盖三种反馈类型（approve/reject/provide_info），展示完整 HITL 能力
- 可重复、可控、无人值守

### MVP 扩展点

1. **灾害随时间恶化**：世界状态随 Agent 步数推进恶化（水位上涨、火势蔓延），人类拖延决策有后果——展示"HITL 不是免费的，响应速度也是约束"
2. **reject 容错路径**：人类 reject 后的替代指令不可执行时（如"派直升机"但无直升机），Agent 报告不可行并再次请求，设连续 reject 上限保护

## Requirements

* Agent 能在执行中主动识别"需要人类确认"的时机并暂停（规则触发）
* 人类三档反馈：approve / reject+替代指令 / provide info
* Agent 根据反馈恢复执行（reject 时解析人类指令调整行动）
* reject 后指令不可执行 → Agent 报告原因并二次请求（上限 3 次）
* 灾害随步数推进恶化（水位/火势/余震），人类延迟决策有可观测后果
* 可视化展示 HITL 交互过程（对齐系列的 display 模块风格）
* demo（预设剧本无人值守）+ interactive（真实 stdin）双模式

## Acceptance Criteria

* [ ] Agent 在 `requires_approval` 工具调用前自动暂停
* [ ] approve → Agent 执行原方案并继续
* [ ] reject + 替代指令 → Agent 解析指令调整行动
* [ ] reject 后指令不可执行 → Agent 报告不可行并再次请求
* [ ] provide info → Agent 将信息纳入后续推理
* [ ] 灾害状态随步数推进恶化，延迟决策后果可在 display 中观测
* [ ] demo 模式无人值守跑完，覆盖三种反馈路径
* [ ] interactive 模式支持真实人类 stdin 交互
* [ ] 展示层清晰区分"Agent 自主执行"与"⏸ 等待人类"状态
* [ ] 连续 reject 超上限后 Agent 优雅终止并说明原因

## Definition of Done

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* 项目 README + 主目录 README + progress 月志 + notes 主题笔记 全部对齐

## Out of Scope (explicit)

* Web UI / 异步回调（纯 CLI）
* 多人协作（只有一个人类参与者）
* 复杂权限/审批链

## Technical Approach

### 文件结构
```
projects/11-hitl-agent/
├── knowledge_base.py    # 明川市世界（~30 实体 + 可变状态 + 时间恶化机制）
├── tools.py             # 救援工具（部分标记 requires_approval）+ execute_tool()
├── schemas.py           # HITLRequest / HITLResponse / Pydantic models
├── hitl.py              # HITL 核心：检查点拦截 + 反馈解析 + 容错（二次请求上限）
├── agent.py             # ReAct 循环 + HITL 检查点集成
├── scenarios.py         # demo 预设剧本（覆盖三种反馈路径）
├── display.py           # ANSI 着色（区分自主执行 / ⏸等待人类 / 灾害恶化提示）
├── main.py              # CLI（--demo / --interactive）
├── requirements.txt
├── .env.example
├── notes.md
└── README.md
```

### 核心数据流
```
main.py → agent.py (ReAct loop)
  ├─ LLM 返回 tool_call
  ├─ hitl.py 检查 requires_approval
  │   ├─ 不需要 → 直接执行 tools.py
  │   └─ 需要 → 暂停，调用 human_input()
  │       ├─ demo: scenarios.py 返回预设回答
  │       └─ interactive: stdin 读取真实输入
  │       → 解析为 HITLResponse (approve/reject/info)
  │       → approve: 执行原工具
  │       → reject: 将替代指令注入 messages，继续 ReAct
  │       → info: 将信息追加到 context，继续 ReAct
  ├─ knowledge_base.py 每轮 tick() 恶化灾害状态
  └─ display.py 渲染每步状态
```

### 关键设计点
1. **工具分层**：低风险工具（查询类）直接执行；高风险工具（调度/撤离/泄洪）标记 `requires_approval`
2. **时间恶化**：`knowledge_base.tick()` 每步推进世界状态，水位+2cm/步、火势扩散1区域/3步
3. **容错循环**：reject→执行不可行→报告→再次请求，上限 3 次后 Agent 声明僵局并终止当前决策
4. **display 状态机**：EXECUTING(绿) / WAITING_HUMAN(黄闪) / DISASTER_UPDATE(红) 三种视觉状态

## Technical Notes

* 前序项目参考：03-react-agent（ReAct 循环基座）、10-planning-and-goal-tree（display 模块风格）
* 系列一贯模式：knowledge_base.py + tools.py + schemas.py + display.py + main.py
* 每个项目独立虚构世界，约 25-35 实体规模
* 复用 09 的 `get_json_schema()` + `_enforce_strict_schema()` 用于 HITLRequest schema
