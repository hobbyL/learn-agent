"""
反思器 —— 从失败中提取经验教训
================================

Reflexion 的核心组件：把"失败经历"转化为"下次可用的经验"。

工作原理：
    输入：问题 + Agent 本轮的推理过程 + 评估器的反馈
    输出：一段自然语言反思摘要

反思摘要的结构（通过 prompt 约束 LLM 输出）：
    1. 错误定位：哪一步出了问题
    2. 原因分析：为什么会出错
    3. 改进策略：下次应该怎么做

为什么反思比"无脑重试"更好？
    无脑重试 = 相同 prompt + 相同输入 → 大概率重复同样的错误
    带反思的重试 = 原 prompt + 反思经验 → LLM 有了"前车之鉴"，
    能针对性地避开上次的坑，走不同的推理路径。

    这就是 Reflexion 论文的核心贡献：
    把"反思"形式化为 Agent 循环的一部分，而非依赖人类 debug。
"""

import os
import json

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class Reflector:
    """
    反思器：从失败尝试中生成结构化的经验总结。

    设计要点：
        1. 反思必须具体——不能是泛泛的"下次要更仔细"，而是指出具体哪步、什么错误
        2. 反思必须可操作——给出明确的"下次应该做什么"
        3. 反思要简洁——太长会占用 context window，稀释有效信息
    """

    # 反思生成 Prompt
    REFLECTION_PROMPT = """你是一个 AI Agent 的经验分析师。请分析这次失败的任务执行，生成一段简洁的经验总结。

## 任务问题
{question}

## Agent 的推理过程
{reasoning}

## Agent 的最终答案
{answer}

## 评估反馈
{feedback}

## 要求

请生成一段简洁的反思总结（不超过 3 句话），必须包含：
1. 哪一步出了问题（定位错误）
2. 为什么会犯这个错误（分析原因）
3. 下次应该怎么做才能避免（改进策略）

## 格式

直接输出反思文本，不要加任何标题或编号。反思应该像是 Agent 对自己说的话，例如：
"上次我在查询实体名时用了不完整的名称'珊瑚城'而非正确的'珊瑚礁城'，导致 lookup 失败后凭记忆编造了数据。下次遇到名称相似的实体，应该先用 search 确认完整名称，再用 lookup 获取具体数据。"
"""

    def __init__(self):
        self._client = OpenAI()
        self._model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def reflect(self, question: str, attempt_result: dict, eval_feedback: str) -> str:
        """
        从一次失败的尝试中生成反思摘要。

        参数：
            question: 原始问题
            attempt_result: Agent 本轮执行结果（包含 answer 和 steps）
            eval_feedback: 评估器给出的反馈文本

        返回：
            反思摘要字符串（将被注入下一轮的 system prompt）
        """
        # 格式化推理过程
        reasoning = self._format_steps(attempt_result.get("steps", []))
        answer = attempt_result.get("answer", "无答案")

        prompt = self.REFLECTION_PROMPT.format(
            question=question,
            reasoning=reasoning,
            answer=answer,
            feedback=eval_feedback,
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "你是一个经验分析师，帮助 AI Agent 从失败中学习。输出要简洁、具体、可操作。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,  # 稍微高一点温度，避免反思太套路化
                max_tokens=300,   # 限制长度，反思要简洁
            )
            reflection = response.choices[0].message.content or ""
            return reflection.strip()

        except Exception as e:
            # API 失败时的降级反思（虽然质量差，但不能让整个循环挂掉）
            return (
                f"上次尝试失败了。评估反馈：{eval_feedback}。"
                f"下次应该更仔细地使用工具获取数据，避免编造信息。"
            )

    def _format_steps(self, steps: list[dict]) -> str:
        """将推理步骤格式化为可读文本，供反思 prompt 使用。"""
        lines = []
        for step in steps:
            step_num = step.get("step", "?")
            thought = step.get("thought", "")
            action = step.get("action", "")
            action_input = step.get("action_input", {})
            observation = step.get("observation", "")

            lines.append(f"Step {step_num}:")
            if thought:
                lines.append(f"  Thought: {thought}")
            if action and not action.startswith("_"):
                input_str = json.dumps(action_input, ensure_ascii=False) if action_input else ""
                lines.append(f"  Action: {action}({input_str})")
            if observation and not action.startswith("_"):
                # 截断过长的 observation
                obs = observation[:150] + "..." if len(observation) > 150 else observation
                lines.append(f"  Observation: {obs}")
            lines.append("")

        return "\n".join(lines) if lines else "（无推理步骤记录）"


# ============================================================
# 快速验证
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("反思器 · 快速验证")
    print("=" * 50)

    reflector = Reflector()

    # 模拟一次失败的尝试
    mock_result = {
        "answer": "深渊王国的面积是珊瑚王国的 2.1 倍。",
        "steps": [
            {
                "step": 1,
                "thought": "我需要查找深渊王国的面积",
                "action": "lookup",
                "action_input": {"entity": "深渊王国", "field": "面积"},
                "observation": "12000",
            },
            {
                "step": 2,
                "thought": "现在查找珊瑚王国的面积",
                "action": "lookup",
                "action_input": {"entity": "珊瑚城", "field": "面积"},  # 用错了实体名！
                "observation": "错误：未找到实体 '珊瑚城'。",
            },
            {
                "step": 3,
                "thought": "查不到，我记得珊瑚王国面积大约是 5700",
                "action": None,
                "action_input": None,
                "observation": None,
            },
        ],
    }

    eval_feedback = "答案不正确。标准答案是 1.63 倍。Agent 使用了错误的实体名导致数据获取失败，然后编造了数据。"

    print("\n生成反思中...")
    reflection = reflector.reflect(
        question="深渊王国的面积是珊瑚王国的多少倍？",
        attempt_result=mock_result,
        eval_feedback=eval_feedback,
    )
    print(f"\n反思结果：\n  {reflection}")
