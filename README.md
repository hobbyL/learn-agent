# Agent 学习之旅

系统性学习 AI Agent 相关知识的完整路径。

---

## 🔥 当前正在学习

**状态**：阶段 2 进行中  
**已完成**：`01-simple-agent` ✅ · `02-tool-calling` ✅ · `03-react-agent` ✅ · `04-agent-reflection` ✅ · `05-streaming-agent` ✅  
**下一步**：`06-streaming-react`（流式 ReAct：边流边解析推理链）

---

## 📊 总体进度

**完成项目**：5 / 17  
**当前阶段**：阶段 2 - Agent 系统设计（1/7 项目已完成）  
**开始时间**：2026-06-25

```
阶段 1: Agent 核心原理        [██████████] 4/4 项目 ✅
阶段 2: Agent 系统设计        [█░░░░░░░░░] 1/7 项目
阶段 3: 多 Agent 系统         [░░░░░░░░░░] 0/4 项目（含 MCP）
阶段 4: 领域应用与优化        [待规划，阶段 1-3 后细化]
```

---

## 📋 学习路径（项目顺序表）

### 阶段 1：Agent 核心原理（2-3周）

| 编号 | 项目名称 | 描述 | 状态 | 完成时间 |
|------|---------|------|------|---------|
| 01 | [simple-agent](./projects/01-simple-agent/) | 手写最简 Agent，OpenAI Function Calling | ✅ 完成 | 2026-06-26 |
| 02 | [tool-calling](./projects/02-tool-calling/) | 工具系统架构：注册表 + 自动 Schema + 校验 | ✅ 完成 | 2026-06-27 |
| 03 | [react-agent](./projects/03-react-agent/) | ReAct 模式：显式推理链 + 虚构知识库 + 双模式对比 | ✅ 完成 | 2026-06-27 |
| 04 | [agent-reflection](./projects/04-agent-reflection/) | Reflexion：外层反思循环 + 双轨评估器 + 深海联盟知识库 | ✅ 完成 | 2026-06-28 |

### 阶段 2：Agent 系统设计（5-7周）

| 编号 | 项目名称 | 描述 | 状态 | 完成时间 |
|------|---------|------|------|---------|
| 05 | [streaming-agent](./projects/05-streaming-agent/) | 流式输出：streaming API + tool_calls delta 拼接 + 双视角展示 | ✅ 完成 | 2026-06-29 |
| 06 | streaming-react | 流式 ReAct：边流边解析推理链 + 实时 Thought/Action 展示 | ⏳ 未开始 | — |
| 07 | short-term-memory | 短期记忆：对话历史管理 + context 压缩 + 摘要策略 | ⏳ 未开始 | — |
| 08 | long-term-memory | 长期记忆：向量化存储 + 语义检索 + 跨 session 记忆 | ⏳ 未开始 | — |
| 09 | structured-output-and-planning | 结构化输出 + 任务分解与目标树 | ⏳ 未开始 | — |
| 10 | hitl-agent | Human-in-the-Loop：主动中断 + 人类反馈 + 恢复执行 | ⏳ 未开始 | — |
| 11 | framework-and-observability | 框架对照（LangGraph / OpenAI Agents SDK）+ tracing/eval | ⏳ 未开始 | — |

### 阶段 3：多 Agent 系统（3-4周）

| 编号 | 项目名称 | 描述 | 状态 | 完成时间 |
|------|---------|------|------|---------|
| 12 | mcp-tool-discovery | MCP 动态工具发现：运行时工具绑定 vs 静态注册表 | ⏳ 未开始 | — |
| 13 | multi-agent-debate | 辩论模式：多 Agent 投票决策 | ⏳ 未开始 | — |
| 14 | code-review-team | 代码审查团队（分工协作） | ⏳ 未开始 | — |
| 15 | workflow-orchestration | 工作流编排引擎 | ⏳ 未开始 | — |

### 阶段 4：领域应用与优化

> 待规划：阶段 1-3 完成后，再根据实际理解程度细化为具体可交付项目。
> 初步设想：选择一个垂直领域（Code / Research / Data / DevOps）做端到端 Agent，
> 并围绕成本、速度、准确性做优化。暂不设为"持续进行"，避免变成无止境的 TODO 黑洞。

---

## 🧭 待评估事项（滚动规划，不急于现在动手）

> 阶段 1 复盘（2026-06-28）：以下事项已完成评估，结论已落入阶段 2 规划。

### 项目边界（已解决）
- ~~**01 / 02 边界重叠**~~ → ✅ 已解决：02 定位为"工具系统架构"，边界清晰
- ~~**03 / 04 可能合并**~~ → ✅ 无需合并：侧重点不同（推理链可审计 vs 试错改进循环）
- ~~**错误处理是否单独立项**~~ → ✅ 已重定位为 09-hitl-agent（Human-in-the-Loop）

### 候选补充主题（已全部落地）
- ~~**上下文管理 / context 压缩**~~ → ✅ 合并进 06-short-term-memory
- ~~**结构化输出 & 可靠解析**~~ → ✅ 合并进 08-structured-output-and-planning
- ~~**流式输出 (streaming)**~~ → ✅ 独立为 05-streaming-agent（FC stream）+ 06-streaming-react（流式 ReAct）
- ~~**MCP 动态工具发现**~~ → ✅ 落地为 11-mcp-tool-discovery（阶段 3 开篇）
- ~~**框架对照节点**~~ → ✅ 落地为 10-framework-and-observability（含 tracing/eval）

> 原则：阶段 2 规划已锁定（7个项目，含 streaming 拆分），阶段 3 已调整（4个项目含MCP，编号12-15）。下一步直接开始 05-streaming-agent。

---

## 📖 快速导航

- [学习笔记](./notes/) - 按主题整理的知识精华
- [学习进度](./progress/) - 每日/每月学习日志
- [学习资源](./resources/) - 论文、文章、视频、开源项目
- [实践项目](./projects/) - 所有学习项目代码

---

## 💡 学习方法

1. **项目驱动**：每个阶段都有可交付的项目
2. **原理优先**：先手写理解原理，再学习框架
3. **记录踩坑**：在项目 `notes.md` 中记录问题和解决方案
4. **定期提炼**：将项目笔记中的通用知识提炼到主目录 `notes/`
5. **阶段复盘**：完成一个阶段后写总结，沉淀经验

---

## 📅 里程碑

| 日期 | 里程碑 | 说明 |
|------|--------|------|
| 2026-06-25 | 🚀 启动学习计划 | 创建学习结构，规划路径 |
| 2026-06-26 | ✅ 完成项目 01 | simple-agent，5工具全部验证通过 |
| 2026-06-27 | ✅ 完成项目 02 | tool-calling，注册表+手搓Schema+Pydantic校验+配置切换 |
| 2026-06-27 | ✅ 完成项目 03 | react-agent，ReAct推理链+虚构知识库+双模式对比+跳步检测 |
| 2026-06-28 | ✅ 完成项目 04 | agent-reflection，Reflexion外层循环+双轨评估器+深海联盟知识库 |
| 2026-06-28 | 🎉 完成阶段 1 | Agent 核心原理（4个项目）全部完成 |
| 2026-06-29 | ✅ 完成项目 05 | streaming-agent，FC流式+delta拼接+太空站联盟+双视角展示+compare对比 |
| 待定 | 🎓 完成阶段 2 | 构建 Agent 系统架构 |
| 待定 | 🏗️ 完成阶段 3 | 实现多 Agent 协作 |

---

**最后更新**：2026-06-29（05-streaming-agent 完成）
