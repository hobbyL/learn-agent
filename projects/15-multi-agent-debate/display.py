"""
ANSI 着色展示
=============

每个角色一种颜色：
- 🔬 科学官 → 青色 (CYAN)
- ⚔️ 军事官 → 红色 (RED)
- 💰 经济官 → 黄色 (YELLOW)

阶段标题 → 品红 (MAGENTA)
工具调用 → 绿色 (GREEN)
系统信息 → 蓝色 (BLUE)
"""

# ANSI 颜色码
COLORS = {
    "science": "\033[36m",   # 青色 — 科学官
    "military": "\033[31m",  # 红色 — 军事官
    "economy": "\033[33m",   # 黄色 — 经济官
    "phase": "\033[35m",     # 品红 — 阶段标题
    "tool": "\033[32m",      # 绿色 — 工具调用
    "system": "\033[34m",    # 蓝色 — 系统信息
    "vote": "\033[1;37m",    # 粗体白 — 投票结果
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
}

# 角色 → 颜色键
ROLE_COLORS = {
    "科学官": "science",
    "军事官": "military",
    "经济官": "economy",
}

# 角色 → emoji
ROLE_EMOJIS = {
    "科学官": "🔬",
    "军事官": "⚔️",
    "经济官": "💰",
}


def c(color_key: str, text: str) -> str:
    """用颜色包裹文本。"""
    return f"{COLORS.get(color_key, '')}{text}{COLORS['reset']}"


def print_header():
    """打印程序标题。"""
    print()
    print(c("system", "=" * 60))
    print(c("system", "  🌌 星际殖民委员会 — 多 Agent 辩论决策系统"))
    print(c("system", "=" * 60))
    print()


def print_phase(phase_num: int, phase_name: str, description: str):
    """打印阶段标题。"""
    print()
    print(c("phase", f"{'━' * 60}"))
    print(c("phase", f"  📋 第 {phase_num} 阶段：{phase_name}"))
    print(c("phase", f"  {description}"))
    print(c("phase", f"{'━' * 60}"))
    print()


def print_agent_start(role: str, phase: str):
    """打印 Agent 开始执行。"""
    emoji = ROLE_EMOJIS.get(role, "🤖")
    color = ROLE_COLORS.get(role, "system")
    print(c(color, f"  ┌─ {emoji} {role} 开始{phase}..."))


def print_agent_response(role: str, text: str):
    """打印 Agent 的回答。"""
    color = ROLE_COLORS.get(role, "system")
    emoji = ROLE_EMOJIS.get(role, "🤖")

    print(c(color, f"  ├─ {emoji} {role} 发言："))
    print(c(color, "  │"))
    for line in text.strip().split("\n"):
        print(c(color, f"  │  {line}"))
    print(c(color, "  │"))
    print(c(color, f"  └{'─' * 50}"))
    print()


def print_tool_call(role: str, tool_name: str, args: dict, result: str):
    """打印工具调用。"""
    color = ROLE_COLORS.get(role, "system")
    args_str = ", ".join(f"{k}={v}" for k, v in args.items())
    print(c("tool", f"  │  🔧 {tool_name}({args_str})"))

    # 结果只显示前100字符
    short_result = result[:100] + "..." if len(result) > 100 else result
    short_result = short_result.replace("\n", " | ")
    print(c("dim", f"  │     → {short_result}"))


def make_tool_callback(role: str):
    """创建特定角色的工具调用回调。"""
    def callback(tool_name, args, result):
        print_tool_call(role, tool_name, args, result)
    return callback


def print_vote_summary(votes: list[dict], stance_changes: list[dict]):
    """
    打印投票汇总表。

    Args:
        votes: [{"role": "科学官", "vote": "蓝晶星", "confidence": 85, "reason": "..."}]
        stance_changes: [{"role": "科学官", "round1": "蓝晶星", "round3": "蓝晶星", "changed": False}]
    """
    print()
    print(c("vote", "=" * 60))
    print(c("vote", "  🗳️  投票结果汇总"))
    print(c("vote", "=" * 60))
    print()

    # 投票表
    print(c("bold", f"  {'角色':<10} {'投票':<10} {'信心':<8} {'理由'}"))
    print(f"  {'─' * 50}")

    vote_counts = {}
    for v in votes:
        emoji = ROLE_EMOJIS.get(v["role"], "🤖")
        color = ROLE_COLORS.get(v["role"], "system")
        planet = v.get("vote", "未投票")
        confidence = v.get("confidence", "?")
        reason = v.get("reason", "未说明")

        # 截断理由
        if len(reason) > 30:
            reason = reason[:30] + "..."

        print(c(color, f"  {emoji} {v['role']:<8} {planet:<10} {confidence}%{'':>4} {reason}"))

        vote_counts[planet] = vote_counts.get(planet, 0) + 1

    print()

    # 共识判断
    if len(vote_counts) == 1:
        winner = list(vote_counts.keys())[0]
        print(c("vote", f"  🎉 全票通过！殖民委员会一致选择：{winner}"))
    else:
        winner = max(vote_counts, key=vote_counts.get)
        count = vote_counts[winner]
        total = len(votes)
        if count > total / 2:
            print(c("vote", f"  ✅ 多数通过（{count}/{total}）：殖民委员会选择 {winner}"))
        else:
            print(c("system", f"  ⚠️  未达成共识，票数分散："))
            for planet, cnt in sorted(vote_counts.items(), key=lambda x: -x[1]):
                print(c("system", f"      {planet}: {cnt} 票"))

    # 立场变化追踪
    print()
    print(c("bold", "  📊 立场变化追踪："))
    print(f"  {'─' * 50}")
    for sc in stance_changes:
        emoji = ROLE_EMOJIS.get(sc["role"], "🤖")
        color = ROLE_COLORS.get(sc["role"], "system")
        r1 = sc.get("round1", "未知")
        r3 = sc.get("round3", "未知")
        if sc.get("changed"):
            print(c(color, f"  {emoji} {sc['role']}: {r1} → {r3} ⚡ 立场改变"))
        else:
            print(c(color, f"  {emoji} {sc['role']}: {r1} → {r3} ✓ 立场一致"))

    print()
    print(c("vote", "=" * 60))
    print()


def print_separator():
    """打印分隔线。"""
    print(c("dim", f"  {'·' * 50}"))


def print_info(text: str):
    """打印系统信息。"""
    print(c("system", f"  ℹ️  {text}"))


def print_interactive_prompt():
    """打印交互模式提示。"""
    print()
    print(c("system", "  📝 交互模式 — 输入自定义议题，或 'quit' 退出"))
    print(c("dim", "     默认议题：选择最适合的殖民地星球"))
    print()
