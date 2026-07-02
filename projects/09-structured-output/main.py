"""
主入口 —— 结构化输出 Agent 运行模式
====================================

支持 3 种运行模式：

1. --compare（默认）
   完整对比：4 层级 × 3 模式 = 12 组，展示对比矩阵 + 汇总统计

2. --demo
   精简对比：2 层级 × 3 模式 = 6 组，快速演示

3. --interactive
   交互模式：用户选择层级 + 模式，实时查看提取结果

环境变量（.env 文件）：
    OPENAI_API_KEY=your-key
    OPENAI_BASE_URL=https://api.openai.com/v1  (可选)
    MODEL_NAME=gpt-4o-mini
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

from knowledge_base import get_full_knowledge_text
from schemas import SCHEMA_REGISTRY, LEVEL_ORDER, LEVEL_LABELS
from extractor import extract
from display import (
    print_session_header,
    print_compare_matrix_header,
    print_compare_row,
    print_compare_summary,
    print_extraction_start,
    print_extraction_result,
    print_error,
    print_info,
    print_separator,
)


# ============================================================
# 配置加载
# ============================================================

def load_config() -> tuple[OpenAI, str]:
    """
    加载环境变量，返回 (OpenAI client, model_name)。
    找不到 API key 时直接退出。
    """
    load_dotenv()

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    model = os.environ.get("MODEL_NAME", "gpt-4o-mini").strip()

    if not api_key:
        print_error("未找到 OPENAI_API_KEY 环境变量。请创建 .env 文件并配置 API Key。")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url=base_url)
    return client, model


# ============================================================
# 运行模式：compare / demo
# ============================================================

def run_compare_mode(levels: list[str], mode: str = "compare") -> None:
    """
    对比模式：多层级 × 3 模式全矩阵对比。

    参数：
        levels — 要测试的层级列表（如 ["level1_developer", "level2_teams"]）
        mode — "compare" | "demo"（用于标题显示）
    """
    client, model_name = load_config()
    knowledge_text = get_full_knowledge_text()
    modes = ["json_schema", "json_object", "text"]

    print_session_header(mode)
    print_info(f"模型: {model_name}")
    print_info(f"知识库字符数: {len(knowledge_text)}")
    print_separator()

    # 打印对比矩阵表头
    print()
    print_compare_matrix_header(levels, modes)

    # 存储所有结果，用于最后的汇总统计
    all_results: dict[str, dict[str, tuple]] = {}

    # 逐层级、逐模式执行提取
    for level_name in levels:
        schema_class, prompt, desc = SCHEMA_REGISTRY[level_name]
        level_label = LEVEL_LABELS[level_name]

        level_results = {}

        for mode_name in modes:
            print_info(f"  执行: {level_label} × {mode_name} ...", )
            try:
                result, metadata = extract(
                    knowledge_text=knowledge_text,
                    prompt=prompt,
                    schema_class=schema_class,
                    mode=mode_name,
                    client=client,
                    model=model_name,
                )
                level_results[mode_name] = (result, metadata)
            except Exception as e:
                print_error(f"提取失败: {e}")
                level_results[mode_name] = (None, {
                    "is_valid": False,
                    "retries": 0,
                    "errors": [str(e)],
                    "raw_output": "",
                })

        # 打印该层级的结果行
        print_compare_row(level_label, level_results)
        all_results[level_name] = level_results

    # 打印汇总统计
    print_compare_summary(all_results)


# ============================================================
# 运行模式：interactive
# ============================================================

def run_interactive_mode() -> None:
    """
    交互模式：用户选择层级 + 模式，实时查看提取结果。
    """
    client, model_name = load_config()
    knowledge_text = get_full_knowledge_text()

    print_session_header("interactive")
    print_info(f"模型: {model_name}")
    print_info(f"知识库字符数: {len(knowledge_text)}")
    print_separator()

    print("\n可用层级:")
    for i, level_name in enumerate(LEVEL_ORDER, 1):
        label = LEVEL_LABELS[level_name]
        _, _, desc = SCHEMA_REGISTRY[level_name]
        print(f"  {i}. {label} — {desc}")

    print("\n可用模式:")
    modes = ["json_schema", "json_object", "text"]
    mode_labels = {
        "json_schema": "json_schema 强制模式（100% 符合 schema）",
        "json_object": "json_object 弱模式（合法 JSON + 重试）",
        "text": "text 纯文本模式（自由文本 + JSON 提取 + 重试）",
    }
    for i, mode in enumerate(modes, 1):
        print(f"  {i}. {mode_labels[mode]}")

    print("\n输入格式：<层级编号> <模式编号>  或  'exit' 退出")
    print("示例：1 1  （提取 L1 单实体 × json_schema 模式）\n")

    while True:
        try:
            user_input = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q"):
            print("再见！")
            break

        parts = user_input.split()
        if len(parts) != 2:
            print_error("输入格式错误。请输入：<层级编号> <模式编号>")
            continue

        try:
            level_idx = int(parts[0]) - 1
            mode_idx = int(parts[1]) - 1
        except ValueError:
            print_error("编号必须是数字。")
            continue

        if not (0 <= level_idx < len(LEVEL_ORDER)):
            print_error(f"层级编号超出范围（1-{len(LEVEL_ORDER)}）。")
            continue

        if not (0 <= mode_idx < len(modes)):
            print_error(f"模式编号超出范围（1-{len(modes)}）。")
            continue

        level_name = LEVEL_ORDER[level_idx]
        mode_name = modes[mode_idx]
        level_label = LEVEL_LABELS[level_name]
        schema_class, prompt, desc = SCHEMA_REGISTRY[level_name]

        print_extraction_start(level_label, mode_name)

        try:
            result, metadata = extract(
                knowledge_text=knowledge_text,
                prompt=prompt,
                schema_class=schema_class,
                mode=mode_name,
                client=client,
                model=model_name,
            )
            print_extraction_result(result, metadata, verbose=True)
        except Exception as e:
            print_error(f"提取失败: {e}")


# ============================================================
# 命令行参数解析
# ============================================================

def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="游戏工作室结构化输出 Agent —— 3 种模式对比",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python3 main.py --compare       # 完整对比（4 层级 × 3 模式）
  python3 main.py --demo          # 快速演示（2 层级 × 3 模式）
  python3 main.py --interactive   # 交互模式
        """,
    )

    parser.add_argument(
        "--compare",
        action="store_true",
        help="完整对比模式（4 层级 × 3 模式 = 12 组）",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="快速演示模式（2 层级 × 3 模式 = 6 组）",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="交互模式（用户选择层级和模式）",
    )

    return parser.parse_args()


# ============================================================
# 主函数
# ============================================================

def main() -> None:
    """程序入口，根据命令行参数分发到对应运行模式。"""
    args = parse_args()

    if args.compare:
        # 完整对比：4 层级
        run_compare_mode(LEVEL_ORDER, mode="compare")
    elif args.demo:
        # 快速演示：2 层级（单实体 + 嵌套关系）
        demo_levels = ["level1_developer", "level3_game"]
        run_compare_mode(demo_levels, mode="demo")
    elif args.interactive:
        # 交互模式
        run_interactive_mode()
    else:
        # 默认：完整对比
        run_compare_mode(LEVEL_ORDER, mode="compare")


if __name__ == "__main__":
    main()
