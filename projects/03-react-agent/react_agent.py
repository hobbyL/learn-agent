"""
ReAct Agent —— 显式推理链（Thought → Action → Observation 循环）
================================================================

这是 03 项目的核心文件。实现 ReAct 模式的完整循环：

    1. 把问题 + 工具描述 + 格式要求注入 system prompt
    2. LLM 输出一段文本，包含 Thought + Action
    3. 我们解析出 Action（工具名 + 参数），执行工具
    4. 把工具结果作为 Observation 追加到对话历史
    5. 重复 2-4，直到 LLM 输出 Final Answer 或达到 max_steps

和 01/02 的本质区别：
    01/02 使用 OpenAI Function Calling（结构化 JSON），推理是隐式的。
    03 使用纯文本格式，要求 LLM 先写 Thought 再写 Action——
    推理过程被显式输出，可审计、可调试、可追溯。

为什么选纯文本而不是 Function Calling？
    因为 ReAct 论文的原始设计就是文本格式。
    Function Calling 是 OpenAI 的工程化包装（帮你做了格式解析），
    但它隐藏了推理过程。03 的学习目标正是体验"显式推理"的价值，
    所以故意不用 Function Calling，自己解析文本。
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

# 检测 Thought 中"未完成计划"的中文关键词。
# 背景：LLM 有时会在 Thought 里写"接下来要查 X"，然后跳过工具调用直接输出
# Final Answer（编造假数字）。这是 ReAct 的经典跳步 bug——"计划"不等于"已执行"。
# 解决方法：若 Final Answer 出现时 Thought 里含有这些词，说明 LLM 自相矛盾，
# 应拒绝该 Final Answer，让它先把计划中的工具调用真正执行一遍。
_UNFINISHED_PLAN_PATTERNS = [
    "接下来", "还需要", "再查", "再查询", "需要再", "然后查", "然后再",
    "继续查", "分别查询", "查询每个", "查完", "再计算", "然后计算",
]
# LLM 输出必须遵循的格式（通过 prompt 约束）。
# 我们用正则从输出中提取 Thought、Action、Action Input、Final Answer。

# Action 格式示例：
#   Thought: 我需要先查找星辰王国的面积
#   Action: lookup
#   Action Input: {"entity": "星辰王国", "field": "面积"}
#
# 终止格式：
#   Thought: 我已经得到了所有需要的信息，可以回答了
#   Final Answer: 星辰王国的面积是 8500 平方千米

# 解析正则（兼容 LLM 可能输出的 markdown 加粗格式 **Thought:** ）
RE_THOUGHT = re.compile(
    r"\*{0,2}Thought:?\*{0,2}\s*(.+?)(?=\n\*{0,2}(?:Action|Final Answer):?\*{0,2}|$)",
    re.DOTALL,
)
RE_ACTION = re.compile(r"\*{0,2}Action:?\*{0,2}\s*(\w+)")
RE_ACTION_INPUT = re.compile(r"\*{0,2}Action Input:?\*{0,2}\s*(\{.*?\})", re.DOTALL)
RE_FINAL_ANSWER = re.compile(r"\*{0,2}Final Answer:?\*{0,2}\s*(.+)", re.DOTALL)


# ============================================================
# System Prompt —— 告诉 LLM 如何做 ReAct
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

- 绝对禁止编造数据：如果你需要某个数值但还没有通过工具获取到，你必须先调用工具获取，绝不能猜测或编造
- Final Answer 中的每一个数据点都必须有对应的 Observation 来源——如果你发现自己要引用一个没有从工具返回过的数据，停下来，先去查询
- "计划查询"不等于"已经查询"：在 Thought 中说"接下来要查 X"之后，你必须真的执行 Action 去查，不能跳过直接给 Final Answer
- 涉及计算的问题，必须使用 calculate 工具得出结果，不要心算

## 示例

问题：星辰王国的国王是谁？

Thought: 我需要查找星辰王国的国王信息。先搜索一下星辰王国。
Action: search
Action Input: {{"query": "星辰王国"}}

（收到 Observation 后继续）

Thought: 搜索到了星辰王国，现在查询它的国王字段。
Action: lookup
Action Input: {{"entity": "星辰王国", "field": "统治者"}}

（收到 Observation 后继续）

Thought: 查到了，星辰王国的统治者是艾瑞克三世。
Final Answer: 星辰王国的国王是艾瑞克三世。
"""


class ReactAgent:
    """
    ReAct Agent 实现。

    核心循环：
        用户提问 → [Thought → Action → Observation] × N → Final Answer

    关键设计决策：
        1. 用 messages 列表累积对话历史（和 01/02 一样，LLM 是无状态的）
        2. 每轮从 LLM 输出中解析 Action，执行后把 Observation 注入 messages
        3. Observation 作为 user 消息注入（模拟"环境反馈"）
        4. max_steps 防止死循环
    """

    def __init__(self, max_steps: int = 10, verbose: bool = True):
        """
        初始化 ReAct Agent。

        参数：
            max_steps: 最大推理步数（防止死循环）
            verbose: 是否打印推理链详情
        """
        self._client = OpenAI()
        self._model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._max_steps = max_steps
        self._verbose = verbose

        # 构建 system prompt
        tool_desc = get_tool_descriptions()
        self._system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            tool_descriptions=tool_desc
        )

    def run(self, question: str) -> dict:
        """
        运行 ReAct 循环回答问题。

        参数：
            question: 用户问题

        返回：
            {
                "answer": "最终答案文本",
                "steps": [  # 推理链详情
                    {
                        "step": 1,
                        "thought": "...",
                        "action": "tool_name",
                        "action_input": {...},
                        "observation": "...",
                    },
                    ...
                ],
                "total_steps": 3,
                "terminated_by": "final_answer" | "max_steps" | "parse_error",
            }
        """
        # 初始化对话历史
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": f"问题：{question}"},
        ]

        steps = []
        answer = None
        terminated_by = "max_steps"

        for step_num in range(1, self._max_steps + 1):
            if self._verbose:
                print(f"\n{'─' * 50}")
                print(f"  步骤 {step_num}/{self._max_steps}")
                print(f"{'─' * 50}")

            # 调用 LLM
            response = self._call_llm(messages)
            content = response.choices[0].message.content or ""

            # 把 LLM 输出加入历史
            messages.append({"role": "assistant", "content": content})

            # 解析输出
            parsed = self._parse_output(content)

            if self._verbose and parsed.get("thought"):
                print(f"\n  💭 Thought: {parsed['thought']}")

            # 情况 1：LLM 给出了 Final Answer
            if parsed.get("final_answer"):
                thought = parsed.get("thought", "")

                # ── 跳步检测 ────────────────────────────────────────────────
                # 检查 Thought 是否含有"计划性语言"——LM 说了"接下来要做 X"
                # 但却没有真正执行工具就给出了 Final Answer（自相矛盾的跳步）。
                # 这是 ReAct 的经典 bug：LM 把"计划写进 Thought"当成了"已经完成"，
                # 然后依赖自身先验知识编造数字。
                # 对策：拒绝该 Final Answer，把矛盾点明确告知 LM，让它补完计划步骤。
                unfinished = [kw for kw in _UNFINISHED_PLAN_PATTERNS if kw in thought]
                if unfinished:
                    hint = "、".join(unfinished[:3])
                    # 汇总已成功获取的 Observation（跳过 _format_error / _unfinished_plan_rejected 等内部步骤）
                    # 目的：让 LM 明确知道自己已经收集了哪些数据，避免"拒绝后失忆"——
                    # 即看到"请继续执行计划"就从头重新规划、重复查询已有数据，导致步数耗尽。
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
                            f"不要重新查询你已经有的数据。"
                        ),
                    })
                    steps.append({
                        "step": step_num,
                        "thought": thought,
                        "action": "_unfinished_plan_rejected",
                        "action_input": {"unfinished_keywords": unfinished},
                        "observation": f"答案被拒绝：Thought 中有未执行的计划（{hint}），需先完成",
                    })
                    if self._verbose:
                        print(f"\n  🚫 计划未完成：Thought 提到「{hint}」但直接给了 Final Answer，拒绝")
                    continue
                # ── 跳步检测结束 ─────────────────────────────────────────────

                # 没有未完成计划，正常接受 Final Answer
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
                    print(f"\n  ✅ Final Answer: {answer}")
                break

            # 情况 2：解析出了 Action
            if parsed.get("action"):
                action = parsed["action"]
                action_input = parsed.get("action_input", {})

                if self._verbose:
                    print(f"  🔧 Action: {action}")
                    print(f"  📥 Input: {json.dumps(action_input, ensure_ascii=False)}")

                # 执行工具
                observation = execute_tool(action, action_input)

                if self._verbose:
                    print(f"  👁️ Observation: {observation}")

                # 把 Observation 作为 user 消息注入
                # 为什么用 user 消息？因为 Observation 是"环境反馈"，
                # 不是 LLM 自己说的话。用 user 角色模拟"环境告诉 Agent 结果"。
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

            # 情况 3：解析失败（LLM 输出格式不对）
            else:
                if self._verbose:
                    print(f"  ⚠️ 格式解析失败，提示 LLM 重新输出")
                    print(f"  原始输出：{content[:200]}...")

                # 格式容错：告诉 LLM 格式不对，让它重试
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

                # 如果连续 3 次格式错误，放弃
                recent_errors = sum(
                    1 for s in steps[-3:]
                    if s.get("action") == "_format_error"
                )
                if recent_errors >= 3:
                    terminated_by = "parse_error"
                    answer = "抱歉，推理过程遇到格式问题，无法完成回答。"
                    break

        # 如果达到 max_steps 但没有 Final Answer
        if answer is None:
            answer = "抱歉，达到最大推理步数仍未能得出结论。"

        return {
            "answer": answer,
            "steps": steps,
            "total_steps": len(steps),
            "terminated_by": terminated_by,
        }

    def _call_llm(self, messages: list[dict]) -> object:
        """
        调用 OpenAI API。

        注意：03 不使用 tools 参数（Function Calling），
        而是让 LLM 以纯文本输出 Action，由我们自己解析。
        这是 ReAct 和 Function Calling 的核心区别。
        """
        return self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0,  # 推理任务用低温度，减少随机性
        )

    def _parse_output(self, content: str) -> dict:
        """
        从 LLM 输出文本中解析 Thought / Action / Final Answer。

        返回：
            {
                "thought": str | None,
                "action": str | None,
                "action_input": dict | None,
                "final_answer": str | None,
            }

        解析策略：
            用正则分别匹配各个字段。容忍一定的格式偏差
            （比如多余空行、大小写混用），但核心标记必须存在。
        """
        result = {
            "thought": None,
            "action": None,
            "action_input": None,
            "final_answer": None,
        }

        # 提取 Thought
        thought_match = RE_THOUGHT.search(content)
        if thought_match:
            result["thought"] = thought_match.group(1).strip()

        # 检查是否是 Final Answer
        final_match = RE_FINAL_ANSWER.search(content)
        if final_match:
            result["final_answer"] = final_match.group(1).strip()
            return result  # Final Answer 优先，不再解析 Action

        # 提取 Action
        action_match = RE_ACTION.search(content)
        if action_match:
            result["action"] = action_match.group(1).strip()

        # 提取 Action Input
        input_match = RE_ACTION_INPUT.search(content)
        if input_match:
            try:
                result["action_input"] = json.loads(input_match.group(1))
            except json.JSONDecodeError:
                # JSON 解析失败，尝试修复常见问题（单引号→双引号）
                raw = input_match.group(1).replace("'", '"')
                try:
                    result["action_input"] = json.loads(raw)
                except json.JSONDecodeError:
                    result["action_input"] = {}
        else:
            result["action_input"] = {}

        return result


# ============================================================
# 快速测试
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("ReAct Agent 快速验证")
    print("=" * 60)

    agent = ReactAgent(max_steps=8, verbose=True)
    question = "星辰王国的面积是月影王国的多少倍？"

    print(f"\n❓ 问题：{question}")
    result = agent.run(question)

    print(f"\n{'=' * 60}")
    print(f"📊 运行结果")
    print(f"{'=' * 60}")
    print(f"  答案：{result['answer']}")
    print(f"  总步数：{result['total_steps']}")
    print(f"  终止原因：{result['terminated_by']}")
