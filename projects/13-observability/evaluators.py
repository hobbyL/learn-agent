"""
evaluators.py —— 规则匹配评分器 + LLM-as-Judge 评分器
=====================================================

两种评估方式的适用场景：
- 规则匹配：适合事实型问题（有明确答案/关键词），快速、确定性、零成本
- LLM-as-Judge：适合开放型问题（需要综合判断），灵活、主观、需要 LLM 调用

两者不互斥，可以同时使用。事实型问题先跑规则匹配（快速 pass/fail），
再跑 LLM-as-Judge（评估表述质量）。
"""

import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# 规则匹配评分器
# ============================================================

def rule_evaluator(answer: str, expected_keywords: list[str]) -> dict:
    """
    规则匹配评分器：检查 answer 是否包含所有 expected_keywords。

    参数：
        answer: Agent 的回答文本
        expected_keywords: 必须出现的关键词列表（任一匹配即可）

    返回：
        {
            "pass": bool,         # 是否通过（至少匹配一个关键词）
            "matched": [...],     # 匹配到的关键词
            "missed": [...],      # 未匹配到的关键词
            "score": float,       # 匹配比例 0.0-1.0
        }

    评分规则：
        - 如果 expected_keywords 为空（开放型问题），直接返回 pass=True, score=1.0
        - 否则，至少匹配一个关键词算 pass
        - score = 匹配数 / 总关键词数
    """
    if not expected_keywords:
        return {"pass": True, "matched": [], "missed": [], "score": 1.0}

    matched = []
    missed = []

    for kw in expected_keywords:
        if kw in answer:
            matched.append(kw)
        else:
            missed.append(kw)

    passed = len(matched) > 0
    score = len(matched) / len(expected_keywords)

    return {
        "pass": passed,
        "matched": matched,
        "missed": missed,
        "score": score,
    }


# ============================================================
# LLM-as-Judge 评分器
# ============================================================

_JUDGE_SYSTEM_PROMPT = """你是一个评估专家。你的任务是评估一个 AI 助手对问题的回答质量。

请从以下三个维度进行评分（每项 1-5 分）：

1. **正确性**：回答是否事实正确、数据准确
2. **完整性**：是否涵盖了问题要求的所有方面
3. **相关性**：是否紧扣问题，没有无关内容

最终给出一个综合评分（1-5 分）和简短评价理由。

## 评分标准

- 5 分：优秀——完全正确、全面、紧扣问题
- 4 分：良好——基本正确，略有遗漏
- 3 分：合格——方向正确但有明显缺陷
- 2 分：较差——有较多错误或严重遗漏
- 1 分：很差——答非所问或完全错误

## 输出格式（严格遵守）

请严格按以下 JSON 格式输出，不要输出其他内容：

{
  "correctness": <1-5>,
  "completeness": <1-5>,
  "relevance": <1-5>,
  "score": <1-5 综合评分>,
  "reasoning": "<简短评价理由，50字以内>"
}"""


def llm_judge_evaluator(
    question: str,
    answer: str,
    reference: str,
    client: OpenAI | None = None,
) -> dict:
    """
    LLM-as-Judge 评分器：用 LLM 评估回答质量。

    参数：
        question: 原始问题
        answer: Agent 的回答
        reference: 参考答案
        client: OpenAI client（不传时自动创建）

    返回：
        {
            "score": int,          # 综合评分 1-5
            "correctness": int,    # 正确性 1-5
            "completeness": int,   # 完整性 1-5
            "relevance": int,      # 相关性 1-5
            "reasoning": str,      # 评价理由
        }
    """
    if client is None:
        client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            base_url=os.environ.get("OPENAI_BASE_URL") or None,
        )

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    user_content = (
        f"## 问题\n{question}\n\n"
        f"## AI 助手的回答\n{answer}\n\n"
        f"## 参考答案\n{reference}\n\n"
        f"请评估 AI 助手的回答质量。"
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content or ""

        # 从回复中提取 JSON
        result = _extract_json(content)
        if result:
            return {
                "score": int(result.get("score", 3)),
                "correctness": int(result.get("correctness", 3)),
                "completeness": int(result.get("completeness", 3)),
                "relevance": int(result.get("relevance", 3)),
                "reasoning": result.get("reasoning", ""),
            }

        # JSON 解析失败，返回默认值
        return {
            "score": 3,
            "correctness": 3,
            "completeness": 3,
            "relevance": 3,
            "reasoning": f"评分解析失败，原始输出：{content[:100]}",
        }

    except Exception as e:
        return {
            "score": 0,
            "correctness": 0,
            "completeness": 0,
            "relevance": 0,
            "reasoning": f"LLM 调用失败：{e}",
        }


def _extract_json(text: str) -> dict | None:
    """从文本中提取 JSON 对象。"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试从 markdown 代码块中提取
    import re
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试从文本中找到 { ... } 块
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None
