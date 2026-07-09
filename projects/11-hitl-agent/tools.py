"""
救援工具集 —— 灾害应急指挥中心的操作工具
==========================================

每个工具的 schema 中包含 `requires_approval` 字段标记是否需要 HITL 审批：
- True：调用前自动暂停，请求人类指挥官确认
- False：Agent 可自主执行

工具列表（9 个）：
- check_situation    查看灾区/基础设施当前状态（不需审批）
- check_resources    查看物资/人力库存（不需审批）
- query_knowledge    查询知识库实体详情（不需审批）
- dispatch_team      派遣救援队到灾区（需审批：人命风险）
- evacuate           下令撤离（需审批：不可逆、人命风险）
- allocate_resource  分配物资（需审批：资源冲突）
- release_flood      主动泄洪（需审批：不可逆）
- repair_infra       抢修基础设施（不需审批）
- set_alert_level    设置警报等级（不需审批）

设计逻辑：
- 查询类工具不需审批（信息收集阶段 Agent 自主完成）
- 执行类工具根据风险等级决定是否需审批
- 失败条件确定性：依赖 knowledge_base 的世界状态
"""

from __future__ import annotations

from knowledge_base import get_state, lookup_entity
from schemas import ApprovalType

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 工具 Schema（OpenAI Function Calling 格式）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TOOLS_SCHEMA: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "check_situation",
            "description": "查看指定灾区或基础设施的当前状态（伤亡人数、受困人数、损坏程度、当前险情等级）",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "要查看的灾区或基础设施名称",
                    }
                },
                "required": ["target"],
            },
        },
        "requires_approval": False,
    },
    {
        "type": "function",
        "function": {
            "name": "check_resources",
            "description": "查看物资库存和救援队状态（可用数量、当前部署位置、剩余体力/燃料）",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["teams", "supplies", "all"],
                        "description": "查看类别：teams=救援队，supplies=物资，all=全部",
                    }
                },
                "required": ["category"],
            },
        },
        "requires_approval": False,
    },
    {
        "type": "function",
        "function": {
            "name": "query_knowledge",
            "description": "查询知识库中的实体详情（灾区背景、基础设施参数、历史记录等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "要查询的实体名称",
                    }
                },
                "required": ["entity_name"],
            },
        },
        "requires_approval": False,
    },
    {
        "type": "function",
        "function": {
            "name": "dispatch_team",
            "description": "派遣救援队前往指定灾区执行任务（搜救/灭火/医疗/工程抢修）。人命风险：队员可能遭遇余震、建筑倒塌等危险。",
            "parameters": {
                "type": "object",
                "properties": {
                    "team": {
                        "type": "string",
                        "description": "救援队名称",
                    },
                    "destination": {
                        "type": "string",
                        "description": "目标灾区",
                    },
                    "mission": {
                        "type": "string",
                        "description": "任务类型（搜救/灭火/医疗救治/工程抢修/警戒）",
                    },
                },
                "required": ["team", "destination", "mission"],
            },
        },
        "requires_approval": True,
        "approval_type": "life_risk",
    },
    {
        "type": "function",
        "function": {
            "name": "evacuate",
            "description": "下令撤离指定区域居民。不可逆操作：撤离一旦启动无法中止，且会占用大量交通和人力资源。",
            "parameters": {
                "type": "object",
                "properties": {
                    "area": {
                        "type": "string",
                        "description": "要撤离的区域",
                    },
                    "population": {
                        "type": "integer",
                        "description": "预计撤离人数",
                    },
                    "destination": {
                        "type": "string",
                        "description": "撤离目的地（避难所）",
                    },
                },
                "required": ["area", "population", "destination"],
            },
        },
        "requires_approval": True,
        "approval_type": "irreversible",
    },
    {
        "type": "function",
        "function": {
            "name": "allocate_resource",
            "description": "分配物资到指定位置。资源有限，分配后其他区域将减少可用量。",
            "parameters": {
                "type": "object",
                "properties": {
                    "resource": {
                        "type": "string",
                        "description": "物资名称",
                    },
                    "amount": {
                        "type": "integer",
                        "description": "分配数量",
                    },
                    "destination": {
                        "type": "string",
                        "description": "目标位置",
                    },
                },
                "required": ["resource", "amount", "destination"],
            },
        },
        "requires_approval": True,
        "approval_type": "resource_conflict",
    },
    {
        "type": "function",
        "function": {
            "name": "release_flood",
            "description": "对堰塞湖执行主动泄洪。极高风险不可逆操作：将淹没下游指定区域，但可解除堰塞湖溃坝威胁。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dam": {
                        "type": "string",
                        "description": "堰塞湖/坝体名称",
                    },
                    "flood_zone": {
                        "type": "string",
                        "description": "泄洪将影响的下游区域",
                    },
                },
                "required": ["dam", "flood_zone"],
            },
        },
        "requires_approval": True,
        "approval_type": "irreversible",
    },
    {
        "type": "function",
        "function": {
            "name": "repair_infra",
            "description": "安排抢修队修复基础设施（通信塔、桥梁、水电站等）。风险较低的维护操作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "facility": {
                        "type": "string",
                        "description": "要抢修的基础设施",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["urgent", "normal", "low"],
                        "description": "抢修优先级",
                    },
                },
                "required": ["facility", "priority"],
            },
        },
        "requires_approval": False,
    },
    {
        "type": "function",
        "function": {
            "name": "set_alert_level",
            "description": "设置区域的警报等级（影响后续行动的约束条件）",
            "parameters": {
                "type": "object",
                "properties": {
                    "area": {
                        "type": "string",
                        "description": "区域名称",
                    },
                    "level": {
                        "type": "string",
                        "enum": ["green", "yellow", "orange", "red"],
                        "description": "警报等级：green=安全, yellow=关注, orange=警告, red=紧急",
                    },
                },
                "required": ["area", "level"],
            },
        },
        "requires_approval": False,
    },
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 工具注册表（方便查询）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TOOL_REGISTRY: dict[str, dict] = {t["function"]["name"]: t for t in TOOLS_SCHEMA}


# report_result 工具：Agent 用来表示任务完成/放弃的结构化信号
REPORT_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "report_result",
        "description": "报告当前救援任务的最终结果。任务完成或无法继续时调用此工具。",
        "parameters": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "任务是否成功完成",
                },
                "summary": {
                    "type": "string",
                    "description": "结果摘要：完成了什么、救了多少人、剩余风险等",
                },
                "reason": {
                    "type": "string",
                    "description": "如果失败，说明原因",
                },
            },
            "required": ["success", "summary"],
        },
    },
}


def requires_approval(tool_name: str) -> bool:
    """判断工具是否需要 HITL 审批。"""
    tool = TOOL_REGISTRY.get(tool_name)
    if tool is None:
        return False
    return tool.get("requires_approval", False)


def get_approval_type(tool_name: str) -> str | None:
    """获取工具的审批类型。"""
    tool = TOOL_REGISTRY.get(tool_name)
    if tool is None:
        return None
    return tool.get("approval_type")


def get_tools_for_llm() -> list[dict]:
    """返回供 LLM 使用的工具列表（去除 requires_approval/approval_type 元数据）。"""
    clean = []
    for t in TOOLS_SCHEMA:
        clean.append({"type": t["type"], "function": t["function"]})
    return clean


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 工具执行逻辑
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def execute_tool(tool_name: str, args: dict) -> dict:
    """
    执行工具并返回结果。

    返回 {"success": bool, "message": str, "alerts": list[str]}
    """
    dispatch = {
        "check_situation": _exec_check_situation,
        "check_resources": _exec_check_resources,
        "query_knowledge": _exec_query_knowledge,
        "dispatch_team": _exec_dispatch_team,
        "evacuate": _exec_evacuate,
        "allocate_resource": _exec_allocate_resource,
        "release_flood": _exec_release_flood,
        "repair_infra": _exec_repair_infra,
        "set_alert_level": _exec_set_alert_level,
    }

    handler = dispatch.get(tool_name)
    if handler is None:
        return {"success": False, "message": f"未知工具: {tool_name}", "alerts": []}

    return handler(args)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 各工具具体实现
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _exec_check_situation(args: dict) -> dict:
    """查看灾区/基础设施状态。"""
    target = args.get("target", "")
    state = get_state()

    # 先查灾区
    if target in state["zones"]:
        zone = state["zones"][target]
        lines = [f"【{target}】当前态势：", f"  险情等级：{zone.get('severity', '未知')}"]
        if "trapped_people" in zone:
            lines.append(f"  受困人数：{zone['trapped_people']} 人")
        if "water_level_m" in zone:
            lines.append(f"  水位：{zone['water_level_m']}m / 警戒：{zone.get('warning_level_m', 'N/A')}m")
            lines.append(f"  坝体完整度：{zone.get('dam_integrity_pct', 'N/A')}%")
        if "affected_area_sqm" in zone:
            lines.append(f"  火灾面积：{zone['affected_area_sqm']} ㎡")
        if "dangerous_buildings" in zone:
            lines.append(f"  危险建筑：{zone['dangerous_buildings']} 栋")
        if zone.get("notes"):
            lines.append(f"  备注：{zone['notes']}")
        return {"success": True, "message": "\n".join(lines), "alerts": _check_alerts(target, zone)}

    # 再查基础设施
    if target in state["infrastructure"]:
        infra = state["infrastructure"][target]
        lines = [
            f"【{target}】当前状态：",
            f"  类型：{infra.get('type', '未知')}",
            f"  运行状态：{infra.get('status', '未知')}",
        ]
        if "damage_level" in infra:
            lines.append(f"  损坏程度：{infra['damage_level']}")
        if "capacity" in infra:
            occupants = infra.get("current_occupants", infra.get("current_patients", 0))
            lines.append(f"  容量：{infra['capacity']}，当前：{occupants}")
        if infra.get("notes"):
            lines.append(f"  备注：{infra['notes']}")
        return {"success": True, "message": "\n".join(lines), "alerts": []}

    return {"success": False, "message": f"未找到目标: {target}", "alerts": []}


def _exec_check_resources(args: dict) -> dict:
    """查看资源状态。"""
    category = args.get("category", "all")
    state = get_state()
    lines = []

    if category in ("teams", "all"):
        lines.append("═══ 救援队状态 ═══")
        for name, team in state["teams"].items():
            status = "🟢 待命" if team["status"] == "待命" else f"🔴 {team['status']}"
            lines.append(f"  {name}：{status}  位置：{team['location']}")

    if category in ("supplies", "all"):
        lines.append("═══ 物资库存 ═══")
        for name, supply in state["supplies"].items():
            remaining = supply["total"] - supply["deployed"]
            lines.append(f"  {name}：{remaining}/{supply['total']} {supply['unit']}")

    return {"success": True, "message": "\n".join(lines), "alerts": []}


def _exec_query_knowledge(args: dict) -> dict:
    """查询知识库实体。"""
    name = args.get("entity_name", "")
    detail = lookup_entity(name)
    if detail and not detail.startswith("未找到"):
        return {"success": True, "message": detail, "alerts": []}
    return {"success": False, "message": f"未找到实体: {name}", "alerts": []}


def _exec_dispatch_team(args: dict) -> dict:
    """派遣救援队。"""
    team_name = args.get("team", "")
    destination = args.get("destination", "")
    mission = args.get("mission", "")
    state = get_state()

    # 查找队伍
    if team_name not in state["teams"]:
        return {"success": False, "message": f"救援队不存在: {team_name}", "alerts": []}

    team = state["teams"][team_name]

    if team["status"] != "待命":
        return {
            "success": False,
            "message": f"{team_name} 当前不可用（状态：{team['status']}，位置：{team['location']}）",
            "alerts": [],
        }

    # 检查目标位置（灾区或基础设施）
    if destination not in state["zones"] and destination not in state["infrastructure"]:
        return {"success": False, "message": f"目标位置不存在: {destination}", "alerts": []}

    # 检查环境限制：余震预警期间禁止进入不稳定建筑
    env = state["environment"]
    if env.get("aftershock_warning") and "搜救" in mission:
        return {
            "success": False,
            "message": "⚠️ 余震预警生效中，禁止派遣队伍进入不稳定建筑执行搜救任务",
            "alerts": ["余震预警限制搜救行动"],
        }

    # 执行派遣
    team["status"] = f"执行任务:{destination}"
    team["location"] = destination

    return {
        "success": True,
        "message": f"✅ {team_name} 已派遣至 {destination} 执行{mission}任务",
        "alerts": [],
    }


def _exec_evacuate(args: dict) -> dict:
    """执行撤离。"""
    area = args.get("area", "")
    population = args.get("population", 0)
    destination = args.get("destination", "")
    state = get_state()

    # 查找区域
    if area not in state["zones"]:
        return {"success": False, "message": f"区域不存在: {area}", "alerts": []}
    zone = state["zones"][area]

    # 检查避难所容量
    if destination not in state["infrastructure"]:
        return {"success": False, "message": f"避难所不存在: {destination}", "alerts": []}
    shelter = state["infrastructure"][destination]

    capacity = shelter.get("capacity", 0)
    current = shelter.get("current_occupants", 0)
    remaining = capacity - current
    if remaining < population:
        return {
            "success": False,
            "message": f"避难所容量不足: {destination} 剩余 {remaining} 人容量，需撤离 {population} 人",
            "alerts": ["需要寻找额外避难所或分批撤离"],
        }

    # 检查道路
    env = state["environment"]
    if env.get("road_blocked") and area in env.get("blocked_routes", []):
        return {
            "success": False,
            "message": f"通往 {area} 的道路已塌方，无法执行撤离",
            "alerts": ["需要先抢修道路或寻找替代路线"],
        }

    # 执行撤离
    zone["evacuation_status"] = "撤离中"
    if "trapped_people" in zone:
        zone["trapped_people"] = max(0, zone["trapped_people"] - population)
    shelter["current_occupants"] = current + population

    return {
        "success": True,
        "message": f"✅ 已启动 {area} 撤离行动：{population} 人转移至 {destination}",
        "alerts": ["撤离预计耗时 2 小时，期间占用主干道通行能力"],
    }


def _exec_allocate_resource(args: dict) -> dict:
    """分配物资。"""
    resource_name = args.get("resource", "")
    amount = args.get("amount", 0)
    destination = args.get("destination", "")
    state = get_state()

    if resource_name not in state["supplies"]:
        return {"success": False, "message": f"物资不存在: {resource_name}", "alerts": []}
    supply = state["supplies"][resource_name]

    available = supply["total"] - supply["deployed"]
    if available < amount:
        return {
            "success": False,
            "message": f"物资不足: {resource_name} 可用 {available}{supply['unit']}，需求 {amount}{supply['unit']}",
            "alerts": [],
        }

    # 执行分配
    supply["deployed"] += amount
    remaining = supply["total"] - supply["deployed"]

    alerts = []
    if remaining < supply["total"] * 0.2:
        alerts.append(f"⚠️ {resource_name} 库存低于 20%（剩余 {remaining}/{supply['total']}）")

    return {
        "success": True,
        "message": f"✅ 已分配 {amount}{supply['unit']} {resource_name} 至 {destination}",
        "alerts": alerts,
    }


def _exec_release_flood(args: dict) -> dict:
    """主动泄洪。"""
    dam = args.get("dam", "")
    flood_zone = args.get("flood_zone", "")
    state = get_state()

    if dam not in state["zones"]:
        return {"success": False, "message": f"堰塞湖不存在: {dam}", "alerts": []}
    dam_zone = state["zones"][dam]

    water_level = dam_zone.get("water_level_m", 0)
    warning_level = dam_zone.get("warning_level_m", 45.0)

    # 仅当水位接近警戒线（3m 以内）时才允许泄洪
    if water_level < warning_level - 3:
        return {
            "success": False,
            "message": f"当前水位 {water_level}m，距警戒线 {warning_level}m 尚有 {round(warning_level - water_level, 1)}m 余量，暂不需要泄洪",
            "alerts": [],
        }

    # 执行泄洪（降低水位 2m，降低坝体压力）
    new_level = round(max(0, water_level - 2.0), 1)
    dam_zone["water_level_m"] = new_level
    dam_zone["severity"] = "中"

    return {
        "success": True,
        "message": f"✅ 已对 {dam} 执行泄洪，水位从 {water_level}m 降至 {new_level}m。\n⚠️ {flood_zone} 区域需临时疏散",
        "alerts": [f"紧急通知：{flood_zone} 需临时疏散", f"{dam} 溃坝风险已降低"],
    }


def _exec_repair_infra(args: dict) -> dict:
    """抢修基础设施。"""
    facility = args.get("facility", "")
    priority = args.get("priority", "normal")
    state = get_state()

    if facility not in state["infrastructure"]:
        return {"success": False, "message": f"基础设施不存在: {facility}", "alerts": []}
    infra = state["infrastructure"][facility]

    if infra["status"] in ("运行中", "启用"):
        return {"success": True, "message": f"{facility} 当前运行正常，无需抢修", "alerts": []}

    # 执行抢修（优先级影响恢复程度）
    recovery = {"urgent": "临时恢复", "normal": "部分恢复", "low": "排队等待"}
    prev_status = infra["status"]
    infra["status"] = recovery.get(priority, "部分恢复")

    return {
        "success": True,
        "message": f"✅ 已安排 {facility} 抢修（优先级：{priority}），状态：{prev_status} → {infra['status']}",
        "alerts": [],
    }


def _exec_set_alert_level(args: dict) -> dict:
    """设置警报等级。"""
    area = args.get("area", "")
    level = args.get("level", "yellow")
    state = get_state()

    if area not in state["zones"]:
        return {"success": False, "message": f"区域不存在: {area}", "alerts": []}

    state["zones"][area]["alert_level"] = level
    level_desc = {"green": "安全", "yellow": "关注", "orange": "警告", "red": "紧急"}
    return {
        "success": True,
        "message": f"✅ {area} 警报等级已设置为 {level}（{level_desc.get(level, level)}）",
        "alerts": [],
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 辅助函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _check_alerts(name: str, zone: dict) -> list[str]:
    """根据灾区状态生成警报。"""
    alerts = []
    if zone.get("severity") in ("极重", "危急"):
        alerts.append(f"🔴 {name} 处于最高险情等级（{zone['severity']}）")
    if zone.get("trapped_people", 0) > 20:
        alerts.append(f"⚠️ {name} 仍有 {zone['trapped_people']} 人受困")
    if "water_level_m" in zone:
        water_level = zone["water_level_m"]
        warning = zone.get("warning_level_m", 45.0)
        if water_level >= warning:
            alerts.append(f"🌊 {name} 水位 {water_level}m 已超警戒线 {warning}m！溃坝风险极高！")
        elif water_level >= warning - 1.0:
            alerts.append(f"🌊 {name} 水位 {water_level}m，距警戒线仅 {round(warning - water_level, 1)}m")
    return alerts
