"""
双轨评估器 —— Ground Truth + LLM-as-Judge
==========================================

评估 Agent 的回答是否正确，为 Reflexion 外层循环提供"是否需要重试"的判断依据。

两种评估策略：
    1. Ground Truth（默认）：预定义标准答案，程序自动比对
       - 优点：确定性、可重复、无额外 API 调用
       - 缺点：需要预先准备答案、只能判"对/错"
       - 适用：自动化测试、CI/CD、学习验证

    2. LLM-as-Judge：用另一次 LLM 调用来评估答案质量
       - 优点：灵活、能评估部分正确、能给出改进建议
       - 缺点：有额外 API 成本、判断本身可能出错
       - 适用：演示模式、开放式问题、真实场景模拟

通过 EVALUATOR_MODE 环境变量切换（ground_truth | llm_judge）。

设计决策：为什么不融合两种评估器？
    因为学习目标是理解两种范式的差异。分开实现让学习者能清楚对比：
    - 程序化评估的确定性 vs LLM 评估的灵活性
    - 评估器本身的可靠性问题（LLM Judge 也可能犯错）
"""

import os
import re
from dataclasses import dataclass

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# 评估结果数据类
# ============================================================

@dataclass
class EvalResult:
    """
    评估结果。

    字段：
        is_correct: 答案是否正确
        confidence: 评估置信度（0.0~1.0）
        feedback: 评估反馈（用于反思器生成反思时参考）
        evaluator_type: 评估器类型标识
    """
    is_correct: bool
    confidence: float
    feedback: str
    evaluator_type: str  # "ground_truth" | "llm_judge"


# ============================================================
# Ground Truth 评估器
# ============================================================

class GroundTruthEvaluator:
    """
    基于预定义标准答案的评估器。

    评估逻辑：
        1. 将 Agent 答案和标准答案都做标准化处理（去空格、统一标点等）
        2. 检查标准答案中的"关键词"是否都出现在 Agent 答案中
        3. 对数值答案做模糊匹配（允许小数点误差）

    为什么不用简单的字符串相等？
        因为 LLM 的回答风格多变——同一个意思可能有多种表达：
        "深渊王国面积是 12000" vs "深渊王国的面积为一万两千平方公里"
        关键词匹配更鲁棒。
    """

    def evaluate(self, question: str, agent_answer: str, ground_truth: str) -> EvalResult:
        """
        评估 Agent 答案是否与标准答案匹配。

        参数：
            question: 原始问题
            agent_answer: Agent 的回答
            ground_truth: 预定义的标准答案

        返回：
            EvalResult
        """
        # 标准化处理
        normalized_answer = self._normalize(agent_answer)
        normalized_truth = self._normalize(ground_truth)

        # 策略 1：提取标准答案中的关键信息点
        key_points = self._extract_key_points(ground_truth)

        # 计算匹配度
        matched = 0
        total = len(key_points)

        for point in key_points:
            if self._point_matches(point, normalized_answer):
                matched += 1

        # 判定逻辑：所有关键点都匹配才算正确
        is_correct = matched == total and total > 0
        confidence = matched / total if total > 0 else 0.0

        # 生成反馈
        if is_correct:
            feedback = "答案正确，所有关键信息点都匹配。"
        else:
            missed = [p for p in key_points if not self._point_matches(p, normalized_answer)]
            feedback = (
                f"答案不完全正确。"
                f"匹配了 {matched}/{total} 个关键点。"
                f"缺失的关键信息：{', '.join(missed)}。"
                f"标准答案参考：{ground_truth}"
            )

        return EvalResult(
            is_correct=is_correct,
            confidence=confidence,
            feedback=feedback,
            evaluator_type="ground_truth",
        )

    def _normalize(self, text: str) -> str:
        """标准化文本：去除多余空白、统一标点。"""
        text = text.strip()
        # 统一中英文标点
        text = text.replace("，", ",").replace("。", ".").replace("：", ":")
        # 去除多余空格
        text = re.sub(r"\s+", " ", text)
        return text.lower()

    def _extract_key_points(self, ground_truth: str) -> list[str]:
        """
        从标准答案中提取关键信息点。

        提取策略：
            1. 数字（包括小数）
            2. 中文命名实体（2字以上的连续中文）
            3. 显式标记的关键词（用 | 分隔的答案取每一段）

        标准答案格式约定：
            - 简单答案："奥西里斯大帝"
            - 多关键点答案："奥西里斯大帝|深渊王国|3200"（用 | 分隔）
            - 数值答案："1.63"（带数字的自动做数值比较）
        """
        # 如果标准答案用 | 分隔了关键点
        if "|" in ground_truth:
            return [p.strip() for p in ground_truth.split("|") if p.strip()]

        # 否则把整个答案作为一个关键点
        return [ground_truth.strip()]

    def _point_matches(self, point: str, answer: str) -> bool:
        """
        检查某个关键点是否在答案中匹配。

        对数字做模糊匹配（允许 ±0.01 的误差，以及整数/小数互转）。
        """
        point_clean = point.strip().lower()

        # 尝试数值匹配
        try:
            point_num = float(point_clean)
            # 在答案中找所有数字
            numbers_in_answer = re.findall(r"[\d]+\.?[\d]*", answer)
            for num_str in numbers_in_answer:
                try:
                    ans_num = float(num_str)
                    # 允许小误差（处理浮点精度和四舍五入差异）
                    if abs(ans_num - point_num) < 0.05:
                        return True
                    # 处理"约等于"场景：如标准答案是 1.63，Agent 回答 1.6
                    if abs(ans_num - point_num) / max(abs(point_num), 0.001) < 0.05:
                        return True
                except ValueError:
                    continue
            return False
        except ValueError:
            pass

        # 文本匹配：关键点出现在答案中
        return point_clean in answer


# ============================================================
# LLM-as-Judge 评估器
# ============================================================

class LLMJudgeEvaluator:
    """
    用 LLM 评估 Agent 答案质量。

    工作原理：
        给评估用 LLM 提供：问题、Agent 的答案、Agent 的推理步骤。
        让它判断答案是否正确，给出评分和改进建议。

    局限性（必须认识到的）：
        - LLM Judge 本身可能犯错（评估者也有幻觉）
        - 对虚构数据评估困难（因为 Judge 也不知道真实答案）
        - 额外的 API 调用成本
        - 判断可能不确定性

    为什么仍然实现它？
        因为在真实场景中（没有 Ground Truth 的开放问题），
        LLM-as-Judge 是唯一可用的自动评估手段。学习其优劣很重要。
    """

    # 评估 Prompt —— 让 LLM 当裁判
    JUDGE_PROMPT = """你是一个答案质量评估专家。请评估以下 AI Agent 的回答质量。

## 问题
{question}

## Agent 的回答
{answer}

## Agent 的推理过程
{reasoning}

## 评估要求

请从以下维度评估：
1. 答案是否直接回答了问题
2. 推理过程是否逻辑自洽
3. 数据引用是否有工具调用支持（而非编造）
4. 最终答案的表述是否清晰准确

## 输出格式（严格遵守）

Score: <0-10 的整数评分>
Correct: <YES 或 NO>
Feedback: <一句话评价，指出主要优点或问题>
"""

    def __init__(self):
        self._client = OpenAI()
        self._model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def evaluate(self, question: str, agent_answer: str, steps: list[dict]) -> EvalResult:
        """
        用 LLM 评估答案质量。

        参数：
            question: 原始问题
            agent_answer: Agent 的回答
            steps: Agent 的推理步骤列表

        返回：
            EvalResult
        """
        # 把推理步骤格式化为文本
        reasoning = self._format_reasoning(steps)

        prompt = self.JUDGE_PROMPT.format(
            question=question,
            answer=agent_answer,
            reasoning=reasoning,
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "你是一个严格的答案质量评估专家。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )
            content = response.choices[0].message.content or ""
            return self._parse_judge_output(content)

        except Exception as e:
            # API 调用失败时的降级处理
            return EvalResult(
                is_correct=False,
                confidence=0.0,
                feedback=f"评估器调用失败：{e}",
                evaluator_type="llm_judge",
            )

    def _format_reasoning(self, steps: list[dict]) -> str:
        """把推理步骤列表格式化为可读文本。"""
        lines = []
        for step in steps:
            step_num = step.get("step", "?")
            thought = step.get("thought", "")
            action = step.get("action", "")
            observation = step.get("observation", "")

            lines.append(f"[Step {step_num}]")
            if thought:
                lines.append(f"  Thought: {thought}")
            if action and action != "_format_error":
                action_input = step.get("action_input", {})
                lines.append(f"  Action: {action}({json.dumps(action_input, ensure_ascii=False)})")
            if observation:
                lines.append(f"  Observation: {observation[:200]}")
            lines.append("")

        return "\n".join(lines) if lines else "（无推理步骤）"

    def _parse_judge_output(self, content: str) -> EvalResult:
        """解析 LLM Judge 的输出。"""
        # 提取 Score
        score_match = re.search(r"Score:\s*(\d+)", content)
        score = int(score_match.group(1)) if score_match else 5

        # 提取 Correct
        correct_match = re.search(r"Correct:\s*(YES|NO)", content, re.IGNORECASE)
        is_correct = correct_match.group(1).upper() == "YES" if correct_match else (score >= 7)

        # 提取 Feedback
        feedback_match = re.search(r"Feedback:\s*(.+)", content)
        feedback = feedback_match.group(1).strip() if feedback_match else "无具体反馈"

        return EvalResult(
            is_correct=is_correct,
            confidence=score / 10.0,
            feedback=feedback,
            evaluator_type="llm_judge",
        )


# ============================================================
# 评估器工厂 —— 根据环境变量选择评估器
# ============================================================

# 需要导入 json 给 LLM Judge 用
import json


def get_evaluator() -> GroundTruthEvaluator | LLMJudgeEvaluator:
    """
    根据 EVALUATOR_MODE 环境变量返回对应的评估器实例。

    支持的值：
        - "ground_truth"（默认）：Ground Truth 评估器
        - "llm_judge"：LLM-as-Judge 评估器
    """
    mode = os.environ.get("EVALUATOR_MODE", "ground_truth").lower().strip()

    if mode == "llm_judge":
        return LLMJudgeEvaluator()
    else:
        return GroundTruthEvaluator()


# ============================================================
# 快速验证
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("评估器 · 快速验证")
    print("=" * 50)

    # 测试 Ground Truth 评估器
    gt_eval = GroundTruthEvaluator()

    print("\n--- Ground Truth 评估器 ---")

    # 正确答案
    result = gt_eval.evaluate(
        question="深渊王国的统治者是谁？",
        agent_answer="深渊王国的统治者是奥西里斯大帝。",
        ground_truth="奥西里斯大帝",
    )
    print(f"  正确案例：is_correct={result.is_correct}, confidence={result.confidence}")

    # 错误答案
    result = gt_eval.evaluate(
        question="深渊王国的统治者是谁？",
        agent_answer="深渊王国的统治者是珊瑚女皇。",
        ground_truth="奥西里斯大帝",
    )
    print(f"  错误案例：is_correct={result.is_correct}, feedback={result.feedback}")

    # 数值答案
    result = gt_eval.evaluate(
        question="深渊王国面积是珊瑚王国的多少倍？",
        agent_answer="深渊王国面积是珊瑚王国的 1.63 倍。",
        ground_truth="1.63",
    )
    print(f"  数值案例：is_correct={result.is_correct}, confidence={result.confidence}")

    # 多关键点
    result = gt_eval.evaluate(
        question="谁更年长？大多少？",
        agent_answer="奥西里斯大帝更年长，大 15 岁。",
        ground_truth="奥西里斯大帝|15",
    )
    print(f"  多关键点：is_correct={result.is_correct}, confidence={result.confidence}")
