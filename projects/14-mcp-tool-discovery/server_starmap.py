"""
MCP Server A —— 星图数据库
===========================

暴露 2 个工具：search_starmap / lookup_starmap
传输方式：stdio（由 MCP Client 通过子进程启动）
"""

import sys
import os

# 让 import knowledge_base 能找到同目录文件
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP

from knowledge_base import STAR_MAP, search_starmap, lookup_starmap

mcp = FastMCP("星图数据库")


@mcp.tool()
def search_stars(query: str) -> str:
    """在星图数据库中搜索星系、星球或航线。输入关键词，返回匹配的实体列表。"""
    results = search_starmap(query)
    if not results:
        return "未找到相关星图数据。请尝试其他关键词。"
    lines = [f"找到 {len(results)} 个结果："]
    for r in results:
        lines.append(f"  - {r['name']}（{r['type']}）：{r['summary']}")
    return "\n".join(lines)


@mcp.tool()
def lookup_star_info(entity: str, field: str) -> str:
    """精确查询星图实体的某个属性。entity=实体名称，field=属性名。"""
    result = lookup_starmap(entity, field)
    if result is None:
        if entity not in STAR_MAP:
            return f"错误：未找到星图实体 '{entity}'。请先用 search_stars 搜索。"
        available = [k for k in STAR_MAP[entity].keys() if k != "type"]
        return f"错误：实体 '{entity}' 没有 '{field}' 属性。可用属性：{available}"
    return result


if __name__ == "__main__":
    mcp.run(transport="stdio")
