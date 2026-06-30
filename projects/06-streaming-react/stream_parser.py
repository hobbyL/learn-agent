"""
StreamParser —— 流式 ReAct 文本增量解析器
==========================================

核心学习目标：
1. 理解 streaming 模式下文本格式解析的挑战：标签跨 chunk
2. 掌握小 buffer 回溯策略：保留尾部 ≤15 字符，等下一个 chunk 确认标签完整性
3. 实现状态机驱动的实时解析：边流边识别 Thought/Action/Observation/Final Answer

与 03-react-agent 的对比：
----------------------------
03（非流式）：等完整响应 → 一次性正则解析 → 提取 Thought/Action/Final Answer
06（流式）：  逐 chunk 喂入 → 状态机实时识别边界 → 增量输出解析事件

关键挑战：标签跨 chunk
    LLM 输出 "\\nThought: 我需要查询" 时，可能被切成：
    chunk1: "\\nTho"
    chunk2: "ught: 我需要"
    chunk3: "查询"
    状态机必须在 chunk1 到达时不能误判，在 chunk2 到达时才切换到 THOUGHT 状态。

解决方案：小 buffer
    维护一个 ≤15 字符的 buffer，新文本到达后先拼接到 buffer，
    然后扫描是否有完整标签。若发现标签前缀但还不完整，暂缓输出等下一 chunk。
    若明确不是标签前缀，则安全刷出。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ============================================================
# 状态定义
# ============================================================

class Section(Enum):
    """ReAct 文本中各段落的状态。"""
    IDLE = "idle"               # 初始/未知状态
    THOUGHT = "thought"         # Thought: ... 段
    ACTION = "action"           # Action: ... 段
    ACTION_INPUT = "action_input"  # Action Input: {...} 段
    FINAL_ANSWER = "final_answer"  # Final Answer: ... 段


# 各 Section 对应的 ANSI 颜色（供 display.py 使用）
SECTION_COLORS = {
    Section.IDLE: "\033[0m",
    Section.THOUGHT: "\033[90m",           # 灰色
    Section.ACTION: "\033[33m",            # 黄色
    Section.ACTION_INPUT: "\033[33m",      # 黄色（同 Action）
    Section.FINAL_ANSWER: "\033[97m",      # 亮白
}

# Section 显示标题
SECTION_TITLES = {
    Section.THOUGHT: "🧠 Thought",
    Section.ACTION: "⚡ Action",
    Section.ACTION_INPUT: "📥 Action Input",
    Section.FINAL_ANSWER: "✅ Final Answer",
}

# ============================================================
# 解析事件（ParseEvent）
# ============================================================

@dataclass
class TextChunk:
    """一段文本片段，属于当前 section，应实时展示。"""
    text: str
    section: Section


@dataclass
class SectionStart:
    """检测到新 section 开始。"""
    section: Section


@dataclass
class ActionReady:
    """Action + Action Input 都解析完毕，可以执行工具了。"""
    tool_name: str          # Action 的工具名
    tool_input_str: str     # Action Input 的原始 JSON 字符串


@dataclass
class FinalAnswerReady:
    """Final Answer 段落完整接收完毕。"""
    text: str


@dataclass
class SkipStepDetected:
    """检测到跳步：Final Answer 出现时 Thought 还包含未完成计划。"""
    thought_text: str       # 当前 Thought 内容（供警告展示）


@dataclass
class FormatError:
    """格式错误，通常需要重试提示。"""
    message: str


# 所有事件类型的联合
ParseEvent = TextChunk | SectionStart | ActionReady | FinalAnswerReady | SkipStepDetected | FormatError


# ============================================================
# 跳步检测：Thought 中"未完成计划"关键词
# ============================================================

# 背景：LLM 有时在 Thought 里写"接下来要查 X"，然后直接给 Final Answer 而不调用工具。
# 这是 ReAct 的经典跳步 bug——"计划写进 Thought"不等于"Action 已执行"。
# 03 项目的教训：必须代码层检测，prompt 约束对弱模型无效。
_UNFINISHED_PLAN_PATTERNS = [
    "接下来", "还需要", "再查", "再查询", "需要再", "然后查", "然后再",
    "继续查", "分别查询", "查询每个", "查完", "再计算", "然后计算",
]

# 已知 section 标签（顺序重要：较长的放前面，避免 "Action" 误匹配 "Action Input"）
_SECTION_TAGS = [
    ("\nFinal Answer:", Section.FINAL_ANSWER),
    ("\nAction Input:", Section.ACTION_INPUT),
    ("\nThought:", Section.THOUGHT),
    ("\nAction:", Section.ACTION),
    # 行首无换行版本（用于第一行）
    ("Final Answer:", Section.FINAL_ANSWER),
    ("Action Input:", Section.ACTION_INPUT),
    ("Thought:", Section.THOUGHT),
    ("Action:", Section.ACTION),
]

# buffer 保留的最大字符数（等待确认标签完整性）
_BUFFER_MAX = 20


# ============================================================
# StreamParser：核心状态机
# ============================================================

class StreamParser:
    """
    流式 ReAct 文本增量解析器。

    用法：
        parser = StreamParser()
        for chunk in stream:
            text = chunk.choices[0].delta.content or ""
            events = parser.feed(text)
            for event in events:
                handle(event)
        events = parser.flush()  # 流结束后刷出 buffer 剩余内容
    """

    def __init__(self):
        self._buf: str = ""             # 待处理 buffer（≤_BUFFER_MAX 字符）
        self._section = Section.IDLE    # 当前 section 状态
        self._thought_buf: str = ""     # 当前 Thought 的累积内容（用于跳步检测）
        self._action_name: str = ""     # 当前 Action 工具名
        self._action_input_buf: str = ""  # Action Input JSON 累积内容

    # ── 公开接口 ──────────────────────────────────────────────

    def feed(self, text: str) -> list[ParseEvent]:
        """
        喂入新文本片段，返回本次产生的解析事件列表。

        每次调用对应一个 streaming chunk 的 content 部分。
        """
        if not text:
            return []

        self._buf += text
        return self._process_buffer()

    def flush(self) -> list[ParseEvent]:
        """
        流结束后强制刷出 buffer 剩余内容。

        在 for chunk in stream 循环结束后必须调用。

        关键：LLM 在 Action Input 之后不会再输出新 section（ReAct 每轮只输出一个 Action），
        所以 ActionReady 只能在 flush() 时发出，而不是等下一个 section 触发。
        """
        events: list[ParseEvent] = []
        if self._buf:
            events.extend(self._emit_text(self._buf))
            self._buf = ""

        # ACTION_INPUT 结束（流结束时停在此状态，说明 Action 完整接收）
        if self._section == Section.ACTION_INPUT and self._action_input_buf:
            events.append(ActionReady(
                tool_name=self._action_name.strip(),
                tool_input_str=self._action_input_buf.strip(),
            ))

        # FINAL_ANSWER 结束（流结束时停在此状态，说明 Final Answer 完整接收）
        elif self._section == Section.FINAL_ANSWER and self._thought_buf:
            events.append(FinalAnswerReady(self._thought_buf.strip()))

        return events

    def reset(self) -> None:
        """重置解析器状态（开始新一轮 ReAct 循环）。"""
        self._buf = ""
        self._section = Section.IDLE
        self._thought_buf = ""
        self._action_name = ""
        self._action_input_buf = ""

    # ── 内部处理 ──────────────────────────────────────────────

    def _process_buffer(self) -> list[ParseEvent]:
        """
        扫描 buffer，尝试检测 section 标签。

        策略：
        1. 遍历所有已知标签，找最早出现的那个
        2. 若找到完整标签 → 切换状态，分割输出
        3. 若 buffer 尾部是某标签的前缀 → 暂缓（等下一 chunk）
        4. 否则 → 安全刷出 buffer 内容
        """
        events: list[ParseEvent] = []

        while True:
            # 找最早出现的完整标签
            earliest_pos = -1
            earliest_tag = ""
            earliest_section = Section.IDLE

            for tag, section in _SECTION_TAGS:
                pos = self._buf.find(tag)
                if pos != -1 and (earliest_pos == -1 or pos < earliest_pos):
                    earliest_pos = pos
                    earliest_tag = tag
                    earliest_section = section

            if earliest_pos != -1:
                # 找到完整标签：刷出标签前内容，切换状态
                if earliest_pos > 0:
                    events.extend(self._emit_text(self._buf[:earliest_pos]))
                self._buf = self._buf[earliest_pos + len(earliest_tag):]
                events.extend(self._switch_section(earliest_section))
                # 继续扫描 buffer 剩余内容
                continue

            # 没有完整标签：检查 buffer 尾部是否是某标签的前缀
            safe_end = self._find_safe_flush_boundary()
            if safe_end > 0:
                # 安全刷出前 safe_end 个字符
                events.extend(self._emit_text(self._buf[:safe_end]))
                self._buf = self._buf[safe_end:]
            elif safe_end == 0 and len(self._buf) > _BUFFER_MAX:
                # buffer 溢出但全部是潜在前缀：强制刷出，避免死锁
                events.extend(self._emit_text(self._buf[:-_BUFFER_MAX]))
                self._buf = self._buf[-_BUFFER_MAX:]

            break  # buffer 已处理完毕

        return events

    def _find_safe_flush_boundary(self) -> int:
        """
        找到可以安全刷出的最大位置（不包含任何标签的前缀）。

        返回值：可以安全刷出的字符数（0 表示全部暂缓）。
        """
        buf = self._buf
        n = len(buf)

        # 从后往前，找最大的"安全前缀长度"
        # 即：确保刷出的内容不会是某个标签的前缀
        for flush_end in range(n, 0, -1):
            tail = buf[flush_end - 1: flush_end]  # 不是完整 tail，用下面的方式
            # 检查 buf[:flush_end] 的末尾是否是任何标签的前缀
            candidate_tail = buf[:flush_end]
            is_safe = True
            for tag, _ in _SECTION_TAGS:
                # 检查 candidate_tail 的尾部是否与 tag 的某前缀匹配
                for prefix_len in range(1, min(len(tag), flush_end) + 1):
                    if candidate_tail.endswith(tag[:prefix_len]):
                        is_safe = False
                        break
                if not is_safe:
                    break
            if is_safe:
                return flush_end

        return 0  # 全部暂缓

    def _switch_section(self, new_section: Section) -> list[ParseEvent]:
        """
        切换到新 section，同时处理旧 section 的收尾逻辑。
        """
        events: list[ParseEvent] = []
        old_section = self._section

        # ── 旧 section 收尾 ──────────────────────────
        if old_section == Section.ACTION_INPUT:
            # Action Input 结束 → 发出 ActionReady（工具调用就绪）
            events.append(ActionReady(
                tool_name=self._action_name.strip(),
                tool_input_str=self._action_input_buf.strip(),
            ))
            self._action_name = ""
            self._action_input_buf = ""

        elif old_section == Section.FINAL_ANSWER:
            # 流式场景下不应该在这里出现新 section（Final Answer 应该是最后一个）
            # 但保持健壮性
            pass

        # ── 新 section 初始化 ────────────────────────
        self._section = new_section

        if new_section == Section.THOUGHT:
            self._thought_buf = ""

        elif new_section == Section.FINAL_ANSWER:
            # 跳步检测：Final Answer 出现时，Thought 是否还有未完成计划
            for pattern in _UNFINISHED_PLAN_PATTERNS:
                if pattern in self._thought_buf:
                    events.append(SkipStepDetected(thought_text=self._thought_buf))
                    break
            self._thought_buf = ""  # 复用 _thought_buf 来积累 Final Answer 内容

        # 发出 SectionStart 事件（让 display 层打印 section 标题）
        events.append(SectionStart(section=new_section))
        return events

    def _emit_text(self, text: str) -> list[ParseEvent]:
        """
        发出文本片段事件，同时更新各 section 的内容 buffer。
        """
        if not text:
            return []

        # 按 section 积累内容（用于跳步检测和 Final Answer 收集）
        if self._section == Section.THOUGHT:
            self._thought_buf += text
        elif self._section == Section.ACTION:
            self._action_name += text
        elif self._section == Section.ACTION_INPUT:
            self._action_input_buf += text
        elif self._section == Section.FINAL_ANSWER:
            self._thought_buf += text  # 复用 thought_buf 积累 Final Answer

        return [TextChunk(text=text, section=self._section)]
