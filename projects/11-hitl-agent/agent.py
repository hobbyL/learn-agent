"""
ReAct Agent + HITL 检查点集成
==============================

核心循环：标准 ReAct（Thought → Action → Observation），但在 Action 执行前
检查工具是否标记 `requires_approval`——如果是，暂停循环，请求人类反馈，根据
反馈决定：
    - approve → 执行原工具调用
    - reject + 替代指令 → 将指令注入 messages，让 LM 重新推理
    - provide_info → 将信息注入 messages，让 LM 重新推理

灾害恶化机制：每个 Agent 步骤后调用 knowledge_base.tick()，推进世界时间，
使灾害状态恶化（水位↑、火势↑），人类拖延有可观测后果。

终止条件：
    - LM 调用 report_result 表示任务完成/放弃
    - 达到 max_steps 上限
    - 连续 reject 超上限（由 HITL 层保护）
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv
from openai import OpenAI

from display import (
    print_action,
    print_disaster_update,
    print_final_summary,
    print_header,
    print_hitl_response,
    print_observation,
    print_step_divider,
    print_thought,
)
from hitl import (
    HITLCheckpoint,
    HITLHandler,
    InteractiveHandler,
    MAX_REJECT_RETRIES,
    ScriptedHandler,
    build_checkpoint,
    should_pause,
)
from knowledge_base import get_full_briefing, get_state, tick, reset_state
from schemas import FeedbackType, HITLResponse
from tools import TOOLS_SCHEMA, REPORT_TOOL_SCHEMA, execute_tool

load_dotenv()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 系统 Prompt
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SYSTEM_PROMPT = """\
你是明川市灾害应急指挥中心的 AI 助手。你的职责是分析灾情、评估风险、调度资源、\
协调救援行动。

当前灾情：明川市遭遇 6.8 级地震，伴随次生火灾和堰塞湖险情。你需要在有限资源\
下做出高效的救援调度决策。

你可以使用以下工具执行操作。部分高风险操作（涉及人命、不可逆、资源冲突）需要\
指挥官确认后才能执行。

重要规则：
1. 每步先分析当前态势（Thought），再决定行动（Action）
2. 高风险操作会暂停等待指挥官确认，你不需要主动询问——系统会自动拦截
3. 当你认为当前阶段任务完成或无法继续时，调用 report_result
4. 善用 check_situation 了解实时态势变化
5. 资源有限，需要权衡优先级

当前可用工具：
- check_situation：查看当前灾害态势（无需审批）
- check_resources：查看可用资源（无需审批）
- dispatch_team：派遣救援队（需审批 — 人命风险）
- evacuate：撤离居民（需审批 — 不可逆操作）
- allocate_resource：分配物资（需审批 — 资源冲突）
- release_flood：泄洪（需审批 — 不可逆操作）
- report_result：报告任务结果
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Agent 主类
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class StepRecord:
    """单步执行记录（供 display 渲染）。"""

    step_num: int
    thought: str = ""
    action: str = ""
    action_args: dict = field(default_factory=dict)
    observation: str = ""
    hitl_checkpoint: HITLCheckpoint | None = None
    is_report: bool = False
    report_success: bool = False
    report_reason: str = ""


class HITLAgent:
    """
    ReAct + HITL 检查点 Agent。

    在标准 ReAct 循环中集成 HITL 审批检查点：
    1. LM 生成 Thought + 选择 Action
    2. 如果 Action 需要审批 → 暂停请求人类反馈
    3. 根据反馈执行/调整/补充信息
    4. 获取 Observation → 继续下一步
    """

    def __init__(
        self,
        handler: HITLHandler,
        client: OpenAI | None = None,
        model: str | None = None,
        max_steps: int = 15,
        verbose: bool = True,
    ):
        self._handler = handler
        self._max_steps = max_steps
        self._verbose = verbose

        # 构建 OpenAI 客户端
        if client is None:
            api_key = os.environ.get("OPENAI_API_KEY", "").strip()
            base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
            self._client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = client

        self._model = model or os.environ.get("MODEL_NAME", "gpt-4o-mini")

        # 执行记录
        self.steps: list[StepRecord] = []
        self.hitl_events: list[HITLCheckpoint] = []
        self._consecutive_rejects = 0
        self._terminated_by_reject = False

    def run(self, goal: str) -> dict:
        """
        执行主循环。

        返回：
            {
                "success": bool,
                "steps": list[StepRecord],
                "hitl_events": list[HITLCheckpoint],
                "final_message": str,
                "terminated_by_reject": bool,
            }
        """
        # 重置世界状态
        reset_state()

        if self._verbose:
            print_header(goal)

        # 构建 messages
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"当前任务目标：{goal}\n\n当前态势：\n{get_full_briefing()}"},
        ]

        all_tools = TOOLS_SCHEMA + [REPORT_TOOL_SCHEMA]
        final_success = False
        final_message = ""

        for step_num in range(1, self._max_steps + 1):
            record = StepRecord(step_num=step_num)

            # 调用 LLM
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=all_tools,
                tool_choice="auto",
            )

            msg = response.choices[0].message

            # 提取 Thought（content 部分）
            if msg.content:
                record.thought = msg.content.strip()
                if self._verbose:
                    print_step_divider()
                    print_thought(step_num, record.thought)

            # 无工具调用 → LM 只输出文字，追加继续
            if not msg.tool_calls:
                messages.append({"role": "assistant", "content": msg.content or ""})
                # 如果没有 tool call 也没有内容，可能是终止信号
                if not msg.content:
                    record.observation = "(无输出)"
                else:
                    record.observation = "(LM 仅输出文字，未调用工具)"
                self.steps.append(record)
                continue

            # 处理工具调用（一次只取第一个——ReAct 模式）
            tool_call = msg.tool_calls[0]
            tool_name = tool_call.function.name
            try:
                tool_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            record.action = tool_name
            record.action_args = tool_args

            if self._verbose:
                print_action(tool_name, tool_args)

            # ─────────────────────────────────────────────
            # report_result：任务终止信号
            # ─────────────────────────────────────────────
            if tool_name == "report_result":
                record.is_report = True
                record.report_success = tool_args.get("success", False)
                record.report_reason = tool_args.get("reason", "")
                final_success = record.report_success
                final_message = record.report_reason
                self.steps.append(record)
                break

            # ─────────────────────────────────────────────
            # HITL 检查点：需审批的工具
            # ─────────────────────────────────────────────
            if should_pause(tool_name):
                context_summary = get_full_briefing()
                checkpoint = build_checkpoint(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    context_summary=context_summary,
                    attempt=self._consecutive_rejects + 1,
                )

                # 请求人类反馈
                feedback = self._handler.request_feedback(checkpoint)
                checkpoint.response = feedback
                self.hitl_events.append(checkpoint)
                record.hitl_checkpoint = checkpoint

                if self._verbose:
                    is_demo = isinstance(self._handler, ScriptedHandler)
                    print_hitl_response(feedback, is_demo=is_demo)

                if feedback.feedback_type == FeedbackType.APPROVE:
                    # 批准 → 执行原工具
                    self._consecutive_rejects = 0
                    tool_result = execute_tool(tool_name, tool_args)
                    observation = tool_result["message"]
                    if tool_result.get("alerts"):
                        observation += "\n" + "\n".join(tool_result["alerts"])

                elif feedback.feedback_type == FeedbackType.REJECT:
                    # 否决 → 将替代指令注入 messages，让 LM 重新推理
                    self._consecutive_rejects += 1

                    if self._consecutive_rejects >= MAX_REJECT_RETRIES:
                        self._terminated_by_reject = True
                        record.observation = f"(连续 {MAX_REJECT_RETRIES} 次被否决，Agent 终止)"
                        final_message = f"指挥官连续否决 {MAX_REJECT_RETRIES} 次，Agent 终止执行"
                        self.steps.append(record)
                        break

                    # 注入否决信息，让 LM 重新规划
                    messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
                        {"id": tool_call.id, "type": "function", "function": {"name": tool_name, "arguments": tool_call.function.arguments}}
                    ]})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"⚠️ 操作被指挥官否决。\n指挥官指令：{feedback.message}\n请根据指挥官的指令重新规划行动。",
                    })
                    record.observation = f"操作被否决，指挥官指令：{feedback.message}"
                    self.steps.append(record)

                    # 推进灾害时间
                    tick_alerts = tick()
                    if self._verbose and tick_alerts:
                        print_disaster_update(get_state()["tick"], tick_alerts)
                    continue

                elif feedback.feedback_type == FeedbackType.PROVIDE_INFO:
                    # 补充信息 → 注入 messages，让 LM 利用新信息重新推理
                    self._consecutive_rejects = 0
                    messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
                        {"id": tool_call.id, "type": "function", "function": {"name": tool_name, "arguments": tool_call.function.arguments}}
                    ]})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"📋 指挥官补充信息：{feedback.message}\n请结合这一新信息重新评估是否继续执行该操作，或调整方案。",
                    })
                    record.observation = f"收到补充信息：{feedback.message}"
                    self.steps.append(record)

                    # 推进灾害时间
                    tick_alerts = tick()
                    if self._verbose and tick_alerts:
                        print_disaster_update(get_state()["tick"], tick_alerts)
                    continue

                else:
                    # fallback: approve
                    tool_result = execute_tool(tool_name, tool_args)
                    observation = tool_result["message"]
                    if tool_result.get("alerts"):
                        observation += "\n" + "\n".join(tool_result["alerts"])

            else:
                # ─────────────────────────────────────────────
                # 普通工具：直接执行，无需审批
                # ─────────────────────────────────────────────
                self._consecutive_rejects = 0
                tool_result = execute_tool(tool_name, tool_args)
                observation = tool_result["message"]
                if tool_result.get("alerts"):
                    observation += "\n" + "\n".join(tool_result["alerts"])

            # 记录 observation
            record.observation = observation
            if self._verbose:
                print_observation(observation)
            self.steps.append(record)

            # 构建 messages 继续对话
            messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
                {"id": tool_call.id, "type": "function", "function": {"name": tool_name, "arguments": tool_call.function.arguments}}
            ]})
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": observation,
            })

            # 推进灾害时间
            tick_alerts = tick()
            if self._verbose and tick_alerts:
                print_disaster_update(get_state()["tick"], tick_alerts)

        # ─────────────────────────────────────────────
        # 循环结束
        # ─────────────────────────────────────────────
        if not final_message and not self._terminated_by_reject:
            final_message = "达到最大步数上限"

        if self._verbose:
            from schemas import FeedbackType as _FT
            approve_cnt = sum(
                1 for ev in self.hitl_events
                if ev.response and ev.response.feedback_type == _FT.APPROVE
            )
            reject_cnt = sum(
                1 for ev in self.hitl_events
                if ev.response and ev.response.feedback_type == _FT.REJECT
            )
            info_cnt = sum(
                1 for ev in self.hitl_events
                if ev.response and ev.response.feedback_type == _FT.PROVIDE_INFO
            )
            print_final_summary(
                total_steps=len(self.steps),
                hitl_count=len(self.hitl_events),
                approve_count=approve_cnt,
                reject_count=reject_cnt,
                info_count=info_cnt,
                final_message=final_message,
            )

        return {
            "success": final_success,
            "steps": self.steps,
            "hitl_events": self.hitl_events,
            "final_message": final_message,
            "terminated_by_reject": self._terminated_by_reject,
        }
