"""
规划器 —— 生成 / 重规划 / 动态展开目标树（DAG）
=================================================

这是"Plan → Execute → Re-plan"双层结构中的 **Plan** 层。
用 LLM + json_schema 强制模式产出结构化计划，保证输出 100% 可解析为 Pydantic 对象。

三个规划动作：
    generate_plan   —— 初始全计划：把高层目标拆成有依赖的子任务 DAG
    replan_subtree  —— 局部重规划：某子任务失败后，只重规划受影响子树
    expand_subtask  —— 动态展开：执行后判断某子任务是否需要进一步细化

API 调用方式对齐 09-structured-output/extractor.py 的 json_schema 强制模式：
    response_format={"type": "json_schema", "json_schema": get_json_schema(Model)}
    OpenAI 保证输出符合 schema，无需重试；仍处理 refusal 与意外解析失败。

为什么规划全部走 json_schema 强制模式而非自由文本？
    目标树的 depends_on / id 引用必须精确，自由文本极易产生格式漂移
    （漏字段、id 写错、依赖写成名称而非 id）。强制模式把结构约束交给 API，
    我们只需在 prompt 里讲清"依赖语义"，让 LLM 专注于"怎么拆"而非"格式对不对"。
"""

import json

from openai import BadRequestError
from pydantic import ValidationError

from knowledge_base import get_base_state, get_full_knowledge_text
from schemas import Plan, ReplanResult, SubTaskExpansion, get_json_schema


# ============================================================
# 通用：json_schema 强制模式调用
# ============================================================

def _call_structured(
    client,
    model: str,
    schema_class,
    system_prompt: str,
    user_prompt: str,
):
    """
    以 json_schema 强制模式调用 LLM，返回 (result, error)。

    result 为对应 schema_class 的 Pydantic 实例；出错时 result=None、error 为原因串。
    对齐 09 extractor 的处理：捕获 BadRequestError、refusal、意外解析失败。
    """
    json_schema = get_json_schema(schema_class)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_schema", "json_schema": json_schema},
        )
    except BadRequestError as e:
        return None, f"API 请求失败：{e}"

    msg = resp.choices[0].message

    # 模型拒绝返回结构化输出
    if getattr(msg, "refusal", None):
        return None, f"模型拒绝：{msg.refusal}"

    raw = msg.content or ""
    try:
        data = json.loads(raw)
        result = schema_class.model_validate(data)
        return result, None
    except (json.JSONDecodeError, ValidationError) as e:
        # 强制模式下理论不该走到这里，保险处理
        return None, f"解析失败（意外）：{e}"


# ============================================================
# 1. 初始规划：generate_plan
# ============================================================

_PLAN_SYSTEM_PROMPT = """你是新曙光太空基地的总规划师。你的任务是把一个高层建设目标，
拆解成一份结构化的子任务 DAG（有向无环图），供执行团队按依赖顺序施工。

拆解规则（务必遵守）：
1. 每个子任务是一个可独立执行的最小动作，主要是两类：
   - 采集资源：如"采集钛矿×6"（对应工具 mine_resource）
   - 建造模块：如"建造居住舱"（对应工具 build_module）
   必要时可包含"运输""环境确认"等辅助子任务。
2. 依赖用 depends_on 表达（存的是**前置子任务的 id**，不是名称）：
   - 建造某模块前，必须先有采集其所需资源的子任务，并 depends_on 它们。
   - 模块有前置模块的（如实验室依赖居住舱+太阳能阵列），建造该模块的子任务
     必须 depends_on 建造其前置模块的子任务。
3. id 用 t1、t2、t3… 顺序编号，全局唯一。
4. target_module 填该子任务操作的模块或资源名；无关联填"无"。
5. estimated_steps 给出预估的执行步数（1~5 的小整数即可）。
6. 充分利用知识库信息：模块的所需资源/所需设备/前置模块都已给出，据此设计依赖。
7. 注意当前库存：若现有库存已够，可不必再安排采集子任务；库存不足的才安排采集。

reasoning 字段先写清楚你的拆解思路（依赖关系、排序理由），再给出 subtasks。"""


def generate_plan(goal: str, client, model: str, verbose: bool = True) -> Plan:
    """
    生成初始建设计划（子任务 DAG）。

    给 LLM 提供：高层目标 + 基地知识库全文 + 当前库存快照，
    要求用 json_schema 强制模式产出结构化 Plan。

    参数：
        goal   — 高层建设目标（如"建造载人空间站 Phase-1"）
        client — OpenAI 客户端
        model  — 模型名
        verbose— 是否打印

    返回：
        schemas.Plan 对象。若 LLM 调用失败，抛出 RuntimeError（外层决定如何处理）。
    """
    knowledge = get_full_knowledge_text()
    inventory = _format_inventory(get_base_state())

    user_prompt = (
        f"【高层建设目标】\n{goal}\n\n"
        f"【当前基地状态】\n{inventory}\n\n"
        f"【知识库】\n{knowledge}\n\n"
        f"请把上述目标拆解为子任务 DAG，合理设置 depends_on 形成依赖关系。"
    )

    if verbose:
        print(f"  🧭 规划中：{goal}")

    plan, error = _call_structured(
        client, model, Plan, _PLAN_SYSTEM_PROMPT, user_prompt
    )
    if plan is None:
        raise RuntimeError(f"初始规划失败：{error}")

    if verbose:
        print(f"  ✓ 生成 {len(plan.subtasks)} 个子任务")

    return plan


# ============================================================
# 2. 局部重规划：replan_subtree
# ============================================================

_REPLAN_SYSTEM_PROMPT = """你是新曙光太空基地的应急规划师。某个子任务执行失败了，
你要做**局部重规划**：只重新规划受这次失败影响的部分，已成功完成的任务保持不动。

你会拿到：原目标、当前目标树状态（各子任务的完成情况）、失败的子任务、失败原因、知识库。

重规划规则：
1. 先分析失败根因（analysis 字段）。常见根因与对策：
   - 资源不足 → 替换方案里必须**先插入采集资源的子任务**，再让建造子任务 depends_on 它们。
   - 前置模块未完成 → 先插入建造前置模块的子任务。
   - 设备不可用 → 插入修复/等待类子任务（若知识库支持），或说明需等待。
   - 环境事件禁止作业 → 插入"等待环境恢复/确认环境"子任务，或调整执行顺序。
2. affected_task_ids：列出因这次失败需要作废重做的子任务 id
   —— 至少包含失败任务自身；若有下游任务强依赖它的产物，也一并列入。
   已经成功完成、与失败无关的任务**不要**列入。
3. replacement_subtasks：用于替换受影响任务的新子任务列表。
   - 新子任务 id 用 r1、r2、r3… 编号，避免与现有 id 冲突。
   - 新子任务之间用 depends_on 表达先后（如先采集 r1，再建造 r2 依赖 r1）。
   - 替换方案要能真正绕过失败原因（这是重规划的意义）。
4. 不要重复已完成的工作：如果某资源已采集充足、某前置模块已建好，不要再安排。"""


def replan_subtree(
    goal: str,
    goal_tree,
    failed_task,
    failure_reason: str,
    client,
    model: str,
    verbose: bool = True,
) -> ReplanResult:
    """
    局部重规划：某子任务失败后，重新规划受影响的子树。

    参数：
        goal          — 原高层目标
        goal_tree     — GoalTree 对象（用 to_display_rows/get_progress 编码当前状态）
        failed_task   — 失败的 TaskNode（需有 id/name/description/target_module）
        failure_reason— 失败原因（来自 executor 的 failure_reason）
        client/model  — LLM 配置
        verbose       — 是否打印

    返回：
        schemas.ReplanResult 对象。LLM 调用失败时抛出 RuntimeError。
    """
    knowledge = get_full_knowledge_text()
    tree_state = _format_tree_state(goal_tree)
    inventory = _format_inventory(get_base_state())

    failed_id = getattr(failed_task, "id", "?")
    failed_name = getattr(failed_task, "name", "")
    failed_desc = getattr(failed_task, "description", "")

    user_prompt = (
        f"【原建设目标】\n{goal}\n\n"
        f"【当前目标树状态】\n{tree_state}\n\n"
        f"【当前基地状态】\n{inventory}\n\n"
        f"【失败的子任务】\n"
        f"- id：{failed_id}\n"
        f"- 名称：{failed_name}\n"
        f"- 描述：{failed_desc}\n"
        f"- 失败原因：{failure_reason}\n\n"
        f"【知识库】\n{knowledge}\n\n"
        f"请分析失败根因，给出受影响的子任务 id 列表和能绕过失败的替换子任务。"
    )

    if verbose:
        print(f"  🔧 局部重规划：因 [{failed_id}] {failed_name} 失败")

    result, error = _call_structured(
        client, model, ReplanResult, _REPLAN_SYSTEM_PROMPT, user_prompt
    )
    if result is None:
        raise RuntimeError(f"局部重规划失败：{error}")

    if verbose:
        print(
            f"  ✓ 受影响 {len(result.affected_task_ids)} 个，"
            f"替换为 {len(result.replacement_subtasks)} 个新子任务"
        )

    return result


# ============================================================
# 3. 动态展开：expand_subtask
# ============================================================

_EXPAND_SYSTEM_PROMPT = """你是太空基地建设的复盘助手。一个子任务刚刚执行完成，
你要判断：这个子任务是否**过于笼统**，需要拆解为更细的子任务插入目标树？

这是"混合规划"的动态调整部分。判断准则（务必保守）：
1. 多数情况 needs_expansion=false —— 子任务通常已足够原子，不需要拆。
2. 仅当子任务在执行中明显暴露出"其实包含多个独立步骤、当前这步没真正覆盖全部"时，
   才 needs_expansion=true。
3. 若 needs_expansion=true：
   - new_subtasks 给出更细的子任务，id 用 e1、e2… 编号。
   - 新子任务之间用 depends_on 表达先后。
   - 不要把已经做过的工作再拆一遍。
4. needs_expansion=false 时，new_subtasks 必须为空列表，reason 简述"无需展开"的理由。"""


def expand_subtask(
    subtask,
    execution_result: dict,
    client,
    model: str,
    verbose: bool = True,
) -> SubTaskExpansion:
    """
    动态展开判断：子任务执行后，LLM 判断是否需要将其拆解为更细子任务。

    参数：
        subtask         — 刚执行完的 TaskNode/SubTask（需有 id/name/description）
        execution_result— executor.execute_subtask 的返回 dict（取 final_message 作上下文）
        client/model    — LLM 配置
        verbose         — 是否打印

    返回：
        schemas.SubTaskExpansion 对象。LLM 调用失败时返回"无需展开"的兜底结果
        （展开是可选优化，失败不应中断主流程）。
    """
    task_id = getattr(subtask, "id", "?")
    name = getattr(subtask, "name", "")
    description = getattr(subtask, "description", "")
    final_message = execution_result.get("final_message", "")

    user_prompt = (
        f"【刚完成的子任务】\n"
        f"- id：{task_id}\n"
        f"- 名称：{name}\n"
        f"- 描述：{description}\n"
        f"- 执行总结：{final_message}\n\n"
        f"请判断这个子任务是否需要进一步拆解为更细的子任务。多数情况下不需要。"
    )

    result, error = _call_structured(
        client, model, SubTaskExpansion, _EXPAND_SYSTEM_PROMPT, user_prompt
    )
    if result is None:
        # 展开判断是可选优化，失败就当作"无需展开"，不打断主流程
        if verbose:
            print(f"  （展开判断失败，默认不展开：{error}）")
        return SubTaskExpansion(
            needs_expansion=False,
            reason=f"展开判断调用失败，默认不展开：{error}",
            new_subtasks=[],
        )

    if verbose and result.needs_expansion:
        print(f"  ↳ 动态展开 [{task_id}] → {len(result.new_subtasks)} 个子任务")

    return result


# ============================================================
# 状态编码辅助（把运行时状态转成 LLM 可读文本）
# ============================================================

def _format_inventory(state: dict) -> str:
    """把基地当前状态编码成紧凑文本，供规划 prompt 注入。"""
    inv = state.get("资源库存", {})
    inv_text = "、".join(f"{k}×{v}" for k, v in inv.items())
    done = state.get("已完成模块", [])
    done_text = "、".join(done) if done else "（暂无）"
    event = state.get("当前环境事件") or "正常"
    return (
        f"资源库存：{inv_text}\n"
        f"已完成模块：{done_text}\n"
        f"当前环境事件：{event}"
    )


def _format_tree_state(goal_tree) -> str:
    """
    把目标树当前状态编码成文本，供重规划 prompt 注入。

    这是"局部重规划"的关键——LLM 必须看清哪些任务已完成/失败/待办，
    才能正确判断影响范围、避免重做已完成的工作。
    用 GoalTree.to_display_rows() 拿到按拓扑序排列的行数据。
    """
    rows = goal_tree.to_display_rows()
    lines = []
    for r in rows:
        deps = "、".join(r["depends_on"]) if r["depends_on"] else "无"
        lines.append(
            f"- [{r['status']}] {r['id']} {r['name']} "
            f"(依赖：{deps}，模块：{r['target_module']})"
        )
    progress = goal_tree.get_progress()
    header = (
        f"进度：完成 {progress['done']}/{progress['total']}，"
        f"失败 {progress['failed']}，待办 {progress['pending']}，"
        f"跳过 {progress['skipped']}"
    )
    return header + "\n" + "\n".join(lines)


# ============================================================
# 快速验证（不调真实 API，仅验证 prompt 构造与状态编码）
# ============================================================

if __name__ == "__main__":
    from knowledge_base import reset_base_state

    print("=== Planner 状态编码验证（不调 LLM）===\n")

    reset_base_state()
    state = get_base_state()

    print("▸ _format_inventory():")
    print(_format_inventory(state))

    print("\n▸ 构造一个 mock GoalTree 验证 _format_tree_state():")
    from goal_tree import GoalTree, TaskStatus
    from dataclasses import dataclass

    @dataclass
    class MockSubTask:
        id: str
        name: str
        description: str
        depends_on: list
        target_module: str
        estimated_steps: int

    subtasks = [
        MockSubTask("t1", "采集钛矿×6", "从矿区采集", [], "钛矿", 2),
        MockSubTask("t2", "建造居住舱", "组装居住舱", ["t1"], "居住舱", 3),
    ]

    class MockPlan:
        goal = "建造居住舱"
        subtasks = subtasks

    tree = GoalTree(MockPlan())
    tree.mark_status("t1", TaskStatus.DONE)
    tree.mark_status("t2", TaskStatus.FAILED)

    print(_format_tree_state(tree))

    print("\nPlanner 状态编码验证通过 ✓")
