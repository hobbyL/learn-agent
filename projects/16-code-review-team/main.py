"""
代码审查团队 —— 主入口
=======================

CLI: --demo / --interactive
"""

import os
import argparse
from dotenv import load_dotenv
from openai import OpenAI

from code_samples import get_sample, get_all_samples, get_preset_issues_count
from orchestrator import run_code_review
from agents import REVIEWERS
from display import (
    print_header, print_code_sample, print_reviewer_start, print_reviewer_result,
    print_lead_start, print_final_report, print_summary_table,
    print_preset_issues_comparison
)


def run_demo(client: OpenAI, model: str):
    """
    Demo 模式：展示完整审查流程。
    审查代码片段 A（用户认证模块，安全问题最多）。
    """
    print_header("代码审查团队 Demo")

    # 选择代码片段 A（安全问题）
    sample = get_sample("A_user_auth")
    code = sample["code"]
    file_name = sample["file"]

    print_code_sample(file_name, code)

    # 回调：审查员完成时展示
    def on_reviewer_complete(reviewer_name: str, result):
        reviewer_config = next((r for r in REVIEWERS if r["name"] == reviewer_name), None)
        if reviewer_config:
            print_reviewer_result(reviewer_name, result, reviewer_config["color"])

    # 回调：主审完成时展示
    def on_lead_complete(report: str):
        print_final_report(report)

    # 执行审查（带进度展示）
    print(f"\n{'▶ 启动 4 位审查员并行审查...'}\n")
    for reviewer in REVIEWERS:
        print_reviewer_start(reviewer["name"], reviewer["color"])

    reviewer_results, final_report = run_code_review(
        code=code,
        file_name=file_name,
        client=client,
        model=model,
        on_reviewer_complete=on_reviewer_complete
    )

    # 主审汇总
    print_lead_start()
    print_final_report(final_report)

    # 汇总表
    print_summary_table(reviewer_results)

    # 召回率对比（仅针对代码 A）
    preset_count = {
        "security": len(sample["preset_issues"]["security"]),
        "performance": len(sample["preset_issues"]["performance"]),
        "architecture": len(sample["preset_issues"]["architecture"]),
        "style": len(sample["preset_issues"]["style"])
    }

    found_count = {
        "security": len(reviewer_results[0].findings),      # 安全审查员
        "performance": len(reviewer_results[1].findings),   # 性能审查员
        "architecture": len(reviewer_results[2].findings),  # 架构审查员
        "style": len(reviewer_results[3].findings)          # 规范审查员
    }

    print_preset_issues_comparison(preset_count, found_count)


def run_interactive(client: OpenAI, model: str):
    """
    Interactive 模式：用户选择代码片段或输入自定义代码。
    """
    print_header("代码审查团队 Interactive")

    print("可用的代码片段：")
    samples = get_all_samples()
    for i, (key, sample) in enumerate(samples.items(), 1):
        print(f"{i}. {sample['description']} ({sample['file']})")

    print(f"{len(samples) + 1}. 输入自定义代码")

    choice = input("\n选择代码片段（输入编号）: ").strip()

    if choice.isdigit() and 1 <= int(choice) <= len(samples):
        sample_key = list(samples.keys())[int(choice) - 1]
        sample = get_sample(sample_key)
        code = sample["code"]
        file_name = sample["file"]
    else:
        print("\n请输入代码（输入 EOF 或按 Ctrl+D 结束）：")
        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass
        code = "\n".join(lines)
        file_name = "custom_code.py"

    print_code_sample(file_name, code)

    # 执行审查
    print(f"\n{'▶ 启动 4 位审查员并行审查...'}\n")
    for reviewer in REVIEWERS:
        print_reviewer_start(reviewer["name"], reviewer["color"])

    reviewer_results, final_report = run_code_review(
        code=code,
        file_name=file_name,
        client=client,
        model=model
    )

    # 展示结果
    for i, result in enumerate(reviewer_results):
        print_reviewer_result(REVIEWERS[i]["name"], result, REVIEWERS[i]["color"])

    print_lead_start()
    print_final_report(final_report)

    print_summary_table(reviewer_results)


def main():
    # 加载 .env
    load_dotenv()

    parser = argparse.ArgumentParser(description="代码审查团队 - 多 Agent 分工协作")
    parser.add_argument("--demo", action="store_true", help="运行 demo 模式")
    parser.add_argument("--interactive", action="store_true", help="运行 interactive 模式")
    args = parser.parse_args()

    # OpenAI client
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL")
    )
    model = os.getenv("OPENAI_MODEL", "gpt-4")

    if args.interactive:
        run_interactive(client, model)
    else:
        # 默认 demo
        run_demo(client, model)


if __name__ == "__main__":
    main()
