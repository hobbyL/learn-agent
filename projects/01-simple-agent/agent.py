"""
Agent 核心循环 —— 深度注释学习版
=====================================

什么是 Agent 核心循环？
-----------------------
传统程序的执行路径是固定的：代码写死了"先做 A，再做 B，再做 C"。
而 Agent（智能体）的执行路径是动态的：由大语言模型（LLM）在每一步决定
"接下来该做什么"。

这种动态决策能力来自 LLM 强大的推理能力。Agent 的核心循环模式如下：

    用户输入
        ↓
    LLM 推理（"我需要调用工具吗？调用哪个工具？"）
        ↓
    如果需要工具 ──────────────────→ 执行工具
                                         ↓
                               把工具结果返回给 LLM ──→ 回到 LLM 推理
        ↓
    如果不需要工具（直接回答）
        ↓
    返回最终答案给用户

这个"LLM 推理 → 工具执行 → LLM 推理"的循环，就是 ReAct 模式
（Reasoning + Acting），是现代 AI Agent 最核心的设计模式之一。

------------------------------------------------------------------

OpenAI Function Calling 的工作原理
------------------------------------
OpenAI 的 Function Calling（函数调用）是实现上述循环的技术机制。
整体流程分为以下几步：

步骤 1：开发者定义工具描述（JSON Schema 格式），告诉 LLM 有哪些工具可用。
        示例：{
            "type": "function",
            "function": {
                "name": "calculator",
                "description": "计算数学表达式",
                "parameters": { "type": "object", "properties": { ... } }
            }
        }

步骤 2：把工具描述列表（tools 参数）和对话历史（messages 参数）一起传给 LLM。
        LLM 会读取工具描述，判断是否需要调用工具。

步骤 3：LLM 的响应有两种可能：
        情况 A：直接回答（finish_reason == "stop"）
                LLM 认为不需要调用工具，直接生成文本回答。
        情况 B：请求调用工具（finish_reason == "tool_calls"）
                LLM 输出结构化的工具调用请求，例如：
                {
                    "id": "call_abc123",
                    "type": "function",
                    "function": {
                        "name": "calculator",
                        "arguments": '{"expression": "2 + 3"}'
                    }
                }
                注意：LLM 只是"请求"调用工具，它自己无法执行代码！
                真正执行工具的是我们的 Python 代码。

步骤 4：我们的代码接收到工具调用请求后：
        a. 解析工具名称和参数（arguments 是 JSON 字符串，需要反序列化）
        b. 找到对应的 Python 函数并执行
        c. 把执行结果序列化为字符串，以 role="tool" 的消息追加到 messages

步骤 5：把包含工具结果的 messages 再次传给 LLM，让它根据结果继续推理。

步骤 6：重复步骤 2~5，直到 LLM 输出最终文本回答。

这个机制的关键洞察：
- LLM 是"大脑"，负责推理和决策。
- 我们的代码是"手脚"，负责实际执行工具。
- messages 列表是"记忆"，保存了完整的对话历史（包括工具调用和结果）。

------------------------------------------------------------------
"""

import json
import os
from typing import Optional

from openai import OpenAI, APIError, APIConnectionError, APITimeoutError, RateLimitError

# ============================================================
# 简易分级日志工具
# ============================================================
# 通过环境变量 LOG_LEVEL 控制输出级别：
#   DEBUG — 显示所有细节（工具参数、API 响应等）
#   INFO  — 只显示关键步骤（默认）
#   OFF   — 静默模式，不输出任何日志

_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

_LEVEL_RANK = {"DEBUG": 0, "INFO": 1, "WARN": 2, "OFF": 99}
_COLORS = {
    "DEBUG": "\033[90m",  # 灰色
    "INFO":  "\033[36m",  # 青色
    "WARN":  "\033[33m",  # 黄色
    "ERROR": "\033[31m",  # 红色
}
_RESET = "\033[0m"


def _log(level: str, msg: str) -> None:
    """输出带颜色的日志，根据 LOG_LEVEL 环境变量过滤级别"""
    if _LEVEL_RANK.get(level, 0) >= _LEVEL_RANK.get(_LOG_LEVEL, 1):
        color = _COLORS.get(level, "")
        print(f"{color}[{level}]{_RESET}  {msg}")

# 导入工具函数和工具定义元数据
# TOOLS_DEFINITION 是描述工具的 JSON Schema 列表，传给 LLM 让它知道有哪些工具
# 各个工具函数是实际执行逻辑的 Python 函数
from tools import (
    TOOLS_DEFINITION,
    calculator,
    get_current_time,
    get_weather,
    text_stats,
    unit_converter,
)


class Agent:
    """
    简单 AI Agent，实现了基于 OpenAI Function Calling 的工具调用循环。

    核心设计思想：
    - messages 列表是 Agent 的"工作记忆"，保存完整对话历史
    - 通过循环让 LLM 反复推理，直到它给出最终文本回答
    - 工具调用是 LLM 驱动的：LLM 决定调用什么，我们负责执行并返回结果

    使用示例：
        agent = Agent()
        response = agent.run("北京现在的天气怎么样？")
        print(response)
    """

    # 系统提示词：告诉 LLM 它是谁、有哪些能力、如何行动
    # 这个 prompt 会作为 role="system" 的第一条消息，影响 LLM 的整体行为风格
    SYSTEM_PROMPT = """你是一个智能助手，拥有以下工具能力：

1. **calculator** — 计算数学表达式（支持四则运算、幂运算等）
2. **get_current_time** — 获取当前日期和时间
3. **unit_converter** — 单位换算（温度：摄氏/华氏/开尔文；长度：米/千米/英里等）
4. **text_stats** — 统计文本信息（字符数、单词数、中文字符数等）
5. **get_weather** — 查询指定城市的实时天气（需要 OpenWeatherMap API Key）

使用工具的原则：
- 当用户询问需要计算、查询或换算的问题时，主动调用相关工具获取准确结果。
- 不要猜测计算结果，应使用 calculator 工具确保精确性。
- 查询天气时，城市名称尽量使用英文以提高准确率。
- 获取工具结果后，用自然语言向用户清晰解释结果。

回答风格：
- 简洁、友好、准确。
- 如果工具返回错误，向用户说明原因并提供替代建议。
"""

    def __init__(self, model: Optional[str] = None):
        """
        初始化 Agent。

        从环境变量读取配置，初始化 OpenAI 客户端，并设置初始对话状态。

        参数：
            model (str, optional): 使用的模型名称。
                                   如果不传，则从环境变量 MODEL_NAME 读取，
                                   默认为 "gpt-4o-mini"。
        """
        # ---- 读取 API Key ----
        # API Key 存放在环境变量中，而不是硬编码在代码里
        # 这是安全最佳实践，防止密钥被提交到代码仓库
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "未找到 OPENAI_API_KEY 环境变量。\n"
                "请在项目目录下创建 .env 文件，并添加：\n"
                "OPENAI_API_KEY=your_key_here"
            )

        # ---- 读取 Base URL（可选）----
        # base_url 允许使用兼容 OpenAI 接口的第三方服务
        # 例如：Azure OpenAI、本地 Ollama、或国内的 API 代理
        # 如果环境变量未设置，则使用 OpenAI 官方默认地址
        base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None

        # ---- 读取模型名称 ----
        # 优先使用构造函数传入的 model 参数
        # 其次读取环境变量 MODEL_NAME
        # 最后使用默认值 gpt-4o-mini（性价比较高的模型）
        self.model = model or os.environ.get("MODEL_NAME", "gpt-4o-mini").strip()

        # ---- 初始化 OpenAI 客户端 ----
        # OpenAI 客户端封装了 HTTP 请求的细节，包括认证、重试等
        # 如果提供了 base_url，则使用自定义 API 端点
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,  # None 表示使用官方默认地址
        )

        # ---- 设置最大迭代次数 ----
        # 防止工具调用陷入无限循环（理论上不应发生，但作为安全兜底）
        # 例如：如果 LLM 的工具调用产生了意外的循环依赖，这里会强制终止
        self.max_iterations = 10

        # ---- 初始化对话历史 ----
        # messages 是整个 Agent 的"工作记忆"
        # OpenAI API 是无状态的，每次请求都需要把完整历史传进去
        # 所以我们在本地维护 messages 列表，每次调用时都传入
        self.messages: list[dict] = []

        # 添加系统提示词（角色扮演 + 工具能力说明）
        # 系统提示词始终是 messages 的第一条，角色为 "system"
        self._add_system_message()

    def _add_system_message(self) -> None:
        """
        把系统提示词添加到 messages 的开头。

        系统提示词的作用：
        - 设定 AI 的角色和行为风格
        - 告知 AI 有哪些工具可用（虽然工具细节在 TOOLS_DEFINITION 中，
          但在系统提示里再说明一次可以强化 AI 的工具使用意愿）
        - 这条消息的 role 为 "system"，不是用户输入，不计入对话轮数
        """
        self.messages.append({
            "role": "system",
            "content": self.SYSTEM_PROMPT,
        })

    def reset(self) -> None:
        """
        重置对话历史，开始全新对话。

        清空 messages 列表后，重新添加系统提示词。
        这样 Agent 就忘记了之前所有的对话内容，像刚启动一样。

        使用场景：
        - 用户想开始一个全新话题，不希望之前的对话内容影响当前回答
        - 对话历史太长，token 消耗过多
        """
        # 清空所有历史消息
        self.messages.clear()

        # 重新添加系统提示词（系统提示词是必须存在的基础配置）
        self._add_system_message()

    def _dispatch_tool(self, name: str, args: dict) -> str:
        """
        根据工具名称找到对应的 Python 函数并执行，返回 JSON 字符串结果。

        为什么要返回 JSON 字符串？
        -------------------------
        OpenAI 要求工具结果（role="tool" 的消息）必须是字符串类型。
        我们的工具函数返回的是 Python dict，所以需要用 json.dumps() 序列化。
        LLM 能理解 JSON 格式，会自动解析其中的字段。

        参数：
            name (str): 工具名称，例如 "calculator"、"get_weather"
            args (dict): 工具参数，例如 {"expression": "2 + 3"}

        返回：
            str: 工具执行结果的 JSON 字符串
        """
        # 工具名称 -> Python 函数的映射表
        # 这是一个简单的分发机制（dispatch），根据名字找到对应函数
        # 如果工具增多，也可以用字典+注册机制来代替 if-elif 链
        tool_map = {
            "calculator":       calculator,
            "get_current_time": get_current_time,
            "unit_converter":   unit_converter,
            "text_stats":       text_stats,
            "get_weather":      get_weather,
        }

        if name not in tool_map:
            # 工具不存在时，返回错误信息（字符串格式）
            # LLM 接收到这个错误后，会向用户说明该工具不可用
            return json.dumps({"error": f"未知工具：{name}"}, ensure_ascii=False)

        # 找到对应函数
        func = tool_map[name]

        try:
            # 使用 **args 解包字典为关键字参数并调用函数
            # 例如 func(**{"expression": "2+3"}) 等价于 func(expression="2+3")
            result = func(**args)
        except TypeError as e:
            # 参数类型或数量不匹配时捕获 TypeError
            # 例如 LLM 传了一个工具不接受的参数名
            result = {"error": f"工具参数错误：{e}"}
        except Exception as e:
            # 捕获工具执行过程中的任何其他异常
            # 工具内部已经有错误处理，这里是最后的兜底
            result = {"error": f"工具执行异常：{type(e).__name__}: {e}"}

        # 把结果序列化为 JSON 字符串，ensure_ascii=False 保留中文字符
        return json.dumps(result, ensure_ascii=False)

    def run(self, user_input: str) -> str:
        """
        Agent 的核心执行方法：接收用户输入，返回最终回答。

        这是整个 Agent 的精华所在。
        它实现了一个"思考 → 行动 → 观察 → 再思考"的循环（ReAct 模式）：
        - 思考（Reasoning）：LLM 推理下一步该做什么
        - 行动（Acting）：调用工具执行具体操作
        - 观察（Observation）：把工具结果作为新的观察输入
        - 再思考：基于观察结果继续推理

        参数：
            user_input (str): 用户的问题或指令

        返回：
            str: LLM 的最终文本回答

        异常：
            不会抛出异常，所有错误都以文字形式返回给用户。
        """

        # ============================================================
        # 步骤 1：把用户输入追加到对话历史
        # ============================================================
        # role="user" 表示这条消息来自用户
        # LLM 会根据完整的 messages 历史来理解上下文
        self.messages.append({
            "role": "user",
            "content": user_input,
        })

        # ============================================================
        # 核心循环：让 LLM 反复推理，直到给出最终回答
        # ============================================================
        # 为什么需要循环？
        # 因为一个任务可能需要多次工具调用：
        # 例如"先查当前时间，再查北京天气，最后计算温度转换"
        # 每次 LLM 调用工具后，我们都要把结果返回给 LLM，让它继续推理
        # 直到 LLM 认为它已经有足够的信息，可以给出最终回答了
        for iteration in range(self.max_iterations):

            # 每轮循环开始时打印当前迭代轮次和 messages 数量
            _log("INFO", f"第 {iteration + 1} 轮推理，当前 messages 数量：{len(self.messages)}")

            # ============================================================
            # 步骤 2：调用 LLM（把对话历史和工具定义一起传入）
            # ============================================================
            try:
                response = self.client.chat.completions.create(
                    model=self.model,          # 使用的模型，例如 gpt-4o-mini
                    messages=self.messages,    # 完整对话历史（包括系统提示、用户输入、工具结果等）
                    tools=TOOLS_DEFINITION,    # 可用工具的 JSON Schema 描述列表
                    tool_choice="auto",        # "auto" 让 LLM 自己决定是否调用工具
                                               # 其他选项："none"（禁用工具）、"required"（强制调用）
                )
            except APIConnectionError as e:
                # 网络连接失败（没有互联网、DNS 解析失败等）
                return f"网络连接失败，请检查网络：{e}"
            except APITimeoutError as e:
                # 请求超时（服务器响应太慢）
                return f"请求超时，请稍后重试：{e}"
            except RateLimitError as e:
                # API 调用频率超限（免费账户限制较严）
                return f"API 调用频率超限，请稍后重试：{e}"
            except APIError as e:
                # 其他 OpenAI API 错误（如无效请求、服务端错误）
                return f"API 错误（状态码 {e.status_code}）：{e.message}"

            # ============================================================
            # 步骤 3：检查 LLM 的响应类型
            # ============================================================
            # LLM 的响应是一个 choices 列表，我们只关心第一个选择
            # finish_reason 告诉我们 LLM 为什么停止生成：
            # - "stop"：LLM 认为回答完整，直接给出文本
            # - "tool_calls"：LLM 需要调用工具，等待工具结果再继续

            choice = response.choices[0]
            finish_reason = choice.finish_reason
            message = choice.message  # LLM 生成的消息对象

            # ============================================================
            # 情况 A：LLM 要调用工具（finish_reason == "tool_calls"）
            # ============================================================
            if finish_reason == "tool_calls":

                # ---- 步骤 3a：把 LLM 的 assistant 消息追加到 messages ----
                # 为什么要保存这条 assistant 消息？
                # 因为 OpenAI API 要求：当 messages 中出现 role="tool" 的消息时，
                # 它前面必须有对应的 role="assistant" 消息（包含 tool_calls 字段）。
                # 这样 LLM 才能把工具结果和它自己的请求对应起来。
                self.messages.append(message)  # message 对象会被 OpenAI SDK 自动序列化

                # ---- 步骤 3b：遍历所有工具调用请求 ----
                # 一次响应中可能包含多个工具调用（并行工具调用）
                # 例如 LLM 可能同时请求"查天气"和"查时间"
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name  # 工具名称，例如 "calculator"

                    # 打印 LLM 决定调用的工具名称
                    _log("INFO", f"LLM 决定调用工具：{tool_name}")

                    # arguments 是 JSON 字符串，需要反序列化为 Python dict
                    # 例如 '{"expression": "2 + 3"}' -> {"expression": "2 + 3"}
                    try:
                        tool_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        # 如果 LLM 生成了无效的 JSON，捕获异常并返回错误
                        tool_args = {}

                    # 打印工具参数（DEBUG 级别，细节信息）
                    _log("DEBUG", f"工具参数：{json.dumps(tool_args, ensure_ascii=False)}")

                    # ---- 步骤 3b（续）：执行工具，获取结果 ----
                    # _dispatch_tool 会找到对应的 Python 函数并执行
                    # 返回值是 JSON 字符串（工具结果）
                    tool_result = self._dispatch_tool(tool_name, tool_args)

                    # 打印工具执行结果（DEBUG 级别，细节信息）
                    _log("DEBUG", f"工具执行结果：{tool_result}")

                    # ---- 步骤 3c：把工具结果追加到 messages ----
                    # role="tool" 是 OpenAI 专门为工具结果设计的消息角色
                    # tool_call_id 把这条结果和 LLM 的调用请求关联起来
                    # （一次响应可能有多个工具调用，每个都有唯一 id）
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,  # 与请求的 id 配对
                        "content": tool_result,         # 工具执行结果（JSON 字符串）
                    })

                # 工具调用完成，追加结果后通知
                _log("INFO", "工具调用完成，追加结果到 messages")

                # ---- 步骤 3d：回到步骤 2，让 LLM 继续推理 ----
                # 所有工具都执行完了，继续下一次循环
                # LLM 会看到我们新追加的工具结果，然后决定是继续调工具还是直接回答
                continue  # 跳过当前循环体的剩余代码，进入下一次迭代

            # ============================================================
            # 情况 B：LLM 直接回答（finish_reason == "stop"）
            # ============================================================
            elif finish_reason == "stop":

                # 打印 LLM 输出最终回答的信息
                _log("INFO", f"LLM 输出最终回答（finish_reason=stop）")

                # 提取 LLM 生成的文本内容
                # content 是最终的文字回答，例如"北京现在气温 28°C，晴天"
                final_content = message.content or ""

                # 把这条 assistant 消息保存到历史中
                # 这样如果用户继续追问，LLM 能看到自己之前说了什么
                self.messages.append({
                    "role": "assistant",
                    "content": final_content,
                })

                # 返回最终答案给调用方（main.py 会把它打印出来）
                return final_content

            else:
                # 其他不常见的 finish_reason（如 "length" 表示超出 token 限制）
                # 尝试返回已有内容，或者返回提示信息
                partial_content = message.content or ""
                if partial_content:
                    self.messages.append({
                        "role": "assistant",
                        "content": partial_content,
                    })
                    return partial_content
                return f"LLM 响应结束原因未知：{finish_reason}"

        # ============================================================
        # 步骤 4：超过最大迭代次数，强制结束
        # ============================================================
        # 正常情况下不会走到这里
        # 但如果 LLM 陷入了无限工具调用循环，这里会兜底终止
        _log("WARN", f"已超过最大迭代次数（{self.max_iterations} 轮），强制终止循环")
        return (
            f"已执行 {self.max_iterations} 轮工具调用，但 LLM 仍未给出最终回答。"
            "请尝试更简单的问题，或检查工具是否正常工作。"
        )
