"""
Agent 核心循环 —— 02 版（从 01 改造）
=====================================

和 01 的核心循环逻辑完全一样（ReAct：LLM 推理 → 工具执行 → 再推理），
本文件只改了「工具从哪来」这一件事，这正是 02 的主题。

01 vs 02 的关键区别
-------------------
                        01（硬编码）                      02（注册表驱动）
    工具 Schema   手写的 TOOLS_DEFINITION 常量      registry.get_schemas() 自动汇总
    工具分发      _dispatch_tool 里写死 tool_map    registry.get_func(name) 查表
    加一个工具    改函数 + 改 Schema + 改 tool_map   只写一个 @tool 函数，agent 零改动

也就是说，agent.py 从此「对工具一无所知」——它不知道有哪些工具、叫什么名字，
全部通过 registry 间接获取。这就是「解耦」：新增/删除工具不再需要碰 agent 代码。

--------------------------------------------------------------------
为什么这样更好？
--------------------------------------------------------------------
01 里每加一个工具要改三处，三处容易不同步（改了函数忘了改 Schema）。
02 里「函数即唯一信息源」：
  - 函数签名 → schema_gen 自动生成 Schema
  - @tool 装饰 → 自动登记到 registry
  - agent 从 registry 取用
信息只有一份，永远不会不同步。这就是工业级 Agent 框架（LangChain、
OpenAI Agents SDK 等）都采用「工具注册」的根本原因。
"""

import json
import os
from typing import Optional

from openai import OpenAI, APIError, APIConnectionError, APITimeoutError, RateLimitError

# ============================================================
# 简易分级日志工具（与 01 相同）
# ============================================================
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
    """输出带颜色的日志，根据 LOG_LEVEL 环境变量过滤级别。"""
    if _LEVEL_RANK.get(level, 0) >= _LEVEL_RANK.get(_LOG_LEVEL, 1):
        color = _COLORS.get(level, "")
        print(f"{color}[{level}]{_RESET}  {msg}")


# ============================================================
# 关键改动：import 工具与注册表
# ============================================================
# 注意这里 import tools 的「副作用」：
#   tools.py 里每个函数都被 @tool 装饰，import 这一刻它们就全部注册到了 registry。
#   所以下面这行 `import tools` 看似没用到 tools，其实是「触发注册」的关键——
#   不 import 它，registry 就是空的。
#
# 这是 02 一个值得记住的细节：注册是「import 时」发生的副作用。
import tools  # noqa: F401  （仅为触发 @tool 注册，故意不直接使用）
from registry import registry


class Agent:
    """
    AI Agent（02 版）：工具来自注册表，agent 本身不感知具体工具。

    使用示例：
        agent = Agent()
        print(agent.run("帮我生成一个 16 位带符号的密码"))
    """

    # 系统提示词：注意这里「不再手写每个工具的清单」。
    # 因为工具会动态变化，把清单写死在 prompt 里又会陷入 01 的"多处维护"问题。
    # 工具的详细信息已经通过 tools 参数（registry.get_schemas()）传给 LLM 了，
    # 系统提示只需要给出「行为风格」和「使用工具的总原则」即可。
    SYSTEM_PROMPT = """你是一个智能助手，可以调用一系列本地工具来完成任务
（生成密码、随机抽取、颜色转换、进制转换、文本大小写转换、掷骰子、哈希计算、文本转字符画等）。

【能力边界】（最重要的规则，优先级最高）
你只有上面列出的这几个工具，它们的能力是有限的。当用户的需求超出这些工具
能覆盖的范围时（例如要做数学计算、查天气、翻译等——而你并没有对应的工具）：
- 绝对不要为了"用上工具"而硬凑一个不相关的工具来调用。
  （例如：用户要算数学题，你却去调哈希工具，这是严重错误。）
- 应当如实告知用户："我当前的工具无法完成这个任务。"
- 在如实说明之后，可以本着帮忙的态度，凭自身知识尽力给出一个参考答案，
  但必须明确标注这是"仅凭记忆、未经工具验证"的，提醒用户自行核对。

【工具结果必须被使用】
- 一旦你调用了某个工具，你的最终回答就必须建立在该工具实际返回的结果之上。
- 严禁无视工具返回值、改用自己心算/记忆来作答。
- 如果你发现工具返回的结果和用户的问题驴唇不对马嘴，说明你调错了工具——
  这时应承认调用有误并如实说明，而不是假装结果有用、或自行编一个答案。

【常规使用原则】
- 当用户的需求确实匹配某个工具时，主动调用它，不要凭空编造结果。
- 涉及这些工具能做的精确转换、随机场景，必须用工具，不要自己心算。
- 如果工具返回了错误（error 字段），仔细阅读错误信息：
  * 如果是参数取值/格式问题（如超出范围、格式不对），按提示调整参数后重试一次。
  * 如果是本质性问题（如无法满足的请求），如实向用户说明，不要无意义地反复重试。
- 拿到工具结果后，用自然、简洁的中文向用户解释。

回答风格：简洁、友好、准确、诚实。
"""

    def __init__(self, model: Optional[str] = None):
        """初始化 Agent（与 01 基本一致）。"""
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "未找到 OPENAI_API_KEY 环境变量。\n"
                "请在项目目录下创建 .env 文件，并添加：\n"
                "OPENAI_API_KEY=your_key_here"
            )

        base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
        self.model = model or os.environ.get("MODEL_NAME", "gpt-4o-mini").strip()

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.max_iterations = 10
        self.messages: list[dict] = []
        self._add_system_message()

        # 启动时打印一下注册表里有哪些工具，确认注册成功（学习期很有用）
        _log("INFO", f"已从注册表加载 {len(registry)} 个工具：{registry.list_names()}")

    def _add_system_message(self) -> None:
        """把系统提示词加到 messages 开头。"""
        self.messages.append({"role": "system", "content": self.SYSTEM_PROMPT})

    def reset(self) -> None:
        """重置对话历史。"""
        self.messages.clear()
        self._add_system_message()

    def _dispatch_tool(self, name: str, args: dict) -> str:
        """
        核心改动：不再硬编码 tool_map，改为向注册表查询函数。

        对比 01：
            01: func = {"calculator": calculator, ...}.get(name)   # 写死
            02: func = registry.get_func(name)                      # 查表

        无论注册了多少工具、叫什么名字，这段代码都不用改——这就是注册表的价值。
        """
        func = registry.get_func(name)

        if func is None:
            # 工具不存在。错误信息明确告知 LLM 这是"工具不存在"，不可通过重试解决。
            return json.dumps(
                {"error": f"未知工具：{name}。该工具不存在，请勿重试此工具。"},
                ensure_ascii=False,
            )

        try:
            # **args 解包为关键字参数调用
            result = func(**args)
        except TypeError as e:
            # 参数名/数量不匹配（比如 LLM 漏传了必填参数，或传了多余参数）
            # 把它转成对 LLM 友好的提示，让它有机会修正参数后重试。
            result = {
                "error": (
                    f"调用工具 {name} 的参数不正确：{e}。"
                    f"请检查参数名和必填项后重试。"
                )
            }
        except Exception as e:
            # 兜底：工具内部未预料的异常
            result = {"error": f"工具执行异常：{type(e).__name__}: {e}"}

        return json.dumps(result, ensure_ascii=False)

    def run(self, user_input: str) -> str:
        """
        Agent 核心循环（ReAct）。逻辑与 01 完全一致，唯一区别是：
        调用 LLM 时 tools 参数来自 registry.get_schemas()，而非手写常量。
        """
        # 步骤 1：把用户输入加入历史
        self.messages.append({"role": "user", "content": user_input})

        # 核心循环
        for iteration in range(self.max_iterations):
            _log("INFO", f"第 {iteration + 1} 轮推理，当前 messages 数量：{len(self.messages)}")

            # 步骤 2：调用 LLM
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    # ★ 关键改动：工具 Schema 由注册表自动汇总，不再是手写的 TOOLS_DEFINITION
                    tools=registry.get_schemas(),
                    tool_choice="auto",
                )
            except APIConnectionError as e:
                return f"网络连接失败，请检查网络：{e}"
            except APITimeoutError as e:
                return f"请求超时，请稍后重试：{e}"
            except RateLimitError as e:
                return f"API 调用频率超限，请稍后重试：{e}"
            except APIError as e:
                return f"API 错误（状态码 {e.status_code}）：{e.message}"

            # 步骤 3：检查响应类型
            choice = response.choices[0]
            finish_reason = choice.finish_reason
            message = choice.message

            # 情况 A：要调用工具
            if finish_reason == "tool_calls":
                self.messages.append(message)

                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    _log("INFO", f"LLM 决定调用工具：{tool_name}")

                    try:
                        tool_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        tool_args = {}

                    _log("DEBUG", f"工具参数：{json.dumps(tool_args, ensure_ascii=False)}")

                    tool_result = self._dispatch_tool(tool_name, tool_args)
                    _log("DEBUG", f"工具执行结果：{tool_result}")

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    })

                _log("INFO", "工具调用完成，追加结果到 messages")
                continue

            # 情况 B：直接回答
            elif finish_reason == "stop":
                _log("INFO", "LLM 输出最终回答（finish_reason=stop）")
                final_content = message.content or ""
                self.messages.append({"role": "assistant", "content": final_content})
                return final_content

            else:
                # 其他结束原因（如 length 超长）
                partial_content = message.content or ""
                if partial_content:
                    self.messages.append({"role": "assistant", "content": partial_content})
                    return partial_content
                return f"LLM 响应结束原因未知：{finish_reason}"

        # 步骤 4：超过最大迭代次数兜底
        _log("WARN", f"已超过最大迭代次数（{self.max_iterations} 轮），强制终止循环")
        return (
            f"已执行 {self.max_iterations} 轮工具调用，但 LLM 仍未给出最终回答。"
            "请尝试更简单的问题，或检查工具是否正常工作。"
        )
