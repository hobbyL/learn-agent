"""
Pydantic Schema 定义 —— 目标树 DAG 的结构化描述
================================================

定义规划 Agent 所需的结构化输出 Schema，供 OpenAI json_schema 强制模式使用：

- SubTask       —— DAG 中的单个子任务节点（扁平列表 + depends_on 表达依赖）
- Plan          —— 完整建设计划（子任务 DAG）
- SubTaskExpansion —— 执行中判断是否需要动态展开子任务
- ReplanResult  —— 失败后的局部重规划结果

为什么用「扁平节点列表 + depends_on」而非嵌套树？
    OpenAI Structured Outputs 的 strict 模式有两个硬约束：
    1. 不支持可选字段（所有字段必填、不能有默认值语义）
    2. 递归/深层嵌套会让 $defs 迅速膨胀且难以表达"跨分支依赖"
    嵌套树只能表达"父子层级"，无法表达"t5 同时依赖 t2 和 t3"这类跨分支边。
    因此我们用扁平的 SubTask 列表，靠每个节点的 depends_on 字段还原完整 DAG。
    这也和 goal_tree.py 的 Kahn 拓扑排序天然契合。

get_json_schema() 和 _enforce_strict_schema() 直接复用 09-structured-output 的实现，
保持整个项目系列的一致性（strict 模式补丁逻辑完全相同）。
"""

from pydantic import BaseModel, Field


# ============================================================
# DAG 节点：SubTask
# ============================================================

class SubTask(BaseModel):
    """
    DAG 中的单个子任务节点。

    id + depends_on 共同构成有向无环图：
        depends_on 里的 id 全部 DONE 后，本节点才可执行（拓扑序约束）。
    target_module 让执行器知道这个子任务操作的是哪个模块/资源，
        无关联时填 '无'（strict 模式不允许省略字段，故用占位串而非 None）。
    """
    id: str = Field(description="子任务唯一标识，如 't1'、't2'")
    name: str = Field(description="子任务名称，简短动宾短语，如'采集钛矿×6'")
    description: str = Field(description="子任务详细描述，说明目标和成功标准")
    depends_on: list[str] = Field(description="前置依赖的子任务 id 列表，无依赖则为空列表")
    target_module: str = Field(description="关联的目标模块/资源名称，无则填'无'")
    estimated_steps: int = Field(description="预估执行步数（ReAct 内层循环轮数）")


# ============================================================
# 完整计划：Plan
# ============================================================

class Plan(BaseModel):
    """
    完整的建设计划（子任务 DAG）。

    reasoning 字段强制 LLM 先解释"为什么这样拆解和排序"，
    这既有助于调试规划质量，也让 LLM 在生成 subtasks 前先想清楚依赖关系
    （链式思维前置，减少 depends_on 写错的概率）。
    """
    goal: str = Field(description="高层建设目标")
    reasoning: str = Field(description="规划思路：为什么这样拆解和排序")
    subtasks: list[SubTask] = Field(description="子任务节点列表，构成 DAG")


# ============================================================
# 动态展开：SubTaskExpansion
# ============================================================

class SubTaskExpansion(BaseModel):
    """
    执行某子任务前，LLM 判断是否需要将其进一步拆解为更细的子任务。

    对应"混合规划"中的"执行中动态调整"：初始计划可能把某步拆得太粗，
    执行器发现它其实包含多个独立步骤时，可请求展开成新的子任务插入 DAG。
    needs_expansion=False 时 new_subtasks 应为空列表。
    """
    needs_expansion: bool = Field(description="是否需要将当前子任务拆解为更细的子任务")
    reason: str = Field(description="判断理由")
    new_subtasks: list[SubTask] = Field(description="若需展开，给出新的子任务列表；否则空列表")


# ============================================================
# 局部重规划：ReplanResult
# ============================================================

class ReplanResult(BaseModel):
    """
    局部重规划结果 —— 子任务失败后，只重规划受影响的子树。

    affected_task_ids：本次失败会波及、需要作废重做的子任务 id（含失败任务自身及其下游）。
    replacement_subtasks：用来替换这些受影响任务的新子任务列表。
    未列入 affected 的已完成任务保持不动，实现"局部"而非"全局"重规划。
    """
    analysis: str = Field(description="失败原因分析")
    affected_task_ids: list[str] = Field(description="受失败影响、需要重规划的子任务 id 列表")
    replacement_subtasks: list[SubTask] = Field(description="用于替换受影响子任务的新子任务列表")


# ============================================================
# 工具函数（复用自 09-structured-output）
# ============================================================

def get_json_schema(model_class: type[BaseModel]) -> dict:
    """
    从 Pydantic Model 生成 OpenAI json_schema 模式所需的完整 schema 字典。

    返回格式符合 OpenAI API response_format.json_schema 的要求：
    {
        "name": "ModelName",
        "strict": True,
        "schema": { ... JSON Schema ... }
    }
    """
    schema = model_class.model_json_schema()

    # OpenAI Structured Outputs 要求：
    # 1. additionalProperties: false（在所有 object 层级）
    # 2. 所有属性必须在 required 中
    _enforce_strict_schema(schema)

    return {
        "name": model_class.__name__,
        "strict": True,
        "schema": schema,
    }


def _enforce_strict_schema(schema: dict) -> None:
    """
    递归修改 JSON Schema 以满足 OpenAI strict 模式要求：
    - 所有 object 类型添加 "additionalProperties": false
    - 所有 properties 中的 key 都加入 required
    - 处理 $defs 中的嵌套定义（如 Plan 里嵌套的 SubTask）
    """
    # 处理顶层 $defs（Pydantic v2 生成的子模型定义）
    if "$defs" in schema:
        for def_schema in schema["$defs"].values():
            _enforce_strict_schema(def_schema)

    # 处理当前层级
    if schema.get("type") == "object" and "properties" in schema:
        schema["additionalProperties"] = False
        # 确保所有属性都在 required 中
        schema["required"] = list(schema["properties"].keys())
        # 递归处理子属性
        for prop_schema in schema["properties"].values():
            _enforce_strict_schema(prop_schema)

    # 处理 array 的 items
    if schema.get("type") == "array" and "items" in schema:
        _enforce_strict_schema(schema["items"])

    # 处理 $ref（不需要额外处理，$defs 已经递归了）


# ============================================================
# Schema 注册表（供 planner 使用）
# ============================================================
# 规划器根据不同阶段取用不同 schema：初始规划用 Plan，动态展开用 SubTaskExpansion，
# 失败重规划用 ReplanResult。集中登记方便后续批次统一引用。
SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {
    "plan": Plan,
    "expansion": SubTaskExpansion,
    "replan": ReplanResult,
}


# ============================================================
# 快速验证
# ============================================================

if __name__ == "__main__":
    import json

    print("=== Schema 模块快速验证 ===\n")

    for key, model_class in SCHEMA_REGISTRY.items():
        schema = get_json_schema(model_class)
        props = list(schema["schema"].get("properties", {}).keys())
        defs = list(schema["schema"].get("$defs", {}).keys())
        print(f"■ {key} — {model_class.__name__}")
        print(f"  顶层字段: {props}")
        print(f"  $defs: {defs if defs else '（无）'}")
        print(f"  strict: {schema['strict']}")
        print()

    # 详细展示 Plan 的完整 JSON Schema（含嵌套 SubTask）
    print("─" * 50)
    print("Plan 完整 JSON Schema（示例，前 700 字）:")
    print(json.dumps(get_json_schema(Plan), indent=2, ensure_ascii=False)[:700])
    print("...")

    print("\nSchema 模块验证通过 ✓")
