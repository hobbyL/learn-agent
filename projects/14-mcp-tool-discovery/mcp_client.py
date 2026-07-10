"""
MCP Client —— 多 Server 连接 + 工具聚合 + Schema 转换
=====================================================

核心职责：
1. 通过 stdio 连接多个 MCP Server（子进程）
2. list_tools() 聚合所有 Server 的工具列表
3. 将 MCP tool schema → OpenAI Function Calling schema（供 Agent 使用）
4. call_tool() 路由到正确的 Server 执行
5. 支持运行时动态加载新 Server（热加载）

生命周期管理：
    使用 contextlib.AsyncExitStack 管理所有 async context manager，
    避免 anyio task scope 跨 task 退出的问题。
"""

import sys
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass, field

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass
class ServerConnection:
    """一个 MCP Server 连接的运行时状态。"""
    name: str
    session: ClientSession | None = None
    tools: list = field(default_factory=list)


class MCPClient:
    """
    多 Server MCP Client。

    用法（推荐 async with）：
        async with MCPClient() as client:
            await client.connect_server("星图", StdioServerParameters(...))
            tools = client.get_openai_tools()
            result = await client.call_tool("search_stars", {"query": "蓝晶"})

    也可以手动管理：
        client = MCPClient()
        await client.connect_server(...)
        ...
        await client.cleanup()
    """

    def __init__(self):
        self._servers: dict[str, ServerConnection] = {}
        self._tool_router: dict[str, str] = {}  # 工具名 → Server 名
        self._exit_stack = AsyncExitStack()

    async def __aenter__(self):
        await self._exit_stack.__aenter__()
        return self

    async def __aexit__(self, *exc):
        await self._exit_stack.__aexit__(*exc)
        self._servers.clear()
        self._tool_router.clear()

    async def connect_server(self, name: str, params: StdioServerParameters) -> list[str]:
        """
        连接一个 MCP Server 并发现其工具。

        返回新发现的工具名列表。
        """
        # 通过 ExitStack 管理 stdio_client 和 ClientSession 的生命周期
        read, write = await self._exit_stack.enter_async_context(
            stdio_client(params)
        )
        session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )

        # 初始化协议
        await session.initialize()

        # 发现工具
        result = await session.list_tools()

        conn = ServerConnection(name=name, session=session, tools=result.tools)

        # 注册路由
        tool_names = []
        for tool in conn.tools:
            self._tool_router[tool.name] = name
            tool_names.append(tool.name)

        self._servers[name] = conn
        return tool_names

    async def cleanup(self) -> None:
        """手动清理所有连接（不使用 async with 时调用）。"""
        await self._exit_stack.aclose()
        self._servers.clear()
        self._tool_router.clear()

    async def refresh_tools(self, name: str | None = None) -> list[str]:
        """
        刷新指定 Server（或所有 Server）的工具列表。

        返回当前所有工具名。
        """
        targets = [name] if name else list(self._servers.keys())
        for server_name in targets:
            conn = self._servers[server_name]
            # 清除旧路由
            for tool in conn.tools:
                self._tool_router.pop(tool.name, None)
            # 重新发现
            result = await conn.session.list_tools()
            conn.tools = result.tools
            for tool in conn.tools:
                self._tool_router[tool.name] = server_name

        return list(self._tool_router.keys())

    def get_all_tools(self) -> list[dict]:
        """
        获取所有工具的 MCP 原始信息。

        返回 [{name, description, server, input_schema}, ...]
        """
        all_tools = []
        for name, conn in self._servers.items():
            for tool in conn.tools:
                all_tools.append({
                    "name": tool.name,
                    "description": tool.description or "",
                    "server": name,
                    "input_schema": tool.inputSchema,
                })
        return all_tools

    def get_openai_tools(self) -> list[dict]:
        """
        将所有 MCP 工具转换为 OpenAI Function Calling schema。

        MCP tool schema:
            {name, description, inputSchema: {type: "object", properties: {...}, required: [...]}}

        OpenAI Function Calling schema:
            {type: "function", function: {name, description, parameters: {type: "object", properties, required}}}
        """
        openai_tools = []
        for name, conn in self._servers.items():
            for tool in conn.tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": tool.inputSchema,
                    },
                })
        return openai_tools

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """
        调用工具，自动路由到正确的 Server。

        返回工具执行结果（字符串）。
        """
        if tool_name not in self._tool_router:
            available = list(self._tool_router.keys())
            return f"错误：未知工具 '{tool_name}'。可用工具：{available}"

        server_name = self._tool_router[tool_name]
        conn = self._servers[server_name]

        result = await conn.session.call_tool(tool_name, arguments=arguments)

        # 提取文本内容
        texts = []
        for content in result.content:
            if hasattr(content, "text"):
                texts.append(content.text)
            else:
                texts.append(str(content))
        return "\n".join(texts)

    @property
    def connected_servers(self) -> list[str]:
        """当前已连接的 Server 列表。"""
        return list(self._servers.keys())

    @property
    def tool_count(self) -> int:
        """当前可用工具总数。"""
        return len(self._tool_router)

    def get_tool_server(self, tool_name: str) -> str | None:
        """查询工具属于哪个 Server。"""
        return self._tool_router.get(tool_name)
