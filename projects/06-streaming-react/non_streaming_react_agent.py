"""
NonStreamingReActAgent —— 非流式 ReAct Agent（用于 --compare 对比）
====================================================================

从 03-react-agent 移植，适配太空站联盟知识库。
使用 stream=False 等完整响应，然后一次性正则解析 Thought/Action/Final Answer。

与 streaming_react_agent.py 的对比：
- 本文件（非流式）：等完整响应 → 正则解析 → 一次展示
- streaming_react_agent.py（流式）：逐 chunk 状态机 → 边解析边展示

二者的 ReAct 逻辑完全相同（循环结构、工具调用、跳步检测），
只有"消费 LLM 输出"的方式不同。
"""

import json
import os
import re
import time
from typing import Optional

from openai import OpenAI
from dotenv import load_dotenv

from tools import execute_tool, get_tool_descriptions
from streaming_react_agent import _SYSTEM_PROMPT_TEMPLATE

load_dotenv()

# ============================================================
# 解析正则（与 03 相同，兼容 markdown 加粗格式）
# ============================================================

RE_THOUGHT = re.compile(
    r"\*{0,2}Thought:?\*{0,2}\s*(.+?)(?=\n\*{0,2}(?:Action|Final Answer):?\*{0,2}|$)",
    re.DOTALL,
)
RE_ACTION = re.compile(r"\*{0,2}Action:?\*{0,2}\s*(\w+)")
RE_ACTION_INPUT = re.compile(r"\*{0,2}Action Input:?\*{0,2}\s*(\{.*?\})", re.DOTALL)
RE_FINAL_ANSWER = re.compile(r"\*{0,2}Final Answer:?\*{0,2}\s*(.+)", re.DOTALL)

# 跳步检测关键词（与 streaming 版保持一致）
_UNFINISHED_PLAN_PATTERNS = [
    "接下来", "还需要", "再查", "再查询", "需要再", "然后查", "然后再",
    "继续查", "分别查询", "查询每个", "查完", "再计算", "然后计算",
]


class NonStreamingReActAgent:
    """
    非流式 ReAct Agent，用于 --compare 对照。

    与 StreamingReActAgent 相同的 ReAct 逻辑，
    但使用 stream=False 一次性获取完整响应后正则解析。
    """

    def __init__(self):
        self._client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("OPENAI_BASE_URL"),
        )
        self._model = os.environ.get("OPENAI_MODEL") or os.environ.get("MODEL_NAME", "gpt-4o-mini")
        self._max_steps = int(os.environ.get("MAX_ITERATIONS", "15"))
        self._max_format_retries = 2

        tool_desc = get_tool_descriptions()
        self._system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(tool_descriptions=tool_desc)

        self._messages: list[dict] = []
        self._step_count = 0
        self._total_time_ms: float = 0.0
        self._reset_messages()

    def run(self, user_input: str) -> str:
        """执行非流式 ReAct 循环，返回最终答案。"""
        self._messages.append({"role": "user", "content": f"问题：{user_input}"})
        self._step_count = 0
        start = time.time()

        for step in range(1, self._max_steps + 1):
            self._step_count = step
            format_retry = 0

            while format_retry <= self._max_format_retries:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=self._messages,
                    stream=False,
                )
                text = response.choices[0].message.content or ""
                self._messages.append({"role": "assistant", "content": text})

                # 解析 Final Answer
                fa_match = RE_FINAL_ANSWER.search(text)
                if fa_match:
                    answer = fa_match.group(1).strip()

                    # 跳步检测
                    thought_match = RE_THOUGHT.search(text)
                    thought_text = thought_match.group(1).strip() if thought_match else ""
                    for pattern in _UNFINISHED_PLAN_PATTERNS:
                        if pattern in thought_text:
                            # 拒绝 Final Answer，追加警告
                            self._messages.append({
                                "role": "user",
                                "content": (
                                    "你的 Thought 包含未完成计划，但你直接给出了 Final Answer。\n"
                                    "请先执行工具调用，获取数据后再给出 Final Answer。"
                                ),
                            })
                            format_retry += 1
                            break
                    else:
                        self._total_time_ms = (time.time() - start) * 1000
                        return answer

                    continue  # 跳步后重试

                # 解析 Action
                action_match = RE_ACTION.search(text)
                input_match = RE_ACTION_INPUT.search(text)

                if action_match and input_match:
                    tool_name = action_match.group(1).strip()
                    try:
                        tool_args = json.loads(input_match.group(1))
                    except json.JSONDecodeError:
                        tool_args = {}

                    tool_result = execute_tool(tool_name, tool_args)
                    self._messages.append({
                        "role": "user",
                        "content": f"Observation: {tool_result}",
                    })
                    break  # 成功执行工具，进入下一步

                # 格式错误，重试
                format_retry += 1
                if format_retry <= self._max_format_retries:
                    self._messages.append({
                        "role": "user",
                        "content": (
                            "格式错误：请严格按以下格式输出：\n\n"
                            "Thought: <思考>\n"
                            "Action: <工具名>\n"
                            "Action Input: {\"参数\": \"值\"}\n\n"
                            "或：\n\nThought: <总结>\nFinal Answer: <答案>"
                        ),
                    })

        self._total_time_ms = (time.time() - start) * 1000
        return "[达到最大步数，Agent 循环终止]"

    def get_step_count(self) -> int:
        return self._step_count

    def get_total_time_ms(self) -> float:
        return self._total_time_ms

    def reset(self) -> None:
        self._reset_messages()
        self._step_count = 0
        self._total_time_ms = 0.0

    def _reset_messages(self) -> None:
        self._messages = [{"role": "system", "content": self._system_prompt}]
