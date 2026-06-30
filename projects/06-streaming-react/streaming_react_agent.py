"""
StreamingReActAgent —— 流式 ReAct Agent
========================================

核心学习目标：
1. 理解流式 ReAct 与非流式 ReAct 的本质差异
2. 掌握 streaming 模式下文本格式解析的挑战（标签跨 chunk）
3. 体会状态机驱动的实时展示 vs 等待完整响应后解析的体验差异

关键差异对比：
--------------
03（非流式 ReAct）：
    response = client.chat.completions.create(stream=False, ...)
    text = response.choices[0].message.content
    → 正则一次性解析 Thought/Action/Final Answer

05（流式 FC）：
    stream = client.chat.completions.create(stream=True, tools=TOOLS_SCHEMA, ...)
    → delta 拼接 tool_calls JSON（不涉及文本格式）

06（流式 ReAct，本文件）：
    stream = client.chat.completions.create(stream=True, ...)  # 不传 tools=
    for chunk in stream:
        text = chunk.choices[0].delta.content or ""
        events = parser.feed(text)  # 状态机增量解析
        → 实时识别 Thought/Action/Final Answer 边界

注意：ReAct 不使用 tools= 参数（不是 Function Calling），
     而是依赖 system prompt 中的自然语言描述约束 LLM 输出格式。
"""

import json
import os
import time
from typing import Optional

from openai import OpenAI
from dotenv import load_dotenv

from tools import execute_tool, get_tool_descriptions
from stream_parser import (
    StreamParser, Section,
    TextChunk, SectionStart, ActionReady, FinalAnswerReady,
    SkipStepDetected, FormatError,
)
from display import (
    print_section_header, print_streaming_char, print_observation,
    print_final_answer, print_skip_warning, print_step_header,
    print_format_retry, print_error,
)

load_dotenv()

# ============================================================
# System Prompt —— 太空站联盟 ReAct 格式
# ============================================================

_SYSTEM_PROMPT_TEMPLATE = """你是太空站联盟的智能助手。你通过「思考-行动-观察」循环来回答问题。

## 知识库
太空站联盟知识库包含以下实体：
- 4 个太空站：极光站、天琴站、深红站、冰环站
- 5 位人物：陈星河、林夜霜、赵铁翼、苏晴岚、周明远
- 3 个设备/飞船：天琴号、赤焰号、极光之眼

注意：「天琴站」是太空站，「天琴号」是飞船，不要混淆。

## 可用工具

{tool_descriptions}

## 输出格式（严格遵守）

每一步按以下格式输出：

Thought: <你的思考过程——分析问题、决定下一步做什么>
Action: <工具名：search 或 lookup 或 calculate 或 compare>
Action Input: {{"参数名": "参数值"}}

收集到足够信息后：

Thought: <总结推理过程>
Final Answer: <最终答案>

## 规则

1. 每次只输出一个 Thought + 一个 Action（或 Final Answer），不要一次输出多步
2. 只有通过工具获取信息后才给出 Final Answer，不要编造数据
3. Action Input 必须是合法的 JSON 对象
4. 涉及计算的问题使用 calculate 工具，不要心算
5. 「计划查询」不等于「已经查询」：写了「接下来要查X」就必须真的执行 Action

## 示例

问题：极光站的站长是谁？

Thought: 我需要查询极光站的站长信息。
Action: lookup
Action Input: {{"entity": "极光站", "field": "站长"}}

（收到 Observation 后）

Thought: 已获取极光站的站长信息。
Final Answer: 极光站的站长是陈星河。
"""


class StreamingReActAgent:
    """
    流式 ReAct Agent。

    使用 stream=True 逐 chunk 接收 LLM 输出，通过 StreamParser 状态机
    实时识别 Thought/Action/Final Answer 边界，实现边流边解析边展示。

    与 03 的 ReactAgent 对比：
    - 03：等完整响应 → 一次性正则解析 → 结构化输出
    - 06：逐 chunk 喂入状态机 → 实时识别边界 → 实时着色展示
    """

    def __init__(self):
        self._client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("OPENAI_BASE_URL"),
        )
        self._model = os.environ.get("OPENAI_MODEL") or os.environ.get("MODEL_NAME", "gpt-4o-mini")
        self._max_steps = int(os.environ.get("MAX_ITERATIONS", "15"))
        self._max_format_retries = 2

        # 构建 system prompt（ReAct 格式 + 工具描述）
        tool_desc = get_tool_descriptions()
        self._system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(tool_descriptions=tool_desc)

        # 对话历史
        self._messages: list[dict] = []
        self._step_count = 0
        self._total_time_ms: float = 0.0

        self._reset_messages()

    # ── 公开接口 ──────────────────────────────────────────────

    def run(self, user_input: str, show_realtime: bool = True) -> str:
        """
        执行一次完整的流式 ReAct 循环。

        参数：
            user_input: 用户问题
            show_realtime: 是否实时打印推理链

        返回：
            Agent 最终文本答案
        """
        self._messages.append({"role": "user", "content": f"问题：{user_input}"})
        self._step_count = 0
        start = time.time()

        for step in range(1, self._max_steps + 1):
            self._step_count = step
            if show_realtime:
                print_step_header(step)

            # 一次流式 LLM 调用
            result = self._stream_step(show_realtime)

            if result is None:
                # 格式错误且重试耗尽
                break

            step_type, data = result

            if step_type == "final_answer":
                # ReAct 循环结束
                self._total_time_ms = (time.time() - start) * 1000
                return data

            elif step_type == "tool_call":
                # 工具调用：执行工具，把 Observation 注入对话历史
                tool_name, tool_args_str = data
                tool_args = self._parse_tool_args(tool_args_str)
                tool_result = execute_tool(tool_name, tool_args)

                if show_realtime:
                    print_observation(tool_name, tool_result)

                # 追加 LLM 输出（Thought + Action + Action Input）到 messages
                # 注意：这一步在 _stream_step 里已经 append 了 assistant 消息

                # 把 Observation 作为 user 消息追加（ReAct 标准做法）
                self._messages.append({
                    "role": "user",
                    "content": f"Observation: {tool_result}",
                })

            elif step_type == "skip_step":
                # 跳步检测：LLM 想给 Final Answer 但 Thought 还有未完成计划
                thought_text = data
                if show_realtime:
                    print_skip_warning(thought_text)

                # 拒绝 Final Answer，追加警告让 LLM 补完工具调用
                self._messages.append({
                    "role": "user",
                    "content": (
                        "你的 Thought 中包含未完成的计划（如「接下来查」、「还需要」等），"
                        "但你试图直接给出 Final Answer。\n\n"
                        "请先执行你计划中的工具调用，获取所需数据，再给出 Final Answer。\n"
                        "不要重复查询你已经有 Observation 的内容。"
                    ),
                })
                # 不推进 step，继续循环

        self._total_time_ms = (time.time() - start) * 1000
        return "[达到最大步数，Agent 循环终止]"

    def get_step_count(self) -> int:
        """返回本次 run() 执行的步数。"""
        return self._step_count

    def get_total_time_ms(self) -> float:
        """返回本次 run() 的总耗时（毫秒）。"""
        return self._total_time_ms

    def reset(self) -> None:
        """重置对话历史和计数器。"""
        self._reset_messages()
        self._step_count = 0
        self._total_time_ms = 0.0

    # ── 内部方法 ──────────────────────────────────────────────

    def _reset_messages(self) -> None:
        """初始化对话历史（仅含 system prompt）。"""
        self._messages = [{"role": "system", "content": self._system_prompt}]

    def _stream_step(self, show_realtime: bool) -> Optional[tuple]:
        """
        执行一次流式 LLM 调用，返回解析结果。

        这是流式 ReAct 的核心：
        1. stream=True 调用 API（不传 tools=，纯文本格式）
        2. 逐 chunk 喂入 StreamParser
        3. 实时处理 ParseEvent
        4. 流结束后返回决策结果

        返回：
            ("final_answer", text) — LLM 给出了最终答案
            ("tool_call", (tool_name, args_str)) — LLM 要调用工具
            ("skip_step", thought_text) — 检测到跳步
            None — 格式错误且重试耗尽
        """
        format_retry_count = 0

        while format_retry_count <= self._max_format_retries:
            parser = StreamParser()
            assistant_text_parts: list[str] = []  # 积累本轮 LLM 输出（用于 messages）

            # 用于收集解析结果的状态
            pending_action_name: str = ""
            pending_action_input: str = ""
            final_answer: Optional[str] = None
            skip_step_thought: Optional[str] = None
            got_action_ready = False

            try:
                stream = self._client.chat.completions.create(
                    model=self._model,
                    messages=self._messages,
                    stream=True,
                    # 注意：不传 tools= 参数！
                    # ReAct 靠 prompt 约束输出格式，不使用 Function Calling
                )

                for chunk in stream:
                    # 某些 chunk（如心跳包）choices 可能为空列表
                    if not chunk.choices:
                        continue
                    delta_text = chunk.choices[0].delta.content or ""
                    if delta_text:
                        assistant_text_parts.append(delta_text)
                        events = parser.feed(delta_text)
                        self._handle_events(events, show_realtime)

                        # 检查是否已有完整工具调用就绪
                        for event in events:
                            if isinstance(event, ActionReady):
                                pending_action_name = event.tool_name
                                pending_action_input = event.tool_input_str
                                got_action_ready = True
                            elif isinstance(event, FinalAnswerReady):
                                final_answer = event.text
                            elif isinstance(event, SkipStepDetected):
                                skip_step_thought = event.thought_text

                # 流结束：刷出 parser buffer 剩余内容
                flush_events = parser.flush()
                self._handle_events(flush_events, show_realtime)
                for event in flush_events:
                    if isinstance(event, ActionReady):
                        pending_action_name = event.tool_name
                        pending_action_input = event.tool_input_str
                        got_action_ready = True
                    elif isinstance(event, FinalAnswerReady):
                        final_answer = event.text
                    elif isinstance(event, SkipStepDetected):
                        skip_step_thought = event.thought_text

                # 换行（流结束后）
                if show_realtime:
                    print()

            except Exception as e:
                if show_realtime:
                    print_error(f"Streaming 中断: {e}")
                return None

            # 把本轮 LLM 输出追加到 messages（保留完整推理链供下一轮参考）
            assistant_text = "".join(assistant_text_parts)
            self._messages.append({"role": "assistant", "content": assistant_text})

            # ── 决策：本轮是工具调用、Final Answer 还是跳步？──

            if skip_step_thought is not None:
                return ("skip_step", skip_step_thought)

            if final_answer is not None:
                return ("final_answer", final_answer)

            if got_action_ready:
                return ("tool_call", (pending_action_name, pending_action_input))

            # 没有识别到有效格式 → 重试
            format_retry_count += 1
            if format_retry_count <= self._max_format_retries:
                if show_realtime:
                    print_format_retry(format_retry_count, self._max_format_retries)
                self._messages.append({
                    "role": "user",
                    "content": (
                        "格式错误：你的输出不符合要求的格式。请严格按照以下格式输出：\n\n"
                        "Thought: <你的思考>\n"
                        "Action: <工具名>\n"
                        "Action Input: {\"参数\": \"值\"}\n\n"
                        "或者如果有足够信息：\n\n"
                        "Thought: <总结>\n"
                        "Final Answer: <最终答案>\n\n"
                        "不要使用 markdown 加粗（**），直接按上述格式输出。"
                    ),
                })

        return None  # 重试耗尽

    def _handle_events(self, events: list, show_realtime: bool) -> None:
        """处理 ParseEvent 列表，实时展示。"""
        for event in events:
            if isinstance(event, SectionStart):
                if show_realtime:
                    print_section_header(event.section)
            elif isinstance(event, TextChunk):
                if show_realtime:
                    print_streaming_char(event.text, event.section)

    def _parse_tool_args(self, args_str: str) -> dict:
        """
        解析 Action Input 的 JSON 字符串。

        容错处理：
        - 尝试直接 json.loads
        - 失败则尝试提取第一个 {...} 片段
        """
        args_str = args_str.strip()
        try:
            return json.loads(args_str)
        except json.JSONDecodeError:
            # 尝试提取 {...} 部分
            import re
            match = re.search(r"\{.*\}", args_str, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return {}
