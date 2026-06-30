"""
工具层 —— 4 个知识库查询工具
==============================

与 03/04 保持一致的工具模式：search / lookup / calculate / compare。

06 项目（流式 ReAct）与 05 项目（流式 FC）的区别：
- 05 把 TOOLS_SCHEMA（JSON Schema）传给 API 的 tools= 参数
- 06 把 get_tool_descriptions()（自然语言描述）注入 system prompt，不传 tools=
  因为 ReAct 是纯文本格式，LLM 靠 prompt 约束输出 Action/Action Input，而非 Function Calling
"""

import ast
import operator

from knowledge_base import search_entities, lookup_entity, compare_entities


# ============================================================
# 工具函数
# ============================================================

def search(query: str) -> str:
    """搜索知识库中与 query 相关的实体"""
    results = search_entities(query)
    if results and "error" in results[0]:
        return results[0]["error"]
    lines = [f"找到 {len(results)} 个相关结果："]
    for r in results:
        lines.append(f"  - {r['摘要']}")
    return "\n".join(lines)


def lookup(entity: str, field: str = "") -> str:
    """精确查询实体的某个属性（或全部属性）"""
    return lookup_entity(entity, field)


def calculate(expression: str) -> str:
    """安全计算数学表达式（AST 白名单，禁止任意代码执行）"""
    allowed_ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
    }

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        elif isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            op_func = allowed_ops.get(type(node.op))
            if op_func is None:
                raise ValueError(f"不支持的运算符: {type(node.op).__name__}")
            return op_func(left, right)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        else:
            raise ValueError(f"不支持的表达式节点: {type(node).__name__}")

    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval(tree)
        return f"计算结果: {result}"
    except (ValueError, SyntaxError, ZeroDivisionError) as e:
        return f"计算错误: {e}"


def compare(entity_a: str, entity_b: str, field: str) -> str:
    """比较两个实体的同一属性"""
    return compare_entities(entity_a, entity_b, field)


# ============================================================
# 工具 Schema（OpenAI Function Calling 格式）
# ============================================================

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "模糊搜索知识库，返回与查询相关的实体列表。当不确定实体完整名称时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，如人名、地名、类型等",
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
            "description": "精确查询某个实体的指定属性。需要知道确切的实体名称。",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {
                        "type": "string",
                        "description": "实体名称（必须精确匹配）",
                    },
                    "field": {
                        "type": "string",
                        "description": "要查询的属性名（可选，留空返回全部属性）",
                    },
                },
                "required": ["entity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "安全计算数学表达式。支持加减乘除、幂运算。用于数值比较或推导。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，如 '2400 / 960' 或 '58 - 45'",
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
            "description": "比较两个实体的同一属性值，返回两者数据和差值。",
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
                        "description": "要比较的属性名",
                    },
                },
                "required": ["entity_a", "entity_b", "field"],
            },
        },
    },
]


# ============================================================
# 工具分发
# ============================================================

TOOL_MAP = {
    "search": search,
    "lookup": lookup,
    "calculate": calculate,
    "compare": compare,
}


def execute_tool(name: str, arguments: dict) -> str:
    """执行指定工具并返回结果字符串"""
    func = TOOL_MAP.get(name)
    if func is None:
        return f"错误：未知工具 '{name}'。可用工具：{', '.join(TOOL_MAP.keys())}"
    try:
        return func(**arguments)
    except TypeError as e:
        return f"工具 '{name}' 参数错误: {e}"
    except Exception as e:
        return f"工具 '{name}' 执行异常: {e}"


# ============================================================
# ReAct 工具描述（自然语言，注入 system prompt）
# ============================================================

# ReAct 模式下，LLM 需要自然语言描述来决定调哪个工具。
# 这与 Function Calling（JSON Schema）不同——这里是 prompt 文本，不是 API 参数。
_TOOL_DESCRIPTIONS = {
    "search": {
        "description": "模糊搜索知识库，返回与查询相关的实体列表。当不确定实体名称时使用。",
        "params": {"query": "搜索关键词，如人名、站名、设备名等"},
    },
    "lookup": {
        "description": "精确查询某个实体的指定属性。需要知道确切的实体名称。",
        "params": {
            "entity": "实体名称（必须精确匹配）",
            "field": "要查询的属性名（可选，留空返回全部属性）",
        },
    },
    "calculate": {
        "description": "安全计算数学表达式。支持加减乘除、幂运算。",
        "params": {"expression": "数学表达式，如 '2400 - 1800' 或 '8500 / 960'"},
    },
    "compare": {
        "description": "比较两个实体的同一属性值，返回两者数据和差值。",
        "params": {
            "entity_a": "第一个实体名称",
            "entity_b": "第二个实体名称",
            "field": "要比较的属性名",
        },
    },
}


def get_tool_descriptions() -> str:
    """
    生成自然语言工具描述，用于注入 ReAct Agent 的 system prompt。

    ReAct 模式下，LLM 通过 prompt 了解工具——与 Function Calling 的 JSON Schema 不同。
    """
    lines = ["你可以使用以下工具：", ""]
    for name, info in _TOOL_DESCRIPTIONS.items():
        lines.append(f"工具名：{name}")
        lines.append(f"说明：{info['description']}")
        lines.append("参数：")
        for param, desc in info["params"].items():
            lines.append(f"  - {param}: {desc}")
        lines.append("")
    return "\n".join(lines)
