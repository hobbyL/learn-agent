"""
工具层 —— 连接知识库与 MemoryAgent
=====================================

提供 4 个工具供 Agent 调用：
- search(query)           在星际学院知识库中模糊搜索实体
- lookup(entity, field)   精确查询实体某一属性
- calculate(expression)   AST 白名单安全计算器
- compare(entity1, entity2, field)  比较两实体同一字段

TOOLS_SCHEMA 是 OpenAI Function Calling 所需的 JSON Schema 格式工具描述，
传给 API 的 tools= 参数，让 LLM 知道可以调用哪些工具。
"""

import ast
import operator

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
    在星际学院知识库中搜索实体。
    返回摘要列表而非完整数据，迫使 Agent 再用 lookup 获取细节。
    """
    results = search_entities(query)
    if not results:
        return "未找到相关实体，请尝试其他关键词。"

    # 检查是否返回了错误
    if len(results) == 1 and "error" in results[0]:
        return results[0]["error"]

    lines = [f"找到 {len(results)} 个相关结果："]
    for r in results:
        lines.append(f"  - {r['名称']}（{r['类型']}）：{r['摘要']}")
    return "\n".join(lines)


def lookup(entity: str, field: str) -> str:
    """
    精确查询某个实体的某个属性值。
    需要提供完整的实体名和字段名。
    field 传空字符串时返回全部属性。
    """
    return lookup_entity(entity, field)


def calculate(expression: str) -> str:
    """
    计算数学表达式。
    支持 +、-、*、/、//、**、% 和括号。
    使用 AST 白名单策略，不执行任意代码。
    """
    try:
        result = _safe_eval(expression)
        # 整数结果去掉小数点
        if isinstance(result, float) and result == int(result):
            result = int(result)
        return str(result)
    except (ValueError, TypeError, ZeroDivisionError) as e:
        return f"计算错误：{e}。请检查表达式格式（如 '2026 - 2022'）。"


def compare(entity_a: str, entity_b: str, field: str) -> str:
    """
    比较两个实体的同一属性值。
    数值型字段额外给出大小关系。
    """
    return compare_entities(entity_a, entity_b, field)


# ============================================================
# 安全数学表达式求值（AST 白名单）
# ============================================================

_SAFE_OPERATORS = {
    ast.Add:      operator.add,
    ast.Sub:      operator.sub,
    ast.Mult:     operator.mul,
    ast.Div:      operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Pow:      operator.pow,
    ast.Mod:      operator.mod,
    ast.USub:     operator.neg,
}


def _safe_eval(expr: str) -> int | float:
    """
    安全求值数学表达式。
    使用 AST 解析 + 白名单校验，只允许数字和基本运算符。
    避免 eval() 执行任意代码的安全风险。
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        raise ValueError(f"表达式语法错误：'{expr}'")
    return _eval_node(tree.body)


def _eval_node(node: ast.AST) -> int | float:
    """递归求值 AST 节点（只允许数字和白名单运算符）。"""
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
# OpenAI Function Calling Schema
# ============================================================
# MemoryAgent 通过这个 schema 告诉 LLM 有哪些工具可用。
# 格式要求见 OpenAI 文档：tools 参数接受 list[dict]，每个 dict 包含 type + function。

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "在星际学院知识库中搜索实体（院系、人物、合作机构等）。返回摘要列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，如人名、院系名、机构名、研究方向等",
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
            "description": "精确查询某个实体的某个属性值。需要提供完整实体名和字段名。",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {
                        "type": "string",
                        "description": "实体名称，如'林晨'、'量子院'、'星际探索局'",
                    },
                    "field": {
                        "type": "string",
                        "description": "要查询的字段名，如'导师'、'院长'、'合作机构'、'入学年份'等。传空字符串返回全部属性。",
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
            "description": "计算数学表达式。支持加减乘除、乘方、括号。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，如 '2026 - 2022'、'320 + 280'",
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
            "description": "比较两个实体的同一属性值，返回两者数值和大小关系。",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_a": {"type": "string", "description": "第一个实体名称"},
                    "entity_b": {"type": "string", "description": "第二个实体名称"},
                    "field":    {"type": "string", "description": "要比较的字段名"},
                },
                "required": ["entity_a", "entity_b", "field"],
            },
        },
    },
]


# ============================================================
# 工具执行分发
# ============================================================

_TOOL_MAP = {
    "search":    search,
    "lookup":    lookup,
    "calculate": calculate,
    "compare":   compare,
}


def execute_tool(tool_name: str, args: dict) -> str:
    """
    统一工具执行入口。
    根据工具名找到对应函数，传入参数并返回结果字符串。
    """
    func = _TOOL_MAP.get(tool_name)
    if func is None:
        available = ", ".join(_TOOL_MAP.keys())
        return f"错误：未知工具 '{tool_name}'。可用工具：{available}"

    try:
        return func(**args)
    except TypeError as e:
        return f"错误：参数不匹配。工具 '{tool_name}' 参数问题：{e}"


# ============================================================
# 快速验证
# ============================================================

if __name__ == "__main__":
    print("=== 工具层快速验证 ===\n")

    print("search('量子'):")
    print(execute_tool("search", {"query": "量子"}))

    print("\nlookup('林晨', '导师'):")
    print(execute_tool("lookup", {"entity": "林晨", "field": "导师"}))

    print("\nlookup('量子院', '院长'):")
    print(execute_tool("lookup", {"entity": "量子院", "field": "院长"}))

    print("\ncalculate('2026 - 2022'):")
    print(execute_tool("calculate", {"expression": "2026 - 2022"}))

    print("\ncompare('量子院', '生命院', '学员人数'):")
    print(execute_tool("compare", {"entity_a": "量子院", "entity_b": "生命院", "field": "学员人数"}))
