"""
工具层 —— 连接知识库与 StructuredAgent
========================================

提供 2 个工具供 Agent 调用：
- search_entities(query)       在游戏工作室知识库中模糊搜索实体
- lookup_entity(entity, field)  精确查询实体某一属性

TOOLS_SCHEMA 是 OpenAI Function Calling 所需的 JSON Schema 格式工具描述。
"""

from knowledge_base import search_entities, lookup_entity


# ============================================================
# OpenAI Function Calling Schema
# ============================================================

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_entities",
            "description": "在游戏工作室知识库中搜索实体（工作室、项目组、游戏作品、开发者、技术栈、里程碑等）。返回摘要列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，如开发者姓名、项目组名、游戏名、技术栈等",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_entity",
            "description": "精确查询某个实体的某个属性值。需要提供完整实体名和字段名。",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {
                        "type": "string",
                        "description": "实体名称，如'林昊天'、'破晓组'、'破晓传说'",
                    },
                    "field": {
                        "type": "string",
                        "description": "要查询的字段名，如'角色'、'技能'、'负责人'、'核心成员'等。传空字符串返回全部属性。",
                    },
                },
                "required": ["entity", "field"],
            },
        },
    },
]


# ============================================================
# 工具执行分发
# ============================================================

_TOOL_MAP = {
    "search_entities": search_entities,
    "lookup_entity":   lookup_entity,
}


def execute_tool(tool_name: str, args: dict) -> str:
    """
    统一工具执行入口。
    根据工具名找到对应函数，传入参数并返回结果字符串。
    """
    func = _TOOL_MAP.get(tool_name)
    if func is None:
        available = ", ".join(_TOOL_MAP.keys())
        return f"错误：未知工具 '{tool_name}'。可用工具：{available}"

    try:
        result = func(**args)
        # search_entities 返回 list[dict]，需要格式化为字符串
        if tool_name == "search_entities":
            if not result:
                return "未找到相关实体。"
            if len(result) == 1 and "error" in result[0]:
                return result[0]["error"]
            lines = [f"找到 {len(result)} 个相关结果："]
            for r in result:
                lines.append(f"  - {r['名称']}（{r['类型']}）：{r['摘要']}")
            return "\n".join(lines)
        # lookup_entity 直接返回字符串
        return result
    except TypeError as e:
        return f"错误：参数不匹配。工具 '{tool_name}' 参数问题：{e}"


# ============================================================
# 快速验证
# ============================================================

if __name__ == "__main__":
    print("=== 工具层快速验证 ===\n")

    print("search_entities('破晓'):")
    print(execute_tool("search_entities", {"query": "破晓"}))

    print("\nlookup_entity('林昊天', '技能'):")
    print(execute_tool("lookup_entity", {"entity": "林昊天", "field": "技能"}))

    print("\nlookup_entity('破晓组', '核心成员'):")
    print(execute_tool("lookup_entity", {"entity": "破晓组", "field": "核心成员"}))

    print("\n工具层验证通过 ✓")
