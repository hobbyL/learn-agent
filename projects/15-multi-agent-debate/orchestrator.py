"""
辩论编排器
==========

三阶段辩论流程控制 + 消息路由 + 投票解析。

阶段流程：
1. 独立立论：各 Agent 独立查数据 + 推荐（信息隔离）
2. 交叉质疑：看到所有人第一轮发言，针对性回应
3. 总结投票：看到所有历史，最终投票
"""

import json
import re

from openai import OpenAI
from agents import run_agent, AGENTS
from display import (
    print_phase,
    print_agent_start,
    print_agent_response,
    print_vote_summary,
    print_separator,
    print_info,
    make_tool_callback,
)


class DebateOrchestrator:
    """辩论编排器：管理三阶段辩论流程。"""

    def __init__(self, client: OpenAI, model: str):
        self.client = client
        self.model = model
        self.roles = list(AGENTS.keys())

        # 存储每轮发言
        self.round1_arguments: dict[str, str] = {}  # role → 第一轮发言
        self.round2_arguments: dict[str, str] = {}  # role → 第二轮发言
        self.round3_arguments: dict[str, str] = {}  # role → 第三轮发言

        # 推荐追踪
        self.round1_recommendations: dict[str, str | None] = {}  # role → 星球名
        self.votes: list[dict] = []  # 最终投票

    def run_debate(self, topic: str | None = None):
        """执行完整三阶段辩论。"""
        if topic:
            print_info(f"辩论议题：{topic}")

        # --- 第一阶段：独立立论 ---
        self._phase1_independent()

        # --- 第二阶段：交叉质疑 ---
        self._phase2_cross_question()

        # --- 第三阶段：总结投票 ---
        self._phase3_vote()

        # --- 投票汇总 ---
        self._show_results()

    def _phase1_independent(self):
        """第一阶段：独立立论。"""
        print_phase(1, "独立立论", "各委员独立调查数据，提出推荐（信息隔离）")

        for role in self.roles:
            print_agent_start(role, "独立立论")
            callback = make_tool_callback(role)

            response, recommendation = run_agent(
                role=role,
                phase="独立立论",
                client=self.client,
                model=self.model,
                on_tool_call=callback,
            )

            self.round1_arguments[role] = response
            self.round1_recommendations[role] = recommendation

            print_agent_response(role, response)

            if recommendation:
                print_info(f"{role} 第一轮推荐：{recommendation}")

            print_separator()

    def _phase2_cross_question(self):
        """第二阶段：交叉质疑。"""
        print_phase(2, "交叉质疑", "各委员审视他人立论，针对性回应")

        for role in self.roles:
            # 构建其他人的发言上下文
            other_args = self._format_others_arguments(role, self.round1_arguments)

            print_agent_start(role, "交叉质疑")
            callback = make_tool_callback(role)

            response, _ = run_agent(
                role=role,
                phase="交叉质疑",
                client=self.client,
                model=self.model,
                context=other_args,
                on_tool_call=callback,
            )

            self.round2_arguments[role] = response
            print_agent_response(role, response)
            print_separator()

    def _phase3_vote(self):
        """第三阶段：总结投票。"""
        print_phase(3, "总结投票", "最终陈述 + 投票决策")

        for role in self.roles:
            # 构建完整历史上下文
            all_args = self._format_all_arguments(role)

            print_agent_start(role, "总结投票")
            callback = make_tool_callback(role)

            response, _ = run_agent(
                role=role,
                phase="总结投票",
                client=self.client,
                model=self.model,
                context=all_args,
                on_tool_call=callback,
            )

            self.round3_arguments[role] = response
            print_agent_response(role, response)

            # 解析投票
            vote = self._parse_vote(response, role)
            self.votes.append(vote)

            print_separator()

    def _show_results(self):
        """展示投票结果和立场变化。"""
        stance_changes = []
        for role in self.roles:
            r1 = self.round1_recommendations.get(role, "未知")
            r3_vote = None
            for v in self.votes:
                if v["role"] == role:
                    r3_vote = v.get("vote", "未知")
                    break
            stance_changes.append({
                "role": role,
                "round1": r1 or "未明确",
                "round3": r3_vote or "未知",
                "changed": r1 != r3_vote and r1 is not None and r3_vote is not None,
            })

        print_vote_summary(self.votes, stance_changes)

    # ================================================================
    # 辅助方法
    # ================================================================

    def _format_others_arguments(self, current_role: str, arguments: dict) -> str:
        """格式化其他人的发言（排除当前角色）。"""
        lines = []
        emojis = {"科学官": "🔬", "军事官": "⚔️", "经济官": "💰"}
        for role, text in arguments.items():
            if role != current_role:
                emoji = emojis.get(role, "🤖")
                lines.append(f"--- {emoji} {role}的立论 ---")
                lines.append(text)
                lines.append("")
        return "\n".join(lines)

    def _format_all_arguments(self, current_role: str) -> str:
        """格式化所有轮次的发言。"""
        lines = []
        emojis = {"科学官": "🔬", "军事官": "⚔️", "经济官": "💰"}

        lines.append("=== 第一轮：独立立论 ===\n")
        for role, text in self.round1_arguments.items():
            emoji = emojis.get(role, "🤖")
            tag = "（你自己）" if role == current_role else ""
            lines.append(f"--- {emoji} {role}的立论{tag} ---")
            lines.append(text)
            lines.append("")

        lines.append("\n=== 第二轮：交叉质疑 ===\n")
        for role, text in self.round2_arguments.items():
            emoji = emojis.get(role, "🤖")
            tag = "（你自己）" if role == current_role else ""
            lines.append(f"--- {emoji} {role}的回应{tag} ---")
            lines.append(text)
            lines.append("")

        return "\n".join(lines)

    def _parse_vote(self, text: str, role: str) -> dict:
        """从回答中解析投票 JSON。"""
        vote = {"role": role, "vote": None, "confidence": None, "reason": None}

        # 尝试提取 JSON 块
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if not json_match:
            json_match = re.search(r'(\{"vote".*?\})', text, re.DOTALL)

        if json_match:
            try:
                data = json.loads(json_match.group(1))
                vote["vote"] = data.get("vote")
                vote["confidence"] = data.get("confidence")
                vote["reason"] = data.get("reason")
                return vote
            except json.JSONDecodeError:
                pass

        # JSON 解析失败，用启发式提取
        planets = ["蓝晶星", "赤焰星", "翡翠星"]
        for planet in planets:
            if f"投票：{planet}" in text or f"投票: {planet}" in text:
                vote["vote"] = planet
                break
            if f"最终选择{planet}" in text or f"最终选择 {planet}" in text:
                vote["vote"] = planet
                break

        # 最后兜底：文中最后提到的星球
        if not vote["vote"]:
            last_pos = -1
            for planet in planets:
                pos = text.rfind(planet)
                if pos > last_pos:
                    last_pos = pos
                    vote["vote"] = planet

        vote["confidence"] = vote["confidence"] or 70
        vote["reason"] = vote["reason"] or "（自动提取）"
        return vote
