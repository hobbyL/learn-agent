"""
明川市灾害应急指挥中心 —— 世界知识库
========================================

虚构城市「明川市」遭遇复合灾害（地震 + 次生火灾 + 堰塞湖），
Agent 作为指挥中心 AI 助手调度救援。

核心特性：
- ~30 个实体：救援队/灾区/物资/基础设施/灾害事件/状态
- 可变状态（_CITY_STATE）：随操作和时间推进改变
- 灾害恶化机制：每 N 步调用 tick() 让灾情自动恶化
- reset_state() 重置到初始快照
"""

import copy

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 静态知识（不随游戏状态变化）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RESCUE_TEAMS = {
    "消防突击队": {
        "type": "消防",
        "personnel": 25,
        "capabilities": ["灭火", "破拆", "高空救援"],
        "equipment": ["消防车×3", "云梯×1", "破拆器×5"],
        "status": "待命",
        "location": "指挥中心",
    },
    "医疗救护队": {
        "type": "医疗",
        "personnel": 15,
        "capabilities": ["现场急救", "伤员转运", "心理疏导"],
        "equipment": ["救护车×4", "移动手术台×1", "医疗包×50"],
        "status": "待命",
        "location": "指挥中心",
    },
    "搜救犬队": {
        "type": "搜救",
        "personnel": 12,
        "capabilities": ["废墟搜救", "生命探测", "狭窄空间救援"],
        "equipment": ["生命探测仪×3", "搜救犬×6", "液压扩张器×4"],
        "status": "待命",
        "location": "指挥中心",
    },
    "工程抢修队": {
        "type": "工程",
        "personnel": 20,
        "capabilities": ["道路抢通", "桥梁加固", "堤坝修复"],
        "equipment": ["挖掘机×2", "装载机×1", "沙袋×500", "钢支撑×20"],
        "status": "待命",
        "location": "指挥中心",
    },
    "民兵预备队": {
        "type": "综合",
        "personnel": 40,
        "capabilities": ["居民疏散", "物资搬运", "治安维护", "临时安置"],
        "equipment": ["对讲机×20", "手电×40", "担架×10"],
        "status": "待命",
        "location": "指挥中心",
    },
}

DISASTER_ZONES = {
    "震中广场": {
        "type": "震区",
        "severity": "极重",
        "trapped_people": 45,
        "collapsed_buildings": 8,
        "access": "部分可通行",
        "notes": "多栋居民楼倒塌，地下有生命信号",
    },
    "东城火灾区": {
        "type": "火灾",
        "severity": "重",
        "affected_area_sqm": 12000,
        "trapped_people": 12,
        "wind_direction": "西北风",
        "notes": "化工仓库起火，有爆炸风险，火势向东蔓延",
    },
    "堰塞湖区域": {
        "type": "堰塞湖",
        "severity": "危急",
        "water_level_m": 42.5,
        "warning_level_m": 45.0,
        "dam_integrity_pct": 72,
        "downstream_population": 8000,
        "notes": "山体滑坡形成堰塞湖，水位持续上涨",
    },
    "老城区": {
        "type": "老旧建筑",
        "severity": "中",
        "population": 5200,
        "dangerous_buildings": 15,
        "evacuation_status": "未疏散",
        "notes": "砖混结构老楼多，余震可能导致二次坍塌",
    },
    "明川小学": {
        "type": "学校",
        "severity": "重",
        "trapped_people": 28,
        "building_status": "部分坍塌",
        "access": "主入口被堵，需从侧面进入",
        "notes": "教学楼三层坍塌，操场临时安置点已启用",
    },
}

SUPPLIES = {
    "帐篷": {"total": 200, "deployed": 0, "unit": "顶"},
    "食品": {"total": 5000, "deployed": 0, "unit": "份"},
    "医疗包": {"total": 300, "deployed": 0, "unit": "个"},
    "重型设备": {"total": 4, "deployed": 0, "unit": "台"},
    "通信设备": {"total": 15, "deployed": 0, "unit": "套"},
}

INFRASTRUCTURE = {
    "明川大桥": {
        "type": "桥梁",
        "status": "受损",
        "damage_level": "中",
        "connects": "城区↔堰塞湖方向",
        "notes": "桥面裂缝，限载10吨，重型设备无法通过",
    },
    "市中心医院": {
        "type": "医院",
        "status": "运行中",
        "capacity": 200,
        "current_patients": 85,
        "notes": "停电中，靠备用发电机运行，燃油仅够12小时",
    },
    "上游水电站": {
        "type": "水电站",
        "status": "停运",
        "dam_status": "安全",
        "notes": "地震后自动停机，闸门可远程控制",
    },
    "北山通信塔": {
        "type": "通信基站",
        "status": "故障",
        "coverage": "城区北部",
        "notes": "天线倾斜，北部片区通信中断",
    },
    "体育馆避难所": {
        "type": "避难所",
        "status": "启用",
        "capacity": 3000,
        "current_occupants": 1200,
        "notes": "已有1200人入住，物资紧张",
    },
}

DISASTER_EVENTS = {
    "余震": {
        "active": True,
        "intensity": "4.2级",
        "frequency": "每2小时一次",
        "impact": "建筑再次受损风险，搜救人员危险增加",
    },
    "火势蔓延": {
        "active": True,
        "direction": "向东",
        "speed": "每小时扩展500平米",
        "impact": "威胁东部居民区，30分钟内到达加油站",
    },
    "水位上涨": {
        "active": True,
        "rate": "每小时0.3米",
        "impact": "堰塞湖溢坝风险，下游8000人受威胁",
    },
    "道路塌方": {
        "active": True,
        "location": "环城北路",
        "impact": "北部救援通道中断，绕行增加20分钟",
    },
    "通信中断": {
        "active": True,
        "affected_area": "城区北部",
        "impact": "无法联系北部灾区群众，搜救协调困难",
    },
}

ENVIRONMENT_STATUS = {
    "当前时间": "2026-07-08 14:30",
    "天气": "阴，间歇小雨",
    "温度": "28°C",
    "能见度": "良好",
    "夜间预计": "20:00天黑，需提前部署照明",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 可变状态（随 Agent 操作和时间推进而改变）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_INITIAL_STATE = {
    "tick": 0,  # 当前步数（每次工具调用 +1）
    "teams": copy.deepcopy(RESCUE_TEAMS),
    "zones": copy.deepcopy(DISASTER_ZONES),
    "supplies": copy.deepcopy(SUPPLIES),
    "infrastructure": copy.deepcopy(INFRASTRUCTURE),
    "events": copy.deepcopy(DISASTER_EVENTS),
    "environment": copy.deepcopy(ENVIRONMENT_STATUS),
    "action_log": [],  # 已执行操作记录
    "alerts": [],  # 未处理的紧急警报
}

_CITY_STATE: dict = {}


def reset_state() -> None:
    """重置世界到初始快照（每次 Agent.run() 开始时调用）。"""
    global _CITY_STATE
    _CITY_STATE = copy.deepcopy(_INITIAL_STATE)


def get_state() -> dict:
    """获取当前世界状态引用（工具函数直接操作此状态）。"""
    if not _CITY_STATE:
        reset_state()
    return _CITY_STATE


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 灾害恶化机制（每 tick 调用一次）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def tick() -> list[str]:
    """
    推进一个时间步，灾害自动恶化。
    返回本步产生的警报列表。
    """
    state = get_state()
    state["tick"] += 1
    t = state["tick"]
    alerts = []

    # 水位上涨：每 tick +0.3m
    lake = state["zones"]["堰塞湖区域"]
    if state["events"]["水位上涨"]["active"]:
        lake["water_level_m"] = round(lake["water_level_m"] + 0.3, 1)
        lake["dam_integrity_pct"] = max(0, lake["dam_integrity_pct"] - 2)

        if lake["water_level_m"] >= lake["warning_level_m"]:
            alert = f"⚠️ 紧急：堰塞湖水位 {lake['water_level_m']}m 已超警戒线 {lake['warning_level_m']}m！溢坝风险极高！"
            alerts.append(alert)
        elif lake["water_level_m"] >= lake["warning_level_m"] - 1.0:
            alert = f"⚠️ 警告：堰塞湖水位 {lake['water_level_m']}m，距警戒线仅 {round(lake['warning_level_m'] - lake['water_level_m'], 1)}m"
            alerts.append(alert)

    # 火势蔓延：每 tick 面积 +500
    fire = state["zones"]["东城火灾区"]
    if state["events"]["火势蔓延"]["active"]:
        fire["affected_area_sqm"] += 500
        if fire["affected_area_sqm"] >= 15000:
            alert = "⚠️ 紧急：火势即将蔓延至加油站区域！爆炸风险！"
            alerts.append(alert)

    # 余震：每 3 tick 发生一次
    if state["events"]["余震"]["active"] and t % 3 == 0:
        # 随机增加被困人数（建筑再次坍塌）
        state["zones"]["老城区"]["dangerous_buildings"] += 1
        alert = "⚠️ 余震发生：老城区又有建筑出现裂缝，危险建筑数 +1"
        alerts.append(alert)

    # 医院燃油倒计时
    hospital = state["infrastructure"]["市中心医院"]
    if hospital["status"] == "运行中":
        remaining = 12 - t * 0.5  # 每 tick 消耗 0.5 小时燃油
        if remaining <= 2:
            alert = f"⚠️ 紧急：市中心医院备用发电机燃油仅剩约 {max(0, remaining):.1f} 小时！"
            alerts.append(alert)

    state["alerts"].extend(alerts)
    return alerts


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 知识检索接口（供 Agent 使用）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_full_briefing() -> str:
    """获取当前灾情完整简报（所有实体当前状态）。"""
    state = get_state()
    lines = [
        "═══ 明川市灾害应急指挥中心 ═══",
        f"当前时刻：{state['environment']['当前时间']}（第 {state['tick']} 步）",
        f"天气：{state['environment']['天气']}，{state['environment']['温度']}",
        "",
        "━━ 灾区态势 ━━",
    ]

    for name, zone in state["zones"].items():
        lines.append(f"【{name}】 严重度={zone['severity']}，被困人数={zone.get('trapped_people', 'N/A')}")
        if "water_level_m" in zone:
            lines.append(f"  水位={zone['water_level_m']}m / 警戒={zone['warning_level_m']}m，坝体完整度={zone['dam_integrity_pct']}%")
        if "affected_area_sqm" in zone:
            lines.append(f"  火灾面积={zone['affected_area_sqm']}㎡")
        lines.append(f"  备注：{zone['notes']}")

    lines.append("\n━━ 救援队伍 ━━")
    for name, team in state["teams"].items():
        lines.append(f"【{name}】 {team['type']}，{team['personnel']}人，状态={team['status']}，位置={team['location']}")

    lines.append("\n━━ 物资库存 ━━")
    for name, supply in state["supplies"].items():
        remaining = supply["total"] - supply["deployed"]
        lines.append(f"  {name}：剩余 {remaining}/{supply['total']} {supply['unit']}")

    lines.append("\n━━ 基础设施 ━━")
    for name, infra in state["infrastructure"].items():
        lines.append(f"【{name}】 {infra['type']}，状态={infra['status']}，{infra['notes']}")

    lines.append("\n━━ 活跃灾害事件 ━━")
    for name, event in state["events"].items():
        if event["active"]:
            lines.append(f"  ⚡ {name}：{event['impact']}")

    if state["alerts"]:
        lines.append("\n━━ 未处理警报 ━━")
        for alert in state["alerts"][-5:]:  # 最近 5 条
            lines.append(f"  {alert}")

    return "\n".join(lines)


def search_info(query: str) -> str:
    """根据关键词搜索相关信息。"""
    state = get_state()
    results = []
    query_lower = query.lower()

    # 搜索灾区
    for name, zone in state["zones"].items():
        if query_lower in name.lower() or query_lower in zone.get("notes", "").lower():
            results.append(f"[灾区] {name}：严重度={zone['severity']}，{zone['notes']}")

    # 搜索队伍
    for name, team in state["teams"].items():
        if query_lower in name.lower() or query_lower in team["type"].lower():
            results.append(f"[队伍] {name}：{team['personnel']}人，状态={team['status']}，位置={team['location']}")

    # 搜索设施
    for name, infra in state["infrastructure"].items():
        if query_lower in name.lower() or query_lower in infra.get("notes", "").lower():
            results.append(f"[设施] {name}：状态={infra['status']}，{infra['notes']}")

    # 搜索物资
    for name, supply in state["supplies"].items():
        if query_lower in name.lower():
            remaining = supply["total"] - supply["deployed"]
            results.append(f"[物资] {name}：剩余 {remaining}/{supply['total']} {supply['unit']}")

    if not results:
        return f"未找到与「{query}」相关的信息。"
    return "\n".join(results)


def lookup_entity(name: str) -> str:
    """查询指定实体的详细信息。"""
    state = get_state()

    # 依次在各类别中查找
    if name in state["zones"]:
        return f"[灾区] {name}：{state['zones'][name]}"
    if name in state["teams"]:
        return f"[队伍] {name}：{state['teams'][name]}"
    if name in state["infrastructure"]:
        return f"[设施] {name}：{state['infrastructure'][name]}"
    if name in state["supplies"]:
        s = state["supplies"][name]
        return f"[物资] {name}：总量={s['total']}，已部署={s['deployed']}，剩余={s['total'] - s['deployed']} {s['unit']}"
    if name in state["events"]:
        return f"[事件] {name}：{state['events'][name]}"

    return f"未找到实体「{name}」。可用实体：{list(state['zones'].keys()) + list(state['teams'].keys()) + list(state['infrastructure'].keys())}"
