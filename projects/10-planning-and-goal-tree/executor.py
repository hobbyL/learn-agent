"""
内层 ReAct 执行器 —— 单个子任务的执行单元
=============================================

这是"Plan → Execute → Re-plan"双层结构中的 **Execute** 层。
给定一个 SubTask，用 LLM 通过 Function Calling（ReAct 内层循环）自主完成它。

与 08-long-term-memory/agent.py 的 loop 同源：
    循环调用 LLM → 处理 tool_calls → 追加 tool 消息 → 直到收尾。
关键差异：08 的收尾是"LLM 给出自然语言回答"，
    本执行器需要一个**明确、可靠的成功/失败信号**供外层规划器决策。

成功判定机制的选择 —— report_result 收尾工具（而非解析自然语言）：
    我们额外给 LLM 一个 report_result(success, reason) 工具，约定它必须调用它来收尾。
    理由：
        1. 可靠：success 是结构化 bool，外层无需用关键词/正则去猜 LLM 到底成没成，
           避免"我觉得完成了""看起来失败了"这类自然语言歧义。
        2. 与失败重规划契合：reason 字段直接就是给 replan LLM 的失败原因，
           格式统一、语义明确。
        3. 强制反思：调用 report_result 前，LLM 必须明确判断任务是否真的完成，
           呼应 prompt 里"不要假装成功"的约束。
    若 LLM 在收尾时没调 report_result 而是直接自然语言回复，我们兜底解析：
        回复里出现明确失败词则判失败，否则视为成功（附带原始回复）。
"""

import json

# report_result 收尾工具的 schema —— 追加到基础工具集之后，让 LLM 用它汇报结果。
REPORT_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "report_result",
        "description": (
            "汇报子任务的最终执行结果。完成或确定无法完成时，必须调用此工具收尾。"
            "success=true 表示任务成功达成目标；success=false 表示因某种原因无法完成。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "任务是否成功完成",
                },
                "reason": {
                    "type": "string",
                    "description": (
                        "成功时简述完成情况；失败时说明具体原因"
                        "（如资源不足/设备不可用/环境限制/前置未完成），供上层重规划参考"
                    ),
                },
            },
            "required": ["success", "reason"],
        },
    },
}


EXECUTOR_SYSTEM_PROMPT = """你是太空基地建设的执行单元，负责完成分配给你的**单个子任务**。

你可以使用以下工具操作基地：
- check_inventory()：查看当前资源库存、已完成模块、设备状态
- check_environment()：查看当前环境事件（舱外作业前务必确认）
- lookup(name, field)：查询模块的所需资源/前置依赖等信息
- mine_resource(resource, amount)：采集资源，增加库存
- build_module(module)：建造模块（会自动校验资源/前置/设备/环境）
- transport(item, destination)：运输物资
- report_result(success, reason)：**收尾工具**，汇报本子任务最终结果

执行原则：
1. 只专注完成当前分配的这一个子任务，不要越权去做其他子任务的事。
2. 建造/采集前，先用 check_inventory / check_environment / lookup 确认前提条件。
3. 工具返回以"失败："开头时，说明遇到了障碍。分析原因：
   - 如果是本子任务能自行解决的（如需要先采集一点资源），可以尝试。
   - 如果是根本性障碍（前置模块未建、设备不可用、环境禁止、资源缺口巨大需大量采集），
     不要硬撑，直接 report_result(success=false, reason=...) 如实汇报，交给上层重新规划。
4. **绝不假装成功**：只有工具真正返回"成功"、目标确实达成，才 report_result(success=true)。
5. 完成或确认无法完成后，必须调用 report_result 收尾，不要只用自然语言回复。
"""


def execute_subtask(
    subtask,
    client,
    model: str,
    max_steps: int = 8,
    verbose: bool = True,
) -> dict:
    """
    用内层 ReAct 循环执行单个子任务。

    LLM 拿到子任务描述 + 可用工具，自主决定调用哪些工具完成它，
    最后通过 report_result 汇报成功/失败。

    参数：
        subtask  — schemas.SubTask 对象（需有 id/name/description/target_module 属性）
        client   — OpenAI 客户端
        model    — 模型名
        max_steps— 内层最大工具调用步数（防止死循环）
        verbose  — 是否打印执行过程

    返回：
        {
            "success": bool,
            "subtask_id": str,
            "steps": [ {step, thought, action, action_input, observation} ],
            "final_message": str,      # LLM 的完成总结或失败说明
            "failure_reason": str|None,# 失败时的原因（供 re-planning）
        }
    """
    # 延迟 import，避免与 tools 的模块级副作用产生循环
    from tools import TOOLS_SCHEMA, execute_tool

    subtask_id = getattr(subtask, "id", "?")
    name = getattr(subtask, "name", "")
    description = getattr(subtask, "description", "")
    target_module = getattr(subtask, "target_module", "无")

    # 工具集 = 基础工具 + report_result 收尾工具
    tools = TOOLS_SCHEMA + [REPORT_TOOL_SCHEMA]

    user_prompt = (
        f"请完成以下子任务：\n"
        f"- 任务ID：{subtask_id}\n"
        f"- 名称：{name}\n"
        f"- 描述：{description}\n"
        f"- 关联模块/资源：{target_module}\n\n"
        f"请使用工具完成它，完成或确认无法完成后调用 report_result 汇报结果。"
    )

    messages = [
        {"role": "system", "content": EXECUTOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    steps: list[dict] = []
    result = {
        "success": False,
        "subtask_id": subtask_id,
        "steps": steps,
        "final_message": "",
        "failure_reason": None,
    }

    if verbose:
        print(f"    ┌─ 执行子任务 [{subtask_id}] {name}")

    for step_num in range(1, max_steps + 1):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        choice = resp.choices[0]
        msg = choice.message

        # LLM 请求工具调用
        if choice.finish_reason == "tool_calls" and msg.tool_calls:
            # 必须把含 tool_calls 的 assistant 消息整体加入历史
            messages.append(msg)

            # thought = LLM 在调用工具前给出的自然语言说明（可能为空）
            thought = (msg.content or "").strip()

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}

                # ── report_result：收尾信号，结束执行 ──
                if tool_name == "report_result":
                    success = bool(tool_args.get("success", False))
                    reason = str(tool_args.get("reason", "")).strip()

                    steps.append({
                        "step": step_num,
                        "thought": thought,
                        "action": "report_result",
                        "action_input": tool_args,
                        "observation": f"{'成功' if success else '失败'}：{reason}",
                    })

                    result["success"] = success
                    result["final_message"] = reason
                    result["failure_reason"] = None if success else (reason or "未说明原因")

                    if verbose:
                        flag = "✅ 成功" if success else "❌ 失败"
                        print(f"    └─ {flag}：{reason}")

                    # 需要给这个 tool_call 一个 tool 响应，保持消息完整性
                    # （即便随后就 return，也遵守 API 的 tool_call/tool 配对约定）
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": "已记录结果。",
                    })
                    return result

                # ── 普通工具：执行并把结果作为 Observation 追加 ──
                observation = execute_tool(tool_name, tool_args)

                if verbose:
                    arg_text = json.dumps(tool_args, ensure_ascii=False)
                    print(f"    │  step{step_num} 🔧 {tool_name}({arg_text})")
                    print(f"    │       👁 {observation}")

                steps.append({
                    "step": step_num,
                    "thought": thought,
                    "action": tool_name,
                    "action_input": tool_args,
                    "observation": observation,
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": observation,
                })

            # 继续循环，让 LLM 根据 Observation 决定下一步
            continue

        # LLM 没有调用工具，直接自然语言收尾（未按约定用 report_result）
        # 兜底解析：出现明确失败词判失败，否则视为成功。
        final_text = (msg.content or "").strip()
        steps.append({
            "step": step_num,
            "thought": final_text,
            "action": None,
            "action_input": None,
            "observation": None,
        })

        looks_failed = any(
            kw in final_text
            for kw in ("失败", "无法完成", "无法建造", "不足", "未能", "不可用")
        )
        result["success"] = not looks_failed
        result["final_message"] = final_text
        result["failure_reason"] = final_text if looks_failed else None

        if verbose:
            flag = "✅ 成功" if result["success"] else "❌ 失败"
            print(f"    └─ {flag}（自然语言收尾）：{final_text[:80]}")
        return result

    # 达到 max_steps 仍未收尾 → 视为失败，交给重规划
    result["success"] = False
    result["final_message"] = f"达到最大步数 {max_steps} 仍未完成"
    result["failure_reason"] = (
        f"执行超过 {max_steps} 步仍未通过 report_result 收尾，"
        f"可能子任务过于复杂或陷入反复尝试，建议拆解或调整。"
    )
    if verbose:
        print(f"    └─ ❌ 超过最大步数 {max_steps}，判为失败")
    return result


# ============================================================
# 快速验证（用 mock client + mock subtask，不调真实 API）
# ============================================================

if __name__ == "__main__":
    from knowledge_base import reset_base_state
    from tools import set_random_seed

    print("=== Executor 结构验证（mock LLM）===\n")

    reset_base_state()
    set_random_seed(42)

    class MockSubTask:
        id = "t_demo"
        name = "建造储物仓"
        description = "使用现有资源建造储物仓"
        target_module = "储物仓"
        estimated_steps = 2

    # Mock：第一轮请求 check_inventory，第二轮请求 build_module，第三轮 report_result 成功
    class MockToolCall:
        def __init__(self, call_id, fname, args):
            self.id = call_id
            self.function = type("F", (), {"name": fname, "arguments": json.dumps(args)})()

    class MockMessage:
        def __init__(self, content, tool_calls):
            self.content = content
            self.tool_calls = tool_calls
            self.role = "assistant"

    class MockChoice:
        def __init__(self, finish_reason, message):
            self.finish_reason = finish_reason
            self.message = message

    class MockResp:
        def __init__(self, choice):
            self.choices = [choice]

    class MockCompletions:
        def __init__(self):
            self._turn = 0

        def create(self, **kwargs):
            self._turn += 1
            if self._turn == 1:
                mc = MockMessage("先看看库存", [MockToolCall("c1", "check_inventory", {})])
                return MockResp(MockChoice("tool_calls", mc))
            if self._turn == 2:
                mc = MockMessage("资源够，建造储物仓", [MockToolCall("c2", "build_module", {"module": "储物仓"})])
                return MockResp(MockChoice("tool_calls", mc))
            mc = MockMessage("", [MockToolCall("c3", "report_result", {"success": True, "reason": "储物仓建造完成"})])
            return MockResp(MockChoice("tool_calls", mc))

    class MockClient:
        def __init__(self):
            self.chat = type("C", (), {"completions": MockCompletions()})()

    res = execute_subtask(MockSubTask(), MockClient(), "mock-model", max_steps=5, verbose=True)

    print(f"\n结果: success={res['success']}, steps={len(res['steps'])}")
    print(f"final_message: {res['final_message']}")
    print(f"failure_reason: {res['failure_reason']}")

    print("\nExecutor 结构验证通过 ✓")
