# 12 · Framework & Observability

> LangGraph 框架对照学习：三路 ReAct 实现对比 + LangSmith 可观测性入门

---

## 目标

用 LangGraph 重新实现项目 03（ReAct Agent）的核心功能，通过**三路对比**展示框架在每一层抽象掉了什么：

```
v1 手写纯文本 ReAct  →  v2 手动 StateGraph  →  v3 create_react_agent
```

---

## 三路实现对比

| 维度 | v1 手写纯文本 | v2 手动 StateGraph | v3 prebuilt |
|------|------------|-------------------|-------------|
| 工具调用 | 纯文本正则解析 | Function Calling (bind_tools) | Function Calling |
| 循环控制 | for 循环 + continue/break | 条件边 + END | 内置 |
| messages 管理 | 手动 append | add_messages reducer | 内置 |
| 工具执行 | 手写 execute_tool() | ToolNode 自动 | ToolNode 内置 |
| 状态持久化 | 无 | InMemorySaver | InMemorySaver |
| 代码量（agent 层） | ~130 行 | ~35 行 | ~5 行 |
| 可视化 | 无 | draw_mermaid() | 同左 |
| 多轮对话 | 无（每次重置） | 同 thread_id 即保留 | 同左 |

---

## 文件结构

```
projects/12-framework-and-observability/
├── knowledge_base.py       # 星云大陆虚构知识库（从 03 复制，不修改）
├── tools.py                # 双接口：原有 execute_tool/TOOLS_SCHEMA + LangChain @tool 版本
├── agent_v1_handwritten.py # 手写纯文本 ReAct（03 react_agent.py 复用）
├── agent_v2_stategraph.py  # 手动 StateGraph + ToolNode + InMemorySaver
├── agent_v3_prebuilt.py    # create_react_agent（~5 行核心）
├── display.py              # ANSI 着色，三路用不同颜色，对比表格
├── main.py                 # CLI 入口
├── requirements.txt
├── .env.example
├── notes.md                # 迁移过程关键差异和踩坑
└── notes/
    └── langgraph-pattern.md  # LangGraph 核心模式知识笔记
```

---

## 快速开始

### 1. 安装依赖

```bash
cd projects/12-framework-and-observability
uv venv .venv --python 3.13
source .venv/bin/activate
uv pip install -r requirements.txt
```

### 2. 配置环境

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY 和 OPENAI_BASE_URL
```

### 3. 运行

```bash
# v2 完整演示（推荐首次运行）
python main.py --demo

# 三路实现并排对比
python main.py --compare

# 单独运行某路
python main.py --version v1
python main.py --version v2
python main.py --version v3
```

---

## LangSmith Tracing（可选）

无需修改任何代码，仅设置环境变量即可开启：

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=<your-key>
export LANGSMITH_PROJECT=12-framework-and-observability
```

在 [smith.langchain.com](https://smith.langchain.com) 注册免费账号后，可以可视化查看每次 Agent 运行的完整 trace：包括每个节点执行、LLM 调用、工具调用的耗时和输入输出。

---

## 图结构（v2/v3 共享）

```
__start__ → agent → (有 tool_calls?) → tools → agent → ... → __end__
                 ↘ __end__（无 tool_calls）
```

由 `draw_mermaid()` 生成，demo 模式自动打印。

---

## 关键学习点

1. **框架价值**：v2 把 v1 的 for 循环 + append + execute_tool 替换为：条件边 + add_messages reducer + ToolNode，代码量从 ~130 行降到 ~35 行，逻辑更清晰。

2. **Checkpointer 的意义**：v2/v3 用 `InMemorySaver` 在每步后快照 state，同一 `thread_id` 可跨 `invoke()` 调用连续对话（不丢上下文）。v1 无此能力。

3. **两代 ReAct 范式**：v1（纯文本格式）是 ReAct 论文原始设计，LLM 显式输出 Thought/Action。v2/v3（Function Calling）是工程化演进，推理隐式、结构可靠。学习时两者都应理解。

4. **LangSmith 零代码集成**：对 LangChain 模块来说，tracing 只需环境变量，无需改动业务代码。

---

## 知识库场景

复用项目 03 的"星云大陆"虚构知识库（~25 个实体），包含王国、城市、人物、物品等，强迫 Agent 用工具而不是用训练数据回答。

经典多步问题：
- `"星辰王国和月影王国，哪个人口更多？多多少？"`（需 compare 或两次 lookup + calculate）
- `"星辰王国国王的导师住在哪里？"`（需三步串联：查国王→查导师→查居住地）
