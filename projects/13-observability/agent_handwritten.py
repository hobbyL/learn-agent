"""
agent_handwritten.py —— 手写 ReAct Agent（接入 wrap_openai + custom_tracer）
==========================================================================

从项目 03 的 react_agent.py 复用核心 ReAct 循环，增加两层可观测性：

1. wrap_openai：包装 OpenAI client，LangSmith 开启时自动追踪 LLM 调用
2. custom_tracer：在循环关键位置手动调用 on_* 方法，记录到本地 JSON/终端

设计要点：
- wrap_openai 在 LangSmith 未开启时和原 client 行为完全一致（no-op）
- custom_tracer 是可选参数，不传时不影响功能
- 两者独立工作，可以同时开启
"""

import json
import os
import re
import time

from openai import OpenAI
from dotenv import load_dotenv

try:
    from langsmith.wrappers import wrap_openai
except ImportError:
    # langsmith 未安装时 wrap_openai 是 identity 函数
    def wrap_openai(client):
        return client

from tools import execute_tool, get_tool_descriptions
from custom_tracer import AgentTracer

load_dotenv()


# ============================================================
# 解析正则（和 03 一致）
# ============================================================

RE_THOUGHT = re.compile(
    r"\*{0,2}Thought:?\*{0,2}\s*(.+?)(?=\n\*{0,2}(?:Action|Final Answer):?\*{0,2}|$)",
    re.DOTALL,
)
RE_ACTION = re.compile(r"\*{0,2}Action:?\*{0,2}\s*(\w+)")
RE_ACTION_INPUT = re.compile(r"\*{0,2}Action Input:?\*{0,2}\s*(\{.*?\})", re.DOTALL)
RE_FINAL_ANSWER = re.compile(r"\*{0,2}Final Answer:?\*{0,2}\s*(.+)", re.DOTALL)

_UNFINISHED_PLAN_PATTERNS = [
    "接下来", "还需要", "再查", "再查询", "需要再", "然后查", "然后再",
    "继续查", "分别查询", "查询每个", "查完", "再计算", "然后计算",
]


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

- 绝对禁止编造数据：如果你需要某个数值但还没有通过工具获取到，你必须先调用工具获取，绝不能猜测或编造
- Final Answer 中的每一个数据点都必须有对应的 Observation 来源
- "计划查询"不等于"已经查询"：在 Thought 中说"接下来要查 X"之后，你必须真的执行 Action 去查
- 涉及计算的问题，必须使用 calculate 工具得出结果，不要心算
"""


class HandwrittenAgent:
    """
    手写 ReAct Agent，接入 wrap_openai + custom_tracer。

    和 03 ReactAgent 的区别：
    - client 用 wrap_openai 包装（LangSmith 可用时自动追踪）
    - run() 接受可选 tracer 参数，在关键位置手动调用 on_* 方法
    """

    def __init__(self, max_steps: int = 10, verbose: bool = True):
        # wrap_openai 包装 client（LangSmith 未开启时是 no-op）
        raw_client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            base_url=os.environ.get("OPENAI_BASE_URL") or None,
        )
        self._client = wrap_openai(raw_client)
        self._model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._max_steps = max_steps
        self._verbose = verbose

        tool_desc = get_tool_descriptions()
        self._system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            tool_descriptions=tool_desc
        )

    def run(self, question: str, tracer: AgentTracer | None = None) -> dict:
        """
        运行 ReAct 循环回答问题。

        参数：
            question: 用户问题
            tracer: 可选的自定义 tracer，传入时在关键位置记录 span

        返回：
            {
                "answer": str,
                "steps": [...],
                "total_steps": int,
                "terminated_by": str,
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
            # ── tracer: LLM 调用开始 ──
            prompt_summary = f"step {step_num}, messages={len(messages)}"
            if tracer:
                tracer.on_llm_start(prompt_summary, self._model)

            # 调用 LLM
            t0 = time.time()
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0,
            )
            duration_ms = (time.time() - t0) * 1000
            content = response.choices[0].message.content or ""
            tokens = getattr(response.usage, "total_tokens", 0) if response.usage else 0

            # ── tracer: LLM 调用结束 ──
            if tracer:
                tracer.on_llm_end(content[:200], tokens=tokens, duration_ms=duration_ms)

            messages.append({"role": "assistant", "content": content})

            # 解析输出
            parsed = self._parse_output(content)
            thought = parsed.get("thought", "")

            # ── tracer: Agent 步骤 ──
            action_name = parsed.get("action")
            if parsed.get("final_answer"):
                action_name = "Final Answer"
            if tracer:
                tracer.on_agent_step(step_num, thought or "", action_name)

            # 情况 1：Final Answer
            if parsed.get("final_answer"):
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
                        "step": step_num, "thought": thought,
                        "action": "_unfinished_plan_rejected",
                        "action_input": {"unfinished_keywords": unfinished},
                        "observation": f"答案被拒绝：计划未完成（{hint}）",
                    })
                    continue

                answer = parsed["final_answer"]
                terminated_by = "final_answer"
                steps.append({
                    "step": step_num, "thought": thought,
                    "action": None, "action_input": None, "observation": None,
                })
                break

            # 情况 2：Action
            if parsed.get("action"):
                action = parsed["action"]
                action_input = parsed.get("action_input", {})

                # ── tracer: 工具调用开始 ──
                if tracer:
                    tracer.on_tool_start(action, action_input)

                t0 = time.time()
                observation = execute_tool(action, action_input)
                tool_duration_ms = (time.time() - t0) * 1000

                # ── tracer: 工具调用结束 ──
                if tracer:
                    tracer.on_tool_end(action, observation, duration_ms=tool_duration_ms)

                messages.append({
                    "role": "user",
                    "content": f"Observation: {observation}",
                })

                steps.append({
                    "step": step_num, "thought": thought,
                    "action": action, "action_input": action_input,
                    "observation": observation,
                })

            # 情况 3：解析失败
            else:
                messages.append({
                    "role": "user",
                    "content": (
                        "格式错误：你的输出不符合要求的格式。请严格按照以下格式输出：\n\n"
                        "Thought: <你的思考>\nAction: <工具名>\n"
                        'Action Input: {"参数": "值"}\n\n'
                        "或者如果你已经有足够信息：\n\n"
                        "Thought: <总结>\nFinal Answer: <最终答案>"
                    ),
                })
                steps.append({
                    "step": step_num, "thought": thought,
                    "action": "_format_error",
                    "action_input": {"raw_output": content[:200]},
                    "observation": "格式错误，已提示重试",
                })
                recent_errors = sum(
                    1 for s in steps[-3:] if s.get("action") == "_format_error"
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

    def _parse_output(self, content: str) -> dict:
        """从 LLM 输出文本中解析 Thought / Action / Final Answer。"""
        result = {
            "thought": None, "action": None,
            "action_input": None, "final_answer": None,
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


# ============================================================
# 便捷运行函数（供 eval_runner / main.py 调用）
# ============================================================

def run_handwritten(question: str, tracer: AgentTracer | None = None) -> str:
    """
    运行手写 Agent 并返回答案字符串。

    参数：
        question: 用户问题
        tracer: 可选的自定义 tracer

    返回：
        答案文本
    """
    agent = HandwrittenAgent(max_steps=10, verbose=False)
    result = agent.run(question, tracer=tracer)
    return result["answer"]
