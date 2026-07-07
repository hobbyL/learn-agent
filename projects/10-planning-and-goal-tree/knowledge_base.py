"""
新曙光基地 —— 太空基地建设知识库
====================================

约 35 个实体构成的虚构月球/火星基地世界，专为"任务规划与目标树 Agent"设计。
主题：人类在月球背面建立「新曙光基地」，需要采集资源、组装模块、逐步扩建。

实体类型：
- 资源 Resources（8 个）：钛矿、硅晶、氦-3、水冰、碳纤维、稀土、铝合金、聚合物
- 模块 Modules（8 个）：居住舱、太阳能阵列、推进器、通信塔、实验室、生命维持系统、储物仓、对接口
- 设备 Equipment（6 个）：采矿机器人、3D打印机、运输飞船、机械臂、焊接单元、诊断仪
- 团队 Teams（5 个）：工程队、采矿队、科研组、后勤组、指挥中心
- 环境事件 Environment（5 个）：太阳风暴、流星雨、轨道窗口、温度骤降、通信中断

设计重点：为"任务规划 + 依赖图 + 失败重规划"服务：
- 模块需要资源（居住舱需要钛矿×6 + 碳纤维×4 + 铝合金×3）
- 模块需要设备（组装需要 3D 打印机 / 机械臂 / 焊接单元）
- 模块有前置依赖（实验室必须在居住舱与太阳能阵列之后）
- 环境事件打断特定作业（太阳风暴 → 舱外作业失败）

与 07/09 知识库的关键区别：
    07/09 的知识库是"只读"的——查询不改变世界。
    本项目的世界是"有状态"的——执行工具会扣减资源库存、改变模块状态。
    因此除了静态定义（RESOURCES / MODULES...），还额外维护一份**可变的全局状态**
    （_BASE_STATE），tools 层执行时会修改它，规划器根据它判断当前进度。
"""

import copy


# ============================================================
# 静态知识库数据（世界的"设定"，不随执行改变）
# ============================================================

# ─── 资源（8 个）───
# 说明：初始存量是"基地已有的库存"；采集难度影响执行失败概率与耗时；
#      采集地点用于制造"运输"环节的依赖。
RESOURCES: dict[str, dict] = {
    "钛矿": {
        "类型": "资源",
        "初始存量": 4,
        "采集难度": "高",
        "采集地点": "环形山矿脉",
        "用途": "承重结构与舱体骨架",
    },
    "硅晶": {
        "类型": "资源",
        "初始存量": 6,
        "采集难度": "中",
        "采集地点": "月壤精炼站",
        "用途": "太阳能电池与芯片",
    },
    "氦-3": {
        "类型": "资源",
        "初始存量": 2,
        "采集难度": "极高",
        "采集地点": "极地月壤层",
        "用途": "聚变燃料与推进剂",
    },
    "水冰": {
        "类型": "资源",
        "初始存量": 5,
        "采集难度": "中",
        "采集地点": "永久阴影坑",
        "用途": "生命维持与电解制氧",
    },
    "碳纤维": {
        "类型": "资源",
        "初始存量": 8,
        "采集难度": "低",
        "采集地点": "基地合成车间",
        "用途": "轻量化舱体外壳",
    },
    "稀土": {
        "类型": "资源",
        "初始存量": 3,
        "采集难度": "高",
        "采集地点": "环形山矿脉",
        "用途": "通信天线与精密仪器",
    },
    "铝合金": {
        "类型": "资源",
        "初始存量": 10,
        "采集难度": "低",
        "采集地点": "基地合成车间",
        "用途": "通用结构件",
    },
    "聚合物": {
        "类型": "资源",
        "初始存量": 7,
        "采集难度": "低",
        "采集地点": "基地合成车间",
        "用途": "密封件与管路",
    },
}

# ─── 模块（8 个）───
# 说明：所需资源用 dict（资源名→数量）表达，支撑"资源不足则失败"的场景；
#      前置模块 支撑 DAG 的跨节点依赖；作业类型 决定它会被哪些环境事件打断。
MODULES: dict[str, dict] = {
    "居住舱": {
        "类型": "模块",
        "所需资源": {"钛矿": 6, "碳纤维": 4, "铝合金": 3},
        "所需设备": ["3D打印机", "机械臂"],
        "前置模块": [],
        "建造耗时": 3,
        "作业类型": "舱外",
        "初始状态": "未建造",
        "说明": "基地的核心生活区，几乎所有后续模块都直接或间接依赖它",
    },
    "太阳能阵列": {
        "类型": "模块",
        "所需资源": {"硅晶": 6, "铝合金": 2},
        "所需设备": ["机械臂", "焊接单元"],
        "前置模块": [],
        "建造耗时": 2,
        "作业类型": "舱外",
        "初始状态": "未建造",
        "说明": "基地主要电力来源，实验室等高耗能模块依赖它",
    },
    "生命维持系统": {
        "类型": "模块",
        "所需资源": {"水冰": 4, "聚合物": 3, "硅晶": 1},
        "所需设备": ["3D打印机", "诊断仪"],
        "前置模块": ["居住舱"],
        "建造耗时": 2,
        "作业类型": "舱内",
        "初始状态": "未建造",
        "说明": "提供氧气/水循环，必须在居住舱建好后安装",
    },
    "通信塔": {
        "类型": "模块",
        "所需资源": {"稀土": 3, "铝合金": 2, "硅晶": 1},
        "所需设备": ["机械臂", "焊接单元"],
        "前置模块": [],
        "建造耗时": 2,
        "作业类型": "舱外",
        "初始状态": "未建造",
        "说明": "地月通信中继，受通信中断事件影响",
    },
    "储物仓": {
        "类型": "模块",
        "所需资源": {"铝合金": 4, "碳纤维": 2},
        "所需设备": ["3D打印机"],
        "前置模块": [],
        "建造耗时": 1,
        "作业类型": "舱内",
        "初始状态": "未建造",
        "说明": "存放物资与备件，前置依赖最少，适合先行建造",
    },
    "实验室": {
        "类型": "模块",
        "所需资源": {"钛矿": 3, "硅晶": 2, "稀土": 1},
        "所需设备": ["3D打印机", "机械臂", "诊断仪"],
        "前置模块": ["居住舱", "太阳能阵列"],
        "建造耗时": 3,
        "作业类型": "舱内",
        "初始状态": "未建造",
        "说明": "科研核心，高耗能，必须在居住舱+太阳能阵列之后",
    },
    "对接口": {
        "类型": "模块",
        "所需资源": {"钛矿": 2, "铝合金": 3, "聚合物": 2},
        "所需设备": ["机械臂", "焊接单元"],
        "前置模块": ["居住舱"],
        "建造耗时": 2,
        "作业类型": "舱外",
        "初始状态": "未建造",
        "说明": "飞船停靠与人员进出通道",
    },
    "推进器": {
        "类型": "模块",
        "所需资源": {"氦-3": 2, "钛矿": 2, "铝合金": 2},
        "所需设备": ["焊接单元", "机械臂"],
        "前置模块": ["对接口"],
        "建造耗时": 3,
        "作业类型": "舱外",
        "初始状态": "未建造",
        "说明": "基地轨道微调，依赖稀缺的氦-3",
    },
}

# ─── 设备（6 个）───
# 说明：设备是模块建造的前置条件（工具）；可用状态在执行中可能因故障变为不可用。
EQUIPMENT: dict[str, dict] = {
    "采矿机器人": {
        "类型": "设备",
        "功能": "自动采集矿物资源",
        "初始可用": True,
        "说明": "资源采集任务的主力设备",
    },
    "3D打印机": {
        "类型": "设备",
        "功能": "打印舱体结构件",
        "初始可用": True,
        "说明": "多数模块组装的必需工具",
    },
    "运输飞船": {
        "类型": "设备",
        "功能": "在采集点与基地间运输物资",
        "初始可用": True,
        "说明": "受轨道窗口事件影响",
    },
    "机械臂": {
        "类型": "设备",
        "功能": "舱外精密装配",
        "初始可用": True,
        "说明": "舱外组装的关键设备",
    },
    "焊接单元": {
        "类型": "设备",
        "功能": "结构件焊接固定",
        "初始可用": True,
        "说明": "金属结构连接必需",
    },
    "诊断仪": {
        "类型": "设备",
        "功能": "系统检测与质量验收",
        "初始可用": True,
        "说明": "生命维持/实验室等精密模块的验收工具",
    },
}

# ─── 团队（5 个）───
# 说明：增加调度维度；可调度人数供规划器估算并行度（本项目顺序执行，人数仅作参考）。
TEAMS: dict[str, dict] = {
    "工程队": {
        "类型": "团队",
        "职责": "模块组装与结构施工",
        "可调度人数": 6,
        "说明": "承担绝大多数建造任务",
    },
    "采矿队": {
        "类型": "团队",
        "职责": "资源采集与初步精炼",
        "可调度人数": 4,
        "说明": "操作采矿机器人",
    },
    "科研组": {
        "类型": "团队",
        "职责": "实验室运营与技术验证",
        "可调度人数": 3,
        "说明": "实验室建成后接管",
    },
    "后勤组": {
        "类型": "团队",
        "职责": "物资运输与库存管理",
        "可调度人数": 3,
        "说明": "操作运输飞船与储物仓",
    },
    "指挥中心": {
        "类型": "团队",
        "职责": "任务调度与环境监测",
        "可调度人数": 2,
        "说明": "发布环境预警，协调各队",
    },
}

# ─── 环境事件（5 个）───
# 说明：这是"失败触发器"——执行前 check_environment，若当前事件命中作业类型则任务失败。
#      受影响作业 用于精确匹配：太阳风暴只打断"舱外"作业，舱内作业不受影响。
ENVIRONMENT_EVENTS: dict[str, dict] = {
    "太阳风暴": {
        "类型": "环境事件",
        "影响描述": "高能粒子辐射，人员与机械臂无法在舱外作业",
        "触发条件": "太阳活动高峰",
        "受影响作业": ["舱外"],
    },
    "流星雨": {
        "类型": "环境事件",
        "影响描述": "微陨石撞击风险，暂停所有舱外施工",
        "触发条件": "轨道穿越碎片带",
        "受影响作业": ["舱外"],
    },
    "轨道窗口": {
        "类型": "环境事件",
        "影响描述": "运输飞船仅在窗口期可往返，窗口关闭时运输任务受阻",
        "触发条件": "地月相对位置周期",
        "受影响作业": ["运输"],
    },
    "温度骤降": {
        "类型": "环境事件",
        "影响描述": "极低温导致焊接与精密装配失败率上升",
        "触发条件": "进入月夜阴影区",
        "受影响作业": ["舱外", "焊接"],
    },
    "通信中断": {
        "类型": "环境事件",
        "影响描述": "地月通信丢失，需通信塔作业的任务暂停",
        "触发条件": "太阳合月遮挡",
        "受影响作业": ["通信"],
    },
}


# ============================================================
# 可变的基地全局状态（世界的"当前快照"，随执行改变）
# ============================================================
# 为什么单独维护而不直接改上面的静态 dict？
#   静态定义是"世界设定"，应保持只读（多次 demo 复用同一份设定）。
#   可变状态是"这一局的进度"，reset_base_state 时可以干净地重建，
#   不会污染原始设定。执行工具（后续批次的 tools.py）只改这里。

# 初始状态由静态定义派生，_BASE_STATE 是当前活动的可变副本。
_BASE_STATE: dict = {}


def _build_initial_state() -> dict:
    """
    从静态定义派生一份全新的初始状态。

    资源库存 从各资源的"初始存量"拷贝；
    模块状态 从各模块的"初始状态"拷贝；
    设备可用 从各设备的"初始可用"拷贝；
    当前环境事件 初始为 None（无异常）。
    """
    return {
        "当前阶段": "Phase-0 筹备",
        "资源库存": {name: data["初始存量"] for name, data in RESOURCES.items()},
        "模块状态": {name: data["初始状态"] for name, data in MODULES.items()},
        "设备可用": {name: data["初始可用"] for name, data in EQUIPMENT.items()},
        "已完成模块": [],
        "当前环境事件": None,  # None 表示环境正常；否则为 ENVIRONMENT_EVENTS 的某个 key
    }


def get_base_state() -> dict:
    """
    返回当前基地状态的引用（注意：是引用，调用方修改会直接生效）。

    tools 层执行采集/建造时通过这个引用扣减库存、更新模块状态。
    首次调用时惰性初始化，避免 import 副作用。
    """
    if not _BASE_STATE:
        reset_base_state()
    return _BASE_STATE


def reset_base_state() -> None:
    """
    重置基地状态到初始值（每次 demo/interactive 开始时调用）。

    用 clear + update 原地重建，保证已经持有 _BASE_STATE 引用的调用方
    也能看到重置后的值（不换对象，只换内容）。
    """
    global _BASE_STATE
    fresh = _build_initial_state()
    _BASE_STATE.clear()
    _BASE_STATE.update(fresh)


def set_environment_event(event_name: str | None) -> None:
    """
    设置当前环境事件（供 tools/executor 触发失败场景）。

    event_name 为 None 表示恢复正常；否则必须是 ENVIRONMENT_EVENTS 中的 key。
    非法名称会被忽略并保持原状（防御式，避免误设导致全流程卡死）。
    """
    state = get_base_state()
    if event_name is None or event_name in ENVIRONMENT_EVENTS:
        state["当前环境事件"] = event_name


# ============================================================
# 查询接口（供 planner 作上下文、tools 作校验）
# ============================================================

# 把 5 类实体合并成一张总表，方便统一检索。
# 用函数动态合并而非模块级常量，是为了让类型顺序稳定且语义清晰。
def _all_entities() -> dict[str, tuple[str, dict]]:
    """返回 {实体名: (分类标签, 数据dict)} 的合并总表。"""
    merged: dict[str, tuple[str, dict]] = {}
    for label, table in (
        ("资源", RESOURCES),
        ("模块", MODULES),
        ("设备", EQUIPMENT),
        ("团队", TEAMS),
        ("环境事件", ENVIRONMENT_EVENTS),
    ):
        for name, data in table.items():
            merged[name] = (label, data)
    return merged


def search_entities(query: str) -> list[dict]:
    """
    模糊搜索：在实体名称和字段值中查找匹配项。

    返回 [{type, name, data}]，data 是静态定义的深拷贝（避免调用方误改设定）。
    与 07/09 的 search 类似，但这里返回完整 data —— 因为规划器需要看到
    模块的"所需资源/前置依赖"才能正确拆解任务。
    """
    query_lower = query.lower()
    results: list[dict] = []

    for name, (label, data) in _all_entities().items():
        hit = query_lower in name.lower()
        if not hit:
            # 在字段值中查找（字符串值 / 列表值 / dict 的 key）
            for value in data.values():
                if isinstance(value, str) and query_lower in value.lower():
                    hit = True
                    break
                if isinstance(value, list) and any(
                    query_lower in str(item).lower() for item in value
                ):
                    hit = True
                    break
                if isinstance(value, dict) and any(
                    query_lower in str(k).lower() for k in value
                ):
                    hit = True
                    break
        if hit:
            results.append({
                "type": label,
                "name": name,
                "data": copy.deepcopy(data),
            })

    return results


def lookup_entity(name: str, field: str = "") -> str:
    """
    精确查询实体。

    - field 为空：返回实体全部属性
    - field 非空：返回指定字段值

    返回人类可读字符串（供 LLM 工具调用直接消费）。
    找不到时给出可用实体/字段提示，方便 Agent 纠错。
    """
    entities = _all_entities()
    if name not in entities:
        similar = [k for k in entities if name in k or k in name]
        if similar:
            return f"未找到 '{name}'，你是否在找：{', '.join(similar)}？"
        return f"未找到实体 '{name}'。"

    label, data = entities[name]

    if not field:
        attrs = "；".join(f"{k}: {_fmt_value(v)}" for k, v in data.items())
        return f"{name}（{label}）—— {attrs}"

    if field in data:
        return f"{name} → {field}: {_fmt_value(data[field])}"

    return f"实体 '{name}' 没有 '{field}' 属性。可用属性：{', '.join(data.keys())}"


def _fmt_value(value) -> str:
    """把列表/字典字段格式化为紧凑可读文本。"""
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}×{v}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return str(value)


def get_full_knowledge_text() -> str:
    """
    将整个知识库转为可阅读纯文本，供 planner 规划时作为上下文注入 prompt。

    组织顺序：资源 → 模块 → 设备 → 团队 → 环境事件。
    模块部分重点展开"所需资源/所需设备/前置模块"，因为这是 DAG 拆解的依据。
    """
    lines: list[str] = ["【新曙光基地 · 建设知识库】", ""]

    lines.append("== 资源（当前库存/采集难度/采集地点）==")
    for name, d in RESOURCES.items():
        lines.append(
            f"  - {name}：库存 {d['初始存量']}，难度 {d['采集难度']}，"
            f"产地 {d['采集地点']}（{d['用途']}）"
        )

    lines.append("")
    lines.append("== 模块（所需资源/设备/前置依赖/耗时/作业类型）==")
    for name, d in MODULES.items():
        need_res = "、".join(f"{k}×{v}" for k, v in d["所需资源"].items())
        need_eq = "、".join(d["所需设备"])
        prereq = "、".join(d["前置模块"]) if d["前置模块"] else "无"
        lines.append(
            f"  - {name}：需资源[{need_res}]，需设备[{need_eq}]，"
            f"前置[{prereq}]，耗时 {d['建造耗时']}，{d['作业类型']}作业。{d['说明']}"
        )

    lines.append("")
    lines.append("== 设备 ==")
    for name, d in EQUIPMENT.items():
        lines.append(f"  - {name}：{d['功能']}（{d['说明']}）")

    lines.append("")
    lines.append("== 团队 ==")
    for name, d in TEAMS.items():
        lines.append(f"  - {name}：{d['职责']}，可调度 {d['可调度人数']} 人")

    lines.append("")
    lines.append("== 环境事件（失败触发器）==")
    for name, d in ENVIRONMENT_EVENTS.items():
        affected = "、".join(d["受影响作业"])
        lines.append(f"  - {name}：{d['影响描述']}（影响：{affected}作业）")

    return "\n".join(lines)


# ============================================================
# 快速验证入口
# ============================================================

if __name__ == "__main__":
    print("=== 新曙光基地知识库快速验证 ===\n")

    # 实体统计
    counts = {
        "资源": len(RESOURCES),
        "模块": len(MODULES),
        "设备": len(EQUIPMENT),
        "团队": len(TEAMS),
        "环境事件": len(ENVIRONMENT_EVENTS),
    }
    total = sum(counts.values())
    print("实体统计：")
    for label, n in counts.items():
        print(f"  {label}: {n}")
    print(f"  合计: {total} 个实体\n")

    # 基地初始状态
    reset_base_state()
    state = get_base_state()
    print("基地初始状态：")
    print(f"  当前阶段: {state['当前阶段']}")
    print(f"  资源库存: {state['资源库存']}")
    print(f"  已完成模块: {state['已完成模块']}")
    print(f"  当前环境事件: {state['当前环境事件']}\n")

    # 状态可变性验证：模拟一次采集
    print("模拟采集钛矿×2（直接改状态引用）：")
    state["资源库存"]["钛矿"] += 2
    print(f"  钛矿库存 -> {get_base_state()['资源库存']['钛矿']}")
    reset_base_state()
    print(f"  reset 后钛矿库存 -> {get_base_state()['资源库存']['钛矿']}\n")

    # search / lookup 验证
    print("search_entities('舱')：")
    for r in search_entities("舱"):
        print(f"  [{r['type']}] {r['name']}")

    print("\nlookup_entity('居住舱')：")
    print(" ", lookup_entity("居住舱"))

    print("\nlookup_entity('居住舱', '所需资源')：")
    print(" ", lookup_entity("居住舱", "所需资源"))

    print("\nlookup_entity('实验室', '前置模块')：")
    print(" ", lookup_entity("实验室", "前置模块"))

    print("\n--- get_full_knowledge_text() 前 600 字 ---")
    print(get_full_knowledge_text()[:600])
    print("...")

    print("\n知识库验证通过 ✓")
