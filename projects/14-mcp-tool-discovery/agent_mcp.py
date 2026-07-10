"""
MCP 动态工具 Agent
==================

工具列表通过 MCP Client 的 list_tools() 运行时获取，
转换为 OpenAI Function Calling schema 后供 Agent 使用。
调用工具时通过 MCP Client 的 call_tool() 路由到正确的 Server。

和 agent_static.py 的核心区别：
- 不硬编码 TOOLS_SCHEMA
- 工具来源是运行时协议发现
- 新 Server 上线后无需改代码，重新 get_openai_tools() 即可
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openai import OpenAI

from mcp_client import MCPClient


SYSTEM_PROMPT = """\
你是星际探索指挥中心的 AI 助手。你可以使用动态发现的工具来回答问题。
可用工具由指挥中心的各个子系统（MCP Server）实时提供。
请根据用户的问题选择合适的工具，必要时多次调用工具获取完整信息。
用中文回答。"""


async def ask_mcp(question: str, client: OpenAI, model: str,
                  mcp_client: MCPClient, max_steps: int = 10,
                  on_step=None) -> str:
    """
    MCP 动态工具 Agent：工具列表来自 MCP Client。

    on_step: 回调函数，签名 (step_num, role, content, tool_name=None, server=None)
    """
    # 动态获取当前所有可用工具（核心差异！）
    tools_schema = mcp_client.get_openai_tools()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    for step in range(1, max_steps + 1):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools_schema,
        )
        msg = response.choices[0].message

        if msg.tool_calls:
            messages.append(msg)
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                args = json.loads(tc.function.arguments)
                server = mcp_client.get_tool_server(tool_name)

                if on_step:
                    on_step(step, "tool_call",
                            f"{tool_name}({json.dumps(args, ensure_ascii=False)})",
                            server=server)

                # 通过 MCP Client 路由执行（核心差异！）
                result = await mcp_client.call_tool(tool_name, args)

                if on_step:
                    on_step(step, "tool_result", result,
                            tool_name=tool_name, server=server)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
        else:
            answer = msg.content or ""
            if on_step:
                on_step(step, "answer", answer)
            return answer

    return "[MCP Agent] 达到最大步数，未得到最终答案。"
