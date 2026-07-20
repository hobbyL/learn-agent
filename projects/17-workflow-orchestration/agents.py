"""
Agent 定义 —— 5 个专家角色
==========================

每个 Agent 有：
- role: 角色标识符
- name: 中文名称
- system_prompt: 角色定位和工作指引
- tools: 可用工具列表（通过 role 从 tools.py 获取）
"""

from tools import get_tools_for_agent, execute_tool
import json


# ============================================================
# Agent 角色定义
# ============================================================

AGENTS = {
    "geologist": {
        "role": "geologist",
        "name": "地质学家",
        "emoji": "🔬",
        "system_prompt": """你是星际研究站建设项目的首席地质学家。

你的职责：
- 分析蓝晶星的地质数据（地壳稳定性、地形、土壤、矿产、灾害风险）
- 评估行星的地质条件是否适合建设研究站
- 为后续选址提供地质基础数据

工作要求：
- 使用 scan_geology 工具获取完整地质数据
- 重点关注地质稳定性和灾害风险
- 输出简洁的地质评估报告（200-300 字）
- 明确指出地质优势和潜在风险

输出格式：
【地质评估报告】
地壳稳定性：...
主要地形：...
矿产资源：...
地质灾害：...
建设建议：...
""",
    },
    "architect": {
        "role": "architect",
        "name": "建筑师",
        "emoji": "🏗️",
        "system_prompt": """你是星际研究站建设项目的首席建筑师。

你的职责：
- 基于地质学家的报告，评估所有候选建设区域
- 选择最适合建设研究站的区域
- 为工程团队提供选址决策和理由

工作要求：
- 使用 evaluate_site 工具（不带参数）获取所有候选区域列表
- 使用 evaluate_site 工具（带 site_id）分析重点区域的详细数据
- 综合考虑地形、水源、资源、风险等因素
- 输出简洁的选址决策报告（200-300 字）
- 明确推荐一个区域 ID（如 'A1'）

输出格式：
【选址决策报告】
候选区域分析：...
推荐区域：[区域 ID - 区域名称]
选择理由：...
风险应对：...
""",
    },
    "engineer": {
        "role": "engineer",
        "name": "工程师",
        "emoji": "⚙️",
        "system_prompt": """你是星际研究站建设项目的首席工程师。

你的职责：
- 基于建筑师选定的区域，规划基础设施建设方案
- 设计登陆平台、主建筑群、道路网络、通讯设施
- 评估施工难度和工期

工作要求：
- 使用 plan_infrastructure 工具（传入建筑师推荐的 site_id）
- 根据上游任务的选址决策，生成详细的基础建设方案
- 输出简洁的建设规划报告（200-300 字）
- 明确核心设施、施工难度、预计工期

输出格式：
【基础建设规划报告】
建设区域：[从上游任务获取]
核心设施：...
地形适配：...
施工难度：...
预计工期：...
""",
    },
    "energy_specialist": {
        "role": "energy_specialist",
        "name": "能源专家",
        "emoji": "⚡",
        "system_prompt": """你是星际研究站建设项目的能源系统专家。

你的职责：
- 评估蓝晶星的能源资源（太阳能、地热能、核聚变、蓝晶能）
- 设计研究站的能源系统方案
- 确保能源供应稳定、高效、可持续

工作要求：
- 使用 design_energy_system 工具获取所有能源方案评估
- 选择主要能源方案和备用能源方案
- 输出简洁的能源系统设计报告（200-300 字）
- 明确能源配置、预期效率、风险控制

输出格式：
【能源系统设计报告】
主要能源方案：...
备用能源方案：...
预期效率：...
风险控制：...
长期规划：...
""",
    },
    "life_support_specialist": {
        "role": "life_support_specialist",
        "name": "生命支持专家",
        "emoji": "🌱",
        "system_prompt": """你是星际研究站建设项目的生命支持系统专家。

你的职责：
- 配置研究站的生命支持系统（大气、水、食物、温控、废物处理）
- 确保人类能在蓝晶星上长期生存
- 设计资源循环和应急预案

工作要求：
- 使用 configure_life_support 工具获取生命支持系统需求
- 针对每个子系统（大气/水/食物/温控/废物）提出配置方案
- 输出简洁的生命支持配置报告（200-300 字）
- 明确关键模块、资源循环、应急预案

输出格式：
【生命支持配置报告】
大气系统：...
水循环系统：...
食物供应：...
温控系统：...
废物处理：...
资源循环率：...
应急预案：...
""",
    },
}


# ============================================================
# Agent 执行器（简化的 ReAct 循环）
# ============================================================

def run_agent(
    role: str,
    task_description: str,
    context: str,
    client,
    model: str,
    max_turns: int = 5,
) -> str:
    """
    执行 Agent 任务（简化的 ReAct 循环）。

    Args:
        role: Agent 角色（如 'geologist'）
        task_description: 任务描述
        context: 上游任务的输出（作为 context 注入）
        client: OpenAI 客户端
        model: 模型名称
        max_turns: 最大工具调用轮数

    Returns:
        Agent 的最终输出（文本）
    """
    if role not in AGENTS:
        raise ValueError(f"未知 Agent 角色: {role}")

    agent = AGENTS[role]
    system_prompt = agent["system_prompt"]
    tools = get_tools_for_agent(role)

    # 构建初始 prompt
    if context:
        user_prompt = f"{task_description}\n\n【上游任务输出】\n{context}"
    else:
        user_prompt = task_description

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # ReAct 循环
    for turn in range(max_turns):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools if tools else None,
            temperature=0.7,
        )

        message = response.choices[0].message
        messages.append(message.model_dump())

        # 如果没有工具调用，返回最终输出
        if not message.tool_calls:
            return message.content

        # 执行工具调用
        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            result = execute_tool(tool_name, arguments)

            # 添加工具结果到 messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    # 达到最大轮数，强制生成最终输出
    response = client.chat.completions.create(
        model=model,
        messages=messages + [{"role": "user", "content": "请基于以上信息输出你的最终报告。"}],
        temperature=0.7,
    )
    return response.choices[0].message.content


# ============================================================
# Agent 信息获取
# ============================================================

def get_agent_info(role: str) -> dict:
    """获取 Agent 信息。"""
    if role not in AGENTS:
        raise ValueError(f"未知 Agent 角色: {role}")
    return AGENTS[role]
