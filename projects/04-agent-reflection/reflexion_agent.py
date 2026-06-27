"""
Reflexion Agent —— 外层"试错→评估→反思→重试"循环
===================================================

这是 04 项目的核心文件。实现 Reflexion 论文的完整外层循环：

    1. 用内层 ReAct 循环执行一次任务
    2. 评估执行结果是否正确
    3. 如果正确 → 返回结果，循环结束
    4. 如果错误 → 生成反思摘要 → 注入下一轮 → 重试

和 03 的本质区别：
    03 只有 ReAct 单循环——跑一次就结束，对就对、错就错。
    04 在 ReAct 外面包了一层 Reflexion 循环：
    错了不要紧，反思一下"哪里错了、为什么、怎么改"，带着经验重试。

这和人类学习的过程一样：
    第一次做错 → 老师指出问题 → 自己总结教训 → 下次换个方法试
    Reflexion 就是让 Agent 模拟这个过程。

关键设计：
    - 反思记忆以 list[str] 形式累积（每轮追加一条）
    - 反思注入方式：拼接到 system prompt 末尾（论文标准做法）
    - 评估器和反思器通过依赖注入，支持不同策略
"""

import os
from typing import Optional

from dotenv import load_dotenv

from react_loop import ReactLoop
from evaluator import GroundTruthEvaluator, LLMJudgeEvaluator
from reflector import Reflector

load_dotenv()


class ReflexionAgent:
    """
    Reflexion Agent：在 ReAct 外层增加反思循环。

    核心循环：
        for trial in range(max_trials):
            result = inner_react.run(question, reflections)
            evaluation = evaluator.evaluate(question, result, ground_truth)
            if correct: break
            reflection = reflector.reflect(question, result, evaluation)
            reflections.append(reflection)
        return result + reflection_history

    为什么不直接在 ReAct 内部加反思？
        因为 Reflexion 论文的设计是"整轮反思"——
        让 Agent 跑完一整轮再评估，这样反思是基于"完整行为"的总结，
        而非"单步"的微调。这更接近人类的学习模式：
        做完一道题、对答案、总结经验，而非每写一步就停下来反思。
    """

    def __init__(
        self,
        max_trials: int = None,
        max_steps: int = None,
        evaluator_mode: str = None,
        verbose: bool = True,
    ):
        """
        初始化 Reflexion Agent。

        参数：
            max_trials: 最大反思轮数（默认从 .env 读取，fallback 3）
            max_steps: 内层 ReAct 每轮最大步数（默认从 .env 读取，fallback 10）
            evaluator_mode: 评估器模式 "ground_truth" | "llm_judge"
            verbose: 是否打印详细过程
        """
        self._max_trials = max_trials or int(os.environ.get("MAX_TRIALS", "3"))
        self._max_steps = max_steps or int(os.environ.get("MAX_STEPS", "10"))
        self._verbose = verbose

        # 评估器模式
        mode = evaluator_mode or os.environ.get("EVALUATOR_MODE", "ground_truth")
        if mode == "llm_judge":
            self._evaluator = LLMJudgeEvaluator()
        else:
            self._evaluator = GroundTruthEvaluator()
        self._evaluator_mode = mode

        # 反思器
        self._reflector = Reflector()

        # 内层 ReAct 循环
        self._react_loop = ReactLoop(max_steps=self._max_steps, verbose=verbose)

    def run(self, question: str, ground_truth: Optional[str] = None) -> dict:
        """
        运行 Reflexion 循环回答问题。

        参数：
            question: 用户问题
            ground_truth: 标准答案（Ground Truth 评估器需要，LLM Judge 可选）

        返回：
            {
                "answer": "最终答案",
                "is_correct": bool,
                "trials": [  # 每轮尝试的详情
                    {
                        "trial": 1,
                        "answer": "...",
                        "steps": [...],
                        "evaluation": {"is_correct": bool, "feedback": str, "confidence": float},
                        "reflection": "..." | None,
                    }
                ],
                "total_trials": int,
                "reflections": ["反思1", "反思2", ...],
                "terminated_by": "correct" | "max_trials",
            }
        """
        reflections: list[str] = []  # 反思记忆缓冲区
        trials: list[dict] = []
        final_answer = None
        is_correct = False
        terminated_by = "max_trials"

        for trial_num in range(1, self._max_trials + 1):
            if self._verbose:
                print(f"\n{'═' * 60}")
                print(f"  🔄 Trial {trial_num}/{self._max_trials}")
                if reflections:
                    print(f"  📝 携带 {len(reflections)} 条反思经验")
                print(f"{'═' * 60}")

            # ── Step 1: 内层 ReAct 执行 ──
            react_result = self._react_loop.run(question, reflections=reflections)
            final_answer = react_result["answer"]

            if self._verbose:
                print(f"\n  📤 本轮答案：{final_answer}")

            # ── Step 2: 评估 ──
            if self._evaluator_mode == "llm_judge":
                eval_result = self._evaluator.evaluate(
                    question=question,
                    agent_answer=final_answer,
                    steps=react_result.get("steps", []),
                )
            else:
                eval_result = self._evaluator.evaluate(
                    question=question,
                    agent_answer=final_answer,
                    ground_truth=ground_truth or "",
                )

            # EvalResult 是 dataclass，用属性访问
            is_correct = eval_result.is_correct

            if self._verbose:
                status = "✅ 正确" if is_correct else "❌ 错误"
                print(f"  📊 评估结果：{status}")
                print(f"  💬 反馈：{eval_result.feedback}")
                print(f"  🎯 置信度：{eval_result.confidence:.2f}")

            # 转为 dict 存储到 trial 记录中
            eval_dict = {
                "is_correct": eval_result.is_correct,
                "confidence": eval_result.confidence,
                "feedback": eval_result.feedback,
                "evaluator_type": eval_result.evaluator_type,
            }

            # 记录本轮结果
            trial_record = {
                "trial": trial_num,
                "answer": final_answer,
                "steps": react_result.get("steps", []),
                "total_steps": react_result.get("total_steps", 0),
                "evaluation": eval_dict,
                "reflection": None,
            }

            # ── Step 3: 如果正确，提前终止 ──
            if is_correct:
                trials.append(trial_record)
                terminated_by = "correct"
                if self._verbose:
                    print(f"\n  🎉 答案正确！第 {trial_num} 轮成功。")
                break

            # ── Step 4: 生成反思 ──
            if self._verbose:
                print(f"\n  🤔 生成反思中...")

            reflection = self._reflector.reflect(
                question=question,
                attempt_result=react_result,
                eval_feedback=eval_result.feedback,
            )
            reflections.append(reflection)
            trial_record["reflection"] = reflection

            if self._verbose:
                print(f"  💡 反思：{reflection}")

            trials.append(trial_record)

        # 构建最终返回
        return {
            "answer": final_answer,
            "is_correct": is_correct,
            "trials": trials,
            "total_trials": len(trials),
            "reflections": reflections,
            "terminated_by": terminated_by,
        }

    def run_without_reflection(self, question: str, ground_truth: Optional[str] = None) -> dict:
        """
        无反思模式：只跑一次 ReAct，不做评估和反思（对照组）。

        用于 --compare 模式，展示"有反思"vs"无反思"的差异。
        """
        react_result = self._react_loop.run(question, reflections=[])
        answer = react_result["answer"]

        # 评估（只为了拿评估结果，不触发反思）
        if self._evaluator_mode == "llm_judge":
            eval_result = self._evaluator.evaluate(
                question=question,
                agent_answer=answer,
                steps=react_result.get("steps", []),
            )
        else:
            eval_result = self._evaluator.evaluate(
                question=question,
                agent_answer=answer,
                ground_truth=ground_truth or "",
            )

        eval_dict = {
            "is_correct": eval_result.is_correct,
            "confidence": eval_result.confidence,
            "feedback": eval_result.feedback,
            "evaluator_type": eval_result.evaluator_type,
        }

        return {
            "answer": answer,
            "is_correct": eval_result.is_correct,
            "trials": [{
                "trial": 1,
                "answer": answer,
                "steps": react_result.get("steps", []),
                "total_steps": react_result.get("total_steps", 0),
                "evaluation": eval_dict,
                "reflection": None,
            }],
            "total_trials": 1,
            "reflections": [],
            "terminated_by": "single_run",
        }


# ============================================================
# 快速验证
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Reflexion Agent 快速验证")
    print("=" * 60)

    agent = ReflexionAgent(max_trials=3, max_steps=8, verbose=True)
    question = "深渊王国国王的导师现在住在哪里？"
    ground_truth = "暗流洞穴"

    print(f"\n❓ 问题：{question}")
    print(f"📋 标准答案：{ground_truth}")

    result = agent.run(question, ground_truth=ground_truth)

    print(f"\n{'=' * 60}")
    print(f"📊 最终结果")
    print(f"{'=' * 60}")
    print(f"  答案：{result['answer']}")
    print(f"  正确：{result['is_correct']}")
    print(f"  总轮数：{result['total_trials']}")
    print(f"  终止原因：{result['terminated_by']}")
    if result["reflections"]:
        print(f"  反思历史：")
        for i, r in enumerate(result["reflections"], 1):
            print(f"    {i}. {r}")
