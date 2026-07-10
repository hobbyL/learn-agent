"""
14-mcp-tool-discovery · 主入口
===============================

三阶段 Demo：
  阶段 1: 静态基线 — 硬编码工具
  阶段 2: MCP 动态发现 — 连接 Server A + B
  阶段 3: 运行时热加载 — Server C 上线

用法：
  python main.py --demo        # 三阶段完整演示
  python main.py --interactive  # 交互模式（MCP 全连接）
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from openai import OpenAI
from mcp import StdioServerParameters

from mcp_client import MCPClient
from agent_static import ask_static, TOOLS_SCHEMA
from agent_mcp import ask_mcp
from display import (
    print_header, print_phase, print_question,
    print_tool_discovery, print_static_tools, print_new_tools,
    make_step_callback, print_compare_table, print_server_status,
    C,
)


# ============================================================
# 项目目录（用于定位 Server 脚本）
# ============================================================

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def _server_params(script_name: str) -> StdioServerParameters:
    """构建 MCP Server 的 stdio 启动参数。"""
    return StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(PROJECT_DIR, script_name)],
    )


# ============================================================
# Demo 问题
# ============================================================

# 阶段 1 & 2 共用问题（静态 vs MCP 对比）
PHASE_1_2_QUESTIONS = [
    "蓝晶星有哪些已知资源？",
    "星耀号的当前任务是什么？它的舰长是谁？",
]

# 阶段 3 问题（需要通讯工具才能回答）
PHASE_3_QUESTION = "有没有紧急通讯？赤焰星那边发生了什么？"


# ============================================================
# Demo 模式
# ============================================================

async def run_demo(client: OpenAI, model: str) -> None:
    """三阶段完整演示。"""
    print_header("星际探索指挥中心 · MCP 动态工具发现 Demo")

    compare_results = []

    # ─── 阶段 1: 静态基线 ───
    print_phase(1, "静态基线 — 硬编码工具")
    print_static_tools(TOOLS_SCHEMA)

    for q in PHASE_1_2_QUESTIONS:
        print_question(q)
        callback = make_step_callback(C.BLUE, "静态")
        ask_static(q, client, model, on_step=callback)

    compare_results.append({
        "phase": "阶段 1",
        "mode": "静态基线",
        "tools_count": len(TOOLS_SCHEMA),
        "tools_source": "代码硬编码",
        "new_tools": "-",
    })

    # ─── 阶段 2: MCP 动态发现 ───
    print_phase(2, "MCP 动态发现 — 连接 Server A + B")

    async with MCPClient() as mcp_client:
        # 连接星图服务器
        print(f"  {C.GREEN}🔌 连接 MCP Server: 星图数据库...{C.RESET}")
        tools_a = await mcp_client.connect_server("星图数据库", _server_params("server_starmap.py"))
        print(f"  {C.GREEN}   ✅ 发现 {len(tools_a)} 个工具: {tools_a}{C.RESET}")

        # 连接舰队服务器
        print(f"  {C.GREEN}🔌 连接 MCP Server: 舰队管理...{C.RESET}")
        tools_b = await mcp_client.connect_server("舰队管理", _server_params("server_fleet.py"))
        print(f"  {C.GREEN}   ✅ 发现 {len(tools_b)} 个工具: {tools_b}{C.RESET}")
        print()

        # 展示动态发现的工具
        print_tool_discovery(mcp_client.get_all_tools(), "MCP 动态发现的工具")
        print_server_status(mcp_client.connected_servers, mcp_client.tool_count)

        for q in PHASE_1_2_QUESTIONS:
            print_question(q)
            callback = make_step_callback(C.GREEN, "MCP")
            await ask_mcp(q, client, model, mcp_client, on_step=callback)

        compare_results.append({
            "phase": "阶段 2",
            "mode": "MCP动态",
            "tools_count": mcp_client.tool_count,
            "tools_source": "list_tools()",
            "new_tools": "-",
        })

        # ─── 阶段 3: 运行时热加载 ───
        print_phase(3, "运行时热加载 — Server C 上线")

        print(f"  {C.CYAN}💡 场景：紧急通讯系统上线，无需修改 Agent 代码...{C.RESET}")
        print(f"  {C.CYAN}🔌 连接 MCP Server: 紧急通讯...{C.RESET}")
        tools_c = await mcp_client.connect_server("紧急通讯", _server_params("server_comms.py"))
        print(f"  {C.CYAN}   ✅ 发现 {len(tools_c)} 个新工具: {tools_c}{C.RESET}")
        print()

        print_new_tools(tools_c, "紧急通讯")
        print_tool_discovery(mcp_client.get_all_tools(), "当前所有工具（含新增）")
        print_server_status(mcp_client.connected_servers, mcp_client.tool_count)

        print_question(PHASE_3_QUESTION)
        callback = make_step_callback(C.CYAN, "MCP+热加载")
        await ask_mcp(PHASE_3_QUESTION, client, model, mcp_client, on_step=callback)

        compare_results.append({
            "phase": "阶段 3",
            "mode": "MCP热加载",
            "tools_count": mcp_client.tool_count,
            "tools_source": "list_tools() 刷新",
            "new_tools": f"+{len(tools_c)}",
        })

        # ─── 对比汇总 ───
        print_compare_table(compare_results)


# ============================================================
# 交互模式
# ============================================================

async def run_interactive(client: OpenAI, model: str) -> None:
    """交互模式：连接全部 Server，自由提问。"""
    print_header("星际探索指挥中心 · 交互模式")

    async with MCPClient() as mcp_client:
        # 连接所有 Server
        for name, script in [("星图数据库", "server_starmap.py"),
                              ("舰队管理", "server_fleet.py"),
                              ("紧急通讯", "server_comms.py")]:
            print(f"  {C.GREEN}🔌 连接 {name}...{C.RESET}", end="")
            tools = await mcp_client.connect_server(name, _server_params(script))
            print(f" ✅ {len(tools)} 个工具")

        print()
        print_tool_discovery(mcp_client.get_all_tools())
        print(f"  输入问题开始对话，输入 {C.BOLD}quit{C.RESET} 退出。\n")

        while True:
            try:
                question = input(f"  {C.BOLD}> {C.RESET}").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not question or question.lower() in ("quit", "exit", "q"):
                break

            callback = make_step_callback(C.GREEN, "MCP")
            await ask_mcp(question, client, model, mcp_client, on_step=callback)

    print(f"\n  {C.DIM}已断开所有 MCP 连接。{C.RESET}\n")


# ============================================================
# 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="14-mcp-tool-discovery")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--demo", action="store_true", help="三阶段完整演示（默认）")
    group.add_argument("--interactive", action="store_true", help="交互模式")
    args = parser.parse_args()

    # 加载环境变量
    load_dotenv()

    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", None)
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    openai_client = OpenAI(api_key=api_key, base_url=base_url)

    if args.interactive:
        asyncio.run(run_interactive(openai_client, model))
    else:
        asyncio.run(run_demo(openai_client, model))


if __name__ == "__main__":
    main()
