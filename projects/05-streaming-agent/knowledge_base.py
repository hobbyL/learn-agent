"""
太空站联盟 —— 虚构知识库
============================

约 12 个实体的轻量虚构世界，用于测试 streaming Agent 的工具调用。
主题：人类在太阳系建立的多个太空站组成的联盟。

实体类型：
- 太空站（4 个）：各有位置、人口、站长、建站年份
- 人物（5 个）：站长/工程师/科学家，有职位、年龄、师承、驻站
- 设备/飞船（3 个）：有型号、所属站、操作员、用途

设计意图：
- 足够触发 2-3 步链式推理（A 的站长 → 站长的导师 → 导师的驻站）
- 名字相似陷阱：天琴站 vs 天琴号（一个是太空站，一个是飞船）
- 数值对比场景：人口、建站年份
"""

# ============================================================
# 知识库数据
# ============================================================

KNOWLEDGE_BASE = {
    # ─── 太空站 ───
    "极光站": {
        "类型": "太空站",
        "位置": "近地轨道",
        "人口": 2400,
        "站长": "陈星河",
        "建站年份": 2089,
        "特色": "联盟总部，最大的科研中心",
        "面积": "12000 平方米",
    },
    "天琴站": {
        "类型": "太空站",
        "位置": "月球轨道",
        "人口": 1800,
        "站长": "林夜霜",
        "建站年份": 2095,
        "特色": "月球矿产中转枢纽",
        "面积": "8500 平方米",
    },
    "深红站": {
        "类型": "太空站",
        "位置": "火星轨道",
        "人口": 960,
        "站长": "赵铁翼",
        "建站年份": 2103,
        "特色": "火星殖民前哨站",
        "面积": "6200 平方米",
    },
    "冰环站": {
        "类型": "太空站",
        "位置": "土星环带",
        "人口": 420,
        "站长": "苏晴岚",
        "建站年份": 2112,
        "特色": "氦-3 采集与深空探测",
        "面积": "4800 平方米",
    },

    # ─── 人物 ───
    "陈星河": {
        "类型": "人物",
        "职位": "极光站站长",
        "年龄": 58,
        "驻站": "极光站",
        "导师": "周明远",
        "专长": "轨道力学与对接系统",
    },
    "林夜霜": {
        "类型": "人物",
        "职位": "天琴站站长",
        "年龄": 45,
        "驻站": "天琴站",
        "导师": "陈星河",
        "专长": "月球地质与矿产分析",
    },
    "赵铁翼": {
        "类型": "人物",
        "职位": "深红站站长",
        "年龄": 52,
        "驻站": "深红站",
        "导师": "周明远",
        "专长": "生命维持系统",
    },
    "苏晴岚": {
        "类型": "人物",
        "职位": "冰环站站长",
        "年龄": 39,
        "驻站": "冰环站",
        "导师": "林夜霜",
        "专长": "低温物理与氦-3提纯",
    },
    "周明远": {
        "类型": "人物",
        "职位": "联盟首席顾问（已退休）",
        "年龄": 72,
        "驻站": "极光站",
        "导师": "无（第一代太空人）",
        "专长": "太空站总体设计",
    },

    # ─── 设备/飞船 ───
    "天琴号": {
        "类型": "飞船",
        "型号": "QX-7 穿梭机",
        "所属站": "天琴站",
        "操作员": "林夜霜",
        "用途": "月球轨道-地表穿梭运输",
        "最大载重": "45 吨",
    },
    "赤焰号": {
        "类型": "飞船",
        "型号": "MX-3 远征舰",
        "所属站": "深红站",
        "操作员": "赵铁翼",
        "用途": "火星轨道-地表往返",
        "最大载重": "120 吨",
    },
    "极光之眼": {
        "类型": "设备",
        "型号": "TS-9000 望远镜阵列",
        "所属站": "极光站",
        "操作员": "周明远",
        "用途": "深空观测与小行星预警",
        "精度": "0.001 角秒",
    },
}


# ============================================================
# 查询接口
# ============================================================

def search_entities(query: str) -> list[dict]:
    """
    模糊搜索：在实体名称和所有字段值中查找匹配项。
    返回匹配实体的摘要列表。
    """
    query_lower = query.lower()
    results = []

    for name, data in KNOWLEDGE_BASE.items():
        # 名字匹配
        if query_lower in name.lower():
            results.append({"名称": name, "类型": data["类型"], "摘要": _summarize(name, data)})
            continue
        # 字段值匹配
        for field, value in data.items():
            if isinstance(value, str) and query_lower in value.lower():
                results.append({"名称": name, "类型": data["类型"], "摘要": _summarize(name, data)})
                break

    return results if results else [{"error": f"未找到与 '{query}' 相关的实体"}]


def lookup_entity(entity: str, field: str = "") -> str:
    """
    精确查询：返回实体的指定字段，或返回全部属性。
    """
    if entity not in KNOWLEDGE_BASE:
        # 模糊匹配提示
        similar = [k for k in KNOWLEDGE_BASE if entity in k or k in entity]
        if similar:
            return f"未找到实体 '{entity}'，你是否在找：{', '.join(similar)}？"
        return f"未找到实体 '{entity}'。可用实体：{', '.join(KNOWLEDGE_BASE.keys())}"

    data = KNOWLEDGE_BASE[entity]

    if not field:
        return f"{entity} 的全部属性：" + "；".join(f"{k}: {v}" for k, v in data.items())

    if field in data:
        return f"{entity} → {field}: {data[field]}"

    return f"实体 '{entity}' 没有 '{field}' 属性。可用属性：{', '.join(data.keys())}"


def compare_entities(entity_a: str, entity_b: str, field: str) -> str:
    """
    比较两个实体的同一字段值。
    """
    if entity_a not in KNOWLEDGE_BASE:
        return f"未找到实体 '{entity_a}'"
    if entity_b not in KNOWLEDGE_BASE:
        return f"未找到实体 '{entity_b}'"

    data_a = KNOWLEDGE_BASE[entity_a]
    data_b = KNOWLEDGE_BASE[entity_b]

    if field not in data_a:
        return f"实体 '{entity_a}' 没有 '{field}' 属性"
    if field not in data_b:
        return f"实体 '{entity_b}' 没有 '{field}' 属性"

    val_a = data_a[field]
    val_b = data_b[field]

    result = f"{entity_a} 的 {field}: {val_a}\n{entity_b} 的 {field}: {val_b}\n"

    # 数值比较
    if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
        diff = val_a - val_b
        if diff > 0:
            result += f"{entity_a} 比 {entity_b} 多/大 {abs(diff)}"
        elif diff < 0:
            result += f"{entity_b} 比 {entity_a} 多/大 {abs(diff)}"
        else:
            result += "两者相同"

    return result


def _summarize(name: str, data: dict) -> str:
    """生成实体的一行摘要"""
    entity_type = data.get("类型", "未知")
    if entity_type == "太空站":
        return f"{name}（{entity_type}）— 位置: {data.get('位置', '?')}，人口: {data.get('人口', '?')}"
    elif entity_type == "人物":
        return f"{name}（{entity_type}）— {data.get('职位', '?')}，驻站: {data.get('驻站', '?')}"
    elif entity_type in ("飞船", "设备"):
        return f"{name}（{entity_type}）— {data.get('用途', '?')}，所属: {data.get('所属站', '?')}"
    return f"{name}（{entity_type}）"
