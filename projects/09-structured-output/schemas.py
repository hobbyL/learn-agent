"""
Pydantic Schema 定义 —— 4 层提取难度
======================================

定义结构化输出所需的 Pydantic BaseModel，对应 4 个提取难度层级：
1. 单实体提取（扁平）— DeveloperProfile
2. 多实体提取（列表）— TeamList
3. 嵌套关系提取（深层）— GameDetail
4. 对比分析提取（高级）— ComparisonReport

每个 Model 都可通过 model_json_schema() 导出 JSON Schema，
供 OpenAI json_schema 强制模式使用。

设计为可复用模块，后续项目可直接 import。
"""

from pydantic import BaseModel, Field


# ============================================================
# Level 1：单实体提取（扁平结构）
# ============================================================

class DeveloperProfile(BaseModel):
    """
    开发者档案 —— 扁平字段提取。

    提取目标：从知识库中提取指定开发者的结构化档案。
    """
    name: str = Field(description="开发者姓名")
    role: str = Field(description="职位角色，如'技术总监'、'主程序'")
    team: str = Field(description="所属项目组名称")
    skills: list[str] = Field(description="技能列表")
    experience_years: int = Field(description="工作经验年限")
    education: str = Field(description="教育背景")


# ============================================================
# Level 2：多实体提取（列表结构）
# ============================================================

class TeamSummary(BaseModel):
    """单个项目组的摘要信息。"""
    name: str = Field(description="项目组名称")
    lead: str = Field(description="负责人姓名")
    members_count: int = Field(description="成员人数")
    status: str = Field(description="项目状态，如'研发中'、'已发布'、'测试中'")
    direction: str = Field(description="项目方向")


class TeamList(BaseModel):
    """
    项目组列表 —— 多实体批量提取。

    提取目标：从知识库中提取所有项目组的摘要列表。
    """
    teams: list[TeamSummary] = Field(description="项目组摘要列表")


# ============================================================
# Level 3：嵌套关系提取（深层结构）
# ============================================================

class TeamInfo(BaseModel):
    """项目组嵌套信息。"""
    lead: str = Field(description="项目组负责人")
    members: list[str] = Field(description="核心成员姓名列表")


class MilestoneInfo(BaseModel):
    """里程碑信息。"""
    date: str = Field(description="日期，如 '2024-06'")
    event: str = Field(description="事件名称")
    achievement: str = Field(description="取得的成果")


class GameDetail(BaseModel):
    """
    游戏作品详情 —— 嵌套结构提取。

    提取目标：从知识库中提取指定游戏作品的完整嵌套信息，
    包含项目组信息、技术栈、里程碑等嵌套子对象。
    """
    name: str = Field(description="游戏名称")
    full_name: str = Field(description="游戏全称")
    genre: str = Field(description="游戏类别")
    team: TeamInfo = Field(description="项目组信息")
    tech_stack: list[str] = Field(description="使用的技术栈列表")
    milestones: list[MilestoneInfo] = Field(description="关键里程碑列表")
    platforms: list[str] = Field(description="目标平台列表")
    current_stage: str = Field(description="当前开发阶段")


# ============================================================
# Level 4：对比分析提取（高级结构）
# ============================================================

class ComparisonItem(BaseModel):
    """单个对比维度的结果。"""
    dimension: str = Field(description="对比维度名称")
    a_value: str = Field(description="A 方的值")
    b_value: str = Field(description="B 方的值")
    conclusion: str = Field(description="对比结论或分析")


class ComparisonReport(BaseModel):
    """
    对比分析报告 —— 高级结构化提取。

    提取目标：对比两个项目组/游戏作品，生成多维度的结构化对比报告。
    """
    subject_a: str = Field(description="对比主体 A 名称")
    subject_b: str = Field(description="对比主体 B 名称")
    dimensions: list[str] = Field(description="对比维度列表")
    comparison: list[ComparisonItem] = Field(description="各维度对比结果")
    summary: str = Field(description="总体结论")


# ============================================================
# Schema 注册表（供 extractor 使用）
# ============================================================

# 层级名称 → (Schema 类, 提取提示词, 描述)
SCHEMA_REGISTRY: dict[str, tuple[type[BaseModel], str, str]] = {
    "level1_developer": (
        DeveloperProfile,
        "从以下游戏工作室知识库中，提取开发者「林昊天」的完整档案信息。",
        "单实体提取（扁平）",
    ),
    "level2_teams": (
        TeamList,
        "从以下游戏工作室知识库中，提取所有项目组的摘要信息列表。",
        "多实体提取（列表）",
    ),
    "level3_game": (
        GameDetail,
        "从以下游戏工作室知识库中，提取游戏「破晓传说」的完整详情，包括项目组信息、技术栈和里程碑。",
        "嵌套关系提取（深层）",
    ),
    "level4_compare": (
        ComparisonReport,
        "从以下游戏工作室知识库中，对比「破晓组」和「深渊组」两个项目组，从团队规模、技术栈、项目状态、开发周期、成员经验等维度进行结构化对比分析。",
        "对比分析提取（高级）",
    ),
}

# 层级名称顺序（用于遍历）
LEVEL_ORDER = ["level1_developer", "level2_teams", "level3_game", "level4_compare"]

# 层级简称（展示用）
LEVEL_LABELS = {
    "level1_developer": "L1 单实体",
    "level2_teams":     "L2 多实体",
    "level3_game":      "L3 嵌套",
    "level4_compare":   "L4 对比",
}


# ============================================================
# 工具函数
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
    - 处理 $defs 中的嵌套定义
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
# 快速验证
# ============================================================

if __name__ == "__main__":
    import json

    print("=== Schema 模块快速验证 ===\n")

    for level_name in LEVEL_ORDER:
        model_class, prompt, desc = SCHEMA_REGISTRY[level_name]
        label = LEVEL_LABELS[level_name]
        schema = get_json_schema(model_class)

        print(f"■ {label} — {model_class.__name__}")
        print(f"  描述: {desc}")
        print(f"  提示: {prompt[:50]}...")
        print(f"  Schema name: {schema['name']}")
        print(f"  Schema keys: {list(schema['schema'].get('properties', {}).keys())}")
        print()

    # 详细展示 Level 3 的嵌套 schema
    print("─" * 50)
    print("Level 3 完整 JSON Schema（示例）:")
    print(json.dumps(get_json_schema(GameDetail), indent=2, ensure_ascii=False)[:500])
    print("...")

    print("\nSchema 模块验证通过 ✓")
