"""
工具层 —— 三套接口：execute_tool（手写 Agent）+ @traceable 版本 + @tool 版本（LangGraph）
==================================================================================

本模块在项目 03/12 的 tools.py 基础上做了可观测性适配：

1. 原有接口（手写 ReAct Agent 使用）：
   - execute_tool(tool_name, args) → str
   - TOOLS_SCHEMA（OpenAI Function Calling 格式）
   - get_tool_descriptions()

2. @traceable 版本（LangSmith 手动接入）：
   - 用 `from langsmith import traceable` 装饰业务函数
   - LangSmith 开启时，每次工具调用自动上传 trace
   - 未开启时是 no-op，不影响功能

3. LangChain @tool 版本（LangGraph Agent 使用）：
   - search_tool / lookup_tool / calculate_tool / compare_tool
   - lc_tools 列表：传给 ChatOpenAI.bind_tools() 和 ToolNode
"""

import ast
import operator
from typing import Any

from langchain_core.tools import tool

try:
    from langsmith import traceable
except ImportError:
    # langsmith 未安装时提供 no-op 装饰器
    def traceable(**kwargs):
        def decorator(func):
            return func
        return decorator

from knowledge_base import (
    compare_entities,
    lookup_entity,
    search_entities,
)


# ============================================================
# 原始工具函数（业务逻辑）+ @traceable 装饰
# ============================================================
# @traceable 在 LangSmith 开启时自动记录工具调用 span；
# 未开启时是 no-op，不影响功能。

@traceable(run_type="tool", name="search")
def search(query: str) -> str:
    """在星云大陆知识库中搜索实体。"""
    results = search_entities(query)
    if not results:
        return "未找到相关实体。请尝试其他关键词。"

    lines = [f"找到 {len(results)} 个相关结果："]
    for r in results:
        lines.append(f"  - {r['name']}（{r['type']}）：{r['summary']}")
    return "\n".join(lines)


@traceable(run_type="tool", name="lookup")
def lookup(entity: str, field: str) -> str:
    """精确查询某个实体的某个属性。"""
    result = lookup_entity(entity, field)
    if result is None:
        from knowledge_base import KNOWLEDGE_BASE
        if entity not in KNOWLEDGE_BASE:
            return f"错误：未找到实体 '{entity}'。请确认名称是否正确（提示：可以先用 search 搜索）。"
        else:
            available = list(KNOWLEDGE_BASE[entity].keys())
            return f"错误：实体 '{entity}' 没有 '{field}' 字段。可用字段：{available}"

    if isinstance(result, list):
        return "、".join(str(item) for item in result)
    return str(result)


@traceable(run_type="tool", name="calculate")
def calculate(expression: str) -> str:
    """计算数学表达式。"""
    try:
        result = _safe_eval(expression)
        if isinstance(result, float) and result == int(result):
            result = int(result)
        return str(result)
    except (ValueError, TypeError, ZeroDivisionError) as e:
        return f"计算错误：{e}。请检查表达式格式。"


@traceable(run_type="tool", name="compare")
def compare(entity_a: str, entity_b: str, field: str) -> str:
    """比较两个实体的同一属性值。"""
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
# 安全数学表达式求值（AST 白名单）
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
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        raise ValueError(f"表达式语法错误：'{expr}'")
    return _eval_node(tree.body)


def _eval_node(node: ast.AST) -> int | float:
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
# 原有接口（手写 ReAct Agent 使用）
# ============================================================

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
            "expression": "数学表达式（如 '8500 / 5200'、'52 - 38'）",
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
                        "description": "实体名称（必须是完整名称，如'星辰王国'）",
                    },
                    "field": {
                        "type": "string",
                        "description": "要查询的字段名（如'人口'、'年龄'、'面积'等）",
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
                        "description": "数学表达式（如 '8500 / 5200'）",
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
                    "entity_a": {"type": "string", "description": "第一个实体名称"},
                    "entity_b": {"type": "string", "description": "第二个实体名称"},
                    "field": {"type": "string", "description": "要比较的字段名"},
                },
                "required": ["entity_a", "entity_b", "field"],
            },
        },
    },
]


def get_tool_descriptions() -> str:
    """生成工具描述文本，用于注入到手写 Agent 的 system prompt 中。"""
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
    执行工具调用（手写 ReAct Agent 使用的统一入口）。
    业务函数已加 @traceable，LangSmith 开启时自动记录。
    """
    tool_info = TOOLS.get(tool_name)
    if tool_info is None:
        available = ", ".join(TOOLS.keys())
        return f"错误：未知工具 '{tool_name}'。可用工具：{available}"

    func = tool_info["func"]
    try:
        return func(**args)
    except TypeError as e:
        expected = list(tool_info["params"].keys())
        return f"错误：参数不匹配。工具 '{tool_name}' 期望参数：{expected}，收到：{list(args.keys())}。详情：{e}"


# ============================================================
# LangChain @tool 版本（LangGraph Agent 使用）
# ============================================================

@tool
def search_tool(query: str) -> str:
    """在星云大陆知识库中搜索实体。输入搜索关键词，返回匹配实体的摘要列表。"""
    return search(query)


@tool
def lookup_tool(entity: str, field: str) -> str:
    """精确查询某个实体的某个属性值。需要提供完整的实体名和字段名。"""
    return lookup(entity, field)


@tool
def calculate_tool(expression: str) -> str:
    """计算数学表达式。支持加减乘除、乘方、取模和括号。示例：'8500 / 5200'、'120000 - 85000'"""
    return calculate(expression)


@tool
def compare_tool(entity_a: str, entity_b: str, field: str) -> str:
    """比较两个实体的同一属性值，返回两者的具体数值和大小关系。"""
    return compare(entity_a, entity_b, field)


# v2/v3 使用的工具列表
lc_tools = [search_tool, lookup_tool, calculate_tool, compare_tool]
