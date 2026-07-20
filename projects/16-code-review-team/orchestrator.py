"""
代码审查团队 —— 协作编排器
===========================

两层协作流程：4 个审查员并行执行 → 主审汇总。
"""

from openai import OpenAI
from agents import REVIEWERS, review_code, lead_review, LEAD_REVIEWER
from schemas import ReviewResult
from typing import Callable


def run_code_review(
    code: str,
    file_name: str,
    client: OpenAI,
    model: str,
    on_reviewer_complete: Callable[[str, ReviewResult], None] = None,
    on_lead_complete: Callable[[str], None] = None
) -> tuple[list[ReviewResult], str]:
    """
    运行完整的代码审查流程。

    Args:
        code: 代码片段
        file_name: 文件名
        client: OpenAI client
        model: 模型名称
        on_reviewer_complete: 单个审查员完成时的回调
        on_lead_complete: 主审完成时的回调

    Returns:
        (审查员结果列表, 主审最终报告)
    """
    # 第一层：4 个审查员并行执行（这里顺序执行，实际可用 asyncio 并行）
    reviewer_results = []

    for reviewer in REVIEWERS:
        result = review_code(code, file_name, reviewer, client, model)
        reviewer_results.append(result)

        if on_reviewer_complete:
            on_reviewer_complete(reviewer["name"], result)

    # 第二层：主审汇总
    final_report = lead_review(reviewer_results, client, model)

    if on_lead_complete:
        on_lead_complete(final_report)

    return reviewer_results, final_report
