"""
StreamCollector —— Streaming Delta 收集与拼接
==============================================

核心职责：
1. 逐 chunk 接收 streaming response 的 delta
2. 拼接 content（文本）和 tool_calls（函数调用）
3. 记录原始 delta 时间线（用于 C2 双视角展示）

Streaming 协议关键知识：
-----------------------
OpenAI streaming 响应以 Server-Sent Events 形式逐块发送。
每个 chunk 的结构：
    chunk.choices[0].delta.content      → 文本片段（可能为 None）
    chunk.choices[0].delta.tool_calls   → 工具调用 delta（可能为 None）
    chunk.choices[0].finish_reason      → None（进行中）/ "stop" / "tool_calls"

tool_calls delta 拼接规则：
    - 第一个 delta 包含 index、id、function.name（可能不完整）
    - 后续 delta 只包含 function.arguments 的增量片段
    - 需要按 index 分组，累积拼接 name 和 arguments
    - arguments 拼接完成后是一个 JSON 字符串，需要 json.loads 解析
"""

import json
import time
from dataclasses import dataclass, field


@dataclass
class ToolCallAccumulator:
    """
    单个 tool_call 的增量拼接器。

    streaming 中 tool_calls 以 delta 形式到达：
    - 第 1 个 delta: index=0, id="call_xxx", function={name: "search", arguments: ""}
    - 第 2+ 个 delta: index=0, function={arguments: '{"qu'}
    - 第 3+ 个 delta: index=0, function={arguments: 'ery":'}
    - ...直到 finish_reason="tool_calls"

    本类负责将这些碎片拼接成完整的 tool_call。
    """
    index: int = 0
    id: str = ""
    function_name: str = ""
    arguments_buffer: str = ""

    def apply_delta(self, delta_tool_call) -> None:
        """应用一个 tool_call delta 增量"""
        if delta_tool_call.id:
            self.id = delta_tool_call.id
        if delta_tool_call.function:
            if delta_tool_call.function.name:
                self.function_name += delta_tool_call.function.name
            if delta_tool_call.function.arguments:
                self.arguments_buffer += delta_tool_call.function.arguments

    def to_dict(self) -> dict:
        """转为完整的 tool_call 字典"""
        try:
            args = json.loads(self.arguments_buffer) if self.arguments_buffer else {}
        except json.JSONDecodeError:
            args = {"_raw": self.arguments_buffer, "_error": "JSON parse failed"}
        return {
            "id": self.id,
            "function": {
                "name": self.function_name,
                "arguments": args,
            },
        }


@dataclass
class TimelineEntry:
    """时间线中的一条记录"""
    chunk_index: int
    timestamp: float
    event_type: str  # "content" | "tool_call_delta" | "finish"
    content: str     # 原始内容（用于展示）


@dataclass
class StreamResult:
    """一次 streaming 响应的最终结果"""
    content: str = ""
    tool_calls: list = field(default_factory=list)
    finish_reason: str = ""
    timeline: list = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration_ms(self) -> float:
        """响应总耗时（毫秒）"""
        return (self.end_time - self.start_time) * 1000

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class StreamCollector:
    """
    Streaming 响应收集器。

    用法：
        collector = StreamCollector()
        for chunk in stream_response:
            collector.feed(chunk)
        result = collector.build()
    """

    def __init__(self):
        self._content_parts: list[str] = []
        self._tool_accumulators: dict[int, ToolCallAccumulator] = {}
        self._timeline: list[TimelineEntry] = []
        self._chunk_count: int = 0
        self._finish_reason: str = ""
        self._start_time: float = time.time()

    def feed(self, chunk) -> str | None:
        """
        喂入一个 streaming chunk，返回新增的 content 文本（如有）。

        参数:
            chunk: OpenAI streaming response 的一个 chunk 对象

        返回:
            新增文本片段（如果是 content delta），否则 None
        """
        self._chunk_count += 1
        now = time.time()

        # 安全获取 choice
        if not chunk.choices:
            return None

        choice = chunk.choices[0]
        delta = choice.delta

        # 记录 finish_reason
        if choice.finish_reason:
            self._finish_reason = choice.finish_reason
            self._timeline.append(TimelineEntry(
                chunk_index=self._chunk_count,
                timestamp=now,
                event_type="finish",
                content=f"finish_reason={choice.finish_reason}",
            ))

        # 处理 content delta
        new_text = None
        if delta.content:
            new_text = delta.content
            self._content_parts.append(new_text)
            self._timeline.append(TimelineEntry(
                chunk_index=self._chunk_count,
                timestamp=now,
                event_type="content",
                content=repr(new_text),
            ))

        # 处理 tool_calls delta
        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                if idx not in self._tool_accumulators:
                    self._tool_accumulators[idx] = ToolCallAccumulator(index=idx)
                self._tool_accumulators[idx].apply_delta(tc_delta)

                # 记录时间线
                detail_parts = []
                if tc_delta.id:
                    detail_parts.append(f"id={tc_delta.id}")
                if tc_delta.function:
                    if tc_delta.function.name:
                        detail_parts.append(f"name={tc_delta.function.name}")
                    if tc_delta.function.arguments:
                        detail_parts.append(f"args+={repr(tc_delta.function.arguments)}")
                self._timeline.append(TimelineEntry(
                    chunk_index=self._chunk_count,
                    timestamp=now,
                    event_type="tool_call_delta",
                    content=f"[{idx}] {' '.join(detail_parts)}",
                ))

        return new_text

    def build(self) -> StreamResult:
        """构建最终结果"""
        end_time = time.time()
        tool_calls = [
            self._tool_accumulators[idx].to_dict()
            for idx in sorted(self._tool_accumulators.keys())
        ]
        return StreamResult(
            content="".join(self._content_parts),
            tool_calls=tool_calls,
            finish_reason=self._finish_reason,
            timeline=self._timeline,
            start_time=self._start_time,
            end_time=end_time,
        )
