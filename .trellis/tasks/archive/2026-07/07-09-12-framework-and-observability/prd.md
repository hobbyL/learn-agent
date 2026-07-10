# 12-framework-and-observability

## Goal

用 LangGraph 重新实现项目 03（ReAct Agent）的核心功能，通过三路对比展示：
**手写纯文本 ReAct → 手动 StateGraph（Function Calling）→ `create_react_agent`（prebuilt）**

学习目标：清楚看出框架在每一层抽象掉了什么，手写实现需要自己造什么。
同时轻量集成 LangSmith tracing，演示生产级 Agent 的可观测性基础。

## Requirements

1. **复用项目 03 的知识库和工具**
   - `knowledge_base.py` 原封不动复制（星云大陆场景）
   - `tools.py` 适配为 LangChain `@tool` 装饰器格式（保留原有 4 个工具：search / lookup / calculate / compare）
   - 手写版保留原有 `execute_tool()` + `TOOLS_SCHEMA` 接口不变

2. **三路实现**
   - `agent_v1_handwritten.py`：原手写纯文本 ReAct（从 03 直接复用 `react_agent.py`）
   - `agent_v2_stategraph.py`：手动 `StateGraph` + `ToolNode` + Function Calling（约 30 行）
   - `agent_v3_prebuilt.py`：`create_react_agent`（约 5 行）

3. **统一 main.py 入口**
   - `--compare`：用同一个问题跑三路实现，并排展示结果和步数
   - `--demo`：默认跑 v2（手动 StateGraph），完整展示 LangGraph 的节点/边/状态流转
   - `--version v1/v2/v3`：单独运行某一路实现

4. **Checkpointer 演示**
   - v2/v3 均使用 `InMemorySaver`
   - demo 模式展示同一 thread 的多轮对话（第二个问题复用已有 thread_id）

5. **LangSmith 轻量集成**
   - 检查环境变量 `LANGSMITH_TRACING` 是否设置
   - demo 启动时打印提示：是否开启 tracing，以及如何在 LangSmith 查看
   - 不强依赖 LangSmith 账号，未设置时正常运行

6. **对比展示输出**
   - `display.py`：ANSI 着色，三路实现用不同颜色区分
   - 展示每路实现的：步数、耗时、最终答案
   - compare 模式额外展示对比表格

## Acceptance Criteria

- [ ] `python main.py --demo` 正常运行，输出 v2（手动 StateGraph）完整推理过程
- [ ] `python main.py --compare` 正常运行，三路实现都能得到正确答案
- [ ] `python main.py --version v1` / `v2` / `v3` 各自独立运行
- [ ] v2/v3 支持同一 thread 的多轮对话（第二个问题不重置 thread）
- [ ] 未设置 `LANGSMITH_TRACING` 时，程序正常运行不报错
- [ ] 设置 `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` 后，可以在 LangSmith 看到 trace
- [ ] `requirements.txt` 包含 `langgraph`、`langchain-openai`、`langsmith`

## Definition of Done

- 三路实现均通过 demo 运行验证
- `README.md` 含三路对比表格、架构说明、快速开始
- `notes.md` 记录迁移过程中的关键差异和踩坑
- `notes/langgraph-pattern.md` 知识笔记已写
- 全局 `README.md` 和 `progress/2026-07.md` 已更新

## Technical Approach

### 文件结构

```
projects/12-framework-and-observability/
├── knowledge_base.py       # 从 03 复制（星云大陆，不修改）
├── tools.py                # 适配：原 execute_tool() + 新增 LangChain @tool 版本
├── agent_v1_handwritten.py # 从 03 react_agent.py 复制（纯文本 ReAct）
├── agent_v2_stategraph.py  # 手动 StateGraph + ToolNode（~30 行）
├── agent_v3_prebuilt.py    # create_react_agent（~5 行）
├── display.py              # ANSI 对比渲染
├── main.py                 # CLI 入口（--compare / --demo / --version）
├── requirements.txt
├── .env.example
├── README.md
└── notes.md
```

### 三路实现对比表（关键学习点）

| 维度 | v1 手写纯文本 | v2 手动 StateGraph | v3 prebuilt |
|------|------------|-------------------|-------------|
| 工具调用 | 文本正则解析 | Function Calling (bind_tools) | Function Calling |
| 循环控制 | for 循环 + continue/break | 条件边 + END | 内置 |
| messages 管理 | 手动 append | add_messages reducer | 内置 |
| 工具执行 | 手写 execute_tool() | ToolNode 自动 | ToolNode 内置 |
| 状态持久化 | 无 | InMemorySaver | InMemorySaver |
| 代码量（agent 层） | ~120 行 | ~35 行 | ~5 行 |
| 可视化 | 无 | graph.get_graph().draw_mermaid() | 同左 |

### LangSmith 集成方式

仅设置环境变量，零代码改动：
```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<key>
LANGSMITH_PROJECT=12-framework-and-observability
```

### 依赖

```
openai>=1.12.0
langgraph>=0.2.57      # interrupt() 需要 0.2.57+
langchain-openai>=0.2.0
langsmith>=0.1.0
python-dotenv>=1.0.0
```

## Decision (ADR-lite)

**Context**: LangGraph 标准 ReAct 基于 Function Calling，而项目 03 用纯文本格式。两者并非同一种实现，不能直接1:1替换。

**Decision**: 三路对比中，v1 保留纯文本 ReAct（保留项目 03 的原始学习价值），v2/v3 使用 Function Calling。这样展示了两代 ReAct 实现范式的差异，而不是强行用一种风格统一三路。

**Consequences**: compare 模式输出不完全同质（v1 输出 Thought 文本，v2/v3 输出结构化 tool_calls），需要在 display 层做适配展示。

## Out of Scope

- HITL（interrupt()）对照——留给需要时单独做
- LangGraph 并行/扇出（Send API）——属于 multi-agent 话题，放阶段 3
- LangSmith eval（评估）——留给项目 13
- LangGraph Studio / 可视化 UI——只做 draw_mermaid() 文本输出
- 流式输出（astream）——项目 05/06 已覆盖，不重复

## Technical Notes

- 项目 03 路径：`projects/03-react-agent/`（knowledge_base.py / tools.py / react_agent.py）
- 研究文件：`.trellis/tasks/07-09-12-framework-and-observability/research/langgraph-overview.md`
- LangGraph `interrupt()` 节点会从头重跑（不是从 interrupt 行恢复），单节点只能调用一次 interrupt
- `ChatOpenAI` 读取 `OPENAI_BASE_URL` 环境变量，与项目 03 的 `.env` 完全兼容
- `create_react_agent` 的完整 HITL 支持需要手动 StateGraph，prebuilt 只支持 interrupt_before/after

## Research References

- [`research/langgraph-overview.md`](research/langgraph-overview.md) — LangGraph 核心原语、ReAct 对比、HITL、LangSmith、自定义端点配置
