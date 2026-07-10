"""
MCP Server C —— 紧急通讯
========================

暴露 3 个工具：search_communications / get_comm_detail / send_emergency_message
传输方式：stdio（演示运行时动态加载 —— 启动晚于 A/B）
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP

from knowledge_base import search_comms, get_comms_detail, send_emergency

mcp = FastMCP("紧急通讯")


@mcp.tool()
def search_communications(query: str) -> str:
    """搜索通讯记录。输入关键词（发送方、优先级、内容等），返回匹配的通讯列表。"""
    results = search_comms(query)
    if not results:
        return "未找到相关通讯记录。"
    lines = [f"找到 {len(results)} 条通讯记录："]
    for r in results:
        lines.append(f"  - [{r['id']}] {r['时间']} | {r['发送方']} | 优先级={r['优先级']} | {r['摘要']}")
    return "\n".join(lines)


@mcp.tool()
def get_comm_detail(comm_id: str) -> str:
    """根据通讯ID获取完整通讯记录内容。"""
    record = get_comms_detail(comm_id)
    if record is None:
        return f"错误：未找到通讯记录 '{comm_id}'。"
    lines = [
        f"通讯ID：{record['id']}",
        f"时间：{record['时间']}",
        f"发送方：{record['发送方']}",
        f"接收方：{record['接收方']}",
        f"优先级：{record['优先级']}",
        f"内容：{record['内容']}",
    ]
    return "\n".join(lines)


@mcp.tool()
def send_emergency_message(target: str, message: str) -> str:
    """发送紧急通讯到指定目标。target=接收方，message=消息内容。"""
    result = send_emergency(target, message)
    if result["success"]:
        return f"✅ {result['message']}（通讯ID：{result['comm_id']}）"
    return "❌ 紧急通讯发送失败。"


if __name__ == "__main__":
    mcp.run(transport="stdio")
