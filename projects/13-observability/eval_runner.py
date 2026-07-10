"""
eval_runner.py —— 评估引擎
===========================

加载 eval_dataset.json，对指定 Agent 跑完整评估：
- 对每个问题调用 Agent 获取回答
- 用规则匹配评分器（事实型问题）
- 用 LLM-as-Judge 评分器（所有问题）
- 返回结构化结果列表
"""

import json
import os
import time
from typing import Callable

from openai import OpenAI
from dotenv import load_dotenv

from evaluators import rule_evaluator, llm_judge_evaluator

load_dotenv()


# ============================================================
# 数据集加载
# ============================================================

def load_dataset(filepath: str | None = None) -> list[dict]:
    """
    加载评估数据集。

    参数：
        filepath: JSON 文件路径，默认使用当前目录下的 eval_dataset.json

    返回：
        数据集列表 [{"question": ..., "type": ..., "expected_keywords": ..., "reference_answer": ...}, ...]
    """
    if filepath is None:
        filepath = os.path.join(os.path.dirname(__file__), "eval_dataset.json")

    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 评估引擎
# ============================================================

def run_eval(
    agent_fn: Callable[[str], str],
    dataset: list[dict] | None = None,
    use_llm_judge: bool = True,
    agent_name: str = "Agent",
) -> list[dict]:
    """
    对 agent_fn 跑完整 eval 数据集。

    参数：
        agent_fn: 接受 question 返回 answer 字符串的函数
        dataset: 评估数据集，默认加载 eval_dataset.json
        use_llm_judge: 是否使用 LLM-as-Judge 评分
        agent_name: Agent 名称（用于输出标识）

    返回：
        [
            {
                "question": str,
                "type": "factual" | "open",
                "answer": str,
                "rule_eval": {"pass": bool, "matched": [...], "missed": [...], "score": float} | None,
                "llm_eval": {"score": int, "reasoning": str, ...} | None,
                "elapsed_ms": float,
                "error": str | None,
            },
            ...
        ]
    """
    if dataset is None:
        dataset = load_dataset()

    # LLM-as-Judge 需要的 client
    client = None
    if use_llm_judge:
        client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            base_url=os.environ.get("OPENAI_BASE_URL") or None,
        )

    results = []
    total = len(dataset)

    for i, item in enumerate(dataset, 1):
        question = item["question"]
        q_type = item.get("type", "open")
        expected_keywords = item.get("expected_keywords", [])
        reference_answer = item.get("reference_answer", "")

        print(f"  [{agent_name}] 评估 {i}/{total}: {question[:40]}...", end="", flush=True)

        result_entry = {
            "question": question,
            "type": q_type,
            "answer": "",
            "rule_eval": None,
            "llm_eval": None,
            "elapsed_ms": 0,
            "error": None,
        }

        # 运行 Agent
        try:
            t0 = time.time()
            answer = agent_fn(question)
            elapsed_ms = (time.time() - t0) * 1000
            result_entry["answer"] = answer
            result_entry["elapsed_ms"] = round(elapsed_ms, 1)
        except Exception as e:
            result_entry["error"] = str(e)
            result_entry["answer"] = f"[错误] {e}"
            print(f" 错误: {e}")
            results.append(result_entry)
            continue

        # 规则匹配评分（对有关键词的问题）
        if expected_keywords:
            result_entry["rule_eval"] = rule_evaluator(answer, expected_keywords)

        # LLM-as-Judge 评分
        if use_llm_judge and client:
            result_entry["llm_eval"] = llm_judge_evaluator(
                question, answer, reference_answer, client
            )

        # 简要状态
        rule_status = ""
        if result_entry["rule_eval"]:
            rule_status = "PASS" if result_entry["rule_eval"]["pass"] else "FAIL"
        llm_score = ""
        if result_entry["llm_eval"]:
            llm_score = f"{result_entry['llm_eval']['score']}/5"

        print(f" {elapsed_ms:.0f}ms  规则:{rule_status or '-'}  LLM:{llm_score or '-'}")

        results.append(result_entry)

    return results


# ============================================================
# 汇总统计
# ============================================================

def summarize_eval(results: list[dict]) -> dict:
    """
    汇总评估结果。

    返回：
        {
            "total": int,
            "rule_pass": int,
            "rule_fail": int,
            "rule_na": int,
            "avg_llm_score": float,
            "avg_elapsed_ms": float,
            "errors": int,
        }
    """
    total = len(results)
    rule_pass = sum(1 for r in results if r["rule_eval"] and r["rule_eval"]["pass"])
    rule_fail = sum(1 for r in results if r["rule_eval"] and not r["rule_eval"]["pass"])
    rule_na = sum(1 for r in results if r["rule_eval"] is None)

    llm_scores = [r["llm_eval"]["score"] for r in results if r["llm_eval"] and r["llm_eval"]["score"] > 0]
    avg_llm = sum(llm_scores) / len(llm_scores) if llm_scores else 0.0

    elapsed_values = [r["elapsed_ms"] for r in results if r["elapsed_ms"] > 0]
    avg_elapsed = sum(elapsed_values) / len(elapsed_values) if elapsed_values else 0.0

    errors = sum(1 for r in results if r["error"])

    return {
        "total": total,
        "rule_pass": rule_pass,
        "rule_fail": rule_fail,
        "rule_na": rule_na,
        "avg_llm_score": round(avg_llm, 2),
        "avg_elapsed_ms": round(avg_elapsed, 1),
        "errors": errors,
    }
