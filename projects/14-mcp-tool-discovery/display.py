"""
ANSI 着色展示 + 对比表格
========================

颜色约定：
- 静态 Agent：蓝色
- MCP 动态 Agent：绿色
- MCP 热加载：青色
- 工具调用：黄色
- 工具结果：灰色
- Server 来源：品红色
"""


# ============================================================
# ANSI 颜色码
# ============================================================

class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    # 前景色
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"


# ============================================================
# 分隔与标题
# ============================================================

def print_header(title: str, color: str = C.BOLD) -> None:
    """打印章节标题。"""
    width = 60
    print(f"\n{color}{'═' * width}")
    print(f"  {title}")
    print(f"{'═' * width}{C.RESET}\n")


def print_phase(phase_num: int, title: str) -> None:
    """打印阶段标题。"""
    colors = {1: C.BLUE, 2: C.GREEN, 3: C.CYAN}
    color = colors.get(phase_num, C.WHITE)
    print(f"\n{color}{C.BOLD}{'─' * 50}")
    print(f"  阶段 {phase_num}: {title}")
    print(f"{'─' * 50}{C.RESET}\n")


def print_question(question: str) -> None:
    """打印用户问题。"""
    print(f"  {C.BOLD}❓ 问题：{question}{C.RESET}")
    print()


# ============================================================
# 工具发现展示
# ============================================================

def print_tool_discovery(tools: list[dict], title: str = "已发现工具") -> None:
    """展示发现的工具列表。"""
    print(f"  {C.BOLD}{title}（共 {len(tools)} 个）：{C.RESET}")
    for t in tools:
        server = t.get("server", "?")
        name = t["name"]
        desc = t.get("description", "")[:50]
        print(f"    {C.YELLOW}🔧 {name}{C.RESET} {C.GRAY}← {C.MAGENTA}{server}{C.RESET}")
        if desc:
            print(f"       {C.DIM}{desc}{C.RESET}")
    print()


def print_static_tools(tools_schema: list[dict]) -> None:
    """展示静态注册的工具列表。"""
    print(f"  {C.BOLD}硬编码工具（共 {len(tools_schema)} 个）：{C.RESET}")
    for t in tools_schema:
        name = t["function"]["name"]
        desc = t["function"].get("description", "")[:50]
        print(f"    {C.YELLOW}🔧 {name}{C.RESET} {C.GRAY}← {C.BLUE}代码硬编码{C.RESET}")
        if desc:
            print(f"       {C.DIM}{desc}{C.RESET}")
    print()


def print_new_tools(new_tools: list[str], server_name: str) -> None:
    """展示新发现的工具（热加载）。"""
    print(f"  {C.CYAN}{C.BOLD}🆕 新 Server 上线：{server_name}{C.RESET}")
    print(f"  {C.CYAN}新增 {len(new_tools)} 个工具：{C.RESET}")
    for name in new_tools:
        print(f"    {C.CYAN}🔧 {name}{C.RESET}")
    print()


# ============================================================
# Agent 执行步骤
# ============================================================

def make_step_callback(color: str, label: str):
    """
    创建 on_step 回调函数，用于 agent 执行过程中实时展示。

    返回: (step_num, role, content, tool_name=None, server=None) -> None
    """
    def callback(step_num, role, content, tool_name=None, server=None):
        if role == "tool_call":
            server_tag = f" {C.MAGENTA}[{server}]{C.RESET}" if server else ""
            print(f"  {color}[{label}] Step {step_num} 🔧 {content}{server_tag}{C.RESET}")
        elif role == "tool_result":
            # 截取前 80 字符
            short = content[:80].replace("\n", " ")
            if len(content) > 80:
                short += "..."
            print(f"  {C.GRAY}    → {short}{C.RESET}")
        elif role == "answer":
            print(f"\n  {color}{C.BOLD}[{label}] 💬 回答：{C.RESET}")
            for line in content.split("\n"):
                print(f"  {color}  {line}{C.RESET}")
            print()

    return callback


# ============================================================
# 对比汇总表
# ============================================================

def print_compare_table(results: list[dict]) -> None:
    """
    打印对比汇总表。

    results: [{phase, mode, tools_count, tools_source, question, answered}]
    """
    print_header("对比汇总")

    # 列宽
    w_phase = 10
    w_mode = 14
    w_count = 8
    w_source = 20
    w_newtools = 12

    header = (
        f"  {'阶段':<{w_phase}}"
        f"{'模式':<{w_mode}}"
        f"{'工具数':<{w_count}}"
        f"{'工具来源':<{w_source}}"
        f"{'新增工具':<{w_newtools}}"
    )
    print(f"{C.BOLD}{header}{C.RESET}")
    print(f"  {'─' * (w_phase + w_mode + w_count + w_source + w_newtools)}")

    colors = {"静态基线": C.BLUE, "MCP动态": C.GREEN, "MCP热加载": C.CYAN}

    for r in results:
        color = colors.get(r["mode"], C.WHITE)
        row = (
            f"  {color}{r['phase']:<{w_phase}}"
            f"{r['mode']:<{w_mode}}"
            f"{str(r['tools_count']):<{w_count}}"
            f"{r['tools_source']:<{w_source}}"
            f"{r.get('new_tools', '-'):<{w_newtools}}"
            f"{C.RESET}"
        )
        print(row)

    print()

    # 关键对比
    print(f"  {C.BOLD}关键对比：{C.RESET}")
    print(f"    {C.BLUE}● 静态注册{C.RESET}：工具列表写死在代码里，新增工具 = 改代码 + 重启")
    print(f"    {C.GREEN}● MCP 动态{C.RESET}：工具通过 list_tools() 运行时发现，新增 Server = 连接即用")
    print(f"    {C.CYAN}● MCP 热加载{C.RESET}：运行中新 Server 上线，Agent 无感知自动获得新能力")
    print()


def print_server_status(servers: list[str], tool_count: int) -> None:
    """打印当前 Server 连接状态。"""
    print(f"  {C.BOLD}MCP 连接状态：{C.RESET}")
    for s in servers:
        print(f"    {C.GREEN}● {s}{C.RESET} — 已连接")
    print(f"    {C.BOLD}可用工具总数：{tool_count}{C.RESET}")
    print()
