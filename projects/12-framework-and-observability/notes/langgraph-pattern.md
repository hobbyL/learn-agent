# LangGraph 核心模式知识笔记

> 基于项目 12 实践整理，版本：langgraph==1.2.8

---

## 1. StateGraph 构建模式

```python
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver

# Step 1: 定义 State（用 MessagesState 省去手写 add_messages）
# MessagesState = TypedDict with messages: Annotated[list, add_messages]

# Step 2: 定义节点函数（State → dict）
def agent_node(state: MessagesState) -> dict:
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}   # add_messages 自动追加，不覆盖

# Step 3: 定义路由函数
def should_continue(state: MessagesState) -> Literal["tools", "__end__"]:
    if state["messages"][-1].tool_calls:
        return "tools"
    return "__end__"

# Step 4: 构建图
builder = StateGraph(MessagesState)
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(tools))  # 自动执行所有 tool_calls
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", should_continue)
builder.add_edge("tools", "agent")

# Step 5: 编译（可选 checkpointer）
graph = builder.compile(checkpointer=InMemorySaver())
```

---

## 2. ReAct 图拓扑

```
START → agent → should_continue() ─┬─ "tools" → tools → agent（循环）
                                    └─ "__end__" → END
```

这等价于手写 ReAct 的 `for` 循环：
- `agent_node` = "调 LLM，得到 Thought + Action"
- `tools` = "执行工具，得到 Observation"
- `should_continue` = "判断是否继续循环"

---

## 3. add_messages Reducer

`MessagesState` 里的 `messages` 字段绑定了 `add_messages` reducer：

```python
# 节点返回的 {"messages": [new_msg]} 不会覆盖旧消息
# 而是被 add_messages 追加到列表末尾

# 等价于手写 ReAct 里的：
messages.append(new_msg)
```

**关键**：节点返回 `{"messages": [msg]}` 而不是 `{"messages": msg}`，
list 包装是必须的（reducer 接受列表形式的增量更新）。

---

## 4. Checkpointer 多轮对话模式

```python
checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)

# 同一 thread_id = 连续对话（checkpointer 保留上一轮的 state）
config = {"configurable": {"thread_id": "session-001"}}

# 第一轮
graph.invoke({"messages": [{"role": "user", "content": q1}]}, config=config)

# 第二轮（无需重传历史，checkpointer 自动加载上一轮 state）
graph.invoke({"messages": [{"role": "user", "content": q2}]}, config=config)
```

**注意**：`InMemorySaver` 数据绑定在 Python 对象上，必须用**同一个 graph 实例**。
每次 `build_graph()` 创建新实例，历史 checkpoint 丢失。

---

## 5. create_react_agent（prebuilt）

```python
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver

agent = create_react_agent(
    model=llm,
    tools=lc_tools,
    prompt="你是助手...",        # system prompt（1.x 参数名）
    checkpointer=InMemorySaver(),
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "..."}]},
    config={"configurable": {"thread_id": "t1"}},
)
```

内部结构和手动 StateGraph 完全相同（同样是 agent + tools 两节点 + 条件边）。
区别是对用户隐藏了实现细节，适合快速交付。

---

## 6. @tool 装饰器

```python
from langchain_core.tools import tool

@tool
def lookup_tool(entity: str, field: str) -> str:
    """精确查询某个实体的某个属性值。"""  # docstring = 工具描述
    return lookup(entity, field)

# lookup_tool.name = "lookup_tool"
# lookup_tool.description = "精确查询..."
# lookup_tool.args_schema = 自动从函数签名生成

# 传给 bind_tools 或 ToolNode
llm_with_tools = llm.bind_tools([lookup_tool])
tools_node = ToolNode([lookup_tool])
```

---

## 7. ToolNode 工作原理

```python
tools_node = ToolNode([search_tool, lookup_tool, calculate_tool, compare_tool])
```

`ToolNode` 接收 state，从最后一条 `AIMessage` 提取所有 `tool_calls`，
依次找到对应工具函数，执行，把结果包装成 `ToolMessage` 返回。

等价于手写：
```python
for tc in ai_message.tool_calls:
    result = tool_map[tc["name"]](**tc["args"])
    messages.append(ToolMessage(content=result, tool_call_id=tc["id"], name=tc["name"]))
```

---

## 8. LangSmith 零代码集成

使用 LangChain 模块（ChatOpenAI、ToolNode 等）时，只需环境变量：

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<key>
LANGSMITH_PROJECT=my-project   # 可选
```

LangSmith trace 会自动捕获：
- 每个图节点的执行（输入/输出 state）
- LLM 调用（prompt、completion、latency、token 用量）
- 工具调用（参数、结果）

不需要 `@traceable` 装饰器或 `wrap_openai`（那是用原生 openai SDK 时才需要的）。

---

## 版本兼容提示

| 功能 | 参数/用法 | 版本 |
|------|-----------|------|
| `create_react_agent` system prompt | `prompt=` | 1.x |
| `create_react_agent` system prompt | `state_modifier=` | 0.2.x |
| `interrupt()` | `from langgraph.types import interrupt` | 0.2.57+ |
| `InMemorySaver` | `from langgraph.checkpoint.memory import InMemorySaver` | 0.2+ |
