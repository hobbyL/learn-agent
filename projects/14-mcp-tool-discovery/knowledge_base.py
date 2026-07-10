"""
星际探索指挥中心 —— 知识库
============================

三个领域的数据，分别由三个 MCP Server 提供：

1. 星图数据库（Server A）：星系、星球、航线
2. 舰队管理（Server B）：飞船、船员、任务
3. 紧急通讯（Server C）：通讯记录、紧急消息（动态加载）
"""

# ============================================================
# 星图数据库（Server A）
# ============================================================

STAR_MAP = {
    "银河系": {
        "type": "星系",
        "直径": "10万光年",
        "恒星数量": "2000亿",
        "已探索区域": "12%",
        "主要航线": ["猎户臂航线", "英仙臂航线", "半人马航线"],
    },
    "仙女座星系": {
        "type": "星系",
        "直径": "22万光年",
        "恒星数量": "1万亿",
        "已探索区域": "0.3%",
        "主要航线": ["仙女座-银河桥"],
    },
    "蓝晶星": {
        "type": "星球",
        "所属星系": "银河系",
        "环境": "类地行星，含水量85%",
        "温度范围": "-10°C ~ 35°C",
        "重力": "0.92G",
        "已知资源": ["蓝晶矿", "深海藻能", "淡水冰川"],
        "殖民状态": "已建立前哨站",
    },
    "赤焰星": {
        "type": "星球",
        "所属星系": "银河系",
        "环境": "火山行星，地表温度极高",
        "温度范围": "200°C ~ 800°C",
        "重力": "1.35G",
        "已知资源": ["熔岩晶", "稀有金属矿", "地热能源"],
        "殖民状态": "无法殖民，仅采矿站",
    },
    "翡翠星": {
        "type": "星球",
        "所属星系": "银河系",
        "环境": "丛林行星，植被覆盖率98%",
        "温度范围": "15°C ~ 40°C",
        "重力": "1.05G",
        "已知资源": ["生物基因样本", "药用植物", "木质纤维"],
        "殖民状态": "科研基地",
    },
    "暗影星": {
        "type": "星球",
        "所属星系": "仙女座星系",
        "环境": "永夜行星，无恒星直射",
        "温度范围": "-180°C ~ -60°C",
        "重力": "0.45G",
        "已知资源": ["暗物质痕迹", "低温超导矿"],
        "殖民状态": "未探索",
    },
    "猎户臂航线": {
        "type": "航线",
        "起点": "地球",
        "终点": "蓝晶星",
        "距离": "4200光年",
        "预计航行时间": "42天（曲速5级）",
        "危险等级": "低",
    },
    "英仙臂航线": {
        "type": "航线",
        "起点": "蓝晶星",
        "终点": "赤焰星",
        "距离": "7800光年",
        "预计航行时间": "78天（曲速5级）",
        "危险等级": "中",
    },
    "半人马航线": {
        "type": "航线",
        "起点": "地球",
        "终点": "翡翠星",
        "距离": "3100光年",
        "预计航行时间": "31天（曲速5级）",
        "危险等级": "低",
    },
}

# ============================================================
# 舰队管理（Server B）
# ============================================================

FLEET = {
    "星耀号": {
        "type": "旗舰",
        "舰级": "泰坦级",
        "船员数": 1200,
        "最大曲速": "7级",
        "燃料容量": 50000,
        "当前燃料": 38000,
        "武器系统": ["等离子炮×8", "护盾发生器×4", "鱼雷发射管×12"],
        "当前任务": "巡逻猎户臂航线",
        "状态": "执行任务中",
    },
    "破晓号": {
        "type": "巡洋舰",
        "舰级": "猎鹰级",
        "船员数": 450,
        "最大曲速": "6级",
        "燃料容量": 20000,
        "当前燃料": 12500,
        "武器系统": ["激光炮×4", "护盾发生器×2", "鱼雷发射管×6"],
        "当前任务": "护送补给至蓝晶星",
        "状态": "执行任务中",
    },
    "探索者号": {
        "type": "科考船",
        "舰级": "先驱级",
        "船员数": 180,
        "最大曲速": "8级",
        "燃料容量": 15000,
        "当前燃料": 14200,
        "武器系统": ["防御激光×2"],
        "当前任务": "翡翠星生物样本采集",
        "状态": "执行任务中",
    },
    "铁壁号": {
        "type": "运输舰",
        "舰级": "堡垒级",
        "船员数": 300,
        "最大曲速": "4级",
        "燃料容量": 80000,
        "当前燃料": 65000,
        "武器系统": ["防御激光×4"],
        "当前任务": "无",
        "状态": "港口待命",
    },
    "陈星河": {
        "type": "船员",
        "军衔": "上将",
        "所属舰船": "星耀号",
        "职务": "舰队总指挥",
        "服役年限": 28,
        "专长": ["战术指挥", "外交谈判"],
    },
    "林月": {
        "type": "船员",
        "军衔": "中校",
        "所属舰船": "探索者号",
        "职务": "首席科学官",
        "服役年限": 12,
        "专长": ["外星生物学", "行星地质学"],
    },
    "赵铁柱": {
        "type": "船员",
        "军衔": "上尉",
        "所属舰船": "破晓号",
        "职务": "轮机长",
        "服役年限": 8,
        "专长": ["曲速引擎维护", "能源系统优化"],
    },
}

# ============================================================
# 紧急通讯（Server C — 动态加载）
# ============================================================

COMMS_LOG = [
    {
        "id": "COM-001",
        "时间": "星历2371.42",
        "发送方": "蓝晶星前哨站",
        "接收方": "指挥中心",
        "优先级": "普通",
        "内容": "前哨站运行正常，水资源采集效率提升15%。",
    },
    {
        "id": "COM-002",
        "时间": "星历2371.43",
        "发送方": "探索者号",
        "接收方": "指挥中心",
        "优先级": "重要",
        "内容": "在翡翠星发现未知植物物种，具有极高药用价值，请求延长考察期。",
    },
    {
        "id": "COM-003",
        "时间": "星历2371.44",
        "发送方": "英仙臂航线巡逻队",
        "接收方": "指挥中心",
        "优先级": "紧急",
        "内容": "检测到不明飞行物群，数量约30个，正在接近赤焰星采矿站。请求增援。",
    },
    {
        "id": "COM-004",
        "时间": "星历2371.44",
        "发送方": "赤焰星采矿站",
        "接收方": "指挥中心",
        "优先级": "紧急",
        "内容": "采矿站3号矿井坍塌，12名矿工被困，请求救援队。",
    },
    {
        "id": "COM-005",
        "时间": "星历2371.45",
        "发送方": "指挥中心",
        "接收方": "星耀号",
        "优先级": "最高",
        "内容": "立即前往赤焰星方向，应对不明飞行物威胁并协调救援。",
    },
]


# ============================================================
# 查询接口（供 MCP Server 和静态 Agent 共用）
# ============================================================

def search_starmap(query: str) -> list[dict]:
    """搜索星图数据库，返回匹配的实体列表。"""
    query_lower = query.lower()
    results = []
    for name, data in STAR_MAP.items():
        # 按名称、类型、内容匹配
        searchable = f"{name} {data.get('type', '')} {' '.join(str(v) for v in data.values())}".lower()
        if query_lower in searchable:
            results.append({"name": name, "type": data["type"], "summary": _summarize(name, data)})
    return results


def lookup_starmap(entity: str, field: str) -> str | None:
    """精确查询星图实体的某个字段。"""
    if entity not in STAR_MAP:
        return None
    data = STAR_MAP[entity]
    if field not in data:
        return None
    value = data[field]
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return str(value)


def search_fleet(query: str) -> list[dict]:
    """搜索舰队数据库，返回匹配的实体列表。"""
    query_lower = query.lower()
    results = []
    for name, data in FLEET.items():
        searchable = f"{name} {data.get('type', '')} {' '.join(str(v) for v in data.values())}".lower()
        if query_lower in searchable:
            results.append({"name": name, "type": data["type"], "summary": _summarize(name, data)})
    return results


def lookup_fleet(entity: str, field: str) -> str | None:
    """精确查询舰队实体的某个字段。"""
    if entity not in FLEET:
        return None
    data = FLEET[entity]
    if field not in data:
        return None
    value = data[field]
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return str(value)


def search_comms(query: str) -> list[dict]:
    """搜索通讯记录，返回匹配的记录列表。"""
    query_lower = query.lower()
    results = []
    for record in COMMS_LOG:
        searchable = f"{record['发送方']} {record['接收方']} {record['优先级']} {record['内容']}".lower()
        if query_lower in searchable:
            results.append({
                "id": record["id"],
                "时间": record["时间"],
                "发送方": record["发送方"],
                "优先级": record["优先级"],
                "摘要": record["内容"][:40] + ("..." if len(record["内容"]) > 40 else ""),
            })
    return results


def get_comms_detail(comm_id: str) -> dict | None:
    """根据通讯ID获取完整通讯记录。"""
    for record in COMMS_LOG:
        if record["id"] == comm_id:
            return record
    return None


def send_emergency(target: str, message: str) -> dict:
    """发送紧急通讯。"""
    new_id = f"COM-{len(COMMS_LOG) + 1:03d}"
    new_record = {
        "id": new_id,
        "时间": "星历2371.46",
        "发送方": "指挥中心",
        "接收方": target,
        "优先级": "最高",
        "内容": message,
    }
    COMMS_LOG.append(new_record)
    return {"success": True, "comm_id": new_id, "message": f"紧急通讯已发送至 {target}"}


def _summarize(name: str, data: dict) -> str:
    """生成实体的简短摘要。"""
    entity_type = data.get("type", "")
    if entity_type == "星系":
        return f"{name}，直径{data.get('直径', '未知')}，已探索{data.get('已探索区域', '未知')}"
    elif entity_type == "星球":
        return f"{name}，{data.get('环境', '未知环境')}"
    elif entity_type == "航线":
        return f"{data.get('起点', '?')} → {data.get('终点', '?')}，{data.get('距离', '未知')}"
    elif entity_type in ("旗舰", "巡洋舰", "科考船", "运输舰"):
        return f"{name}（{entity_type}），{data.get('状态', '未知状态')}"
    elif entity_type == "船员":
        return f"{name}，{data.get('军衔', '')}，{data.get('职务', '')}（{data.get('所属舰船', '')}）"
    return f"{name}（{entity_type}）"
