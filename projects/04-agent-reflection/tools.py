"""
工具层 —— 连接深海联盟知识库与 Agent
======================================

和 03 的 tools.py 结构一致：
    - 4 个工具函数（search / lookup / calculate / compare）
    - TOOLS 字典做注册表
    - get_tool_descriptions() 生成 prompt 文本
    - execute_tool() 统一调度入口

04 不做复杂的工具系统，重点在外层 Reflexion 循环，
工具只需要"能工作"就行。
"""

import ast
import operator
from typing import Any

from knowledge_base import (
    compare_entities,
    lookup_entity,
    search_entities,
    KNOWLEDGE_BASE,
)


# ============================================================
# 工具函数
# ============================================================

def search(query: str) -> str:
    """
    在深海联盟知识库中搜索实体。

    参数：
        query: 搜索关键词

    返回：
        匹配实体的摘要列表（文本格式）
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
        entity: 实体名称（必须是知识库中的完整名称）
        field: 要查询的字段名

    返回：
        该字段的值（字符串格式）
    """
    result = lookup_entity(entity, field)
    if result is None:
        if entity not in KNOWLEDGE_BASE:
            return f"错误：未找到实体 '{entity}'。请确认名称是否正确（提示：可以先用 search 搜索）。"
        else:
            available = list(KNOWLEDGE_BASE[entity].keys())
            return f"错误：实体 '{entity}' 没有 '{field}' 字段。可用字段：{available}"

    if isinstance(result, list):
        return "、".join(str(item) for item in result)
    return str(result)


def calculate(expression: str) -> str:
    """
    计算数学表达式。

    参数：
        expression: 数学表达式字符串（如 "9200 / 7600"）

    返回：
        计算结果（字符串格式）

    安全说明：使用 AST 白名单方式，不执行任意代码。
    """
    try:
        result = _safe_eval(expression)
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
        两者的对比结果
    """
    result = compare_entities(entity_a, entity_b, field)
    if result is None:
        return f"比较失败：请确认 '{entity_a}' 和 '{entity_b}' 都存在且都有 '{field}' 字段。"

    val_a = result["value_a"]
    val_b = result["value_b"]

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
# 安全数学表达式求值
# ============================================================

_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
}


def _safe_eval(expr: str) -> int | float:
    """安全求值数学表达式（AST 白名单）。"""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        raise ValueError(f"表达式语法错误：'{expr}'")
    return _eval_node(tree.body)


def _eval_node(node: ast.AST) -> int | float:
    """递归求值 AST 节点。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp):
        op_func = _SAFE_OPERATORS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"不支持的运算符：{type(node.op).__name__}")
        return op_func(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op_func = _SAFE_OPERATORS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"不支持的一元运算符：{type(node.op).__name__}")
        return op_func(_eval_node(node.operand))
    raise ValueError(f"不允许的表达式元素：{type(node).__name__}")


# ============================================================
# 工具注册表
# ============================================================

TOOLS: dict[str, dict[str, Any]] = {
    "search": {
        "func": search,
        "description": "在深海联盟知识库中搜索实体。输入搜索关键词，返回匹配实体的摘要列表。",
        "params": {
            "query": "搜索关键词（如人名、地名、国度名等）",
        },
    },
    "lookup": {
        "func": lookup,
        "description": "精确查询某个实体的某个属性值。需要提供完整的实体名和字段名。",
        "params": {
            "entity": "实体名称（必须是完整名称，如'深渊王国'、'奥西里斯'）",
            "field": "要查询的字段名（如'人口'、'年龄'、'导师'、'面积'等）",
        },
    },
    "calculate": {
        "func": calculate,
        "description": "计算数学表达式。支持加减乘除、乘方、取模和括号。",
        "params": {
            "expression": "数学表达式（如 '9200 / 7600'、'156 - 89'、'(180000 + 220000) / 2'）",
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


def get_tool_descriptions() -> str:
    """
    生成工具描述文本，注入到 ReAct system prompt 中。

    和 03 一样，用自然语言描述而非 JSON Schema。
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
    执行工具调用（统一入口）。

    参数：
        tool_name: 工具名
        args: 参数字典

    返回：
        工具执行结果（字符串）
    """
    tool = TOOLS.get(tool_name)
    if tool is None:
        available = ", ".join(TOOLS.keys())
        return f"错误：未知工具 '{tool_name}'。可用工具：{available}"

    func = tool["func"]
    try:
        return func(**args)
    except TypeError as e:
        expected = list(tool["params"].keys())
        return f"错误：参数不匹配。工具 '{tool_name}' 期望参数：{expected}，收到：{list(args.keys())}。详情：{e}"


# ============================================================
# 快速验证
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("深海联盟工具层 · 快速验证")
    print("=" * 50)

    print("\n▸ get_tool_descriptions()：")
    print(get_tool_descriptions())

    print("▸ execute_tool('search', {'query': '珊瑚'})：")
    print(execute_tool("search", {"query": "珊瑚"}))

    print("\n▸ execute_tool('lookup', {'entity': '深渊王国', 'field': '人口'})：")
    print(execute_tool("lookup", {"entity": "深渊王国", "field": "人口"}))

    print("\n▸ execute_tool('calculate', {'expression': '9200 / 7600'})：")
    print(execute_tool("calculate", {"expression": "9200 / 7600"}))

    print("\n▸ execute_tool('compare', {'entity_a': '深渊王国', 'entity_b': '珊瑚联邦', 'field': '人口'})：")
    print(execute_tool("compare", {"entity_a": "深渊王国", "entity_b": "珊瑚联邦", "field": "人口"}))
