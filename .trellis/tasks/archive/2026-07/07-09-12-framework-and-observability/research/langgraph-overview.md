# Research: LangGraph Overview

- **Query**: LangGraph core primitives, ReAct loop, HITL, observability, custom OpenAI endpoint
- **Scope**: external (official docs + code examples)
- **Date**: 2026-07-09

---

## 1. Core Primitives

### StateGraph

`StateGraph` 是 LangGraph 的核心构建类，接受一个 state schema（TypedDict / Pydantic / dataclass），以声明式 API 定义节点和边。

```python
from langgraph.graph import StateGraph, START, END
from typing_extensions import TypedDict

class State(TypedDict):
    messages: list

builder = StateGraph(State)
builder.add_node("my_node", my_func)
builder.add_edge(START, "my_node")
builder.add_edge("my_node", END)
graph = builder.compile()   # → CompiledStateGraph
```

`StateGraph` 是 builder，不能直接执行；必须调用 `.compile()` 得到 `CompiledStateGraph`，后者支持 `invoke()` / `stream()` / `ainvoke()` / `astream()`。

**关键概念**

| 概念 | 说明 |
|---|---|
| State | 图的共享数据结构，所有节点都读写它 |
| Reducer | 每个 state key 可附加一个 reducer 函数控制合并方式（默认覆盖） |
| `add_messages` | 最常用的 reducer，追加消息而不是覆盖 |
| `MessagesState` | 内置的预定义 state，包含 `messages: Annotated[list, add_messages]` |
| `Overwrite` | 绕过 reducer，直接覆盖某个 key |

### Nodes

节点就是 Python 函数，签名为 `State -> dict`（返回部分更新）：

```python
def call_model(state: State) -> dict:
    response = llm.invoke(state["messages"])
    return {"messages": [response]}
```

`add_node` 的完整参数支持 `retry_policy`、`cache_policy`、`input_schema` 等高级选项。

### Edges

- **普通边**：`add_edge(start, end)` — 固定跳转
- **条件边**：`add_conditional_edges(start, routing_fn, mapping)` — 运行时根据 state 动态路由
- **并行扇出**：`add_edge(["node_a", "node_b"], "merge")` — 等待全部完成后汇入
- **Send API**：支持 map-reduce 模式

```python
def should_continue(state: State) -> Literal["tools", "__end__"]:
    if state["messages"][-1].tool_calls:
        return "tools"
    return "__end__"

builder.add_conditional_edges("agent", should_continue, {"tools": "tools", "__end__": END})
```

### Checkpointer

Checkpointer 是 LangGraph 持久化层，每一步后将图的 state 存为 checkpoint，支持暂停/恢复/时间旅行/容错。

```python
from langgraph.checkpoint.memory import InMemorySaver  # 开发用，进程重启后丢失

checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)

# 调用时必须提供 thread_id
config = {"configurable": {"thread_id": "session-001"}}
result = graph.invoke(inputs, config=config)
```

生产可选项：`SqliteSaver`（本地）、`AsyncPostgresSaver`（云端）。

**Checkpointer vs Store**

| | Checkpointer | Store |
|---|---|---|
| 存储内容 | 图 state 快照 | 应用自定义键值数据 |
| 作用域 | 单个 thread | 跨 thread |
| 用途 | 对话连续性、HITL、时间旅行 | 用户偏好、长期记忆 |

---

## 2. LangGraph ReAct 循环 vs 手写 ReAct

### 手写 ReAct（项目 03/11 的模式）

项目 11（`agent.py`）手写了完整的 ReAct 循环，其核心结构：

```python
for step_num in range(1, max_steps + 1):
    # 1. 调用 LLM（含工具 schema）
    response = client.chat.completions.create(model=..., messages=messages, tools=tools)
    msg = response.choices[0].message

    # 2. 提取 Thought（msg.content）
    # 3. 检查是否有工具调用
    if not msg.tool_calls:
        continue   # 仅文字输出，继续

    tool_call = msg.tool_calls[0]  # ReAct 模式：每步只取第一个
    tool_name = tool_call.function.name

    # 4. HITL 拦截（手写）
    if should_pause(tool_name):
        feedback = handler.request_feedback(checkpoint)
        # ... 根据 approve/reject/provide_info 分支处理 ...

    # 5. 执行工具
    result = execute_tool(tool_name, tool_args)

    # 6. 把 observation 注入 messages 继续循环
    messages.append({"role": "tool", "tool_call_id": ..., "content": result})
```

**手写实现的代价**：
- 手动维护 `messages` 列表
- 手动实现 HITL 拦截逻辑（`HITLCheckpoint`、`HITLHandler`、`ScriptedHandler`）
- 手动实现 reject 重试计数（`_consecutive_rejects`）
- 手动实现 tick（世界时间推进）
- 无内置的 state 持久化（每次运行从头开始）

### LangGraph ReAct 循环

LangGraph 把同样的 think-act-observe 循环建模为图，两个节点 + 一条条件边：

```
START → agent_node → (条件边) → tools_node → agent_node → ... → END
```

**方式 1：`create_react_agent`（5 行）**

```python
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini")
agent = create_react_agent(llm, tools=[my_tool])
result = agent.invoke({"messages": [{"role": "user", "content": "..."}]})
```

**方式 2：手动 StateGraph（等价展开）**

```python
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

def agent_node(state: MessagesState):
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}

def should_continue(state: MessagesState):
    if state["messages"][-1].tool_calls:
        return "tools"
    return "__end__"

builder = StateGraph(MessagesState)
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", should_continue)
builder.add_edge("tools", "agent")
graph = builder.compile()
```

**对比总结**

| 维度 | 手写（项目 11 模式） | LangGraph |
|---|---|---|
| messages 管理 | 手动 append | 由 `add_messages` reducer 自动合并 |
| 循环控制 | `for` 循环 + `continue`/`break` | 条件边 + `END` 节点 |
| 工具执行 | 手写 `execute_tool()` | `ToolNode` 自动处理所有 tool_calls |
| HITL 拦截 | 手写 `HITLHandler` + 拦截代码 | `interrupt()` 函数 + `Command` |
| 状态持久化 | 无（内存，重启丢失） | Checkpointer（可配置 SQLite/Postgres） |
| 错误重试 | 手写 `_consecutive_rejects` 计数 | `RetryPolicy`（节点级别） |
| 可视化 | 无 | `graph.get_graph().draw_mermaid()` |

---

## 3. LangGraph HITL（Human-in-the-Loop）

### 推荐方式：`interrupt()` 函数（LangGraph 0.2.57+）

`interrupt()` 在节点内任意位置调用，暂停图执行，surface payload 给调用方，等待 `Command(resume=...)` 恢复。

```python
from langgraph.types import interrupt, Command

def human_review_node(state: State):
    # 任意位置暂停，payload 传给调用方
    decision = interrupt({
        "proposed_action": state["pending_tool"],
        "instructions": "approve / reject / edit"
    })
    # resume 后，decision 就是 Command(resume=...) 传入的值
    return {"human_decision": decision}

# 编译时必须提供 checkpointer
graph = builder.compile(checkpointer=InMemorySaver())

# 运行到 interrupt 处暂停
config = {"configurable": {"thread_id": "t1"}}
graph.invoke(initial_input, config=config)   # 在 interrupt 处停止

# 恢复执行
graph.invoke(Command(resume="approve"), config=config)
```

**与手写 HITL 的对比**

| 维度 | 手写（项目 11 HITLHandler） | LangGraph interrupt() |
|---|---|---|
| 暂停机制 | 在循环中主动调用 `handler.request_feedback()` 阻塞等待 | `interrupt()` 抛出可恢复异常，运行时持久化 state |
| 恢复方式 | 从阻塞返回后继续 `for` 循环 | 重新调用 `invoke(Command(resume=...))` |
| 跨进程恢复 | 不支持（内存中） | 支持（checkpointer 持久化） |
| 拦截逻辑位置 | 在 agent 主循环中 `if should_pause(tool_name)` | 独立的 `human_review` 节点，与业务逻辑解耦 |
| reject 重试 | 手写计数器 `_consecutive_rejects` | 用条件边路由 + 节点内 `interrupt()` 只调用一次 |

**重要规则**

1. `interrupt()` 后节点会从头重新执行（不是从 interrupt 行恢复），所以节点内 interrupt 之前的代码会重跑
2. 不要在单个节点内用 `while True` + 多次 `interrupt()`，会导致指数级重跑
3. 正确的多次询问模式：用状态存储当前问题 + 条件边循环回节点 + 每次节点只调用一次 `interrupt()`

**三种典型 HITL 模式**

```python
# 1. 二元审批（approve / reject）
decision = interrupt({"question": "Confirm execution?"})
if decision == "approve":
    return Command(goto="execute_node")
else:
    return Command(goto="abort_node")

# 2. 审批 + 编辑
decision = interrupt({"proposed": tool_args})
if decision["action"] == "edit":
    tool_args = decision["correction"]  # 使用修改后的参数

# 3. 仅对敏感工具拦截（其他自动通过）
SENSITIVE = {"send_email", "delete_record"}
if tool_name in SENSITIVE:
    decision = interrupt(...)
```

**静态断点（调试用）**

```python
# 编译时设置
graph = builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["agent"],   # 节点执行前暂停
    interrupt_after=["tools"],    # 节点执行后暂停
)
# 恢复：graph.invoke(None, config=config)
```

---

## 4. LangSmith 可观测性

### 最简配置（环境变量，零代码改动）

如果使用 LangChain 模块（`ChatOpenAI`、`ToolNode` 等），只需设置两个环境变量：

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=<your-api-key>
# 可选：指定项目
export LANGSMITH_PROJECT=my-agent-project
```

LangGraph 会自动推断 tracing 配置，每个节点执行、LLM 调用、工具调用都会出现在 LangSmith 的 trace 视图中。

旧变量 `LANGCHAIN_TRACING_V2=true` 也有效（兼容），但 `LANGSMITH_TRACING` 是新推荐名。

### 使用原生 OpenAI SDK 时（如项目 11）

如果绕过 LangChain 直接用 `openai.Client()`，需要用 `wrap_openai` 包装：

```python
from langsmith.wrappers import wrap_openai
from langsmith import traceable
import openai

wrapped_client = wrap_openai(openai.Client())

# 工具函数加 @traceable 装饰器
@traceable(run_type="tool", name="My Tool")
def my_tool(query: str):
    ...

# 节点内用 wrapped_client 调用 LLM
def call_model(state: State):
    response = wrapped_client.chat.completions.create(
        messages=state["messages"],
        model="gpt-4o-mini",
        tools=[tool_schema]
    )
    ...
```

### 选择性 tracing

```python
import langsmith as ls

with ls.tracing_context(enabled=True, project_name="debug-run"):
    result = agent.invoke(inputs)
```

### 数据脱敏

```python
from langchain_core.tracers.langchain import LangChainTracer
from langsmith import Client
from langsmith.anonymizer import create_anonymizer

anonymizer = create_anonymizer([
    {"pattern": r"\b\d{3}-?\d{2}-?\d{4}\b", "replace": "<ssn>"}
])
tracer = LangChainTracer(client=Client(anonymizer=anonymizer))
graph = builder.compile().with_config({"callbacks": [tracer]})
```

---

## 5. 连接自定义 OpenAI 兼容端点

### 最简配置

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="your-model-name",
    base_url="http://localhost:8000/v1",   # 自定义端点
    api_key="any-string",                  # 本地服务通常不验证
)
```

### 环境变量方式（优先级从高到低）

```
1. 构造函数 base_url= 参数（最高优先级）
2. 环境变量 OPENAI_API_BASE  （LangChain 读取）
3. 环境变量 OPENAI_BASE_URL  （openai SDK 读取）
```

项目 11 已经实现了这个模式：
```python
# agent.py line 134-135
api_key = os.environ.get("OPENAI_API_KEY", "").strip()
base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
self._client = OpenAI(api_key=api_key, base_url=base_url)
```

迁移到 LangGraph 时，只需把 `openai.OpenAI()` 换成 `ChatOpenAI()`：

```python
from langchain_openai import ChatOpenAI
import os

llm = ChatOpenAI(
    model=os.environ.get("MODEL_NAME", "gpt-4o-mini"),
    api_key=os.environ.get("OPENAI_API_KEY", ""),
    base_url=os.environ.get("OPENAI_BASE_URL") or None,
)
```

### 注意事项

- `ChatOpenAI` 目标是 OpenAI 官方 API 规范；非标准响应字段（如某些提供商的 `reasoning_content`）不会被提取
- 对于 vLLM / LM Studio 等添加了自定义参数的端点，用 `extra_body` 传参（不是 `model_kwargs`）：
  ```python
  llm = ChatOpenAI(
      base_url="http://localhost:8000/v1",
      extra_body={"use_beam_search": True}  # 提供商自定义参数
  )
  ```
- 流式 token 用量统计（`stream_usage`）：设置了 `OPENAI_BASE_URL` 时默认关闭，因为很多兼容端点不支持

---

## 6. 最小完整示例（自定义端点 + HITL）

```python
import os
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt, Command

# 1. 连接自定义端点
llm = ChatOpenAI(
    model=os.environ.get("MODEL_NAME", "gpt-4o-mini"),
    api_key=os.environ.get("OPENAI_API_KEY", ""),
    base_url=os.environ.get("OPENAI_BASE_URL") or None,
)

# 2. 定义工具
from langchain_core.tools import tool

@tool
def search(query: str) -> str:
    """搜索信息"""
    return f"结果: {query}"

tools = [search]
llm_with_tools = llm.bind_tools(tools)

# 3. 定义节点
def agent_node(state: MessagesState):
    return {"messages": [llm_with_tools.invoke(state["messages"])]}

def human_review(state: MessagesState):
    last = state["messages"][-1]
    if last.tool_calls:
        decision = interrupt({"tool_calls": last.tool_calls})
        if decision != "approve":
            # 注入拒绝信息
            return {"messages": [{"role": "user", "content": f"操作被拒绝: {decision}"}]}
    return {}

# 4. 构建图
builder = StateGraph(MessagesState)
builder.add_node("agent", agent_node)
builder.add_node("human_review", human_review)
builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, "agent")
builder.add_edge("agent", "human_review")
builder.add_conditional_edges("human_review",
    lambda s: "tools" if s["messages"][-1].tool_calls else END)
builder.add_edge("tools", "agent")

# 5. 编译（必须有 checkpointer 才能用 interrupt）
graph = builder.compile(checkpointer=InMemorySaver())

# 6. 运行 + 处理 HITL
config = {"configurable": {"thread_id": "t1"}}
# 开启 LangSmith（可选）
os.environ["LANGSMITH_TRACING"] = "true"

result = graph.invoke(
    {"messages": [{"role": "user", "content": "查询北京天气"}]},
    config=config
)
# 如果遇到 interrupt，result["__interrupt__"] 包含 payload
# 恢复：graph.invoke(Command(resume="approve"), config=config)
```

---

## Caveats / Not Found

- **LangGraph 版本**：当前文档对应 LangGraph ~1.0（stable, Oct 2025）。`interrupt()` 是 0.2.57+ 推荐方式，旧版用 `interrupt_before/after` + `NodeInterrupt`。
- **`create_react_agent` 的 HITL 支持**：只有部分支持（通过 `interrupt_before/after`），完整的 `interrupt()` HITL 需要手动构建 `StateGraph`。
- **项目 11 的迁移路径**：项目 11 用原生 `openai.OpenAI()` 客户端，迁移到 LangGraph 后需改用 `ChatOpenAI` + `bind_tools()`，HITL 逻辑从 `HITLHandler` 模式改为 `interrupt()` 节点模式，状态管理从手写 `messages` 列表改为 `MessagesState`。
- **LangSmith 免费套餐**：smith.langchain.com 注册免费，有一定的 trace 量限制。
