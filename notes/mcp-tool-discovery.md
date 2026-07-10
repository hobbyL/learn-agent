# MCP 动态工具发现知识笔记

> 基于项目 14 实践整理，版本：mcp==1.28.1

---

## 1. MCP 协议核心

MCP（Model Context Protocol）定义了 AI 应用与工具/数据源之间的标准化通信协议。

核心三件事：
- **发现**：Client 通过 `list_tools()` 获取 Server 的工具列表
- **调用**：Client 通过 `call_tool(name, args)` 远程执行工具
- **通知**：Server 通过 `send_tool_list_changed()` 通知 Client 工具变化

```
Agent ←→ MCP Client ←→ [stdio/SSE] ←→ MCP Server A (工具 1, 2)
                     ←→ [stdio/SSE] ←→ MCP Server B (工具 3, 4)
                     ←→ [stdio/SSE] ←→ MCP Server C (工具 5, 6, 7)  ← 运行时动态加载
```

---

## 2. Server 端：FastMCP + @mcp.tool()

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("服务名称")

@mcp.tool()
def search(query: str) -> str:
    """搜索数据库。"""  # docstring = 工具描述
    return do_search(query)

if __name__ == "__main__":
    mcp.run(transport="stdio")  # stdio 传输
```

- `FastMCP` 是高级 API，一行创建 Server
- `@mcp.tool()` 类似 LangChain 的 `@tool`，但走 MCP 协议
- 函数签名自动生成 JSON Schema（和 LangChain @tool 的机制相同）
- `transport="stdio"` 是最常用的传输方式（Claude Desktop、IDE 插件都用这种）

---

## 3. Client 端：stdio_client + ClientSession

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(
    command="python3",
    args=["server.py"],
)

async with stdio_client(params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()     # 协议握手

        tools = await session.list_tools()   # 发现工具
        result = await session.call_tool("search", {"query": "test"})  # 调用工具
```

- `StdioServerParameters` 定义子进程启动参数
- `stdio_client` 启动子进程并建立 stdio 通道
- `ClientSession` 在通道上运行 MCP 协议
- `initialize()` 完成协议版本协商

---

## 4. Schema 转换：MCP → OpenAI Function Calling

```python
# MCP tool
tool.name         → function.name
tool.description  → function.description
tool.inputSchema  → function.parameters

# 转换代码
openai_tool = {
    "type": "function",
    "function": {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.inputSchema,  # 直接搬过来
    },
}
```

MCP 的 `inputSchema` 和 OpenAI 的 `parameters` 都是标准 JSON Schema，**结构几乎完全相同**，无需深度转换。

---

## 5. 多 Server 聚合 + 工具路由

```python
class MCPClient:
    _tool_router: dict[str, str]  # 工具名 → Server 名

    async def call_tool(self, name, args):
        server = self._tool_router[name]
        return await self._servers[server].session.call_tool(name, args)
```

关键设计：
- 每个 Server 的工具名必须全局唯一（否则路由冲突）
- `get_openai_tools()` 聚合所有 Server 的工具为统一列表
- Agent 不需要知道工具属于哪个 Server，Client 层透明路由

---

## 6. 运行时热加载

```python
# 运行中新增 Server，无需改 Agent 代码
await client.connect_server("新服务", new_params)

# 自动包含新工具
tools = client.get_openai_tools()  # 工具列表已更新
```

MCP 的热加载能力是相对于静态注册的核心优势：
- 静态注册：新增工具 = 改 `TOOLS_SCHEMA` 代码 + 重启程序
- MCP 动态：新增工具 = 连接新 Server + 重新 `list_tools()`
- Agent 代码完全不变，只是 `get_openai_tools()` 返回的列表变长了

---

## 7. 生命周期管理：AsyncExitStack

```python
from contextlib import AsyncExitStack

class MCPClient:
    def __init__(self):
        self._exit_stack = AsyncExitStack()

    async def connect_server(self, name, params):
        read, write = await self._exit_stack.enter_async_context(
            stdio_client(params)
        )
        session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        ...
```

**为什么不能手动 `__aenter__` / `__aexit__`？**

MCP SDK 底层用了 `anyio` 的 `TaskGroup`，`__aexit__` 必须在和 `__aenter__` 相同的 asyncio task 中调用，否则报 `RuntimeError: Attempted to exit cancel scope in a different task`。

`AsyncExitStack` 在同一个上下文中统一管理所有 enter/exit，是正确的做法。

---

## 8. MCP vs 其他工具集成方式

| 维度 | 直接 import | LangChain @tool | MCP |
|------|-----------|----------------|-----|
| 耦合度 | 最高（同模块） | 中（同进程） | 最低（跨进程） |
| 语言限制 | 同语言 | Python only | 协议无关 |
| 工具发现 | 硬编码 | 编译时绑定 | 运行时协议 |
| 更新方式 | 改代码重启 | 改代码重启 | Server 独立更新 |
| 热加载 | ❌ | ❌ | ✅ |
| 适用场景 | 学习/原型 | 单应用 | 工具生态/平台 |

---

## 版本兼容提示

| 功能 | 用法 | 版本 |
|------|------|------|
| `FastMCP` | `from mcp.server.fastmcp import FastMCP` | 1.x |
| `MCPServer` | 文档提到，但 1.28.1 中不存在 | 可能是更新版 API |
| `stdio_client` | `from mcp.client.stdio import stdio_client` | 1.x |
| `ClientSession` | `from mcp import ClientSession` | 1.x |
| `StdioServerParameters` | `from mcp import StdioServerParameters` | 1.x |
