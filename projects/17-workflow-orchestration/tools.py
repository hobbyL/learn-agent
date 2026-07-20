"""
工具系统 —— 5 个领域工具
========================

每个 Agent 使用自己领域的工具：
- 地质学家 → scan_geology
- 建筑师 → evaluate_site
- 工程师 → plan_infrastructure
- 能源专家 → design_energy_system
- 生命支持专家 → configure_life_support
"""

from knowledge_base import (
    get_planet_overview,
    get_geology_data,
    get_site_options,
    analyze_site,
    get_energy_options,
    get_life_support_requirements,
    get_infrastructure_requirements,
)


# ============================================================
# 工具定义（OpenAI Function Calling Schema）
# ============================================================

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "scan_geology",
            "description": "扫描蓝晶星地质数据，包括地壳稳定性、地形、土壤、矿产资源、地质灾害等",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_site",
            "description": "评估候选建设区域，可以列出所有区域或分析指定区域的详细数据",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_id": {
                        "type": "string",
                        "description": "区域 ID（如 'A1', 'A2', 'A3'）。如果不提供，返回所有候选区域列表",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_infrastructure",
            "description": "根据选定区域规划基础设施建设方案",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_id": {
                        "type": "string",
                        "description": "已选定的区域 ID（如 'A1', 'A2', 'A3'）",
                    },
                },
                "required": ["site_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "design_energy_system",
            "description": "设计研究站能源系统，评估太阳能、地热能、核聚变、蓝晶能等方案",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "configure_life_support",
            "description": "配置生命支持系统，包括大气、水、食物、温控、废物处理等模块",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


# ============================================================
# 工具执行函数
# ============================================================

def scan_geology() -> str:
    """地质扫描工具（地质学家专用）。"""
    return get_geology_data()


def evaluate_site(site_id: str | None = None) -> str:
    """选址评估工具（建筑师专用）。"""
    if site_id is None:
        # 返回所有候选区域
        sites = get_site_options()
        lines = ["候选建设区域列表：\n"]
        for s in sites:
            lines.append(f"区域 {s['id']} - {s['name']}")
            lines.append(f"  地形：{s['地形']}")
            lines.append(f"  面积：{s['面积']}")
            lines.append(f"  地质稳定性：{s['地质稳定性']}")
            lines.append(f"  优势：{s['优势']}")
            lines.append(f"  风险：{s['风险']}\n")
        return "\n".join(lines)
    else:
        # 返回指定区域详细分析
        return analyze_site(site_id)


def plan_infrastructure(site_id: str) -> str:
    """基础建设规划工具（工程师专用）。"""
    return get_infrastructure_requirements(site_id)


def design_energy_system() -> str:
    """能源系统设计工具（能源专家专用）。"""
    return get_energy_options()


def configure_life_support() -> str:
    """生命支持系统配置工具（生命支持专家专用）。"""
    return get_life_support_requirements()


# ============================================================
# 工具路由器
# ============================================================

TOOL_HANDLERS = {
    "scan_geology": scan_geology,
    "evaluate_site": evaluate_site,
    "plan_infrastructure": plan_infrastructure,
    "design_energy_system": design_energy_system,
    "configure_life_support": configure_life_support,
}


def execute_tool(tool_name: str, arguments: dict) -> str:
    """执行工具调用。"""
    if tool_name not in TOOL_HANDLERS:
        return f"错误：未知工具 '{tool_name}'"

    handler = TOOL_HANDLERS[tool_name]
    try:
        # 调用工具函数
        if arguments:
            result = handler(**arguments)
        else:
            result = handler()
        return result
    except Exception as e:
        return f"工具执行错误：{str(e)}"


# ============================================================
# 工具过滤（按 Agent 角色）
# ============================================================

def get_tools_for_agent(role: str) -> list[dict]:
    """根据 Agent 角色返回可用工具列表。"""
    role_tools = {
        "geologist": ["scan_geology"],
        "architect": ["evaluate_site"],
        "engineer": ["plan_infrastructure"],
        "energy_specialist": ["design_energy_system"],
        "life_support_specialist": ["configure_life_support"],
    }

    if role not in role_tools:
        return []

    tool_names = role_tools[role]
    return [t for t in TOOLS_SCHEMA if t["function"]["name"] in tool_names]
