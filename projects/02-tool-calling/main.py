"""
命令行交互入口（02 版）
=======================

与 01 的入口几乎一致，仅更新了欢迎信息里的工具清单和示例问题。
启动方式：
    pip install -r requirements.txt
    cp .env.example .env   # 填入 OPENAI_API_KEY
    python main.py
"""

# ⚠️ 必须最先调用：在 import agent 之前加载 .env
# 原因见 01 的踩坑记录：agent.py 在 import 时会读取 LOG_LEVEL 等模块级环境变量，
# load_dotenv 晚于 import 就不生效。
from dotenv import load_dotenv
load_dotenv()

import sys
import os

from agent import Agent


def print_welcome() -> None:
    """打印欢迎信息和使用说明。"""
    print("=" * 60)
    print("  项目 02：工具系统架构 —— 注册表驱动的 Agent")
    print("=" * 60)
    print()
    print("这个 Agent 的工具全部由 @tool 装饰器自动注册，")
    print("Schema 由函数签名自动生成，agent 本身不感知具体工具。")
    print()
    print("可用工具：")
    print("  - password_generator  生成随机密码")
    print("  - random_picker       从列表里随机抽取")
    print("  - color_converter     颜色格式转换（hex/rgb/hsl）")
    print("  - base_converter      进制转换（2~36 进制）")
    print("  - text_caseconverter  文本大小写转换（upper/lower/title/snake/camel）")
    print("  - dice_roller         掷骰子")
    print("  - hash_generator      计算哈希（md5/sha1/sha256）")
    print("  - qr_text_encoder     文本转字符画二维码")
    print()
    print("特殊命令：")
    print("  exit / quit  — 退出程序")
    print("  reset        — 重置对话")
    print()
    print("示例问题：")
    print("  生成一个 16 位带符号的密码")
    print("  把 #ff8800 转成 rgb")
    print("  255 的十六进制是多少？")
    print("  帮我把 hello_world 转成驼峰命名")
    print("  掷 3 个 20 面骰子")
    print("  计算 hello 的 sha256")
    print("  （试试故意传错）把颜色 #ff8800 转成 yuv 格式  ← 看校验如何反馈")
    print()
    print("-" * 60)
    print()


def main() -> None:
    """主函数：初始化环境、创建 Agent、运行交互循环。"""
    try:
        agent = Agent()
    except ValueError as e:
        print(f"[错误] Agent 初始化失败：{e}")
        print()
        print("请按照以下步骤配置：")
        print("1. 复制 .env.example 为 .env：cp .env.example .env")
        print("2. 编辑 .env，填入：OPENAI_API_KEY=sk-xxxxxxxx")
        sys.exit(1)

    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    print(f"[系统] 日志级别：{log_level}  |  使用模型：{agent.model}")
    print()

    print_welcome()

    while True:
        try:
            user_input = input("你: ").strip()

            if not user_input:
                continue

            command = user_input.lower()

            if command in ("exit", "quit", "退出", "q"):
                print()
                print("再见！")
                break

            if command in ("reset", "重置", "clear", "新对话"):
                agent.reset()
                print()
                print("[系统] 对话已重置。")
                print()
                continue

            print()
            print("Agent 正在处理你的请求，请稍候...", flush=True)
            print()

            response = agent.run(user_input)

            print()
            print(f"Agent: {response}")
            print()
            print("-" * 60)
            print()

        except KeyboardInterrupt:
            print()
            print()
            print("收到退出信号（Ctrl+C），再见！")
            break


if __name__ == "__main__":
    main()
