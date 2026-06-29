"""
NonStreamingAgent —— 非流式 Agent（用于 --compare 对比）
========================================================

与 StreamingAgent 功能相同，但使用 stream=False。
用于对比展示 streaming vs non-streaming 的体感差异。
"""

import json
import os
import time
from typing import Optional

from openai import OpenAI

from tools import TOOLS_SCHEMA, execute_tool
from streaming_agent import SYSTEM_PROMPT


class NonStreamingAgent:
    """非流式 Agent，用于对比"""

    def __init__(self):
        self.client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("OPENAI_BASE_URL"),
        )
        self.model = os.environ.get("OPENAI_MODEL") or os.environ.get("MODEL_NAME", "gpt-4o-mini")
        self.max_iterations = int(os.environ.get("MAX_ITERATIONS", "10"))
        self.messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self.total_time_ms: float = 0.0

    def run(self, user_input: str) -> str:
        """执行非流式 Agent 循环"""
        self.messages.append({"role": "user", "content": user_input})
        start = time.time()

        for iteration in range(1, self.max_iterations + 1):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=TOOLS_SCHEMA,
            )

            choice = response.choices[0]

            if choice.finish_reason == "stop":
                answer = choice.message.content or ""
                self.messages.append({"role": "assistant", "content": answer})
                self.total_time_ms = (time.time() - start) * 1000
                return answer

            if choice.finish_reason == "tool_calls":
                # 追加 assistant 消息
                self.messages.append(choice.message.model_dump())

                # 执行工具
                for tc in choice.message.tool_calls:
                    func_name = tc.function.name
                    func_args = json.loads(tc.function.arguments)
                    tool_result = execute_tool(func_name, func_args)
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result,
                    })

        self.total_time_ms = (time.time() - start) * 1000
        return "[达到最大迭代次数]"

    def reset(self) -> None:
        """重置对话历史"""
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.total_time_ms = 0.0
