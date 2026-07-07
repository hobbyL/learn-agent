"""
太空基地执行工具 —— Function Calling 工具层
=============================================

把 knowledge_base 的"有状态世界"操作包装成 OpenAI Function Calling 工具，
供内层执行器（executor.py 的 ReAct 循环）调用。

与 03/08 工具层的关键区别：
    03/08 的工具是"只读查询"——查了不改变世界。
    本项目的工具会**真实修改基地状态**（get_base_state() 返回的可变 dict）：
        - mine_resource 增加资源库存
        - build_module 扣减资源、标记模块完成
    因此工具的返回不仅是"信息"，更是"对世界的一次改动"。

失败设计（这是本项目的灵魂）：
    失败必须"可解释 + 可通过重规划绕过"，才能演示 re-planning 的价值。
    以**确定性条件失败**为主，让上层 LLM 能读懂失败原因并规划出补救子任务：
        - build_module 资源不足 → 上层应插入 mine_resource 前置子任务
        - build_module 前置模块未完成 → 上层应先规划前置模块
        - 环境事件禁止舱外作业 → 上层应先 check_environment、等待或改序
    少量随机失败（采集难度过高）作为点缀，通过 set_random_seed 保证 demo 可复现。

每个失败都返回清晰的中文错误串（以"失败："开头），让 LLM 一眼看懂症结。
"""

import os
import random

from knowledge_base import (
    EQUIPMENT,
    ENVIRONMENT_EVENTS,
    MODULES,
    RESOURCES,
    get_base_state,
    lookup_entity,
)


# ============================================================
# 随机性控制（保证 demo 可复现）
# ============================================================

# 独立的 Random 实例，避免污染全局 random 状态。
# 采集难度导致的随机失败用它决定，seed 固定则每次 demo 结果一致。
_RNG = random.Random()


def set_random_seed(seed: int | None) -> None:
    """
    设置随机种子，控制"采集难度导致的随机失败"是否可复现。

    seed 为 None 时用系统熵源（真随机）；给定整数则可复现。
    也可通过环境变量 RANDOM_SEED 设置（见模块底部初始化）。
    """
    _RNG.seed(seed)


# 采集难度 → 随机失败概率。
# 难度越高越容易采集失败（模拟设备卡顿、矿脉贫瘠等），
# 但概率刻意压低，保证 demo 主要走"确定性失败"路径，随机失败只是点缀。
_DIFFICULTY_FAIL_RATE = {
    "低": 0.0,
    "中": 0.0,
    "高": 0.15,
    "极高": 0.35,
}


# ============================================================
# 工具实现
# ============================================================

def mine_resource(resource: str, amount: int) -> str:
    """
    采集指定资源，成功则增加基地库存。

    失败条件：
        1. 资源名不存在 → 明确报错
        2. 采集地点在舱外，且当前环境事件影响"舱外"作业（太阳风暴/流星雨）
           → 舱外采集受阻（可解释：上层应先 check_environment 或改序）
        3. 采集难度高/极高时，按概率随机失败（矿脉贫瘠/设备卡顿）

    成功则把 amount 加到 state["资源库存"][resource]。
    """
    if resource not in RESOURCES:
        available = "、".join(RESOURCES.keys())
        return f"失败：未知资源 '{resource}'。可采集资源：{available}"

    if amount <= 0:
        return f"失败：采集数量必须为正整数，收到 {amount}"

    state = get_base_state()
    res_data = RESOURCES[resource]
    location = res_data["采集地点"]
    difficulty = res_data["采集难度"]

    # ── 环境事件判定 ──
    # 采集地点不在"基地合成车间"的，视为舱外野外作业，会被舱外类环境事件打断。
    # "基地合成车间"是舱内合成，不受太阳风暴/流星雨影响。
    is_outdoor = location != "基地合成车间"
    event = state["当前环境事件"]
    if is_outdoor and event is not None:
        affected = ENVIRONMENT_EVENTS[event]["受影响作业"]
        if "舱外" in affected:
            return (
                f"失败：当前发生「{event}」（{ENVIRONMENT_EVENTS[event]['影响描述']}），"
                f"采集地点「{location}」属舱外作业，无法采集 {resource}。"
                f"建议先 check_environment 确认，或改为采集舱内合成资源。"
            )

    # ── 随机失败判定（采集难度）──
    fail_rate = _DIFFICULTY_FAIL_RATE.get(difficulty, 0.0)
    if fail_rate > 0 and _RNG.random() < fail_rate:
        return (
            f"失败：采集 {resource} 时遇到困难（采集难度「{difficulty}」，"
            f"矿脉贫瘠/设备卡顿）。可重试，或先调度更适合的设备。"
        )

    # ── 成功：增加库存 ──
    state["资源库存"][resource] = state["资源库存"].get(resource, 0) + amount
    new_stock = state["资源库存"][resource]
    return (
        f"成功：采集 {resource}×{amount}（产地 {location}）。"
        f"当前 {resource} 库存：{new_stock}"
    )


def check_environment() -> str:
    """
    查询当前环境状态，返回当前事件及其影响的作业类型。

    executor 在执行舱外作业前应先调用它，判断是否会被打断。
    无事件时返回"环境正常"。
    """
    state = get_base_state()
    event = state["当前环境事件"]
    if event is None:
        return "环境正常：当前无异常事件，舱内/舱外作业均可正常进行。"

    data = ENVIRONMENT_EVENTS[event]
    affected = "、".join(data["受影响作业"])
    return (
        f"当前环境事件：{event}。{data['影响描述']}。"
        f"受影响的作业类型：{affected}。"
        f"涉及这些作业类型的任务当前会失败，请规避或等待。"
    )


def build_module(module: str) -> str:
    """
    建造指定模块。这是最容易失败、也最能演示重规划的工具。

    失败条件（按顺序检查，返回第一个命中的原因）：
        1. 模块名不存在
        2. 模块已建造完成（幂等保护）
        3. 前置模块未完成 → 上层应先规划前置模块
        4. 所需设备不可用 → 上层应先修复/调度设备
        5. 当前环境事件禁止该模块的"作业类型" → 上层应改序或等待
        6. 所需资源库存不足 → 上层应插入 mine_resource 前置子任务

    成功则：扣减资源、标记模块状态为"已建造"、加入"已完成模块"列表。
    """
    if module not in MODULES:
        available = "、".join(MODULES.keys())
        return f"失败：未知模块 '{module}'。可建造模块：{available}"

    state = get_base_state()
    mod_data = MODULES[module]

    # 1. 幂等保护：已建造则直接返回
    if module in state["已完成模块"]:
        return f"提示：模块「{module}」已经建造完成，无需重复建造。"

    # 2. 前置模块检查
    prereqs = mod_data["前置模块"]
    missing_prereq = [p for p in prereqs if p not in state["已完成模块"]]
    if missing_prereq:
        return (
            f"失败：建造「{module}」需要前置模块 {missing_prereq} 先完成，"
            f"但它们尚未建造。请先规划并完成前置模块。"
        )

    # 3. 设备可用性检查
    need_equipment = mod_data["所需设备"]
    unavailable = [
        eq for eq in need_equipment
        if not state["设备可用"].get(eq, False)
    ]
    if unavailable:
        return (
            f"失败：建造「{module}」需要设备 {need_equipment}，"
            f"但 {unavailable} 当前不可用。请先修复或调度这些设备。"
        )

    # 4. 环境事件检查（模块的作业类型是否被当前事件禁止）
    work_type = mod_data["作业类型"]
    event = state["当前环境事件"]
    if event is not None:
        affected = ENVIRONMENT_EVENTS[event]["受影响作业"]
        if work_type in affected:
            return (
                f"失败：建造「{module}」属「{work_type}」作业，"
                f"当前发生「{event}」（{ENVIRONMENT_EVENTS[event]['影响描述']}），"
                f"该作业被禁止。请等待环境恢复或调整执行顺序。"
            )

    # 5. 资源充足性检查
    need_resources = mod_data["所需资源"]
    shortage = {}
    for res, qty in need_resources.items():
        have = state["资源库存"].get(res, 0)
        if have < qty:
            shortage[res] = {"需要": qty, "现有": have, "缺口": qty - have}
    if shortage:
        detail = "、".join(
            f"{res}(需{info['需要']}/有{info['现有']}/缺{info['缺口']})"
            for res, info in shortage.items()
        )
        return (
            f"失败：建造「{module}」资源不足 —— {detail}。"
            f"请先采集（mine_resource）补足缺口资源再建造。"
        )

    # ── 全部通过：扣减资源、标记完成 ──
    for res, qty in need_resources.items():
        state["资源库存"][res] -= qty
    state["模块状态"][module] = "已建造"
    state["已完成模块"].append(module)
    return (
        f"成功：建造「{module}」完成（{work_type}作业，耗时 {mod_data['建造耗时']}）。"
        f"已扣减资源：{need_resources}。"
        f"当前已完成模块：{state['已完成模块']}"
    )


def transport(item: str, destination: str) -> str:
    """
    运输物资到指定目的地。

    失败条件：
        1. 运输飞船不可用
        2. 当前环境事件影响"运输"作业（轨道窗口关闭）

    成功仅表示"物资已就位"，不改变资源数量（本项目运输是逻辑步骤，
    真正影响库存的是 mine_resource/build_module）。设计为轻量成功，
    主要用于让 LLM 在计划里表达"运输"这一环节，并暴露运输类失败。
    """
    state = get_base_state()

    # 1. 运输飞船可用性
    if not state["设备可用"].get("运输飞船", False):
        return "失败：运输飞船当前不可用，无法执行运输。请先修复或调度运输飞船。"

    # 2. 环境事件（运输类）
    event = state["当前环境事件"]
    if event is not None:
        affected = ENVIRONMENT_EVENTS[event]["受影响作业"]
        if "运输" in affected:
            return (
                f"失败：当前发生「{event}」（{ENVIRONMENT_EVENTS[event]['影响描述']}），"
                f"运输作业受阻，无法将 {item} 运往 {destination}。请等待窗口开启。"
            )

    return f"成功：已将 {item} 运输至 {destination}。"


def lookup(name: str, field: str = "") -> str:
    """
    查询实体信息（薄包装 knowledge_base.lookup_entity）。

    executor 在执行子任务时可用它确认模块的资源需求、前置依赖等，
    避免"盲目建造"。field 为空返回全部属性。
    """
    return lookup_entity(name, field)


def check_inventory() -> str:
    """
    查询当前资源库存、设备可用性和已完成模块。

    executor 在采集/建造前用它掌握"现在手里有什么"，
    是判断资源是否充足的第一手依据。
    """
    state = get_base_state()
    inv = state["资源库存"]
    inv_text = "、".join(f"{res}×{qty}" for res, qty in inv.items())

    done = state["已完成模块"]
    done_text = "、".join(done) if done else "（暂无）"

    unavailable_eq = [
        eq for eq, ok in state["设备可用"].items() if not ok
    ]
    eq_text = "、".join(unavailable_eq) if unavailable_eq else "全部可用"

    return (
        f"【库存快照】\n"
        f"资源库存：{inv_text}\n"
        f"已完成模块：{done_text}\n"
        f"不可用设备：{eq_text}\n"
        f"当前环境事件：{state['当前环境事件'] or '正常'}"
    )


# ============================================================
# OpenAI Function Calling Schema
# ============================================================
# 格式对齐 03-react-agent/tools.py 的 TOOLS_SCHEMA。
# 这份 schema 会作为 tools 参数传给 chat.completions.create，
# 让 LLM 知道有哪些工具、每个工具的参数结构。

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "mine_resource",
            "description": (
                "采集指定资源，成功则增加基地库存。"
                "采集地点在舱外时会受太阳风暴/流星雨等舱外事件影响而失败。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "resource": {
                        "type": "string",
                        "description": "资源名称（如'钛矿'、'硅晶'、'碳纤维'）",
                    },
                    "amount": {
                        "type": "integer",
                        "description": "采集数量（正整数）",
                    },
                },
                "required": ["resource", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_environment",
            "description": "查询当前环境事件及其影响的作业类型。执行舱外作业前应先调用。",
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
            "name": "build_module",
            "description": (
                "建造指定模块。会检查前置模块/设备/环境/资源，任一不满足则失败并说明原因。"
                "成功则扣减所需资源并标记模块完成。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "module": {
                        "type": "string",
                        "description": "模块名称（如'居住舱'、'太阳能阵列'、'实验室'）",
                    },
                },
                "required": ["module"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transport",
            "description": "运输物资到指定目的地。运输飞船不可用或轨道窗口关闭时失败。",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {
                        "type": "string",
                        "description": "要运输的物资名称",
                    },
                    "destination": {
                        "type": "string",
                        "description": "运输目的地",
                    },
                },
                "required": ["item", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup",
            "description": "查询实体信息（模块的所需资源/前置依赖、资源的采集地点等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "实体名称（模块/资源/设备/团队/环境事件）",
                    },
                    "field": {
                        "type": "string",
                        "description": "要查询的字段名（如'所需资源'、'前置模块'）；留空则返回全部属性",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_inventory",
            "description": "查询当前资源库存、已完成模块、不可用设备和当前环境事件。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


# ============================================================
# 工具分发
# ============================================================
# 名称 → 函数映射，execute_tool 统一入口（对齐 03/08 的分发模式）。

_TOOL_FUNCS = {
    "mine_resource": mine_resource,
    "check_environment": check_environment,
    "build_module": build_module,
    "transport": transport,
    "lookup": lookup,
    "check_inventory": check_inventory,
}


def execute_tool(name: str, args: dict) -> str:
    """
    执行工具调用，返回结果字符串。

    统一处理：
        - 未知工具名
        - 参数不匹配（TypeError）
    错误一律以可读中文串返回，交给上层 LLM 消化（不抛异常中断循环）。
    """
    func = _TOOL_FUNCS.get(name)
    if func is None:
        available = "、".join(_TOOL_FUNCS.keys())
        return f"失败：未知工具 '{name}'。可用工具：{available}"

    try:
        return func(**(args or {}))
    except TypeError as e:
        return f"失败：调用 '{name}' 参数不匹配（{e}）。请检查参数名和类型。"


# ============================================================
# 模块初始化：从环境变量读取随机种子
# ============================================================
# 允许通过 .env 的 RANDOM_SEED 固定随机失败序列，便于 demo 复现。
# 未设置则保持真随机。

_seed_env = os.environ.get("RANDOM_SEED", "").strip()
if _seed_env:
    try:
        set_random_seed(int(_seed_env))
    except ValueError:
        pass  # 非法 seed 忽略，保持真随机


# ============================================================
# 快速验证（不调用 LLM，直接操作状态）
# ============================================================

if __name__ == "__main__":
    from knowledge_base import reset_base_state, set_environment_event

    print("=== 太空基地工具层快速验证 ===\n")

    reset_base_state()
    set_random_seed(42)  # 固定随机，保证可复现

    print("▸ check_inventory():")
    print(check_inventory())

    print("\n▸ check_environment():")
    print(check_environment())

    print("\n▸ build_module('储物仓')（资源应充足，前置为空）:")
    print(build_module("储物仓"))

    print("\n▸ build_module('实验室')（前置未完成，应失败）:")
    print(build_module("实验室"))

    print("\n▸ mine_resource('铝合金', 5)（舱内合成，应成功）:")
    print(mine_resource("铝合金", 5))

    print("\n▸ 触发太阳风暴，再采集钛矿（舱外，应失败）:")
    set_environment_event("太阳风暴")
    print(mine_resource("钛矿", 3))

    print("\n▸ 太阳风暴下建造居住舱（舱外作业，应失败）:")
    print(build_module("居住舱"))

    print("\n▸ 恢复环境，再建居住舱（资源可能不足）:")
    set_environment_event(None)
    print(build_module("居住舱"))

    print("\n▸ execute_tool 分发验证:")
    print(execute_tool("check_environment", {}))
    print(execute_tool("unknown_tool", {}))

    print("\n工具层验证通过 ✓")
