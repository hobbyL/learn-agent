"""
工具注册表 + @tool 装饰器 —— 深度注释学习版
================================================

这是 02 项目的核心地基。它要解决 01 暴露的痛点：

    01 里加一个工具，要改三个地方（写函数、手写 JSON Schema、在 tool_map 登记），
    其中 `参数: 类型` 这个信息写了两遍，改了函数忘改 Schema 就会出 bug。

本模块的思路：
    用一个 @tool 装饰器，让"写函数"这个动作本身就完成"注册"。
    函数一旦被 @tool 装饰，它的名字、说明、参数 Schema 就自动登记到一个
    全局注册表（ToolRegistry）里。agent 只管从注册表拿工具，永远不用改 agent 代码。

--------------------------------------------------------------------
装饰器到底是什么？（如果你对装饰器不熟，先读这段）
--------------------------------------------------------------------
装饰器本质上就是"一个接收函数、返回函数的函数"。写法：

    @tool
    def calculator(...): ...

完全等价于：

    def calculator(...): ...
    calculator = tool(calculator)

也就是说，定义完 calculator 后，Python 立刻把它传给 tool()，
tool() 在这一刻做一件事：把这个函数登记到注册表，然后原样把函数还回去。
"原样还回去"意味着 calculator 依然是那个能正常调用的函数，毫发无损，
只是"顺便"被记录到了注册表里。这就是"定义即注册"。

--------------------------------------------------------------------
为什么注册表用模块级单例（全局只有一个 registry）？
--------------------------------------------------------------------
因为我们希望所有工具文件（tools.py 里的每个 @tool 函数）一旦被 import，
就自动汇总到同一个注册表里。agent 只要 import 这个 registry，
就能拿到全部工具，不需要谁手动把工具"交给"agent。
"""

from typing import Any, Callable, Optional


class ToolRegistry:
    """
    工具注册表：保存所有被 @tool 装饰的工具。

    内部用一个字典 _tools 存储，结构为：
        {
            "calculator": {
                "func": <function calculator>,   # 真正执行的 Python 函数
                "schema": {...},                  # 传给 LLM 的 JSON Schema（OpenAI tools 格式）
            },
            ...
        }

    为什么把 func 和 schema 存在一起？
    - schema 是给 LLM "看"的（告诉它有什么工具、参数长什么样）
    - func 是给我们"执行"的（LLM 决定调用后，我们真正运行它）
    两者一一对应，存在一起最自然，dispatch 时一次就能取全。
    """

    def __init__(self) -> None:
        # 工具名 -> {"func": ..., "schema": ...}
        self._tools: dict[str, dict[str, Any]] = {}

    def register(self, name: str, func: Callable, schema: dict) -> None:
        """
        把一个工具登记到注册表。

        参数：
            name (str): 工具名称（LLM 用这个名字来调用工具）
            func (Callable): 工具的实际 Python 函数
            schema (dict): OpenAI tools 格式的 JSON Schema

        说明：
            如果重复注册同名工具会直接覆盖。这里特意不静默覆盖，
            而是抛错——重名通常意味着写错了，早暴露早修复。
        """
        if name in self._tools:
            raise ValueError(
                f"工具名重复注册：'{name}'。"
                f"每个工具名必须唯一，请检查是否有两个函数用了同一个名字。"
            )
        self._tools[name] = {"func": func, "schema": schema}

    def get_func(self, name: str) -> Optional[Callable]:
        """根据工具名取出对应的 Python 函数；不存在则返回 None。"""
        tool = self._tools.get(name)
        return tool["func"] if tool else None

    def get_schemas(self) -> list[dict]:
        """
        返回所有工具的 Schema 列表，可直接作为 OpenAI 的 tools 参数。

        这取代了 01 里手写的 TOOLS_DEFINITION——现在它是自动汇总出来的。
        """
        return [tool["schema"] for tool in self._tools.values()]

    def list_names(self) -> list[str]:
        """返回所有已注册工具的名字列表（方便调试/打印）。"""
        return list(self._tools.keys())

    def __len__(self) -> int:
        """支持 len(registry) 直接看注册了多少个工具。"""
        return len(self._tools)


# ============================================================
# 模块级单例：全局唯一的注册表
# ============================================================
# 所有 @tool 装饰的函数都登记到这一个 registry 上。
# tools.py 里的工具被 import 时，会自动注册到这里；
# agent.py 直接 import 这个 registry 就能拿到全部工具。
registry = ToolRegistry()


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    params: Optional[dict[str, str]] = None,
):
    """
    @tool 装饰器：把一个函数自动注册成工具。

    用法（两种都支持）：

        # 写法一：带参数，显式指定 name / description / 各参数说明
        @tool(
            name="dice_roller",
            description="掷骰子，返回点数",
            params={"sides": "骰子面数", "times": "投掷次数"},
        )
        def dice_roller(...): ...

        # 写法二：不带参数，name 默认取函数名，description 取函数 docstring
        @tool
        def dice_roller(...):
            \"\"\"掷骰子，返回点数\"\"\"
            ...

    关于 params：
        函数签名只能表达"参数叫什么、是什么类型"，无法表达"这个参数是干嘛的"。
        而 LLM 很依赖每个参数的自然语言说明来正确填参。所以这里允许用一个
        {参数名: 说明} 的字典补充描述，build_schema 会把它写进每个参数的 description。
        不传也能用，只是 LLM 少了点提示。

    --------------------------------------------------------------
    为什么要支持"带参数"和"不带参数"两种写法？
    --------------------------------------------------------------
    这是装饰器的一个经典难点。区别在于：

      @tool            → Python 把"被装饰的函数"直接传给 tool，即 tool(func)
      @tool(name=...)  → Python 先执行 tool(name=...) 得到一个"真正的装饰器"，
                          再用它去装饰函数，即 tool(name=...)(func)

    两种调用方式参数完全不同，所以下面用"第一个参数是不是可调用对象"
    来判断走的是哪条路。这是社区里处理"可选参数装饰器"的标准技巧。
    """

    def decorator(func: Callable) -> Callable:
        # 延迟 import：schema_gen 依赖 inspect 解析函数，放在这里避免循环 import，
        # 也让 registry.py 本身不依赖 schema_gen 的实现细节。
        from schema_gen import build_schema

        # 工具名：优先用显式传入的 name，否则用函数名
        tool_name = name or func.__name__

        # 工具说明：优先用显式 description，否则用函数 docstring 的第一段
        tool_desc = description or (func.__doc__ or "").strip()

        # 自动生成这个工具的 JSON Schema（OpenAI tools 格式）
        # build_schema 会用 inspect 读 func 的签名和类型注解，自动产出 parameters；
        # params（{参数名: 说明}）补充每个参数的自然语言描述，帮 LLM 正确填参
        schema = build_schema(func, tool_name, tool_desc, params)

        # 登记到全局注册表
        registry.register(tool_name, func, schema)

        # 原样返回函数本身——被装饰的函数依然能正常调用，毫发无损
        return func

    # ---- 判断走哪条路（见上面 docstring 的解释）----
    if callable(name):
        # 说明是 @tool（不带括号）这种用法：
        # 此时传进来的 name 其实是"被装饰的函数"本身。
        # 先把它取出来，把 name 复位成 None，再走一遍 decorator。
        func = name
        name = None
        return decorator(func)

    # 否则是 @tool(...) 这种用法：返回真正的装饰器，等 Python 拿函数来调用它
    return decorator
