"""
静态工具 Agent（基线对照）
=========================

工具列表硬编码在代码中（TOOLS_SCHEMA），和项目 03 的方式一样。
用于和 MCP 动态 Agent 对比，展示"静态注册"的局限性。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openai import OpenAI

from knowledge_base import (
    search_starmap, lookup_starmap,
    search_fleet, lookup_fleet,
)


# ============================================================
# 硬编码的工具 Schema（只有星图 + 舰队，没有通讯）
# ============================================================

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_stars",
            "description": "在星图数据库中搜索星系、星球或航线。输入关键词，返回匹配的实体列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_star_info",
            "description": "精确查询星图实体的某个属性。entity=实体名称，field=属性名。",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "实体名称"},
                    "field": {"type": "string", "description": "属性名"},
                },
                "required": ["entity", "field"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_ships",
            "description": "在舰队数据库中搜索飞船或船员。输入关键词，返回匹配的实体列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_ship_info",
            "description": "精确查询舰队实体的某个属性。entity=实体名称，field=属性名。",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "实体名称"},
                    "field": {"type": "string", "description": "属性名"},
                },
                "required": ["entity", "field"],
            },
        },
    },
]

# 工具名 → 执行函数
TOOL_HANDLERS = {
    "search_stars": lambda args: _format_search(search_starmap(args["query"])),
    "lookup_star_info": lambda args: lookup_starmap(args["entity"], args["field"]) or "未找到",
    "search_ships": lambda args: _format_search(search_fleet(args["query"])),
    "lookup_ship_info": lambda args: lookup_fleet(args["entity"], args["field"]) or "未找到",
}

SYSTEM_PROMPT = """\
你是星际探索指挥中心的 AI 助手。你可以查询星图数据库和舰队信息来回答问题。
请根据用户的问题选择合适的工具，必要时多次调用工具获取完整信息。
用中文回答。"""


def _format_search(results: list[dict]) -> str:
    if not results:
        return "未找到相关数据。"
    lines = [f"找到 {len(results)} 个结果："]
    for r in results:
        lines.append(f"  - {r['name']}（{r['type']}）：{r['summary']}")
    return "\n".join(lines)


def ask_static(question: str, client: OpenAI, model: str,
               max_steps: int = 10, on_step=None) -> str:
    """
    静态工具 Agent：使用硬编码的 TOOLS_SCHEMA。

    on_step: 回调函数，签名 (step_num, role, content, tool_name=None)
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    for step in range(1, max_steps + 1):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS_SCHEMA,
        )
        msg = response.choices[0].message

        if msg.tool_calls:
            messages.append(msg)
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                args = json.loads(tc.function.arguments)

                if on_step:
                    on_step(step, "tool_call", f"{tool_name}({json.dumps(args, ensure_ascii=False)})")

                handler = TOOL_HANDLERS.get(tool_name)
                if handler:
                    result = handler(args)
                else:
                    result = f"错误：未知工具 '{tool_name}'"

                if on_step:
                    on_step(step, "tool_result", result, tool_name=tool_name)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result),
                })
        else:
            answer = msg.content or ""
            if on_step:
                on_step(step, "answer", answer)
            return answer

    return "[静态 Agent] 达到最大步数，未得到最终答案。"
