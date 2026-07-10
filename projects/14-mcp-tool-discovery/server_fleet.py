"""
MCP Server B —— 舰队管理
========================

暴露 2 个工具：search_ships / lookup_ship_info
传输方式：stdio（由 MCP Client 通过子进程启动）
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP

from knowledge_base import FLEET, search_fleet, lookup_fleet

mcp = FastMCP("舰队管理")


@mcp.tool()
def search_ships(query: str) -> str:
    """在舰队数据库中搜索飞船或船员。输入关键词，返回匹配的实体列表。"""
    results = search_fleet(query)
    if not results:
        return "未找到相关舰队数据。请尝试其他关键词。"
    lines = [f"找到 {len(results)} 个结果："]
    for r in results:
        lines.append(f"  - {r['name']}（{r['type']}）：{r['summary']}")
    return "\n".join(lines)


@mcp.tool()
def lookup_ship_info(entity: str, field: str) -> str:
    """精确查询舰队实体的某个属性。entity=实体名称，field=属性名。"""
    result = lookup_fleet(entity, field)
    if result is None:
        if entity not in FLEET:
            return f"错误：未找到舰队实体 '{entity}'。请先用 search_ships 搜索。"
        available = [k for k in FLEET[entity].keys() if k != "type"]
        return f"错误：实体 '{entity}' 没有 '{field}' 属性。可用属性：{available}"
    return result


if __name__ == "__main__":
    mcp.run(transport="stdio")
