"""
Direct Agent —— 直接工具调用（对照组，无显式推理链）
================================================================

这是 ReAct Agent 的对照版本。使用 OpenAI Function Calling（和 01/02 一样），
LLM 不需要输出 Thought，直接决定调什么工具。

对比 ReAct Agent 的核心区别：
    - ReAct：LLM 输出文本 → 我们解析 Action → 执行工具 → 注入 Observation
    - Direct：LLM 输出 tool_calls JSON → 我们执行 → 注入 role="tool" 结果

两者共享同一套工具层（tools.py），区别仅在"推理是否可见"。

放在同一项目中的意义：
    用同一个问题分别跑两个 Agent，直接观察：
    - ReAct 有完整的 Thought 链路，能看到"为什么调这个工具"
    - Direct 只能看到工具调用序列，推理过程是黑盒
    这个对比就是 03 的学习价值所在。
"""

import json
import os
from typing import Any

from openai import OpenAI
from dotenv import load_dotenv

from tools import execute_tool, TOOLS_SCHEMA

load_dotenv()


# ============================================================
# System Prompt —— 直接模式，不要求输出 Thought
# ============================================================

SYSTEM_PROMPT = """你是星云大陆知识助手。使用提供的工具来查询信息并回答问题。

## 规则

1. 你的知识仅限于工具返回的信息，不要使用训练数据中的知识来回答关于星云大陆的问题
2. 必须通过工具查询后才能回答，不要猜测
3. 如果工具返回了错误，根据错误信息调整参数重试
4. 收集到足够信息后，直接给出最终答案
"""


class DirectAgent:
    """
    Direct Agent —— 使用 Function Calling 的传统工具调用模式。

    核心循环（和 01/02 一样）：
        用户提问 → LLM 返回 tool_calls → 执行工具 → 注入结果 → 循环直到 LLM 给文本回复

    这里没有显式的 Thought——LLM 内部在推理，但我们看不到过程。
    """

    def __init__(self, max_steps: int = 10, verbose: bool = True):
        """
        初始化 Direct Agent。

        参数：
            max_steps: 最大工具调用轮数
            verbose: 是否打印工具调用详情
        """
        self._client = OpenAI()
        self._model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._max_steps = max_steps
        self._verbose = verbose

    def run(self, question: str) -> dict:
        """
        运行 Direct 模式回答问题。

        返回格式和 ReAct Agent 一致，方便对比：
            {
                "answer": "最终答案文本",
                "steps": [...],
                "total_steps": N,
                "terminated_by": "final_answer" | "max_steps",
            }
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        steps = []
        answer = None
        terminated_by = "max_steps"

        for step_num in range(1, self._max_steps + 1):
            if self._verbose:
                print(f"\n{'─' * 50}")
                print(f"  步骤 {step_num}/{self._max_steps}")
                print(f"{'─' * 50}")

            # 调用 LLM（带 tools 参数）
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=TOOLS_SCHEMA,
                temperature=0,
            )

            msg = response.choices[0].message

            # 情况 1：LLM 给出文本回复（没有 tool_calls）→ 完成
            if not msg.tool_calls:
                answer = msg.content or ""
                terminated_by = "final_answer"
                messages.append({"role": "assistant", "content": answer})

                if self._verbose:
                    print(f"\n  ✅ 最终回答：{answer}")

                steps.append({
                    "step": step_num,
                    "thought": None,  # Direct 模式没有显式 Thought
                    "action": None,
                    "action_input": None,
                    "observation": None,
                })
                break

            # 情况 2：LLM 返回 tool_calls → 执行工具
            # 先把 assistant 消息（含 tool_calls）加入历史
            messages.append(msg.model_dump())

            for tool_call in msg.tool_calls:
                func_name = tool_call.function.name
                try:
                    func_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    func_args = {}

                if self._verbose:
                    print(f"  🔧 Tool Call: {func_name}")
                    print(f"  📥 Args: {json.dumps(func_args, ensure_ascii=False)}")

                # 执行工具（复用 ReAct 的同一套工具函数）
                observation = execute_tool(func_name, func_args)

                if self._verbose:
                    print(f"  👁️ Result: {observation}")

                # 注入 role="tool" 结果
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": observation,
                })

                steps.append({
                    "step": step_num,
                    "thought": None,
                    "action": func_name,
                    "action_input": func_args,
                    "observation": observation,
                })

        if answer is None:
            answer = "抱歉，达到最大调用轮数仍未能得出结论。"

        return {
            "answer": answer,
            "steps": steps,
            "total_steps": len(steps),
            "terminated_by": terminated_by,
        }


# ============================================================
# 快速测试
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Direct Agent 快速验证（对照组）")
    print("=" * 60)

    agent = DirectAgent(max_steps=8, verbose=True)
    question = "星辰王国的面积是月影王国的多少倍？"

    print(f"\n❓ 问题：{question}")
    result = agent.run(question)

    print(f"\n{'=' * 60}")
    print(f"📊 运行结果")
    print(f"{'=' * 60}")
    print(f"  答案：{result['answer']}")
    print(f"  总步数：{result['total_steps']}")
    print(f"  终止原因：{result['terminated_by']}")
