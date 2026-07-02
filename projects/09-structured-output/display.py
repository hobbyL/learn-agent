"""
展示模块 —— 结构化输出 ANSI 着色展示
======================================

ANSI 颜色方案：
- 成功（✓ 校验通过）：绿色
- 失败（✗ 校验失败）：红色
- 警告（重试）：黄色
- 标题/分隔线：加粗
- 模式名称：cyan
- 层级名称：灰色
- 数据摘要：亮白

展示内容：
1. 对比矩阵（--compare/--demo）：行=难度层级，列=输出模式
2. 每格内容：提取结果摘要 + 校验状态 + 重试次数
3. 最终汇总：各模式成功率、平均重试次数
4. 交互模式：实时展示提取结果 + 校验状态
"""

import sys
from typing import Any

from pydantic import BaseModel

# ANSI 转义码
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_BRIGHT_WHITE = "\033[97m"
_GRAY = "\033[90m"


# ============================================================
# 会话标题
# ============================================================

def print_session_header(mode: str) -> None:
    """打印会话标题。"""
    mode_labels = {
        "compare": "🔍 结构化输出完整对比（4 层级 × 3 模式）",
        "demo": "⚡ 结构化输出快速演示（2 层级 × 3 模式）",
        "interactive": "💬 交互式结构化提取",
    }
    label = mode_labels.get(mode, mode)
    print(f"\n{_BOLD}{'═'*70}{_RESET}")
    print(f"{_BOLD}{label}{_RESET}")
    print(f"{_BOLD}{'═'*70}{_RESET}\n")


# ============================================================
# 对比矩阵展示
# ============================================================

def print_compare_matrix_header(levels: list[str], modes: list[str]) -> None:
    """
    打印对比矩阵表头。

    格式：
        层级            json_schema      json_object      text
        ──────────────────────────────────────────────────────
    """
    mode_labels = {
        "json_schema": "json_schema",
        "json_object": "json_object",
        "text": "text",
    }

    # 表头行
    header = f"  {'层级':<15}"
    for mode in modes:
        header += f" {mode_labels[mode]:^18}"
    print(f"{_BOLD}{header}{_RESET}")
    print(f"  {_DIM}{'─'*66}{_RESET}")


def print_compare_row(
    level_label: str,
    results: dict[str, tuple[Any, dict]],
) -> None:
    """
    打印对比矩阵的一行（一个难度层级 × 3 种模式的结果）。

    参数：
        level_label — 层级标签（如 "L1 单实体"）
        results — {mode: (result, metadata)} 字典
    """
    row = f"  {_GRAY}{level_label:<15}{_RESET}"

    for mode in ["json_schema", "json_object", "text"]:
        result, meta = results.get(mode, (None, {}))
        cell = _format_result_cell(result, meta)
        row += f" {cell:^25}"  # 18 + 7 for ANSI codes approx

    print(row)


def _format_result_cell(result: Any, metadata: dict) -> str:
    """
    格式化单元格内容：校验状态 + 重试次数。

    示例：
        ✓ 0 次        （绿色，无重试）
        ✓ 2 次        （绿色，重试 2 次后成功）
        ✗ 3 次        （红色，重试 3 次后失败）
    """
    is_valid = metadata.get("is_valid", False)
    retries = metadata.get("retries", 0)

    if is_valid:
        status = f"{_GREEN}✓{_RESET}"
        retry_text = f"{retries} 次"
    else:
        status = f"{_RED}✗{_RESET}"
        retry_text = f"{_RED}{retries} 次{_RESET}"

    return f"{status} {retry_text}"


def print_compare_summary(all_results: dict[str, dict[str, tuple[Any, dict]]]) -> None:
    """
    打印最终汇总统计。

    参数：
        all_results — {level_name: {mode: (result, metadata)}}
    """
    print(f"\n{_BOLD}{'─'*70}{_RESET}")
    print(f"{_BOLD}📊 汇总统计{_RESET}")
    print(f"{_BOLD}{'─'*70}{_RESET}\n")

    # 统计各模式的成功率和平均重试次数
    modes = ["json_schema", "json_object", "text"]
    mode_labels = {
        "json_schema": "json_schema 强制模式",
        "json_object": "json_object 弱模式",
        "text": "text 纯文本模式",
    }

    for mode in modes:
        total = 0
        success = 0
        total_retries = 0

        for level_results in all_results.values():
            if mode in level_results:
                result, meta = level_results[mode]
                total += 1
                if meta.get("is_valid", False):
                    success += 1
                total_retries += meta.get("retries", 0)

        success_rate = (success / total * 100) if total > 0 else 0
        avg_retries = (total_retries / total) if total > 0 else 0

        color = _GREEN if success == total else (_YELLOW if success > 0 else _RED)
        print(f"  {_CYAN}{mode_labels[mode]:<25}{_RESET} "
              f"成功率: {color}{success}/{total}{_RESET} ({success_rate:.0f}%)  "
              f"平均重试: {avg_retries:.1f} 次")

    print()


# ============================================================
# 单次提取展示（交互模式）
# ============================================================

def print_extraction_start(level_label: str, mode: str) -> None:
    """打印提取任务开始提示。"""
    mode_labels = {
        "json_schema": "json_schema 强制模式",
        "json_object": "json_object 弱模式",
        "text": "text 纯文本模式",
    }
    print(f"\n{_BOLD}🔍 开始提取{_RESET}")
    print(f"  层级: {_GRAY}{level_label}{_RESET}")
    print(f"  模式: {_CYAN}{mode_labels.get(mode, mode)}{_RESET}")


def print_extraction_result(
    result: Any,
    metadata: dict,
    verbose: bool = False,
) -> None:
    """
    打印提取结果。

    参数：
        result — Pydantic Model 实例（成功时）或 None（失败时）
        metadata — 提取元数据
        verbose — 是否展示详细错误信息
    """
    is_valid = metadata.get("is_valid", False)
    retries = metadata.get("retries", 0)
    errors = metadata.get("errors", [])

    print(f"\n{_BOLD}{'─'*50}{_RESET}")

    if is_valid:
        print(f"{_GREEN}✓ 校验通过{_RESET}")
        if retries > 0:
            print(f"{_YELLOW}  重试次数: {retries}{_RESET}")
        print(f"\n{_BOLD}提取结果:{_RESET}")
        print(_format_result_summary(result))
    else:
        print(f"{_RED}✗ 校验失败{_RESET}")
        print(f"{_RED}  重试次数: {retries}{_RESET}")
        if verbose and errors:
            print(f"\n{_BOLD}错误信息:{_RESET}")
            for i, err in enumerate(errors, 1):
                print(f"{_RED}  {i}. {err}{_RESET}")

    print(f"{_BOLD}{'─'*50}{_RESET}\n")


def _format_result_summary(result: Any) -> str:
    """
    格式化提取结果的摘要信息。

    对不同类型的 Model 展示不同的关键字段。
    """
    if result is None:
        return f"{_RED}  (无){_RESET}"

    if not isinstance(result, BaseModel):
        return f"{_BRIGHT_WHITE}  {result}{_RESET}"

    # 根据 Model 类型展示关键字段
    model_name = result.__class__.__name__

    if model_name == "DeveloperProfile":
        return (
            f"{_BRIGHT_WHITE}  姓名: {result.name}\n"
            f"  角色: {result.role}\n"
            f"  项目组: {result.team}\n"
            f"  技能: {', '.join(result.skills[:3])}{'...' if len(result.skills) > 3 else ''}{_RESET}"
        )
    elif model_name == "TeamList":
        count = len(result.teams)
        teams_str = ", ".join(t.name for t in result.teams[:3])
        if count > 3:
            teams_str += "..."
        return (
            f"{_BRIGHT_WHITE}  项目组数量: {count}\n"
            f"  项目组: {teams_str}{_RESET}"
        )
    elif model_name == "GameDetail":
        return (
            f"{_BRIGHT_WHITE}  游戏: {result.name}\n"
            f"  类别: {result.genre}\n"
            f"  项目组负责人: {result.team.lead}\n"
            f"  技术栈: {', '.join(result.tech_stack[:3])}{'...' if len(result.tech_stack) > 3 else ''}\n"
            f"  里程碑数: {len(result.milestones)}{_RESET}"
        )
    elif model_name == "ComparisonReport":
        return (
            f"{_BRIGHT_WHITE}  对比主体: {result.subject_a} vs {result.subject_b}\n"
            f"  对比维度数: {len(result.dimensions)}\n"
            f"  总结: {result.summary[:60]}...{_RESET}"
        )
    else:
        # 默认展示前 3 个字段
        lines = []
        for key, value in result.model_dump().items():
            if len(lines) >= 3:
                lines.append("  ...")
                break
            if isinstance(value, list):
                value_str = f"[{len(value)} 项]"
            elif isinstance(value, dict):
                value_str = "{...}"
            else:
                value_str = str(value)[:50]
            lines.append(f"  {key}: {value_str}")
        return f"{_BRIGHT_WHITE}{chr(10).join(lines)}{_RESET}"


# ============================================================
# 错误与信息提示
# ============================================================

def print_error(msg: str) -> None:
    """红色错误信息。"""
    print(f"\n{_RED}❌ 错误：{msg}{_RESET}", file=sys.stderr)


def print_info(msg: str) -> None:
    """普通信息。"""
    print(f"{_DIM}{msg}{_RESET}")


def print_separator() -> None:
    """分隔线。"""
    print(f"{_DIM}{'─'*70}{_RESET}")


# ============================================================
# 快速验证
# ============================================================

if __name__ == "__main__":
    print("=== Display 模块快速验证 ===\n")

    print_session_header("compare")

    # 模拟对比矩阵
    levels = ["level1_developer", "level2_teams"]
    modes = ["json_schema", "json_object", "text"]

    print_compare_matrix_header(levels, modes)

    # 模拟第一行（所有成功）
    results_row1 = {
        "json_schema": (object(), {"is_valid": True, "retries": 0}),
        "json_object": (object(), {"is_valid": True, "retries": 1}),
        "text": (object(), {"is_valid": True, "retries": 2}),
    }
    print_compare_row("L1 单实体", results_row1)

    # 模拟第二行（部分失败）
    results_row2 = {
        "json_schema": (object(), {"is_valid": True, "retries": 0}),
        "json_object": (None, {"is_valid": False, "retries": 3}),
        "text": (object(), {"is_valid": True, "retries": 1}),
    }
    print_compare_row("L2 多实体", results_row2)

    # 汇总统计
    all_results = {
        "level1": results_row1,
        "level2": results_row2,
    }
    print_compare_summary(all_results)

    print("\nDisplay 模块验证通过 ✓")
