"""
工具定义：共享工具 + 专属工具
==============================

共享工具（所有 Agent 可用）：
- search_planets(query)
- lookup_planet(planet, field)

专属工具（每角色独有）：
- 科学官：analyze_habitability(planet)
- 军事官：assess_defense(planet)
- 经济官：evaluate_economics(planet)
"""

from knowledge_base import (
    search_planets,
    lookup_planet,
    get_planet_fields,
    analyze_habitability,
    assess_defense,
    evaluate_economics,
)


# ============================================================
# OpenAI Function Calling Schema 定义
# ============================================================

# --- 共享工具 ---

TOOL_SEARCH_PLANETS = {
    "type": "function",
    "function": {
        "name": "search_planets",
        "description": "搜索候选星球信息。输入关键词，返回匹配的星球摘要列表。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，如 '海洋'、'资源'、'防御'",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

TOOL_LOOKUP_PLANET = {
    "type": "function",
    "function": {
        "name": "lookup_planet",
        "description": (
            "精确查询某星球的某个属性。"
            "可查字段：环境、温度范围、重力、大气成分、殖民状态、"
            "生态系统、科研价值、宜居指数、特殊发现、"
            "防御地形、战略位置、已知威胁、防御评分、"
            "主要资源、资源总估值、开采难度、基础设施、投资回报周期、经济评分"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "planet": {
                    "type": "string",
                    "description": "星球名称：蓝晶星 / 赤焰星 / 翡翠星",
                },
                "field": {
                    "type": "string",
                    "description": "要查询的字段名",
                },
            },
            "required": ["planet", "field"],
            "additionalProperties": False,
        },
    },
}

SHARED_TOOLS = [TOOL_SEARCH_PLANETS, TOOL_LOOKUP_PLANET]

# --- 专属工具 ---

TOOL_ANALYZE_HABITABILITY = {
    "type": "function",
    "function": {
        "name": "analyze_habitability",
        "description": "【科学官专属】综合分析星球宜居性，输出大气、温度、重力、生态系统、科研价值等评估报告。",
        "parameters": {
            "type": "object",
            "properties": {
                "planet": {
                    "type": "string",
                    "description": "星球名称：蓝晶星 / 赤焰星 / 翡翠星",
                },
            },
            "required": ["planet"],
            "additionalProperties": False,
        },
    },
}

TOOL_ASSESS_DEFENSE = {
    "type": "function",
    "function": {
        "name": "assess_defense",
        "description": "【军事官专属】综合分析星球防御态势，输出地形、战略位置、威胁评估报告。",
        "parameters": {
            "type": "object",
            "properties": {
                "planet": {
                    "type": "string",
                    "description": "星球名称：蓝晶星 / 赤焰星 / 翡翠星",
                },
            },
            "required": ["planet"],
            "additionalProperties": False,
        },
    },
}

TOOL_EVALUATE_ECONOMICS = {
    "type": "function",
    "function": {
        "name": "evaluate_economics",
        "description": "【经济官专属】综合分析星球经济价值，输出资源、估值、开采难度、投资回报评估报告。",
        "parameters": {
            "type": "object",
            "properties": {
                "planet": {
                    "type": "string",
                    "description": "星球名称：蓝晶星 / 赤焰星 / 翡翠星",
                },
            },
            "required": ["planet"],
            "additionalProperties": False,
        },
    },
}


# ============================================================
# 角色 → 工具映射
# ============================================================

ROLE_TOOLS = {
    "科学官": SHARED_TOOLS + [TOOL_ANALYZE_HABITABILITY],
    "军事官": SHARED_TOOLS + [TOOL_ASSESS_DEFENSE],
    "经济官": SHARED_TOOLS + [TOOL_EVALUATE_ECONOMICS],
}


# ============================================================
# 工具执行分发
# ============================================================

TOOL_HANDLERS = {
    "search_planets": lambda args: _format(search_planets(args["query"])),
    "lookup_planet": lambda args: lookup_planet(args["planet"], args["field"]) or "未找到该字段",
    "analyze_habitability": lambda args: analyze_habitability(args["planet"]),
    "assess_defense": lambda args: assess_defense(args["planet"]),
    "evaluate_economics": lambda args: evaluate_economics(args["planet"]),
}


def execute_tool(name: str, args: dict) -> str:
    """执行工具调用，返回字符串结果。"""
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return f"错误：未知工具 '{name}'"
    try:
        return handler(args)
    except Exception as e:
        return f"工具执行错误：{e}"


def _format(results: list[dict]) -> str:
    """格式化搜索结果列表。"""
    if not results:
        return "未找到匹配的星球"
    lines = []
    for r in results:
        lines.append(
            f"【{r['name']}】环境：{r['环境']} | "
            f"宜居：{r['宜居指数']} | 防御：{r['防御评分']} | 经济：{r['经济评分']}"
        )
    return "\n".join(lines)
