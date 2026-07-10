# 14-mcp-tool-discovery · 开发笔记

## MCP 协议核心概念

### Server 端

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("服务名称")

@mcp.tool()
def my_tool(param: str) -> str:
    """工具描述（docstring 即描述）。"""
    return "result"

# 启动（stdio 传输）
mcp.run(transport="stdio")
```

`FastMCP` 是高级封装，底层是 `mcp.server.Server`。`@mcp.tool()` 类似 LangChain 的 `@tool`，但走的是 MCP 协议而非 LangChain 的工具系统。

### Client 端

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(command="python3", args=["server.py"])

async with stdio_client(params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        
        # 发现工具
        tools = await session.list_tools()
        
        # 调用工具
        result = await session.call_tool("my_tool", {"param": "value"})
```

### Schema 转换

MCP 和 OpenAI 的 JSON Schema 格式几乎相同，转换非常直接：

```python
# MCP tool schema
{
    "name": "search_stars",
    "description": "搜索星图...",
    "inputSchema": {"type": "object", "properties": {...}, "required": [...]}
}

# OpenAI Function Calling schema
{
    "type": "function",
    "function": {
        "name": "search_stars",
        "description": "搜索星图...",
        "parameters": {"type": "object", "properties": {...}, "required": [...]}
    }
}
```

只需把 `inputSchema` 换到 `function.parameters` 里，外面包一层 `{type: "function", function: {...}}`。

---

## 踩坑记录

### 1. anyio task scope 不能跨 task 退出

MCP 的 `stdio_client()` 和 `ClientSession` 都是 async context manager，底层用了 anyio 的 `create_task_group()`。如果手动保存 context manager 引用，在不同的 asyncio task 里调用 `__aexit__`，会报：

```
RuntimeError: Attempted to exit cancel scope in a different task than it was entered in
```

**解决**：用 `contextlib.AsyncExitStack` 统一管理所有 async context manager 的生命周期：

```python
from contextlib import AsyncExitStack

class MCPClient:
    def __init__(self):
        self._exit_stack = AsyncExitStack()
    
    async def connect_server(self, name, params):
        read, write = await self._exit_stack.enter_async_context(stdio_client(params))
        session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        ...
    
    async def __aenter__(self):
        await self._exit_stack.__aenter__()
        return self
    
    async def __aexit__(self, *exc):
        await self._exit_stack.__aexit__(*exc)
```

`AsyncExitStack` 在同一个 task 上下文中统一管理所有 enter/exit，避免跨 task 问题。

### 2. MCP Server 的 INFO 日志

MCP Server 启动后会在 stderr 输出 `Processing request of type ListToolsRequest` 等 INFO 日志。这些日志来自 `mcp.server.Server`，不影响 stdout 上的 stdio 协议通信，但会混在 demo 输出里。

生产环境可以设置 `log_level="WARNING"` 或重定向 stderr。

### 3. .env 文件位置

前面的项目有的用 `load_dotenv()`（自动查找当前目录 .env），有的用 `load_dotenv("../../.env")`。本项目统一用 `load_dotenv()` + 每个项目目录下放自己的 `.env`。

### 4. 搜索函数的关键词匹配

`search_comms("赤焰星 紧急")` 返回空，因为是全文包含匹配，空格拼接后变成一个整体去 `in` 查找。每个词需要分开匹配，或者只搜单个关键词。LLM 在第一次搜索失败后会自动调整关键词（只搜"紧急"），这反而展示了 Agent 的推理纠错能力。

---

## 架构对比

### 为什么 MCP Schema 和 OpenAI 几乎相同？

因为 MCP 的 tool schema 就是基于 JSON Schema 规范的，和 OpenAI Function Calling 用的是同一套标准。MCP 的贡献不在于发明新 schema 格式，而在于定义了**发现和调用的协议**：

- **发现**：`list_tools()` 请求 → Server 返回工具列表
- **调用**：`call_tool(name, args)` 请求 → Server 执行并返回结果
- **通知**：`send_tool_list_changed()` → Client 重新拉取工具列表

### MCP vs 直接导入

| 维度 | 直接 import | MCP |
|------|-----------|-----|
| 部署 | 同进程 | 可以跨进程/跨机器 |
| 语言 | 必须同语言 | 协议无关（Python/TS/Go） |
| 更新 | 改代码重启 | Server 独立更新 |
| 隔离 | 共享内存 | 进程级隔离 |
| 发现 | 硬编码 | 运行时协议发现 |

### FastMCP vs MCPServer

安装的 `mcp==1.28.1` 中，`FastMCP` 可用，`MCPServer` 不存在（可能是文档 vs 实际版本差异）。`FastMCP` 是推荐的高级 API。
