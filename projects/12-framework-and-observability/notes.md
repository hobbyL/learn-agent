# 12-framework-and-observability · 开发笔记

## 迁移过程：从手写 ReAct → LangGraph

### 关键差异

#### 1. 工具定义方式

手写（v1）需要维护三套东西：
- `TOOLS` 字典（函数 + 描述 + 参数名）
- `TOOLS_SCHEMA`（OpenAI Function Calling 格式 JSON）
- `get_tool_descriptions()`（注入 prompt 的文本格式）

LangGraph（v2/v3）只需要 `@tool` 装饰器：
```python
@tool
def lookup_tool(entity: str, field: str) -> str:
    """精确查询某个实体的某个属性值。"""
    return lookup(entity, field)
```
docstring 同时作为工具描述，函数签名自动生成 JSON Schema，`bind_tools([lookup_tool])` 一行搞定。

#### 2. 循环控制

v1 手写：
```python
for step_num in range(1, max_steps + 1):
    ...
    if parsed.get("final_answer"):
        break
    if parsed.get("action"):
        observation = execute_tool(...)
        messages.append(...)
        continue
```

v2 LangGraph：
```python
def should_continue(state) -> Literal["tools", "__end__"]:
    if state["messages"][-1].tool_calls:
        return "tools"
    return "__end__"

builder.add_conditional_edges("agent", should_continue)
builder.add_edge("tools", "agent")
```
循环完全隐藏在图结构里。没有 `break`，没有 `continue`，纯声明式。

#### 3. messages 管理

v1：每次工具调用后手动 `messages.append({"role": "tool", ...})`。

v2/v3：`MessagesState` 用 `add_messages` reducer，每个节点只需 `return {"messages": [new_msg]}`，框架自动追加（不是覆盖）。这是 LangGraph 最典型的"状态+reducer"模式。

#### 4. ToolNode 自动执行

v1 手写 `execute_tool(action, action_input)` 函数，需要 try/except 处理参数错误。

v2/v3 用 `ToolNode(lc_tools)`，自动：
- 遍历 AI 消息中的所有 `tool_calls`
- 按名称找到对应工具函数
- 解析 `args` 并调用
- 把结果包装成 `ToolMessage` 追加到 state

一行代码代替十几行。

---

### 踩坑记录

#### create_react_agent 参数名变更

研究文档里写的是 `state_modifier` 参数，但实际安装的 `langgraph==1.2.8` 已经改名为 `prompt`：

```python
# 旧（0.2.x）：
create_react_agent(model, tools, state_modifier=SYSTEM_PROMPT)

# 新（1.x）：
create_react_agent(model, tools, prompt=SYSTEM_PROMPT)
```

解决：用 `inspect.signature()` 查实际参数名，不要直接信文档。

#### ChatOpenAI + 自定义端点的 503 模型不存在

`.env` 里 `OPENAI_MODEL=glm-5.1` 在当前端点不可用（渠道下线）。`ChatOpenAI` 的错误信息是 503 / `model_not_found`，和 `openai` SDK 的格式一致。

解决：先用 `client.models.list()` 查可用模型列表，再更新 `.env`。

#### InMemorySaver 多轮对话：必须在同一图实例上 invoke

每次 `build_graph()` 都创建新的 `InMemorySaver()`，历史 checkpoint 不会延续。

演示多轮对话时必须：
```python
graph = build_graph()           # 只 build 一次
config = {"configurable": {"thread_id": "same-id"}}

graph.invoke(q1, config=config)  # 第一轮
graph.invoke(q2, config=config)  # 第二轮——同一 graph，同一 InMemorySaver，有上下文
```

main.py 的 demo 模式已经正确处理了这个问题（直接调 `build_graph()` 一次）。

#### ToolMessage 里的 name 字段

`ToolMessage` 有 `.name` 属性（工具名），在 `display.py` 渲染 Observation 时用 `msg.name` 取工具名。
`AIMessage` 的 `tool_calls` 里每个 tool_call 是 dict，用 `tc['name']` 取名（不是 `.name`）。

---

### 架构选择说明

**为什么 v1 保留纯文本格式而不改成 Function Calling？**

ReAct 论文的原始设计就是文本格式（Thought/Action/Observation）。Function Calling 是 OpenAI 的工程化包装，它隐藏了 Thought 的显式输出。

三路对比的价值在于：
- v1 展示"能理解原理但费力造轮子"的状态
- v2 展示"理解框架原语，能驾驭抽象"的状态
- v3 展示"框架全隐藏，5 行交付"的状态

如果把 v1 也改成 Function Calling，就失去了展示两代 ReAct 范式差异的机会。

---

### LangGraph 版本说明

本项目使用 `langgraph==1.2.8`（2026-07 安装）。

和研究文档（基于 ~1.0）的主要差异：
- `create_react_agent` 的 `state_modifier` → `prompt`
- `InMemorySaver` 引入路径：`from langgraph.checkpoint.memory import InMemorySaver`（未变）
- `MessagesState` 依然可用
- `interrupt()` 函数依然可用（本项目未用到）
