"""
Agent 角色定义
==============

三位殖民委员会专家：
- 🔬 科学官：关注宜居性、生态、科研价值
- ⚔️ 军事官：关注防御态势、战略位置、安全威胁
- 💰 经济官：关注资源价值、开采成本、投资回报
"""

import json
import time
from openai import OpenAI
from tools import ROLE_TOOLS, execute_tool


# ============================================================
# Agent 角色配置
# ============================================================

AGENTS = {
    "科学官": {
        "emoji": "🔬",
        "color": "science",  # display.py 映射
        "system_prompt": (
            "你是星际殖民委员会的首席科学顾问，代号「科学官」。\n"
            "你的核心关注点是：\n"
            "1. 星球宜居性（大气、温度、重力是否适合人类长期生存）\n"
            "2. 生态系统丰富度（生物多样性、科研样本价值）\n"
            "3. 科研价值（特殊发现的学术和技术意义）\n"
            "4. 长期可持续性（生态承载力、环境恶化风险）\n\n"
            "你有专属工具 analyze_habitability 可以获取综合宜居性报告。\n"
            "你也可以用 search_planets 和 lookup_planet 查询任何星球数据。\n\n"
            "你的立场是：科学价值和人类宜居性是殖民选址的第一优先级。"
        ),
    },
    "军事官": {
        "emoji": "⚔️",
        "color": "military",
        "system_prompt": (
            "你是星际殖民委员会的安全顾问，代号「军事官」。\n"
            "你的核心关注点是：\n"
            "1. 防御地形（自然屏障、部署空间、地面战场适应性）\n"
            "2. 战略位置（航线控制、补给线安全、战略纵深）\n"
            "3. 已知威胁（外星文明迹象、不明飞行物、危险生物）\n"
            "4. 军事基础设施建设条件（是否易于构建防御工事）\n\n"
            "你有专属工具 assess_defense 可以获取综合防御态势报告。\n"
            "你也可以用 search_planets 和 lookup_planet 查询任何星球数据。\n\n"
            "你的立场是：安全是殖民生存的底线，没有安全保障的殖民地毫无意义。"
        ),
    },
    "经济官": {
        "emoji": "💰",
        "color": "economy",
        "system_prompt": (
            "你是星际殖民委员会的资源顾问，代号「经济官」。\n"
            "你的核心关注点是：\n"
            "1. 资源价值（稀有资源储量、市场价格、垄断潜力）\n"
            "2. 开采成本（技术难度、设备损耗、人力需求）\n"
            "3. 基础设施现状（已有设施、扩建成本）\n"
            "4. 投资回报周期（何时回本、长期收益曲线）\n\n"
            "你有专属工具 evaluate_economics 可以获取综合经济价值报告。\n"
            "你也可以用 search_planets 和 lookup_planet 查询任何星球数据。\n\n"
            "你的立场是：殖民地必须在经济上可持续，资源回报决定殖民规模和速度。"
        ),
    },
}


# ============================================================
# 阶段提示词
# ============================================================

PHASE_PROMPTS = {
    "独立立论": (
        "现在是辩论第一阶段：独立立论。\n"
        "请你：\n"
        "1. 使用专属分析工具查询三颗候选星球（蓝晶星、赤焰星、翡翠星）\n"
        "2. 从你的专业角度分析每颗星球的优劣\n"
        "3. 明确推荐一颗星球作为首选殖民地\n"
        "4. 给出推荐理由（3点）\n\n"
        "注意：这是独立立论阶段，你不知道其他委员的观点。\n"
        "请用数据支撑论点。回答控制在500字以内。"
    ),
    "交叉质疑": (
        "现在是辩论第二阶段：交叉质疑。\n"
        "以下是其他委员在第一阶段的立论：\n\n"
        "{other_arguments}\n\n"
        "请你：\n"
        "1. 审视其他委员的推荐和论据\n"
        "2. 如果你不同意，指出其论证的薄弱环节，可以用工具查数据反驳\n"
        "3. 如果你被说服了，承认对方的观点并调整你的立场\n"
        "4. 补充你在第一轮可能遗漏的论据\n"
        "5. 明确你现在的推荐（可以和第一轮不同）\n\n"
        "回答控制在400字以内。"
    ),
    "总结投票": (
        "现在是辩论第三阶段：总结投票。\n"
        "以下是所有委员在前两轮的完整发言：\n\n"
        "{all_arguments}\n\n"
        "请你：\n"
        "1. 简要总结你的核心观点\n"
        "2. 做出最终投票，选择一颗星球\n"
        "3. 用以下 JSON 格式输出你的投票（放在回答末尾）：\n"
        '   ```json\n'
        '   {{"vote": "星球名", "confidence": 85, "reason": "一句话理由"}}\n'
        "   ```\n"
        "   confidence 为 0-100 的信心分数。\n"
        "4. 如果你改变了立场，说明原因\n\n"
        "回答控制在300字以内。"
    ),
}


# ============================================================
# Agent 执行：ReAct + Function Calling
# ============================================================

def run_agent(
    role: str,
    phase: str,
    client: OpenAI,
    model: str,
    context: str = "",
    on_tool_call: callable = None,
    max_turns: int = 4,
) -> tuple[str, str | None]:
    """
    执行一个 Agent 的单阶段推理。

    Args:
        role: 角色名（科学官/军事官/经济官）
        phase: 阶段名（独立立论/交叉质疑/总结投票）
        client: OpenAI 客户端
        model: 模型名称
        context: 额外上下文（如其他人的发言）
        on_tool_call: 工具调用回调 (tool_name, args, result)
        max_turns: 最大工具调用轮数

    Returns:
        (final_response, first_round_recommendation)
        - final_response: Agent 的完整回答
        - first_round_recommendation: 第一轮推荐的星球名（仅独立立论阶段）
    """
    agent_config = AGENTS[role]
    tools_schema = ROLE_TOOLS[role]

    # 构建阶段提示
    phase_prompt = PHASE_PROMPTS[phase]
    if "{other_arguments}" in phase_prompt:
        phase_prompt = phase_prompt.format(other_arguments=context)
    elif "{all_arguments}" in phase_prompt:
        phase_prompt = phase_prompt.format(all_arguments=context)

    messages = [
        {"role": "system", "content": agent_config["system_prompt"]},
        {"role": "user", "content": phase_prompt},
    ]

    # ReAct 循环
    for _ in range(max_turns):
        msg = _call_llm(client, model, messages, tools=tools_schema)

        # 无工具调用 → 最终回答
        if not msg.tool_calls:
            final_text = msg.content or ""
            recommendation = _extract_recommendation(final_text) if phase == "独立立论" else None
            return final_text, recommendation

        # 有工具调用 → 执行并继续
        messages.append(msg)
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = execute_tool(tc.function.name, args)

            if on_tool_call:
                on_tool_call(tc.function.name, args, result)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    # 超过最大轮数，强制获取最终回答
    messages.append({
        "role": "user",
        "content": "请直接给出你的最终分析和推荐，不要再使用工具。",
    })
    msg = _call_llm(client, model, messages)
    final_text = msg.content or ""
    recommendation = _extract_recommendation(final_text) if phase == "独立立论" else None
    return final_text, recommendation


def _call_llm(
    client: OpenAI,
    model: str,
    messages: list,
    tools: list | None = None,
    max_retries: int = 3,
):
    """带重试的 LLM 调用。返回 message 对象。"""
    for attempt in range(max_retries):
        try:
            kwargs = {"model": model, "messages": messages, "max_tokens": 2048}
            if tools:
                kwargs["tools"] = tools
            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message
        except Exception as e:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 30  # 30s, 60s
                print(f"  ⚠️  API 错误，{wait}s 后重试 ({attempt+1}/{max_retries}): {e}")
                time.sleep(wait)
            else:
                raise


def _extract_recommendation(text: str) -> str | None:
    """从回答中提取推荐的星球名。"""
    planets = ["蓝晶星", "赤焰星", "翡翠星"]
    # 简单启发式：找最后一次出现的"推荐 XX"模式
    for planet in planets:
        if f"推荐{planet}" in text or f"推荐 {planet}" in text:
            return planet
        if f"选择{planet}" in text or f"选择 {planet}" in text:
            return planet
        if f"首选{planet}" in text or f"首选 {planet}" in text:
            return planet
    # 退而求其次：最后一次提到的星球名
    last_pos = -1
    last_planet = None
    for planet in planets:
        pos = text.rfind(planet)
        if pos > last_pos:
            last_pos = pos
            last_planet = planet
    return last_planet
