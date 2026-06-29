"""
StreamingAgent —— 流式 Agent 循环
==================================

核心学习目标：
1. 理解 stream=True 如何改变 API 调用模式
2. 掌握 tool_calls delta 拼接的完整流程
3. 体会 streaming 下 Agent 循环与非流式的差异

关键差异（对比 01-simple-agent 的非流式版本）：
----------------------------------------------
非流式：response = client.chat.completions.create(...)
        → 等待完整响应 → 一次性拿到 content 或 tool_calls

流式：  stream = client.chat.completions.create(stream=True, ...)
        → 逐 chunk 迭代 → 增量拼接 content 和 tool_calls
        → 完成标志：chunk.choices[0].finish_reason 不为 None

流式的 Agent 循环结构不变（LLM → 工具 → LLM → ...），
但每次"LLM 调用"的消费方式从"一次返回"变成"逐块收集"。
"""

import json
import os
import time
from typing import Optional

from openai import OpenAI

from tools import TOOLS_SCHEMA, execute_tool
from stream_collector import StreamCollector, StreamResult
from display import (
    print_streaming_char,
    print_tool_call_start,
    print_tool_result,
    print_iteration_header,
    print_agent_answer,
    print_raw_timeline,
    print_final_output,
    print_error,
)


# ============================================================
# 系统提示词
# ============================================================

SYSTEM_PROMPT = """你是太空站联盟的智能助手。你可以查询联盟知识库来回答关于太空站、人员和设备的问题。

知识库包含以下信息：
- 4 个太空站：极光站、天琴站、深红站、冰环站
- 5 位人物：陈星河、林夜霜、赵铁翼、苏晴岚、周明远
- 3 个设备/飞船：天琴号、赤焰号、极光之眼

注意：「天琴站」是太空站，「天琴号」是飞船，不要混淆。

规则：
1. 必须通过工具查询知识库获取信息，不要编造数据
2. 如果一个问题需要多步查询，逐步调用工具
3. 计算任务使用 calculate 工具，不要心算
4. 回答要简洁准确，引用具体数据"""


class StreamingAgent:
    """
    流式 Agent：使用 streaming API 的完整工具调用循环。

    与非流式 Agent 的核心区别：
    - API 调用使用 stream=True
    - 响应通过 StreamCollector 逐 chunk 收集和拼接
    - 支持实时输出（边接收边打印）
    """

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
        # 收集所有轮次的 timeline 用于最终展示
        self._all_timelines: list[StreamResult] = []

    def run(self, user_input: str, show_realtime: bool = True) -> str:
        """
        执行一次完整的 Agent 循环（streaming 模式）。

        参数:
            user_input: 用户问题
            show_realtime: 是否实时打印流式输出

        返回:
            Agent 最终文本答案
        """
        self.messages.append({"role": "user", "content": user_input})
        self._all_timelines = []

        for iteration in range(1, self.max_iterations + 1):
            if show_realtime:
                print_iteration_header(iteration)

            # 流式 API 调用
            result = self._stream_call(show_realtime)
            self._all_timelines.append(result)

            if not result.has_tool_calls:
                # LLM 直接给出文本回答，循环结束
                answer = result.content
                self.messages.append({"role": "assistant", "content": answer})
                return answer

            # 有工具调用：拼接完成后执行
            # 构造 assistant 消息（含 tool_calls）
            assistant_msg = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": json.dumps(
                                tc["function"]["arguments"], ensure_ascii=False
                            ),
                        },
                    }
                    for tc in result.tool_calls
                ],
            }
            self.messages.append(assistant_msg)

            # 执行每个工具调用
            for tc in result.tool_calls:
                func_name = tc["function"]["name"]
                func_args = tc["function"]["arguments"]

                if show_realtime:
                    print_tool_call_start(func_name, func_args)

                tool_result = execute_tool(func_name, func_args)

                if show_realtime:
                    print_tool_result(func_name, tool_result)

                # 工具结果追加到 messages
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })

        # 达到最大迭代次数
        return "[达到最大迭代次数，Agent 循环终止]"

    def _stream_call(self, show_realtime: bool) -> StreamResult:
        """
        执行一次 streaming API 调用并收集结果。

        这是 streaming 的核心：
        1. 创建 stream（stream=True）
        2. 逐 chunk 迭代
        3. 用 StreamCollector 拼接 delta
        4. 可选实时输出 content
        """
        collector = StreamCollector()

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=TOOLS_SCHEMA,
                stream=True,
            )

            for chunk in stream:
                new_text = collector.feed(chunk)

                # 实时打印文本片段
                if show_realtime and new_text:
                    print_streaming_char(new_text)

        except Exception as e:
            if show_realtime:
                print_error(f"Streaming 中断: {e}")
            # 返回已收集的部分结果
            return collector.build()

        # 流结束后换行
        if show_realtime and collector._content_parts:
            print()  # content 打印完后换行

        return collector.build()

    def get_all_timelines(self) -> list[StreamResult]:
        """获取所有轮次的 StreamResult（用于最终展示 raw timeline）"""
        return self._all_timelines

    def reset(self) -> None:
        """重置对话历史"""
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._all_timelines = []
