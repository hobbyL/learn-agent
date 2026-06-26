"""
命令行交互入口
==============

这是整个项目的启动入口文件。
它负责：
1. 加载 .env 文件中的环境变量（API Key 等）
2. 初始化 Agent
3. 提供一个友好的命令行对话界面
4. 处理用户输入的特殊命令（exit/quit/reset）
5. 优雅处理中断信号（Ctrl+C）

运行方式：
    # 先安装依赖
    pip install -r requirements.txt

    # 复制并填写环境变量
    cp .env.example .env
    # 编辑 .env 文件，填入你的 API Key

    # 启动
    python main.py
"""

# ⚠️ 必须最先调用：在任何其他 import 之前加载 .env 文件
# 原因：agent.py 在被 import 时会立即读取 LOG_LEVEL 等环境变量（模块级代码）
# 如果 load_dotenv() 调用晚于 import agent，.env 里的配置将不会生效
from dotenv import load_dotenv
load_dotenv()

import sys
import os

# 导入我们实现的 Agent 类
from agent import Agent


def print_welcome() -> None:
    """
    打印欢迎信息和使用说明。

    清晰的使用说明可以帮助用户快速上手，减少困惑。
    """
    print("=" * 60)
    print("  欢迎使用简单 AI Agent 演示")
    print("=" * 60)
    print()
    print("这是一个基于 OpenAI Function Calling 的工具调用 Agent。")
    print("Agent 具备以下能力：")
    print("  - 计算数学表达式（calculator）")
    print("  - 查询当前日期时间（get_current_time）")
    print("  - 单位换算（unit_converter）")
    print("  - 统计文本信息（text_stats）")
    print("  - 查询城市天气（get_weather，需要 OpenWeatherMap API Key）")
    print()
    print("特殊命令：")
    print("  exit 或 quit  — 退出程序")
    print("  reset         — 重置对话（清除历史记录，开始新对话）")
    print()
    print("示例问题：")
    print("  现在几点了？")
    print("  计算 2 的 10 次方")
    print("  100 华氏度是多少摄氏度？")
    print("  北京的天气怎么样？")
    print()
    print("-" * 60)
    print()


def main() -> None:
    """
    主函数：程序入口。

    负责初始化环境、创建 Agent 并运行交互循环。
    """

    # ============================================================
    # 步骤 1：初始化 Agent
    # ============================================================
    # Agent.__init__ 会从环境变量读取 OPENAI_API_KEY，
    # 如果没有找到有效的 key，会抛出 ValueError
    try:
        agent = Agent()
    except ValueError as e:
        # 通常是 API Key 未配置
        print(f"[错误] Agent 初始化失败：{e}")
        print()
        print("请按照以下步骤配置：")
        print("1. 在项目目录下复制 .env.example 为 .env 文件：")
        print("   cp .env.example .env")
        print("2. 编辑 .env 文件，填入你的 OpenAI API Key：")
        print("   OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx")
        sys.exit(1)  # 退出程序，返回错误码 1

    # 打印当前日志级别和使用的模型名称，方便调试
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    print(f"[系统] 日志级别：{log_level}  |  使用模型：{agent.model}")
    print()

    # ============================================================
    # 步骤 2：打印欢迎信息
    # ============================================================
    print_welcome()

    # ============================================================
    # 步骤 3：进入交互循环
    # ============================================================
    # 这是一个无限循环，每次迭代处理一轮用户输入和 Agent 回答
    # 退出条件：用户输入 exit/quit，或按 Ctrl+C
    while True:
        try:
            # ---- 接收用户输入 ----
            # input() 会阻塞等待用户输入，按下回车后返回输入字符串
            # "你: " 是提示符，让界面更直观
            user_input = input("你: ").strip()

            # ---- 跳过空输入 ----
            # 用户只按了回车，没有输入任何内容，继续等待
            if not user_input:
                continue

            # ---- 处理特殊命令 ----
            # 使用 lower() 转换为小写，让命令大小写不敏感
            command = user_input.lower()

            # 退出命令
            if command in ("exit", "quit", "退出", "q"):
                print()
                print("再见！感谢使用 AI Agent 演示。")
                break  # 跳出 while 循环，程序正常结束

            # 重置对话命令
            if command in ("reset", "重置", "clear", "新对话"):
                agent.reset()
                print()
                print("[系统] 对话已重置，可以开始新的对话了。")
                print()
                continue  # 不需要调用 Agent，直接进入下一轮循环

            # ---- 调用 Agent 处理正常用户输入 ----
            print()
            print("Agent 正在处理你的请求，请稍候...", flush=True)  # flush=True 确保立即显示，不被缓冲
            print()

            # agent.run() 是核心调用
            # 它会执行完整的"推理 → 工具调用 → 推理"循环，直到返回最终答案
            response = agent.run(user_input)

            # 打印 Agent 的回答
            # 换行和分隔符让界面更易读
            print()
            print(f"Agent: {response}")
            print()
            print("-" * 60)
            print()

        except KeyboardInterrupt:
            # ============================================================
            # 优雅处理 Ctrl+C
            # ============================================================
            # 用户在输入过程中按下 Ctrl+C 会触发 KeyboardInterrupt
            # 不打印 Python 默认的错误堆栈，而是显示友好的退出提示
            print()  # 换行，避免提示符和"^C"混在一行
            print()
            print("收到退出信号（Ctrl+C），再见！")
            break  # 退出循环


# ============================================================
# Python 模块入口约定
# ============================================================
# 当该文件作为主程序直接运行时（python main.py），__name__ 等于 "__main__"
# 当该文件被其他模块 import 时，__name__ 等于模块名（"main"），不会执行 main()
# 这种写法是 Python 的标准入口约定，可以让文件既能运行，也能被导入
if __name__ == "__main__":
    main()
