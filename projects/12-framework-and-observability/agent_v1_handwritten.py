"""
agent_v1_handwritten.py —— 手写纯文本 ReAct（从项目 03 复用）
==============================================================

这是项目 03 的 react_agent.py 原版实现，只做了最小化适配（import 路径）。

核心特征：
- 工具调用：纯文本格式（Thought / Action / Action Input），正则解析
- 循环控制：for 循环 + continue/break
- messages 管理：手动 append
- 工具执行：手写 execute_tool()
- 状态持久化：无
- 代码量：~120 行

这是"最底层"实现，完全没有框架支持，所有机制都手工实现。
"""

import json
import os
import re
from typing import Optional

from openai import OpenAI
from dotenv import load_dotenv

from tools import execute_tool, get_tool_descriptions

load_dotenv()


# ============================================================
# ReAct 格式定义
# ============================================================

_UNFINISHED_PLAN_PATTERNS = [
    "接下来", "还需要", "再查", "再查询", "需要再", "然后查", "然后再",
    "继续查", "分别查询", "查询每个", "查完", "再计算", "然后计算",
]

RE_THOUGHT = re.compile(
    r"\*{0,2}Thought:?\*{0,2}\s*(.+?)(?=\n\*{0,2}(?:Action|Final Answer):?\*{0,2}|$)",
    re.DOTALL,
)
RE_ACTION = re.compile(r"\*{0,2}Action:?\*{0,2}\s*(\w+)")
RE_ACTION_INPUT = re.compile(r"\*{0,2}Action Input:?\*{0,2}\s*(\{.*?\})", re.DOTALL)
RE_FINAL_ANSWER = re.compile(r"\*{0,2}Final Answer:?\*{0,2}\s*(.+)", re.DOTALL)


# ============================================================
# System Prompt
# ============================================================

SYSTEM_PROMPT_TEMPLATE = """你是星云大陆知识助手。你通过"思考-行动-观察"循环来回答问题。

## 可用工具

{tool_descriptions}

## 输出格式（严格遵守）

每一步你必须按以下格式输出：

Thought: <你的思考过程——分析问题、决定下一步做什么、为什么>
Action: <工具名，必须是上面列出的工具之一>
Action Input: {{"参数名": "参数值", ...}}

当你收集到足够信息可以回答时：

Thought: <总结推理过程>
Final Answer: <最终答案>

## 规则

1. 每次只输出一个 Thought + 一个 Action（或 Final Answer），不要一次输出多步
2. Thought 必须写出你的推理过程——为什么要调这个工具、期望得到什么
3. 只有当你确信有足够信息时才给出 Final Answer
4. 你的知识仅限于工具返回的信息，不要使用训练数据中的知识来回答关于星云大陆的问题
5. Action Input 必须是合法的 JSON 对象
6. 如果工具返回了错误信息，在 Thought 中分析错误原因并调整策略

## 关键约束（最高优先级）

- 绝对禁止编造数据：如果你需要某个数值但还没有通过工具获取到，你必须先调用工具获取
- Final Answer 中的每一个数据点都必须有对应的 Observation 来源
- "计划查询"不等于"已经查询"：在 Thought 中说"接下来要查 X"之后，你必须真的执行 Action 去查
- 涉及计算的问题，必须使用 calculate 工具得出结果，不要心算
"""


class ReactAgent:
    """
    手写纯文本 ReAct Agent（v1）。

    核心循环：用户提问 → [Thought → Action → Observation] × N → Final Answer

    和 v2/v3 的区别：
    - 不依赖任何框架
    - 自己解析文本中的 Action
    - 自己维护 messages 列表
    - 自己实现 execute_tool
    - 无状态持久化（每次重新开始）
    """

    def __init__(self, max_steps: int = 10, verbose: bool = True):
        self._client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            base_url=os.environ.get("OPENAI_BASE_URL") or None,
        )
        self._model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._max_steps = max_steps
        self._verbose = verbose

        tool_desc = get_tool_descriptions()
        self._system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            tool_descriptions=tool_desc
        )

    def run(self, question: str) -> dict:
        """
        运行 ReAct 循环回答问题。

        返回：
            {
                "answer": str,
                "steps": list[dict],
                "total_steps": int,
                "terminated_by": str,  # "final_answer" | "max_steps" | "parse_error"
            }
        """
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": f"问题：{question}"},
        ]

        steps = []
        answer = None
        terminated_by = "max_steps"

        for step_num in range(1, self._max_steps + 1):
            if self._verbose:
                print(f"\n  步骤 {step_num}/{self._max_steps}")

            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0,
            )
            content = response.choices[0].message.content or ""
            messages.append({"role": "assistant", "content": content})

            parsed = self._parse_output(content)

            if self._verbose and parsed.get("thought"):
                print(f"  [Thought] {parsed['thought'][:100]}...")

            # 情况 1：Final Answer
            if parsed.get("final_answer"):
                thought = parsed.get("thought", "")

                # 跳步检测
                unfinished = [kw for kw in _UNFINISHED_PLAN_PATTERNS if kw in thought]
                if unfinished:
                    hint = "、".join(unfinished[:3])
                    collected = [
                        f"  - {s['action']}({s['action_input']}) → {str(s['observation'])[:80]}"
                        for s in steps
                        if s.get("action") and not s["action"].startswith("_") and s.get("observation")
                    ]
                    collected_text = "\n".join(collected) if collected else "  （暂无）"
                    messages.append({
                        "role": "user",
                        "content": (
                            f"你的 Thought 里提到了「{hint}」等计划，"
                            f"但你还没有执行这些步骤就给出了 Final Answer。\n\n"
                            f"你目前已收集的数据：\n{collected_text}\n\n"
                            f"请继续执行计划中尚未完成的工具调用，获取缺失的数据后再给出最终答案。"
                        ),
                    })
                    steps.append({
                        "step": step_num,
                        "thought": thought,
                        "action": "_unfinished_plan_rejected",
                        "action_input": {"unfinished_keywords": unfinished},
                        "observation": f"答案被拒绝：Thought 中有未执行的计划（{hint}）",
                    })
                    continue

                answer = parsed["final_answer"]
                terminated_by = "final_answer"
                steps.append({
                    "step": step_num,
                    "thought": thought,
                    "action": None,
                    "action_input": None,
                    "observation": None,
                })
                if self._verbose:
                    print(f"  [Final Answer] {answer}")
                break

            # 情况 2：Action
            if parsed.get("action"):
                action = parsed["action"]
                action_input = parsed.get("action_input", {})

                if self._verbose:
                    print(f"  [Action] {action}({json.dumps(action_input, ensure_ascii=False)})")

                observation = execute_tool(action, action_input)

                if self._verbose:
                    print(f"  [Observation] {observation[:150]}")

                messages.append({
                    "role": "user",
                    "content": f"Observation: {observation}",
                })

                steps.append({
                    "step": step_num,
                    "thought": parsed.get("thought", ""),
                    "action": action,
                    "action_input": action_input,
                    "observation": observation,
                })

            # 情况 3：解析失败
            else:
                messages.append({
                    "role": "user",
                    "content": (
                        "格式错误：你的输出不符合要求的格式。请严格按照以下格式输出：\n\n"
                        "Thought: <你的思考>\n"
                        "Action: <工具名>\n"
                        'Action Input: {"参数": "值"}\n\n'
                        "或者如果你已经有足够信息：\n\n"
                        "Thought: <总结>\n"
                        "Final Answer: <最终答案>"
                    ),
                })
                steps.append({
                    "step": step_num,
                    "thought": parsed.get("thought", ""),
                    "action": "_format_error",
                    "action_input": {"raw_output": content[:200]},
                    "observation": "格式错误，已提示重试",
                })

                recent_errors = sum(
                    1 for s in steps[-3:]
                    if s.get("action") == "_format_error"
                )
                if recent_errors >= 3:
                    terminated_by = "parse_error"
                    answer = "抱歉，推理过程遇到格式问题，无法完成回答。"
                    break

        if answer is None:
            answer = "抱歉，达到最大推理步数仍未能得出结论。"

        return {
            "answer": answer,
            "steps": steps,
            "total_steps": len(steps),
            "terminated_by": terminated_by,
        }

    def _call_llm(self, messages: list[dict]) -> object:
        return self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0,
        )

    def _parse_output(self, content: str) -> dict:
        result = {
            "thought": None,
            "action": None,
            "action_input": None,
            "final_answer": None,
        }

        thought_match = RE_THOUGHT.search(content)
        if thought_match:
            result["thought"] = thought_match.group(1).strip()

        final_match = RE_FINAL_ANSWER.search(content)
        if final_match:
            result["final_answer"] = final_match.group(1).strip()
            return result

        action_match = RE_ACTION.search(content)
        if action_match:
            result["action"] = action_match.group(1).strip()

        input_match = RE_ACTION_INPUT.search(content)
        if input_match:
            try:
                result["action_input"] = json.loads(input_match.group(1))
            except json.JSONDecodeError:
                raw = input_match.group(1).replace("'", '"')
                try:
                    result["action_input"] = json.loads(raw)
                except json.JSONDecodeError:
                    result["action_input"] = {}
        else:
            result["action_input"] = {}

        return result
