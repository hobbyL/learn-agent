# Journal - name (Part 1)

> AI development session journal
> Started: 2026-06-25

---



## Session 1: 完成项目01-simple-agent：手写 Agent + 修复 date_calculator 多轮历史失效问题

**Date**: 2026-06-26
**Task**: 完成项目01-simple-agent：手写 Agent + 修复 date_calculator 多轮历史失效问题
**Branch**: `main`

### Summary

完成 01-simple-agent 全部实现：OpenAI Function Calling + 6 个工具（计算器、时间、日期计算、单位换算、文本统计、天气）。修复两个 LLM 行为 bug：(1) get_current_time description 不完善导致星期推算错误；(2) date_calculator 在对话历史中有日期时被 LLM 跳过（惰性优化）。两个 bug 都通过强化 description 的强制约束修复，并记录到 notes/tool-calling.md 作为通用教训。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `f05da57` | (see git log) |
| `c4189bb` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: 将工具配置目录加入 gitignore

**Date**: 2026-06-26
**Task**: 将工具配置目录加入 gitignore
**Branch**: `main`

### Summary

将 .trellis/ .claude/ .codex/ .agents/ AGENTS.md 加入 .gitignore，并用 git rm --cached 移出追踪，本地文件保留。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `04a413e` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 3: 完成 03-react-agent：ReAct 推理链 + 虚构知识库 + 双模式对比

**Date**: 2026-06-27
**Task**: 完成 03-react-agent：ReAct 推理链 + 虚构知识库 + 双模式对比
**Branch**: `main`

### Summary

实现了完整的 ReAct Agent 项目（03-react-agent）。核心亮点：纯文本 ReAct 循环（Thought/Action/Observation）对照 Function Calling 直接调用；虚构知识库星云大陆（24实体）强迫 LLM 真正走推理链；ANSI 彩色推理链可视化 + compare 双模式并排对比。踩坑与修复：search 去重 bug、LLM markdown 格式正则失效、跳步检测+防失忆、删除过于粗暴的 MIN_OBSERVATIONS 守卫。核心收获：ReAct 让幻觉可审计（错误有迹可循）；模型能力是框架的天花板；Direct 并行效率更高但 ReAct 透明度更强。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `4222ac7` | (see git log) |
| `251c876` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 4: 修正进度日志 2026-06-27 星期标注（周五→周六）

**Date**: 2026-06-27
**Task**: 修正进度日志 2026-06-27 星期标注（周五→周六）
**Branch**: `main`

### Summary

progress/2026-06.md 中两处「2026-06-27（周五）」均改为「周六」，其他内容不变。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `04e0104` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 5: 提炼 03-react-agent 实战经验到 notes/react-pattern.md

**Date**: 2026-06-27
**Task**: 提炼 03-react-agent 实战经验到 notes/react-pattern.md
**Branch**: `main`

### Summary

在 notes/react-pattern.md 追加「从实践中学到的教训」章节，收录 6 条 03 实战经验：ReAct 幻觉可审计、跳步 bug 代码护栏（关键词检测+防失忆）、模型能力天花板/ReAct 是放大镜、ReAct vs Direct 性能对比（串行 7 步 vs 并行 4 步）、虚构数据设计模式、Function Calling 是工程化 ReAct。更新文件元数据（日期+来源项目）。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `6d79b4f` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 6: 补充 react-pattern.md 容错设计章节（第 6 条）

**Date**: 2026-06-27
**Task**: 补充 react-pattern.md 容错设计章节（第 6 条）
**Branch**: `main`

### Summary

在 notes/react-pattern.md 新增第 6 条「容错设计是 ReAct 循环的必要组成」：格式失败重试提示模板、最多 2 次重试策略（给机会 vs 避免 token 浪费）。原第 6 条 Function Calling 顺延为第 7 条。至此 react-pattern.md 共 7 条实战教训，内容完整无遗漏。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `ce151dd` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 7: 实现项目 04-agent-reflection（Reflexion 自我反思 Agent）

**Date**: 2026-06-28
**Task**: 实现项目 04-agent-reflection（Reflexion 自我反思 Agent）
**Branch**: `main`

### Summary

完成了 04-agent-reflection 项目的完整实现。设计阶段通过 brainstorm 确定了 Reflexion 四组件架构（Actor+Evaluator+Reflector+Memory），采用整轮反思风格、双轨评估器（GroundTruth+LLMJudge）、04 内部重写轻量 ReAct（独立自包含）、反思注入 system prompt 尾部（论文标准做法）、新建深海联盟知识库（32实体，含陷阱设计）。实现阶段生成了 11 个文件（3091 行），所有模块 import 链验证通过，10 个测试问题的答案路径已逐一验证可达。提炼了 notes/reflexion-pattern.md 知识笔记，更新了 spec 中的项目结构和质量规范文档。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `e7f52e4` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 8: 完成项目 04 文档收尾

**Date**: 2026-06-28
**Task**: 完成项目 04 文档收尾
**Branch**: `main`

### Summary

补全 04-agent-reflection 项目内 notes.md（3条踩坑记录：双评估器参数路由、实体名不一致、MAX_STEPS结构约束）；修正 README 日期 2026-06-27→2026-06-28；更新根 README 进度（4/12，阶段1收官）和月度进度日志

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `a33578b` | (see git log) |
| `2629fad` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 9: 修正 04 README 实体数量

**Date**: 2026-06-28
**Task**: 修正 04 README 实体数量
**Branch**: `main`

### Summary

README 知识库实体数量从'25+'改为实际的 32 个（通过 knowledge_base.py 计数验证）

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `3af194f` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 10: 完善 04 README 文件说明表描述

**Date**: 2026-06-28
**Task**: 完善 04 README 文件说明表描述
**Branch**: `main`

### Summary

test_questions.py 描述补充'10道，含答案路径验证'；顺带发现上次误判（-A10截断导致以为该行缺失，实际已存在）

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `2ce7b46` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 11: 修正 02/03 README 完成时间 + 进度统计

**Date**: 2026-06-28
**Task**: 修正 02/03 README 完成时间 + 进度统计
**Branch**: `main`

### Summary

02/03 README 补充完成时间字段（与 01 风格对齐）；进度日志笔记数量从'7篇'修正为'主题笔记4篇+项目笔记4篇=共8篇'

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `7f49d7a` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 12: 补充 04 README 完成标准表

**Date**: 2026-06-28
**Task**: 补充 04 README 完成标准表
**Branch**: `main`

### Summary

04 README 新增 '## ✅ 完成标准' 表格（11项），与 01~03 风格对齐；各项均已通过代码验证

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `21527b0` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 13: 修复根 README 里程碑表格空行

**Date**: 2026-06-28
**Task**: 修复根 README 里程碑表格空行
**Branch**: `main`

### Summary

移除里程碑表内部的空行，修复 Markdown 渲染时'🏗️ 完成阶段 3'一行变成普通文本的问题

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `e74779b` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 14: 更新阶段 2 规划

**Date**: 2026-06-28
**Task**: 更新阶段 2 规划
**Branch**: `main`

### Summary

阶段 1 复盘完成：阶段 2 从 4 个扩展为 6 个项目（新增 streaming/短期记忆/长期记忆拆分/结构化输出合并进规划/HITL重定位/框架对照），阶段 3 加入 MCP 变为 4 个，总计 16 个项目，待评估事项全部落地归档

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `562c4ed` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 15: 09-structured-output 实现与归档

**Date**: 2026-07-06
**Task**: 09-structured-output 实现与归档
**Branch**: `main`

### Summary

完成 09-structured-output 项目：3种输出模式(json_schema/json_object/text) × 4层提取难度，含重试机制、对比矩阵展示、知识库29实体。补充 notes/structured-output.md 主题笔记。归档 9 个历史任务。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `5ca69a1` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 16: 10-planning-and-goal-tree 实现与归档

**Date**: 2026-07-07
**Task**: 10-planning-and-goal-tree 实现与归档
**Branch**: `main`

### Summary

完成 10-planning-and-goal-tree 项目：Plan→Execute→Re-plan 双层认知架构，外层规划器生成子任务 DAG（Kahn 拓扑排序+环检测），内层 ReAct 执行器用 report_result 收尾工具判定成败，失败触发局部重规划（子树替换+依赖重定向）。太空基地「新曙光基地」知识库 32 实体。分 3 批子代理实现 13 文件，真实依赖验证 goal_tree/knowledge_base/schemas 跑通、executor/planner_agent mock 全链路通过。补充 notes/planning-and-goal-tree.md 主题笔记，回填 progress 月志 08/09/10 记录并修正星期，修复主 README 里程碑表格式。归档 10 任务。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `9c0fede` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 17: 实现 11-hitl-agent：Human-in-the-Loop 灾害应急指挥 Agent

**Date**: 2026-07-09
**Task**: 实现 11-hitl-agent：Human-in-the-Loop 灾害应急指挥 Agent
**Branch**: `main`

### Summary

实现 ReAct + HITL 检查点 Agent。场景：明川市 6.8 级地震复合灾害应急指挥中心。核心：rule-based requires_approval 触发 HITL 暂停，三层人类反馈（approve/reject+指令注入/provide_info 信息注入），灾害 tick() 恶化机制（水位/火势/余震），连续 reject 上限容错，ScriptedHandler demo 模式。修复 6 类 bug：dict-vs-list 迭代、7处字段名不一致、execute_tool 返回 dict 传给 OpenAI content、HITLCheckpoint/HITLRequest 混用、构造函数 kwarg 名、tick() 未在 continue 前调用。8 个模块全部集成验证通过。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `cee3a4c` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 18: 实现 12-framework-and-observability：LangGraph 三路 ReAct 对比 + LangSmith 集成

**Date**: 2026-07-10
**Task**: 实现 12-framework-and-observability：LangGraph 三路 ReAct 对比 + LangSmith 集成
**Branch**: `main`

### Summary

复用项目03星云大陆场景，实现三路LangGraph ReAct对比（v1手写纯文本/v2手动StateGraph/v3 create_react_agent），LangSmith轻量集成，Checkpointer多轮对话演示。拆分原12为12(框架对照)+13(observability)，总项目18→19。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `c2268f6` | (see git log) |
| `e5f86fd` | (see git log) |
| `81ec9d9` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete
