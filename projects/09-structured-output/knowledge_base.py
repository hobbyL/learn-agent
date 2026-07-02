"""
游戏工作室 —— 虚构知识库
========================

约 25 个实体构成的虚构游戏公司世界，专为结构化输出提取练习设计。
主题：「星火互娱」游戏工作室，下辖多个项目组开发不同类型的游戏。

实体类型：
- 工作室（1 个）：星火互娱
- 项目组（4 个）：破晓组、深渊组、星轨组、幻境组
- 游戏作品（4 个）：对应 4 个项目组的产品
- 开发者（8 个）：分布在各项目组
- 技术栈（6 个）：引擎、框架、中间件等
- 里程碑（6 个）：各项目的关键节点

设计重点：
- 实体间有丰富的多层关系
- 工作室 → 项目组 → 成员 → 技能
- 项目组 → 游戏作品 → 技术栈 → 里程碑
- 字段类型多样：字符串、数字、列表、嵌套对象
"""

# ============================================================
# 知识库数据
# ============================================================

KNOWLEDGE_BASE: dict[str, dict] = {

    # ─── 工作室（1 个）───
    "星火互娱": {
        "类型": "工作室",
        "全称": "星火互动娱乐科技有限公司",
        "创始人": "陈志远",
        "成立年份": 2018,
        "员工总数": 120,
        "总部": "深圳南山科技园",
        "项目组": ["破晓组", "深渊组", "星轨组", "幻境组"],
        "愿景": "用技术和创意打造世界级游戏体验",
    },

    # ─── 项目组（4 个）───
    "破晓组": {
        "类型": "项目组",
        "工作室": "星火互娱",
        "负责人": "林昊天",
        "成员数": 25,
        "方向": "开放世界 RPG",
        "状态": "研发中",
        "成立年份": 2019,
        "核心成员": ["林昊天", "苏晴", "张鹏飞", "王芷兰"],
        "技术栈": ["Unreal Engine 5", "C++", "Houdini", "Wwise"],
    },
    "深渊组": {
        "类型": "项目组",
        "工作室": "星火互娱",
        "负责人": "赵铁柱",
        "成员数": 18,
        "方向": "Roguelike 动作",
        "状态": "已发布",
        "成立年份": 2020,
        "核心成员": ["赵铁柱", "陈雨萱", "刘星河"],
        "技术栈": ["Unity 2023", "C#", "DOTs", "Addressables"],
    },
    "星轨组": {
        "类型": "项目组",
        "工作室": "星火互娱",
        "负责人": "孙小明",
        "成员数": 15,
        "方向": "太空策略 SLG",
        "状态": "测试中",
        "成立年份": 2021,
        "核心成员": ["孙小明", "周静"],
        "技术栈": ["Godot 4", "GDScript", "Nakama", "Redis"],
    },
    "幻境组": {
        "类型": "项目组",
        "工作室": "星火互娱",
        "负责人": "李梦琪",
        "成员数": 10,
        "方向": "VR 解谜冒险",
        "状态": "预研中",
        "成立年份": 2023,
        "核心成员": ["李梦琪", "何远航"],
        "技术栈": ["Unreal Engine 5", "OpenXR", "MetaHuman", "Niagara"],
    },

    # ─── 游戏作品（4 个）───
    "破晓传说": {
        "类型": "游戏作品",
        "全称": "破晓传说：永夜之光",
        "项目组": "破晓组",
        "类别": "开放世界 ARPG",
        "引擎": "Unreal Engine 5",
        "平台": ["PC", "PS5", "Xbox Series X"],
        "开发周期": "4 年",
        "当前阶段": "Alpha 测试",
        "预计上线": "2025-Q3",
        "特色": "程序化地形生成 + 动态天气系统",
    },
    "深渊回响": {
        "类型": "游戏作品",
        "全称": "深渊回响：命运轮回",
        "项目组": "深渊组",
        "类别": "Roguelike 动作",
        "引擎": "Unity 2023",
        "平台": ["PC", "Nintendo Switch", "Mobile"],
        "开发周期": "2 年",
        "当前阶段": "运营中",
        "上线日期": "2023-11",
        "特色": "DOTs 高性能 ECS 架构 + 随机地牢生成",
    },
    "星轨纪元": {
        "类型": "游戏作品",
        "全称": "星轨纪元：银河征途",
        "项目组": "星轨组",
        "类别": "太空策略 SLG",
        "引擎": "Godot 4",
        "平台": ["PC", "Mobile"],
        "开发周期": "2.5 年",
        "当前阶段": "封闭测试",
        "预计上线": "2025-Q1",
        "特色": "实时多人对战 + 程序化星系生成",
    },
    "幻境之门": {
        "类型": "游戏作品",
        "全称": "幻境之门：维度裂缝",
        "项目组": "幻境组",
        "类别": "VR 解谜冒险",
        "引擎": "Unreal Engine 5",
        "平台": ["Meta Quest 3", "PSVR2"],
        "开发周期": "预研阶段",
        "当前阶段": "概念验证",
        "预计上线": "2026-Q2",
        "特色": "MetaHuman 实时表情捕捉 + 物理交互解谜",
    },

    # ─── 开发者（8 个）───
    "林昊天": {
        "类型": "开发者",
        "角色": "技术总监",
        "项目组": "破晓组",
        "经验年限": 12,
        "专长": "图形渲染与引擎架构",
        "技能": ["C++", "Unreal Engine", "Vulkan", "HLSL", "性能优化"],
        "教育": "清华大学计算机系硕士",
        "曾就职": "腾讯天美工作室",
    },
    "苏晴": {
        "类型": "开发者",
        "角色": "主程序",
        "项目组": "破晓组",
        "经验年限": 8,
        "专长": "游戏逻辑与 AI 系统",
        "技能": ["C++", "Unreal Engine", "行为树", "状态机", "Lua"],
        "教育": "浙江大学计算机系本科",
        "曾就职": "网易雷火工作室",
    },
    "张鹏飞": {
        "类型": "开发者",
        "角色": "TA（技术美术）",
        "项目组": "破晓组",
        "经验年限": 6,
        "专长": "程序化内容生成",
        "技能": ["Houdini", "Substance Designer", "HLSL", "Python", "地形生成"],
        "教育": "中国美术学院数字媒体硕士",
        "曾就职": "米哈游",
    },
    "王芷兰": {
        "类型": "开发者",
        "角色": "音频设计师",
        "项目组": "破晓组",
        "经验年限": 5,
        "专长": "空间音频与动态配乐",
        "技能": ["Wwise", "FMOD", "Pro Tools", "空间音频", "自适应音乐"],
        "教育": "伯克利音乐学院电子音乐制作",
        "曾就职": "育碧上海",
    },
    "赵铁柱": {
        "类型": "开发者",
        "角色": "主程序兼项目负责人",
        "项目组": "深渊组",
        "经验年限": 10,
        "专长": "高性能 ECS 架构",
        "技能": ["C#", "Unity", "DOTs/ECS", "网络同步", "性能分析"],
        "教育": "北京大学信息科学本科",
        "曾就职": "莉莉丝游戏",
    },
    "陈雨萱": {
        "类型": "开发者",
        "角色": "关卡设计师",
        "项目组": "深渊组",
        "经验年限": 4,
        "专长": "程序化地牢生成",
        "技能": ["Unity", "C#", "PCG 算法", "Tilemap", "Lua"],
        "教育": "同济大学软件工程本科",
        "曾就职": "叠纸游戏",
    },
    "刘星河": {
        "类型": "开发者",
        "角色": "服务端工程师",
        "项目组": "深渊组",
        "经验年限": 7,
        "专长": "分布式游戏后端",
        "技能": ["Go", "Redis", "MongoDB", "gRPC", "Docker"],
        "教育": "华中科技大学计算机系硕士",
        "曾就职": "字节跳动",
    },
    "孙小明": {
        "类型": "开发者",
        "角色": "全栈工程师兼项目负责人",
        "项目组": "星轨组",
        "经验年限": 9,
        "专长": "独立游戏开发与网络架构",
        "技能": ["GDScript", "Godot", "Nakama", "TypeScript", "网络编程"],
        "教育": "南京大学软件工程本科",
        "曾就职": "独立开发者",
    },

    # ─── 技术栈（6 个）───
    "Unreal Engine 5": {
        "类型": "技术栈",
        "分类": "游戏引擎",
        "使用项目组": ["破晓组", "幻境组"],
        "版本": "5.3",
        "特性": ["Nanite", "Lumen", "World Partition", "MetaHuman"],
        "适用场景": "3A 级大型项目、VR 项目",
    },
    "Unity 2023": {
        "类型": "技术栈",
        "分类": "游戏引擎",
        "使用项目组": ["深渊组"],
        "版本": "2023.2 LTS",
        "特性": ["DOTs/ECS", "Addressables", "URP/HDRP", "Netcode"],
        "适用场景": "中型项目、跨平台、手游",
    },
    "Godot 4": {
        "类型": "技术栈",
        "分类": "游戏引擎",
        "使用项目组": ["星轨组"],
        "版本": "4.2",
        "特性": ["GDScript 2.0", "Vulkan 渲染", "多人网络", "开源免费"],
        "适用场景": "独立游戏、轻量策略、快速原型",
    },
    "Houdini": {
        "类型": "技术栈",
        "分类": "DCC 工具",
        "使用项目组": ["破晓组"],
        "版本": "20.0",
        "特性": ["程序化建模", "地形生成", "特效模拟", "HDA 资产"],
        "适用场景": "程序化内容生成、大世界地形",
    },
    "Wwise": {
        "类型": "技术栈",
        "分类": "音频中间件",
        "使用项目组": ["破晓组"],
        "版本": "2023.1",
        "特性": ["空间音频", "交互式音乐", "动态混音", "性能分析"],
        "适用场景": "3A 级音频设计、空间音频",
    },
    "Nakama": {
        "类型": "技术栈",
        "分类": "游戏服务器",
        "使用项目组": ["星轨组"],
        "版本": "3.20",
        "特性": ["实时多人", "排行榜", "匹配系统", "开源"],
        "适用场景": "多人在线游戏后端",
    },

    # ─── 里程碑（6 个）───
    "破晓传说-Alpha": {
        "类型": "里程碑",
        "游戏": "破晓传说",
        "项目组": "破晓组",
        "日期": "2024-06",
        "事件": "Alpha 版本内测",
        "成果": "完成主线前 3 章、核心战斗系统、开放世界基础框架",
    },
    "破晓传说-技术Demo": {
        "类型": "里程碑",
        "游戏": "破晓传说",
        "项目组": "破晓组",
        "日期": "2023-01",
        "事件": "技术 Demo 展示",
        "成果": "Nanite + Lumen 完整渲染管线验证通过",
    },
    "破晓传说-立项": {
        "类型": "里程碑",
        "游戏": "破晓传说",
        "项目组": "破晓组",
        "日期": "2021-03",
        "事件": "项目立项",
        "成果": "核心玩法原型 + 美术风格确定",
    },
    "深渊回响-上线": {
        "类型": "里程碑",
        "游戏": "深渊回响",
        "项目组": "深渊组",
        "日期": "2023-11",
        "事件": "正式上线",
        "成果": "Steam/Switch 双平台首发，首周 10 万下载",
    },
    "深渊回响-DLC": {
        "类型": "里程碑",
        "游戏": "深渊回响",
        "项目组": "深渊组",
        "日期": "2024-03",
        "事件": "DLC「虚空之主」发布",
        "成果": "新增 3 个角色、50 层新地牢、PVP 模式",
    },
    "星轨纪元-封测": {
        "类型": "里程碑",
        "游戏": "星轨纪元",
        "项目组": "星轨组",
        "日期": "2024-09",
        "事件": "封闭测试开启",
        "成果": "500 人同时在线压力测试通过",
    },
}


# ============================================================
# 查询接口
# ============================================================

def get_full_knowledge_text() -> str:
    """
    将整个知识库转为可阅读的纯文本，供 LLM 提取时作为上下文使用。

    返回格式化的文本描述，包含所有实体和属性。
    """
    lines = []
    lines.append("=== 星火互娱游戏工作室知识库 ===\n")

    # 按类型分组输出
    type_order = ["工作室", "项目组", "游戏作品", "开发者", "技术栈", "里程碑"]
    grouped: dict[str, list[tuple[str, dict]]] = {t: [] for t in type_order}

    for name, data in KNOWLEDGE_BASE.items():
        entity_type = data.get("类型", "其他")
        if entity_type in grouped:
            grouped[entity_type].append((name, data))
        else:
            grouped.setdefault("其他", []).append((name, data))

    for entity_type in type_order:
        entities = grouped.get(entity_type, [])
        if not entities:
            continue

        lines.append(f"\n【{entity_type}】")
        lines.append("─" * 40)

        for name, data in entities:
            lines.append(f"\n■ {name}")
            for field, value in data.items():
                if field == "类型":
                    continue
                if isinstance(value, list):
                    value_str = "、".join(str(v) for v in value)
                else:
                    value_str = str(value)
                lines.append(f"  {field}: {value_str}")

    return "\n".join(lines)


def search_entities(query: str) -> list[dict]:
    """
    模糊搜索：在实体名称和所有字段值中查找匹配项。
    返回匹配实体的摘要列表。
    """
    query_lower = query.lower()
    results = []

    for name, data in KNOWLEDGE_BASE.items():
        if query_lower in name.lower():
            results.append({
                "名称": name,
                "类型": data.get("类型", "未知"),
                "摘要": _summarize(name, data),
            })
            continue
        for field, value in data.items():
            if isinstance(value, str) and query_lower in value.lower():
                results.append({
                    "名称": name,
                    "类型": data.get("类型", "未知"),
                    "摘要": _summarize(name, data),
                })
                break
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and query_lower in item.lower():
                        results.append({
                            "名称": name,
                            "类型": data.get("类型", "未知"),
                            "摘要": _summarize(name, data),
                        })
                        break

    return results if results else [{"error": f"未找到与 '{query}' 相关的实体"}]


def lookup_entity(name: str, field: str = "") -> str:
    """精确查询实体。field 为空时返回全部属性。"""
    if name not in KNOWLEDGE_BASE:
        similar = [k for k in KNOWLEDGE_BASE if name in k or k in name]
        if similar:
            return f"未找到 '{name}'，你是否在找：{', '.join(similar)}？"
        return f"未找到实体 '{name}'。可用实体：{', '.join(KNOWLEDGE_BASE.keys())}"

    data = KNOWLEDGE_BASE[name]

    if not field:
        attrs = []
        for k, v in data.items():
            if isinstance(v, list):
                attrs.append(f"{k}: {', '.join(str(i) for i in v)}")
            else:
                attrs.append(f"{k}: {v}")
        return f"{name} 的全部属性 —— {'；'.join(attrs)}"

    if field in data:
        value = data[field]
        if isinstance(value, list):
            return f"{name} → {field}: {', '.join(str(i) for i in value)}"
        return f"{name} → {field}: {value}"

    return f"实体 '{name}' 没有 '{field}' 属性。可用属性：{', '.join(data.keys())}"


def _summarize(name: str, data: dict) -> str:
    """生成实体的单行摘要。"""
    entity_type = data.get("类型", "未知")
    if entity_type == "工作室":
        return f"{name}（{entity_type}）— 创始人: {data.get('创始人', '?')}，员工: {data.get('员工总数', '?')} 人"
    elif entity_type == "项目组":
        return f"{name}（{entity_type}）— 负责人: {data.get('负责人', '?')}，方向: {data.get('方向', '?')}"
    elif entity_type == "游戏作品":
        return f"{name}（{entity_type}）— 类别: {data.get('类别', '?')}，引擎: {data.get('引擎', '?')}"
    elif entity_type == "开发者":
        return f"{name}（{entity_type}）— 角色: {data.get('角色', '?')}，项目组: {data.get('项目组', '?')}"
    elif entity_type == "技术栈":
        return f"{name}（{entity_type}）— 分类: {data.get('分类', '?')}，版本: {data.get('版本', '?')}"
    elif entity_type == "里程碑":
        return f"{name}（{entity_type}）— 日期: {data.get('日期', '?')}，事件: {data.get('事件', '?')}"
    return f"{name}（{entity_type}）"


# ============================================================
# 快速验证
# ============================================================

if __name__ == "__main__":
    print("=== 游戏工作室知识库快速验证 ===\n")

    # 统计实体数量
    type_counts: dict[str, int] = {}
    for data in KNOWLEDGE_BASE.values():
        t = data.get("类型", "其他")
        type_counts[t] = type_counts.get(t, 0) + 1

    print(f"总实体数: {len(KNOWLEDGE_BASE)}")
    for t, c in type_counts.items():
        print(f"  {t}: {c} 个")

    print(f"\nsearch_entities('破晓'):")
    for r in search_entities("破晓"):
        print(f"  {r}")

    print(f"\nlookup_entity('林昊天'):")
    print(f"  {lookup_entity('林昊天')}")

    print(f"\nlookup_entity('破晓组', '核心成员'):")
    print(f"  {lookup_entity('破晓组', '核心成员')}")

    print(f"\n知识库文本长度: {len(get_full_knowledge_text())} 字符")

    print("\n知识库验证通过 ✓")
