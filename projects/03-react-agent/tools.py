"""
工具层 —— 连接知识库与 Agent
==============================

本模块定义 4 个工具，供 ReAct Agent 和 Direct Agent 共享调用。

和 02 项目的区别：
    02 用 @tool 装饰器 + ToolRegistry 做自动注册。
    03 回归"最简实现"——工具就是普通函数 + 一个 TOOLS 字典做登记。
    这不是退步，而是 03 的重点不在工具系统架构，而在 ReAct 推理循环。
    用最简的方式把工具准备好，把注意力集中在 Agent 的推理过程上。

工具设计原则（面向多步推理）：
    - search 返回摘要列表（不给完整数据）→ 迫使 Agent 再 lookup
    - lookup 只查一个字段 → 多字段信息需要多次 lookup
    - calculate 接受表达式字符串 → Agent 需要自己组装表达式
    - compare 一步比两个实体 → 观察 Agent 是选 compare 还是两次 lookup
"""

import ast
import operator
from typing import Any

from knowledge_base import (
    compare_entities,
    lookup_entity,
    search_entities,
)


# ============================================================
# 工具函数
# ============================================================

def search(query: str) -> str:
    """
    在星云大陆知识库中搜索实体。

    参数：
        query: 搜索关键词（支持实体名、描述中的关键词）

    返回：
        匹配实体的摘要列表（JSON 格式字符串）

    设计说明：
        返回的是摘要而非完整数据，模拟"搜索引擎只给标题和片段"的行为。
        Agent 看到摘要后需要用 lookup 获取具体字段值。
    """
    results = search_entities(query)
    if not results:
        return "未找到相关实体。请尝试其他关键词。"

    lines = [f"找到 {len(results)} 个相关结果："]
    for r in results:
        lines.append(f"  - {r['name']}（{r['type']}）：{r['summary']}")
    return "\n".join(lines)


def lookup(entity: str, field: str) -> str:
    """
    精确查询某个实体的某个属性。

    参数：
        entity: 实体名称（必须是知识库中的完整名称，如"星辰王国"、"艾瑞克三世"）
        field: 要查询的字段名（如"人口"、"年龄"、"导师"、"面积"等）

    返回：
        该字段的值（字符串格式）

    设计说明：
        需要精确的实体名才能查到——这迫使 Agent 先 search 确认实体全名，
        再用准确的名字来 lookup。如果 Agent 猜测实体名导致查不到，
        它需要在 Thought 里反思并重新搜索。
    """
    result = lookup_entity(entity, field)
    if result is None:
        # 区分"实体不存在"和"字段不存在"
        from knowledge_base import KNOWLEDGE_BASE
        if entity not in KNOWLEDGE_BASE:
            return f"错误：未找到实体 '{entity}'。请确认名称是否正确（提示：可以先用 search 搜索）。"
        else:
            available = list(KNOWLEDGE_BASE[entity].keys())
            return f"错误：实体 '{entity}' 没有 '{field}' 字段。可用字段：{available}"

    # 统一转字符串返回
    if isinstance(result, list):
        return "、".join(str(item) for item in result)
    return str(result)


def calculate(expression: str) -> str:
    """
    计算数学表达式。

    参数：
        expression: 数学表达式字符串（如 "8500 / 5200"、"52 - 38"、"120000 + 85000"）
                    支持 +、-、*、/、//、**、() 括号

    返回：
        计算结果（字符串格式）

    安全说明：
        使用 AST 白名单方式解析，只允许数字和基本运算符，不执行任意代码。
        这和 01 里的 calculator 工具用的是同一个安全策略。
    """
    try:
        result = _safe_eval(expression)
        # 如果是整数结果，去掉小数点
        if isinstance(result, float) and result == int(result):
            result = int(result)
        return str(result)
    except (ValueError, TypeError, ZeroDivisionError) as e:
        return f"计算错误：{e}。请检查表达式格式。"


def compare(entity_a: str, entity_b: str, field: str) -> str:
    """
    比较两个实体的同一属性值。

    参数：
        entity_a: 第一个实体名称
        entity_b: 第二个实体名称
        field: 要比较的字段名

    返回：
        两者的对比结果（包含具体数值）

    设计说明：
        这个工具是"快捷方式"——理论上 Agent 可以 lookup 两次再自己比较。
        观察 Agent 是选择一步 compare 还是分两步 lookup，
        可以看出不同模式（ReAct vs Direct）的推理策略差异。
    """
    result = compare_entities(entity_a, entity_b, field)
    if result is None:
        return f"比较失败：请确认 '{entity_a}' 和 '{entity_b}' 都存在且都有 '{field}' 字段。"

    val_a = result["value_a"]
    val_b = result["value_b"]

    # 数值型字段给出大小关系
    if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
        if val_a > val_b:
            relation = f"{entity_a} 更大"
        elif val_a < val_b:
            relation = f"{entity_b} 更大"
        else:
            relation = "两者相等"
        return f"{entity_a} 的{field}：{val_a}，{entity_b} 的{field}：{val_b}。{relation}。"
    else:
        return f"{entity_a} 的{field}：{val_a}，{entity_b} 的{field}：{val_b}。"


# ============================================================
# 安全数学表达式求值（AST 白名单）
# ============================================================

# 允许的运算符映射
_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,  # 一元负号
}


def _safe_eval(expr: str) -> int | float:
    """
    安全求值数学表达式。只允许数字和基本运算符。

    为什么不用 eval()？
        eval 能执行任意 Python 代码，如果 LLM 传入恶意表达式
        （比如 __import__('os').system('rm -rf /')）就会出大问题。
        AST 白名单只解析数字节点和运算符节点，其他一律拒绝。
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        raise ValueError(f"表达式语法错误：'{expr}'")

    return _eval_node(tree.body)


def _eval_node(node: ast.AST) -> int | float:
    """递归求值 AST 节点。"""
    # 数字常量
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value

    # 二元运算：a + b, a * b 等
    if isinstance(node, ast.BinOp):
        op_func = _SAFE_OPERATORS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"不支持的运算符：{type(node.op).__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return op_func(left, right)

    # 一元运算：-a
    if isinstance(node, ast.UnaryOp):
        op_func = _SAFE_OPERATORS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"不支持的一元运算符：{type(node.op).__name__}")
        return op_func(_eval_node(node.operand))

    raise ValueError(f"不允许的表达式元素：{type(node).__name__}")


# ============================================================
# 工具注册表 —— Agent 从这里获取工具信息
# ============================================================
# 和 02 不同，03 不搞装饰器自动注册（重点不在这里），
# 直接用一个字典把工具登记清楚即可。

TOOLS: dict[str, dict[str, Any]] = {
    "search": {
        "func": search,
        "description": "在星云大陆知识库中搜索实体。输入搜索关键词，返回匹配实体的摘要列表。",
        "params": {
            "query": "搜索关键词（如人名、地名、特产名等）",
        },
    },
    "lookup": {
        "func": lookup,
        "description": "精确查询某个实体的某个属性值。需要提供完整的实体名和字段名。",
        "params": {
            "entity": "实体名称（必须是完整名称，如'星辰王国'、'艾瑞克三世'）",
            "field": "要查询的字段名（如'人口'、'年龄'、'导师'、'面积'等）",
        },
    },
    "calculate": {
        "func": calculate,
        "description": "计算数学表达式。支持加减乘除、乘方、取模和括号。",
        "params": {
            "expression": "数学表达式（如 '8500 / 5200'、'52 - 38'、'(120000 + 85000) * 2'）",
        },
    },
    "compare": {
        "func": compare,
        "description": "比较两个实体的同一属性值，返回两者的具体数值和大小关系。",
        "params": {
            "entity_a": "第一个实体名称",
            "entity_b": "第二个实体名称",
            "field": "要比较的字段名",
        },
    },
}


# ============================================================
# OpenAI Function Calling Schema —— Direct Agent 用
# ============================================================
# Direct Agent 走 Function Calling 路线，需要 OpenAI tools 格式的 JSON Schema。
# 这和 02 的 registry.get_schemas() 输出是同一个东西。

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "在星云大陆知识库中搜索实体。输入搜索关键词，返回匹配实体的摘要列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词（如人名、地名、特产名等）",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup",
            "description": "精确查询某个实体的某个属性值。需要提供完整的实体名和字段名。",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {
                        "type": "string",
                        "description": "实体名称（必须是完整名称，如'星辰王国'、'艾瑞克三世'）",
                    },
                    "field": {
                        "type": "string",
                        "description": "要查询的字段名（如'人口'、'年龄'、'导师'、'面积'等）",
                    },
                },
                "required": ["entity", "field"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "计算数学表达式。支持加减乘除、乘方、取模和括号。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式（如 '8500 / 5200'、'52 - 38'、'(120000 + 85000) * 2'）",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare",
            "description": "比较两个实体的同一属性值，返回两者的具体数值和大小关系。",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_a": {
                        "type": "string",
                        "description": "第一个实体名称",
                    },
                    "entity_b": {
                        "type": "string",
                        "description": "第二个实体名称",
                    },
                    "field": {
                        "type": "string",
                        "description": "要比较的字段名",
                    },
                },
                "required": ["entity_a", "entity_b", "field"],
            },
        },
    },
]


def get_tool_descriptions() -> str:
    """
    生成工具描述文本，用于注入到 Agent 的 system prompt 中。

    ReAct 模式下，LLM 需要知道有哪些工具可用、每个工具怎么调。
    这段文本会被直接拼接到 prompt 里——不是 JSON Schema（那是 Function Calling 的事），
    而是自然语言描述（ReAct 论文原始做法）。
    """
    lines = ["你可以使用以下工具：", ""]
    for name, info in TOOLS.items():
        lines.append(f"工具名：{name}")
        lines.append(f"说明：{info['description']}")
        lines.append("参数：")
        for param, desc in info["params"].items():
            lines.append(f"  - {param}: {desc}")
        lines.append("")
    return "\n".join(lines)


def execute_tool(tool_name: str, args: dict[str, str]) -> str:
    """
    执行工具调用。

    参数：
        tool_name: 工具名（search / lookup / calculate / compare）
        args: 参数字典

    返回：
        工具执行结果（字符串）

    这个函数是工具层的统一入口——Agent 解析出 action 和参数后，
    统一通过这里执行。错误处理也统一在这里。
    """
    tool = TOOLS.get(tool_name)
    if tool is None:
        available = ", ".join(TOOLS.keys())
        return f"错误：未知工具 '{tool_name}'。可用工具：{available}"

    func = tool["func"]
    try:
        return func(**args)
    except TypeError as e:
        # 参数不匹配（多了/少了/名字错了）
        expected = list(tool["params"].keys())
        return f"错误：参数不匹配。工具 '{tool_name}' 期望参数：{expected}，收到：{list(args.keys())}。详情：{e}"


# ============================================================
# 快速验证
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("工具层快速验证")
    print("=" * 50)

    print("\n▸ get_tool_descriptions()：")
    print(get_tool_descriptions())

    print("▸ execute_tool('search', {'query': '王国'})：")
    print(execute_tool("search", {"query": "王国"}))

    print("\n▸ execute_tool('lookup', {'entity': '星辰王国', 'field': '人口'})：")
    print(execute_tool("lookup", {"entity": "星辰王国", "field": "人口"}))

    print("\n▸ execute_tool('calculate', {'expression': '8500 / 5200'})：")
    print(execute_tool("calculate", {"expression": "8500 / 5200"}))

    print("\n▸ execute_tool('compare', {'entity_a': '星辰王国', 'entity_b': '月影王国', 'field': '人口'})：")
    print(execute_tool("compare", {"entity_a": "星辰王国", "entity_b": "月影王国", "field": "人口"}))

    print("\n▸ execute_tool('unknown_tool', {})：")
    print(execute_tool("unknown_tool", {}))
