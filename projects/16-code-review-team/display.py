"""
代码审查团队 —— 展示层
=======================

ANSI 着色展示审查过程（5 种颜色）+ 汇总表。
"""

from schemas import ReviewResult


# ============================================================
# ANSI 颜色定义
# ============================================================

class Colors:
    RED = "\033[91m"      # 安全审查员
    YELLOW = "\033[93m"   # 性能审查员
    BLUE = "\033[94m"     # 架构审查员
    CYAN = "\033[96m"     # 规范审查员
    GREEN = "\033[92m"    # 主审
    GRAY = "\033[90m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


# ============================================================
# 展示函数
# ============================================================

def print_header(text: str):
    """打印标题"""
    print(f"\n{Colors.BOLD}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{text:^60}{Colors.RESET}")
    print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}\n")


def print_code_sample(file_name: str, code: str):
    """打印代码片段"""
    print(f"{Colors.GRAY}【代码文件】{file_name}{Colors.RESET}")
    print(f"{Colors.GRAY}{'-' * 60}{Colors.RESET}")
    # 只展示前 10 行
    lines = code.strip().split('\n')
    for i, line in enumerate(lines[:10], 1):
        print(f"{Colors.GRAY}{i:3d} | {line}{Colors.RESET}")
    if len(lines) > 10:
        print(f"{Colors.GRAY}    ... (共 {len(lines)} 行){Colors.RESET}")
    print()


def print_reviewer_start(reviewer_name: str, color: str):
    """打印审查员开始"""
    color_code = getattr(Colors, color)
    print(f"{color_code}▶ {reviewer_name} 开始审查...{Colors.RESET}")


def print_reviewer_result(reviewer_name: str, result: ReviewResult, color: str):
    """打印审查员结果"""
    color_code = getattr(Colors, color)

    print(f"\n{color_code}{'─' * 60}{Colors.RESET}")
    print(f"{color_code}{Colors.BOLD}{reviewer_name} 审查结果{Colors.RESET}")
    print(f"{color_code}{'─' * 60}{Colors.RESET}")

    print(f"{color_code}发现问题数：{len(result.findings)}{Colors.RESET}")
    print(f"{color_code}通过审查：{'✓ 是' if result.pass_review else '✗ 否'}{Colors.RESET}")
    print(f"{color_code}总结：{result.summary}{Colors.RESET}\n")

    if result.findings:
        print(f"{color_code}问题列表：{Colors.RESET}")
        for i, finding in enumerate(result.findings, 1):
            severity_color = Colors.RED if finding.severity == "P0" else (
                Colors.YELLOW if finding.severity == "P1" else Colors.GRAY
            )
            print(f"{color_code}{i}. {severity_color}[{finding.severity}]{color_code} "
                  f"{finding.file}:{finding.line}{Colors.RESET}")
            print(f"   {Colors.GRAY}{finding.description}{Colors.RESET}")
            print(f"   {Colors.GRAY}建议：{finding.suggestion}{Colors.RESET}")
    else:
        print(f"{color_code}✓ 未发现问题{Colors.RESET}")

    print()


def print_lead_start():
    """打印主审开始"""
    print(f"\n{Colors.GREEN}{Colors.BOLD}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}{'主审汇总':^58}{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}{'=' * 60}{Colors.RESET}\n")
    print(f"{Colors.GREEN}▶ 主审正在汇总所有审查结果...{Colors.RESET}\n")


def print_final_report(report: str):
    """打印最终报告"""
    print(f"{Colors.GREEN}{'─' * 60}{Colors.RESET}")
    print(f"{Colors.GREEN}{report}{Colors.RESET}")
    print(f"{Colors.GREEN}{'─' * 60}{Colors.RESET}\n")


def print_summary_table(reviewer_results: list[ReviewResult]):
    """打印汇总表"""
    print(f"\n{Colors.BOLD}{'审查汇总表':^60}{Colors.RESET}")
    print(f"{Colors.GRAY}{'─' * 60}{Colors.RESET}")
    print(f"{'审查员':<20} {'发现问题':<10} {'P0':<6} {'P1':<6} {'P2':<6} {'通过':<6}")
    print(f"{Colors.GRAY}{'─' * 60}{Colors.RESET}")

    total_findings = 0
    total_p0 = 0
    total_p1 = 0
    total_p2 = 0

    for result in reviewer_results:
        p0 = sum(1 for f in result.findings if f.severity == "P0")
        p1 = sum(1 for f in result.findings if f.severity == "P1")
        p2 = sum(1 for f in result.findings if f.severity == "P2")

        total_findings += len(result.findings)
        total_p0 += p0
        total_p1 += p1
        total_p2 += p2

        pass_mark = "✓" if result.pass_review else "✗"
        print(f"{result.reviewer:<20} {len(result.findings):<10} {p0:<6} {p1:<6} {p2:<6} {pass_mark:<6}")

    print(f"{Colors.GRAY}{'─' * 60}{Colors.RESET}")
    print(f"{'总计':<20} {total_findings:<10} {total_p0:<6} {total_p1:<6} {total_p2:<6}")
    print(f"{Colors.GRAY}{'─' * 60}{Colors.RESET}\n")


def print_preset_issues_comparison(preset_count: dict, found_by_reviewers: dict):
    """打印预设问题对比（验证召回率）"""
    print(f"\n{Colors.BOLD}{'预设问题召回率':^60}{Colors.RESET}")
    print(f"{Colors.GRAY}{'─' * 60}{Colors.RESET}")
    print(f"{'维度':<20} {'预设问题':<10} {'发现问题':<10} {'召回率':<10}")
    print(f"{Colors.GRAY}{'─' * 60}{Colors.RESET}")

    for category in ["security", "performance", "architecture", "style"]:
        preset = preset_count.get(category, 0)
        found = found_by_reviewers.get(category, 0)
        recall = f"{found / preset * 100:.0f}%" if preset > 0 else "N/A"
        print(f"{category:<20} {preset:<10} {found:<10} {recall:<10}")

    print(f"{Colors.GRAY}{'─' * 60}{Colors.RESET}\n")
