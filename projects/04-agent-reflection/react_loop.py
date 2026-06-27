"""
内层轻量 ReAct 循环 —— 为 Reflexion 服务的简化版本
====================================================

和 03 的 react_agent.py 的区别：
    1. 不做跳步检测（故意让 Agent 更容易犯错，以触发外层反思）
    2. 接受 reflections 参数，将历次反思注入 system prompt
    3. 更简洁的实现，因为重点在外层 Reflexion 循环而非 ReAct 本身

设计哲学：
    03 花了大量精力做"护栏"防止 LLM 犯错。
    04 反过来——让 LLM 自然地犯错，然后通过外层反思循环来改正。
    这是两种不同的容错策略：硬护栏 vs 软反思。
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
# 解析正则 —— 从 LLM 输出中提取结构化信息
# ============================================================

# 兼容 markdown 加粗格式（**Thought:**）
RE_THOUGHT = re.compile(
    r"\*{0,2}Thought:?\*{0,2}\s*(.+?)(?=\n\*{0,2}(?:Action|Final Answer):?\*{0,2}|$)",
    re.DOTALL,
)
RE_ACTION = re.compile(r"\*{0,2}Action:?\*{0,2}\s*(\w+)")
RE_ACTION_INPUT = re.compile(r"\*{0,2}Action Input:?\*{0,2}\s*(\{.*?\})", re.DOTALL)
RE_FINAL_ANSWER = re.compile(r"\*{0,2}Final Answer:?\*{0,2}\s*(.+)", re.DOTALL)


# ============================================================
# System Prompt 模板
# ============================================================

SYSTEM_PROMPT_TEMPLATE = """你是深海联盟知识助手。你通过"思考-行动-观察"循环来回答问题。

## 可用工具

{tool_descriptions}

## 输出格式（严格遵守）

每一步你必须按以下格式输出（不要使用 markdown 加粗）：

Thought: <你的思考过程>
Action: <工具名>
Action Input: {{"参数名": "参数值", ...}}

当你收集到足够信息可以回答时：

Thought: <总结推理过程>
Final Answer: <最终答案>

## 规则

1. 每次只输出一个 Thought + 一个 Action（或 Final Answer）
2. Thought 必须写出你的推理过程
3. 只有当你确信有足够信息时才给出 Final Answer
4. 你的知识仅限于工具返回的信息，不要使用训练数据中的知识来回答关于深海联盟的问题
5. Action Input 必须是合法的 JSON 对象
6. 如果工具返回了错误信息，在 Thought 中分析错误原因并调整策略
7. 注意区分名称相似的实体（如"珊瑚城"和"珊瑚礁堡"是不同的地方）

## 示例

问题：深渊王国的国王是谁？

Thought: 我需要查找深渊王国的国王信息。先搜索一下。
Action: search
Action Input: {{"query": "深渊王国"}}

（收到 Observation 后继续）

Thought: 找到了深渊王国，现在查它的统治者。
Action: lookup
Action Input: {{"entity": "深渊王国", "field": "统治者"}}

（收到 Observation 后继续）

Thought: 查到了答案。
Final Answer: 深渊王国的国王是奥西里斯大帝。
"""

# 反思注入模板 —— 追加在 system prompt 末尾
REFLECTION_INJECTION_TEMPLATE = """

## 重要：从之前的尝试中学到的教训

以下是你在之前的尝试中犯的错误和总结的经验。请务必避免重复同样的错误：

{reflections}

请特别注意上述教训，在这次尝试中避免同样的错误。
"""


class ReactLoop:
    """
    内层轻量 ReAct 循环。

    和 03 相比的简化：
        - 不做跳步检测（让错误自然发生）
        - 不做连续格式错误计数（简化逻辑）
        - 支持 reflections 注入（Reflexion 核心功能）

    保留的核心能力：
        - Thought → Action → Observation 循环
        - 格式解析容错（给 LLM 一次重试机会）
        - max_steps 防死循环
    """

    def __init__(self, max_steps: int = 10, verbose: bool = True):
        """
        初始化。

        参数：
            max_steps: 最大推理步数
            verbose: 是否打印推理过程
        """
        self._client = OpenAI()
        self._model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._max_steps = max_steps
        self._verbose = verbose
        self._tool_desc = get_tool_descriptions()

    def run(self, question: str, reflections: list[str] | None = None) -> dict:
        """
        运行 ReAct 循环回答问题。

        参数：
            question: 用户问题
            reflections: 历次反思摘要列表（由外层 Reflexion 循环传入）

        返回：
            {
                "answer": str,           # 最终答案
                "steps": list[dict],     # 推理链
                "total_steps": int,      # 总步数
                "terminated_by": str,    # "final_answer" | "max_steps" | "parse_error"
            }
        """
        # 构建 system prompt（含反思注入）
        system_prompt = self._build_system_prompt(reflections)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"问题：{question}"},
        ]

        steps = []
        answer = None
        terminated_by = "max_steps"
        format_error_count = 0  # 连续格式错误计数

        for step_num in range(1, self._max_steps + 1):
            if self._verbose:
                print(f"\n  {'─' * 40}")
                print(f"  步骤 {step_num}/{self._max_steps}")

            # 调用 LLM
            response = self._call_llm(messages)
            content = response.choices[0].message.content or ""
            messages.append({"role": "assistant", "content": content})

            # 解析输出
            parsed = self._parse_output(content)

            if self._verbose and parsed.get("thought"):
                print(f"  💭 Thought: {parsed['thought']}")

            # 情况 1：Final Answer
            if parsed.get("final_answer"):
                answer = parsed["final_answer"]
                terminated_by = "final_answer"
                steps.append({
                    "step": step_num,
                    "thought": parsed.get("thought", ""),
                    "action": None,
                    "action_input": None,
                    "observation": None,
                })
                if self._verbose:
                    print(f"  ✅ Final Answer: {answer}")
                break

            # 情况 2：有 Action
            if parsed.get("action"):
                format_error_count = 0  # 重置格式错误计数
                action = parsed["action"]
                action_input = parsed.get("action_input", {})

                if self._verbose:
                    print(f"  🔧 Action: {action}")
                    print(f"  📥 Input: {json.dumps(action_input, ensure_ascii=False)}")

                # 执行工具
                observation = execute_tool(action, action_input)

                if self._verbose:
                    obs_display = observation[:150] + "..." if len(observation) > 150 else observation
                    print(f"  👁️ Observation: {obs_display}")

                # 把 Observation 注入对话
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

            # 情况 3：格式错误
            else:
                format_error_count += 1
                if self._verbose:
                    print(f"  ⚠️ 格式解析失败（第 {format_error_count} 次）")

                messages.append({
                    "role": "user",
                    "content": (
                        "格式错误：你的输出不符合要求的格式。请严格按照以下格式输出（不要用 markdown 加粗）：\n\n"
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
                    "action_input": {"raw": content[:200]},
                    "observation": "格式错误，已提示重试",
                })

                # 连续 2 次格式错误就放弃
                if format_error_count >= 2:
                    terminated_by = "parse_error"
                    answer = "推理过程遇到格式问题，无法完成回答。"
                    break

        if answer is None:
            answer = "达到最大推理步数仍未得出结论。"

        return {
            "answer": answer,
            "steps": steps,
            "total_steps": len(steps),
            "terminated_by": terminated_by,
        }

    def _build_system_prompt(self, reflections: list[str] | None) -> str:
        """
        构建 system prompt，含反思注入。

        Reflexion 论文的核心机制：
            把历次反思以自然语言形式拼接后追加到 system prompt 末尾。
            LLM 在推理第一步就能看到"之前哪里犯了错、为什么错、怎么改"。
        """
        base = SYSTEM_PROMPT_TEMPLATE.format(tool_descriptions=self._tool_desc)

        if reflections:
            # 每条反思编号，方便 LLM 区分
            numbered = []
            for i, r in enumerate(reflections, 1):
                numbered.append(f"教训 {i}：{r}")
            reflections_text = "\n\n".join(numbered)

            base += REFLECTION_INJECTION_TEMPLATE.format(reflections=reflections_text)

        return base

    def _call_llm(self, messages: list[dict]) -> object:
        """调用 OpenAI API（纯文本模式，不用 Function Calling）。"""
        return self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0,
        )

    def _parse_output(self, content: str) -> dict:
        """
        从 LLM 输出中解析 Thought / Action / Final Answer。

        返回：
            {
                "thought": str | None,
                "action": str | None,
                "action_input": dict | None,
                "final_answer": str | None,
            }
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

        # Final Answer 优先
        final_match = RE_FINAL_ANSWER.search(content)
        if final_match:
            result["final_answer"] = final_match.group(1).strip()
            return result

        # Action
        action_match = RE_ACTION.search(content)
        if action_match:
            result["action"] = action_match.group(1).strip()

        # Action Input
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


# ============================================================
# 快速验证
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("内层 ReAct 循环 · 快速验证")
    print("=" * 50)

    loop = ReactLoop(max_steps=8, verbose=True)

    # 测试无反思
    print("\n--- 无反思模式 ---")
    result = loop.run("深渊王国的统治者是谁？")
    print(f"\n答案：{result['answer']}")

    # 测试有反思
    print("\n\n--- 有反思模式 ---")
    reflections = [
        "上次我查询'深渊王国'的'国王'字段失败了，正确的字段名是'统治者'而非'国王'。"
    ]
    result = loop.run("深渊王国的统治者是谁？", reflections=reflections)
    print(f"\n答案：{result['answer']}")
