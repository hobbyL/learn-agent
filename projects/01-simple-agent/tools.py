"""
工具（Tools）是 Agent 能力的扩展接口。

什么是工具？
-----------
在 AI Agent 的语境中，"工具"是一段可被 Agent 调用的代码函数。
Agent 本身（大语言模型）只能处理文本，无法直接执行计算、访问网络或操作系统资源。
通过"工具"这一机制，我们把这些能力暴露给 Agent，让它在需要时能主动调用。

工具和 Agent 的关系：
--------------------
1. 开发者定义工具函数，并用 JSON Schema 描述工具的名称、用途和参数。
2. 把工具描述列表传给 LLM（大语言模型）。
3. LLM 在对话中判断是否需要使用工具，如需要则输出结构化的"工具调用"请求。
4. Agent 框架（我们的代码）解析 LLM 的输出，找到对应函数并执行，把结果返回给 LLM。
5. LLM 根据工具执行结果继续生成回复。

这种机制叫做 Function Calling（函数调用）或 Tool Use（工具使用）。
它是构建实用 AI Agent 的核心模式之一。

本文件定义了以下 6 个工具：
- calculator       : 安全计算数学表达式
- get_current_time : 获取当前日期和时间
- date_calculator  : 计算 N 天前/后的日期和星期
- unit_converter   : 单位换算（温度、长度）
- text_stats       : 统计文本信息
- get_weather      : 查询真实天气（调用 OpenWeatherMap API）
"""

import ast
import math
import os
import operator
from datetime import datetime
from typing import Any, Union

import requests


# ============================================================
# 工具 1：计算器
# ============================================================

def calculator(expression: str) -> dict[str, Any]:
    """
    安全计算数学表达式，使用 Python 的 ast 模块而非 eval，避免代码注入风险。

    为什么不用 eval？
    ----------------
    eval("__import__('os').system('rm -rf /')") 可以执行任意代码，非常危险。
    通过 ast 解析表达式树，只允许安全的数学运算节点，可以有效防御注入攻击。

    支持的运算：
    - 四则运算：+  -  *  /
    - 整除：//
    - 取余：%
    - 幂运算：**
    - 括号分组
    - 一元正负号：+x  -x
    - 常用数学常数：pi、e

    参数：
        expression (str): 数学表达式字符串，例如 "2 + 3 * (4 - 1)"

    返回：
        dict: 成功时返回 {"result": 数值, "expression": 原始表达式}
              失败时返回 {"error": 错误描述, "expression": 原始表达式}
    """

    # 允许的运算符映射表：ast 节点类型 -> 对应的 Python operator 函数
    # 只有在这个白名单里的运算符才被允许执行
    ALLOWED_OPERATORS = {
        ast.Add:      operator.add,       # 加法 +
        ast.Sub:      operator.sub,       # 减法 -
        ast.Mult:     operator.mul,       # 乘法 *
        ast.Div:      operator.truediv,   # 除法 /
        ast.FloorDiv: operator.floordiv,  # 整除 //
        ast.Mod:      operator.mod,       # 取余 %
        ast.Pow:      operator.pow,       # 幂运算 **
        ast.UAdd:     operator.pos,       # 一元正号 +x
        ast.USub:     operator.neg,       # 一元负号 -x
    }

    # 允许使用的常数（不含括号）
    ALLOWED_NAMES = {
        "pi": math.pi,   # 圆周率 3.14159...
        "e":  math.e,    # 自然常数 2.71828...
    }

    def _eval_node(node: ast.AST) -> Union[int, float]:
        """
        递归遍历 AST 节点，只处理安全的数学运算。
        遇到任何不在白名单中的节点类型，直接抛出 ValueError。
        """
        if isinstance(node, ast.Expression):
            # 表达式根节点，直接处理其 body
            return _eval_node(node.body)

        elif isinstance(node, ast.Constant):
            # 数字字面量，例如 42、3.14
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"不支持的常量类型：{type(node.value)}")

        elif isinstance(node, ast.Name):
            # 变量名，例如 pi、e，只允许白名单中的常数
            if node.id in ALLOWED_NAMES:
                return ALLOWED_NAMES[node.id]
            raise ValueError(f"不允许使用变量：{node.id}")

        elif isinstance(node, ast.BinOp):
            # 二元运算，例如 2 + 3、a * b
            op_type = type(node.op)
            if op_type not in ALLOWED_OPERATORS:
                raise ValueError(f"不支持的运算符：{op_type.__name__}")
            left  = _eval_node(node.left)
            right = _eval_node(node.right)
            # 除法时检查除数是否为零
            if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
                raise ZeroDivisionError("除数不能为零")
            return ALLOWED_OPERATORS[op_type](left, right)

        elif isinstance(node, ast.UnaryOp):
            # 一元运算，例如 -5、+3
            op_type = type(node.op)
            if op_type not in ALLOWED_OPERATORS:
                raise ValueError(f"不支持的一元运算符：{op_type.__name__}")
            operand = _eval_node(node.operand)
            return ALLOWED_OPERATORS[op_type](operand)

        else:
            # 拒绝所有其他 AST 节点（函数调用、属性访问等）
            raise ValueError(f"不允许的表达式类型：{type(node).__name__}")

    try:
        # 第一步：将字符串解析为 AST（抽象语法树）
        # ast.parse 以 mode='eval' 解析单个表达式
        tree = ast.parse(expression.strip(), mode="eval")

        # 第二步：递归计算 AST 节点
        result = _eval_node(tree)

        # 第三步：将结果格式化（整数返回 int，浮点数保留必要精度）
        if isinstance(result, float) and result.is_integer():
            result = int(result)

        return {"result": result, "expression": expression}

    except ZeroDivisionError:
        return {"error": "除零错误：除数不能为零", "expression": expression}
    except (SyntaxError, ValueError) as e:
        return {"error": f"表达式无效：{e}", "expression": expression}
    except Exception as e:
        return {"error": f"计算失败：{e}", "expression": expression}


# ============================================================
# 工具 2：获取当前时间
# ============================================================

def get_current_time() -> dict[str, Any]:
    """
    返回当前的日期和时间，精确到秒。

    这是一个最简单的工具示例，展示工具不一定需要参数。
    LLM 本身没有实时感知能力，无法知道"现在是几点"，
    通过这个工具，Agent 就获得了感知当前时间的能力。

    参数：
        无

    返回：
        dict: {
            "datetime": "2026-06-25 14:30:00",  # 格式化的日期时间字符串
            "date":     "2026-06-25",            # 仅日期部分
            "time":     "14:30:00",              # 仅时间部分
            "weekday":  "Wednesday",             # 英文星期名
            "weekday_cn": "星期三",              # 中文星期名
            "timestamp": 1750867800.0            # Unix 时间戳（秒）
        }
    """
    now = datetime.now()

    # 中文星期名映射表（weekday() 返回 0=周一 ... 6=周日）
    WEEKDAY_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

    return {
        "datetime":   now.strftime("%Y-%m-%d %H:%M:%S"),
        "date":       now.strftime("%Y-%m-%d"),
        "time":       now.strftime("%H:%M:%S"),
        "weekday":    now.strftime("%A"),         # 英文星期名，如 Wednesday
        "weekday_cn": WEEKDAY_CN[now.weekday()],  # 中文星期名
        "timestamp":  now.timestamp(),            # Unix 时间戳
    }



# ============================================================
# 工具 3：日期计算器
# ============================================================

def date_calculator(offset_days: int) -> dict[str, Any]:
    """
    根据今天的日期计算 N 天前/后的日期和星期。

    为什么需要这个工具？
    -------------------
    LLM 不擅长精确计数（如"今天是星期五，那明天是星期几"容易推算出错）。
    通过这个工具，把日期加减交给 Python 的 datetime 模块精确计算，
    LLM 只需传入偏移天数（offset_days），工具返回完整的日期和星期信息。

    参数：
        offset_days (int): 相对于今天的偏移天数。
                           正数 = 未来（+1 = 明天，+2 = 后天，+7 = 一周后）
                           负数 = 过去（-1 = 昨天，-2 = 前天，-7 = 一周前）
                           0 = 今天

    返回：
        dict: {
            "date":         "2026-06-27",   # 目标日期
            "weekday":      "Saturday",     # 英文星期名
            "weekday_cn":   "星期六",       # 中文星期名
            "offset_days":  1,              # 传入的偏移量
            "label":        "明天",         # 自然语言描述
            "today":        "2026-06-26",   # 今天的日期（供参考）
        }
    """
    from datetime import timedelta

    today = datetime.now()
    target = today + timedelta(days=offset_days)

    WEEKDAY_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

    # 根据偏移量生成自然语言标签
    label_map = {
        -2: "前天",
        -1: "昨天",
         0: "今天",
         1: "明天",
         2: "后天",
    }
    label = label_map.get(offset_days, f"{abs(offset_days)}天{'后' if offset_days > 0 else '前'}")

    return {
        "date":        target.strftime("%Y-%m-%d"),
        "weekday":     target.strftime("%A"),
        "weekday_cn":  WEEKDAY_CN[target.weekday()],
        "offset_days": offset_days,
        "label":       label,
        "today":       today.strftime("%Y-%m-%d"),
    }


# ============================================================
# 工具 4：单位换算
# ============================================================

def unit_converter(value: float, from_unit: str, to_unit: str) -> dict[str, Any]:
    """
    执行单位换算，支持温度和长度两大类别。

    实现思路（中间单位法）：
    -------------------------
    不为每对单位都编写转换公式，而是引入一个"标准中间单位"：
    - 温度：以开尔文（K）作为中间单位
    - 长度：以米（m）作为中间单位

    转换步骤：
    1. 把输入值从 from_unit 转换为中间单位
    2. 再从中间单位转换为 to_unit
    这样只需要 2N 个公式（N 是单位数），而不是 N² 个配对公式。

    支持的单位：
    - 温度：celsius（摄氏度）、fahrenheit（华氏度）、kelvin（开尔文）
    - 长度：meter/m（米）、kilometer/km（千米）、mile（英里）、
            foot/feet/ft（英尺）、centimeter/cm（厘米）、millimeter/mm（毫米）、
            inch/in（英寸）、yard/yd（码）

    参数：
        value     (float): 要换算的数值
        from_unit (str):   来源单位名称（大小写不敏感）
        to_unit   (str):   目标单位名称（大小写不敏感）

    返回：
        dict: 成功时返回 {"result": 换算结果, "from": "原始", "to": "目标", "formula": "公式说明"}
              失败时返回 {"error": 错误描述}
    """

    # 单位名称标准化（统一转小写，去除首尾空格）
    from_unit = from_unit.strip().lower()
    to_unit   = to_unit.strip().lower()

    # ---- 温度换算 ----
    # 温度单位别名映射到标准名称
    TEMP_ALIASES = {
        "celsius":    "celsius",
        "c":          "celsius",
        "°c":         "celsius",
        "摄氏度":     "celsius",
        "fahrenheit": "fahrenheit",
        "f":          "fahrenheit",
        "°f":         "fahrenheit",
        "华氏度":     "fahrenheit",
        "kelvin":     "kelvin",
        "k":          "kelvin",
        "开尔文":     "kelvin",
        "开":         "kelvin",
    }

    # 长度单位别名映射到标准名称
    LENGTH_ALIASES = {
        "meter":      "meter",
        "meters":     "meter",
        "m":          "meter",
        "米":         "meter",
        "kilometer":  "kilometer",
        "kilometers": "kilometer",
        "km":         "kilometer",
        "千米":       "kilometer",
        "公里":       "kilometer",
        "mile":       "mile",
        "miles":      "mile",
        "英里":       "mile",
        "foot":       "foot",
        "feet":       "foot",
        "ft":         "foot",
        "英尺":       "foot",
        "centimeter": "centimeter",
        "centimeters":"centimeter",
        "cm":         "centimeter",
        "厘米":       "centimeter",
        "millimeter": "millimeter",
        "millimeters":"millimeter",
        "mm":         "millimeter",
        "毫米":       "millimeter",
        "inch":       "inch",
        "inches":     "inch",
        "in":         "inch",
        "英寸":       "inch",
        "yard":       "yard",
        "yards":      "yard",
        "yd":         "yard",
        "码":         "yard",
    }

    # 判断属于哪个类别
    from_is_temp   = from_unit in TEMP_ALIASES
    to_is_temp     = to_unit   in TEMP_ALIASES
    from_is_length = from_unit in LENGTH_ALIASES
    to_is_length   = to_unit   in LENGTH_ALIASES

    # ---- 温度换算逻辑 ----
    if from_is_temp and to_is_temp:
        # 第一步：统一转换为开尔文（中间单位）
        src = TEMP_ALIASES[from_unit]
        dst = TEMP_ALIASES[to_unit]

        if src == "celsius":
            kelvin = value + 273.15
        elif src == "fahrenheit":
            kelvin = (value - 32) * 5 / 9 + 273.15
        else:  # kelvin
            if value < 0:
                return {"error": "开尔文温度不能为负数（绝对零度 = 0 K）"}
            kelvin = value

        # 第二步：从开尔文转换为目标单位
        if dst == "celsius":
            result = kelvin - 273.15
        elif dst == "fahrenheit":
            result = (kelvin - 273.15) * 9 / 5 + 32
        else:  # kelvin
            result = kelvin

        # 构造说明公式字符串（方便用户理解换算过程）
        formula_map = {
            ("celsius", "fahrenheit"):   "°F = °C × 9/5 + 32",
            ("celsius", "kelvin"):       "K = °C + 273.15",
            ("fahrenheit", "celsius"):   "°C = (°F − 32) × 5/9",
            ("fahrenheit", "kelvin"):    "K = (°F − 32) × 5/9 + 273.15",
            ("kelvin", "celsius"):       "°C = K − 273.15",
            ("kelvin", "fahrenheit"):    "°F = (K − 273.15) × 9/5 + 32",
        }
        formula = formula_map.get((src, dst), "直接相等（同单位）")

        return {
            "result":    round(result, 6),
            "from":      f"{value} {from_unit}",
            "to":        f"{round(result, 6)} {to_unit}",
            "category":  "temperature",
            "formula":   formula,
        }

    # ---- 长度换算逻辑 ----
    elif from_is_length and to_is_length:
        src = LENGTH_ALIASES[from_unit]
        dst = LENGTH_ALIASES[to_unit]

        # 各单位 -> 米 的换算系数（1 该单位 = X 米）
        TO_METER = {
            "meter":      1.0,
            "kilometer":  1000.0,
            "mile":       1609.344,
            "foot":       0.3048,
            "centimeter": 0.01,
            "millimeter": 0.001,
            "inch":       0.0254,
            "yard":       0.9144,
        }

        # 先转为米，再转为目标单位
        meters = value * TO_METER[src]
        result = meters / TO_METER[dst]

        return {
            "result":   round(result, 8),
            "from":     f"{value} {from_unit}",
            "to":       f"{round(result, 8)} {to_unit}",
            "category": "length",
            "formula":  f"1 {src} = {TO_METER[src]} 米，1 {dst} = {TO_METER[dst]} 米",
        }

    # ---- 错误情况 ----
    elif from_is_temp != to_is_temp or from_is_length != to_is_length:
        return {"error": f"不能在不同类别的单位之间换算：{from_unit} 和 {to_unit} 属于不同类别"}
    else:
        unknown = from_unit if from_unit not in {**TEMP_ALIASES, **LENGTH_ALIASES} else to_unit
        return {"error": f"不支持的单位：{unknown}。支持的单位类别：温度（celsius/fahrenheit/kelvin）、长度（meter/km/mile/foot/cm/mm/inch/yard）"}


# ============================================================
# 工具 5：文本统计
# ============================================================

def text_stats(text: str) -> dict[str, Any]:
    """
    统计输入文本的各项信息，对中英文混合文本友好。

    统计指标：
    - 总字符数（含空格）：len(text)
    - 字符数（不含空格）：去掉所有空白字符后的长度
    - 单词数：按空白字符分割，适用于英文；对于纯中文文本，通常不适用
    - 行数：按换行符 \\n 计数
    - 中文字符数：Unicode 范围 \\u4e00-\\u9fff（基本汉字区）
    - 数字字符数：0-9
    - 英文字母数：a-z / A-Z
    - 非空行数：去掉空白行后的行数
    - 段落数：以连续空行为分隔符

    参数：
        text (str): 要统计的文本内容

    返回：
        dict: 包含各项统计数字，失败时返回 {"error": 错误描述}
    """
    if not isinstance(text, str):
        return {"error": "输入必须是字符串类型"}

    # 按换行符拆分为行列表
    lines = text.split("\n")

    # 非空行：去掉只有空白字符的行
    non_empty_lines = [line for line in lines if line.strip()]

    # 段落：以一个或多个空行为分隔符（类似 Markdown 段落）
    # 思路：将多个连续换行压缩，再按双换行拆分
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    # 中文字符统计（Unicode 基本汉字区：U+4E00 ~ U+9FFF）
    # 注意：扩展汉字区（U+3400~U+4DBF 等）未计入，对学习目的够用
    chinese_chars = sum(1 for ch in text if "一" <= ch <= "鿿")

    # 英文字母统计
    english_letters = sum(1 for ch in text if ch.isalpha() and ch.isascii())

    # 数字字符统计（不含数字所在的单词，只统计独立数字字符）
    digit_chars = sum(1 for ch in text if ch.isdigit())

    # 单词数：按任意空白字符分割，过滤空字符串
    words = text.split()

    return {
        "char_count":          len(text),                # 总字符数（含空格、换行等）
        "char_count_no_space": len(text.replace(" ", "").replace("\n", "").replace("\t", "")),  # 不含空白字符
        "word_count":          len(words),               # 单词数（英文为主）
        "line_count":          len(lines),               # 总行数（含空行）
        "non_empty_line_count":len(non_empty_lines),     # 非空行数
        "paragraph_count":     len(paragraphs),          # 段落数
        "chinese_char_count":  chinese_chars,            # 中文汉字数
        "english_letter_count":english_letters,          # 英文字母数
        "digit_char_count":    digit_chars,              # 数字字符数
        "is_empty":            len(text.strip()) == 0,  # 是否为空文本
    }


# ============================================================
# 工具 6：查询天气
# ============================================================

def get_weather(city: str, country_code: str = "", units: str = "metric") -> dict[str, Any]:
    """
    调用 OpenWeatherMap API 查询指定城市的实时天气信息。

    API Key 说明：
    -------------
    需要在环境变量 OPENWEATHERMAP_API_KEY 中设置有效的 API Key。
    获取方式：访问 https://openweathermap.org/api 免费注册并申请。
    免费版限制：每分钟 60 次调用，每月 100 万次。

    参数：
        city         (str): 城市名称，例如 "Beijing"、"Shanghai"、"London"
                            建议使用英文名称以提高匹配准确率
        country_code (str): 可选，ISO 3166 国家代码，例如 "CN"、"US"、"GB"
                            与城市名一起使用可减少歧义（同名城市）
        units        (str): 温度单位，可选值：
                            - "metric"   -> 摄氏度 °C（默认）
                            - "imperial" -> 华氏度 °F
                            - "standard" -> 开尔文 K

    返回：
        dict: 成功时包含天气详情：
              {
                  "city": "Beijing",
                  "country": "CN",
                  "temperature": 28.5,
                  "feels_like": 30.2,
                  "temp_min": 25.0,
                  "temp_max": 32.0,
                  "humidity": 65,
                  "description": "broken clouds",
                  "description_zh": (仅参考，非官方翻译),
                  "wind_speed": 3.5,
                  "visibility": 10000,
                  "units": "metric",
                  "unit_symbol": "°C"
              }
              失败时返回 {"error": 错误描述}
    """
    # 从环境变量读取 API Key
    # 不硬编码 Key 是安全最佳实践，防止密钥泄露到代码仓库
    api_key = os.environ.get("OPENWEATHERMAP_API_KEY", "").strip()

    if not api_key:
        return {
            "error": (
                "未找到 OpenWeatherMap API Key。"
                "请设置环境变量 OPENWEATHERMAP_API_KEY。"
                "获取方式：访问 https://openweathermap.org/api 免费注册。"
            )
        }

    if not city or not city.strip():
        return {"error": "城市名称不能为空"}

    # 构造查询参数
    # q 参数格式：city name 或 city name,country code（例如 "Beijing,CN"）
    q = city.strip()
    if country_code:
        q = f"{q},{country_code.strip().upper()}"

    # 温度单位符号映射
    unit_symbol_map = {
        "metric":   "°C",
        "imperial": "°F",
        "standard": "K",
    }

    params = {
        "q":     q,
        "appid": api_key,
        "units": units,
        "lang":  "zh_cn",   # 返回中文天气描述（OpenWeatherMap 支持多语言）
    }

    # OpenWeatherMap Current Weather API 端点
    url = "https://api.openweathermap.org/data/2.5/weather"

    try:
        # 发送 HTTP GET 请求，设置超时避免长时间挂起
        response = requests.get(url, params=params, timeout=10)

        # 检查 HTTP 状态码
        if response.status_code == 401:
            return {"error": "API Key 无效或已过期，请检查 OPENWEATHERMAP_API_KEY 环境变量"}
        elif response.status_code == 404:
            return {"error": f"未找到城市：{city}。请检查城市名称拼写，建议使用英文名称"}
        elif response.status_code == 429:
            return {"error": "API 调用频率超限，请稍后重试（免费版每分钟限 60 次）"}
        elif response.status_code != 200:
            return {"error": f"API 请求失败，HTTP 状态码：{response.status_code}"}

        # 解析 JSON 响应
        data = response.json()

        # 从响应数据中提取关键字段
        # OpenWeatherMap API 响应结构参考：
        # https://openweathermap.org/current#example_JSON
        main       = data.get("main", {})
        weather    = data.get("weather", [{}])[0]  # 取第一个天气状态（通常只有一个）
        wind       = data.get("wind", {})
        sys_info   = data.get("sys", {})

        return {
            "city":         data.get("name", city),            # 城市名
            "country":      sys_info.get("country", ""),        # 国家代码
            "temperature":  main.get("temp"),                   # 当前温度
            "feels_like":   main.get("feels_like"),             # 体感温度
            "temp_min":     main.get("temp_min"),               # 当日最低温
            "temp_max":     main.get("temp_max"),               # 当日最高温
            "humidity":     main.get("humidity"),               # 湿度（%）
            "pressure":     main.get("pressure"),               # 气压（hPa）
            "description":  weather.get("description", ""),     # 天气描述（中文，因为 lang=zh_cn）
            "icon":         weather.get("icon", ""),            # 天气图标代码
            "wind_speed":   wind.get("speed"),                  # 风速（metric: m/s）
            "wind_deg":     wind.get("deg"),                    # 风向（度）
            "visibility":   data.get("visibility"),             # 能见度（米）
            "cloudiness":   data.get("clouds", {}).get("all"),  # 云量（%）
            "units":        units,                              # 使用的单位制
            "unit_symbol":  unit_symbol_map.get(units, ""),     # 温度单位符号
        }

    except requests.exceptions.ConnectionError:
        return {"error": "网络连接失败，请检查网络连接"}
    except requests.exceptions.Timeout:
        return {"error": "请求超时（10 秒），OpenWeatherMap 服务可能暂时不可用"}
    except requests.exceptions.RequestException as e:
        return {"error": f"HTTP 请求异常：{e}"}
    except (KeyError, ValueError, TypeError) as e:
        return {"error": f"解析 API 响应失败：{e}"}


# ============================================================
# OpenAI Function Calling 格式的工具定义
# ============================================================
#
# 什么是 TOOLS_DEFINITION？
# --------------------------
# 这是一个描述工具的元数据列表，遵循 OpenAI Function Calling 的 JSON Schema 规范。
# 把这个列表传给 LLM（例如 GPT-4、Claude），LLM 就知道：
# 1. 有哪些工具可用
# 2. 每个工具的用途是什么
# 3. 需要哪些参数，参数的类型和含义
#
# LLM 会根据这些描述，在合适的时机输出结构化的"工具调用"请求，
# 我们的代码再把这个请求分发到对应的 Python 函数执行。
#
# JSON Schema 规范参考：https://json-schema.org/
# OpenAI Function Calling 文档：https://platform.openai.com/docs/guides/function-calling

TOOLS_DEFINITION = [
    # ---- 工具 1：计算器 ----
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": (
                "安全计算数学表达式。支持加减乘除（+、-、*、/）、"
                "整除（//）、取余（%）、幂运算（**）、括号分组，"
                "以及常数 pi 和 e。不能执行函数调用（如 sin、log）。"
                "例如：'2 + 3 * (4 - 1)'、'2 ** 10'、'pi * 3 ** 2'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": (
                            "要计算的数学表达式字符串。"
                            "例如：'2 + 3 * (4 - 1)'、'100 / 4 + 2 ** 8'、'pi * r ** 2'（其中 r 需要提前替换为数字）。"
                            "注意：不支持函数调用，如 sin()、sqrt() 等。"
                        ),
                    }
                },
                "required": ["expression"],
            },
        },
    },

    # ---- 工具 2：获取当前时间 ----
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": (
                "获取当前服务器的日期和时间（精确到秒）。"
                "返回格式化的日期时间字符串、星期名称（中英文）和 Unix 时间戳。"
                "无需任何参数。"
                "重要：每当需要计算任何相对日期或星期（例如昨天、明天、后天、下周一等），"
                "必须重新调用此工具获取最新的当前时间，不能依赖对话历史中已有的日期信息，"
                "因为历史中的日期可能已经过时，且 LLM 自行推算星期容易出错。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},  # 该工具不需要任何参数
                "required": [],
            },
        },
    },

    # ---- 工具 3：日期计算器 ----
    {
        "type": "function",
        "function": {
            "name": "date_calculator",
            "description": (
                "根据今天的日期计算 N 天前或后的具体日期和星期。"
                "当用户询问昨天、明天、后天、前天、N天后、N天前、下周X等相对日期时，"
                "必须使用此工具获取精确的日期和星期，不能自行推算星期。"
                "例如：offset_days=1 表示明天，offset_days=-1 表示昨天，offset_days=7 表示一周后。"
                "即使对话历史中已出现过今天的日期，计算任何相对日期时也必须重新调用此工具，不能从历史推算。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "offset_days": {
                        "type": "integer",
                        "description": (
                            "相对于今天的偏移天数（整数）。"
                            "正数表示未来：+1=明天，+2=后天，+7=一周后。"
                            "负数表示过去：-1=昨天，-2=前天，-7=一周前。"
                            "0=今天。"
                        ),
                    }
                },
                "required": ["offset_days"],
            },
        },
    },

    # ---- 工具 4：单位换算 ----
    {
        "type": "function",
        "function": {
            "name": "unit_converter",
            "description": (
                "在不同单位之间进行换算。"
                "支持温度换算：摄氏度（celsius/°C）、华氏度（fahrenheit/°F）、开尔文（kelvin/K）。"
                "支持长度换算：米（meter/m）、千米（kilometer/km）、英里（mile）、"
                "英尺（foot/feet/ft）、厘米（centimeter/cm）、毫米（millimeter/mm）、"
                "英寸（inch/in）、码（yard/yd）。"
                "注意：不能跨类别换算（如不能把温度换算为长度）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "number",
                        "description": "要换算的数值。例如：100、-40、3.14",
                    },
                    "from_unit": {
                        "type": "string",
                        "description": (
                            "来源单位。"
                            "温度单位：celsius、fahrenheit、kelvin（或中文：摄氏度、华氏度、开尔文）。"
                            "长度单位：meter、kilometer、mile、foot、centimeter、millimeter、inch、yard "
                            "（或简写：m、km、ft、cm、mm、in、yd）。"
                        ),
                    },
                    "to_unit": {
                        "type": "string",
                        "description": "目标单位，格式同 from_unit。",
                    },
                },
                "required": ["value", "from_unit", "to_unit"],
            },
        },
    },

    # ---- 工具 5：文本统计 ----
    {
        "type": "function",
        "function": {
            "name": "text_stats",
            "description": (
                "统计文本的各项信息，包括字符数（含/不含空格）、单词数、"
                "行数、非空行数、段落数、中文汉字数、英文字母数、数字字符数。"
                "适用于中英文混合文本。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要统计的文本内容，可以是任意中英文字符串，支持多行文本。",
                    }
                },
                "required": ["text"],
            },
        },
    },

    # ---- 工具 6：查询天气 ----
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "调用 OpenWeatherMap API 查询指定城市的实时天气信息。"
                "返回温度、体感温度、最高/最低温、湿度、天气描述、风速、能见度等信息。"
                "需要在环境变量 OPENWEATHERMAP_API_KEY 中配置有效的 API Key。"
                "城市名称建议使用英文，例如 'Beijing'、'Shanghai'、'New York'。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": (
                            "城市名称，建议使用英文名称以提高匹配准确率。"
                            "例如：'Beijing'（北京）、'Shanghai'（上海）、'Chengdu'（成都）、"
                            "'London'（伦敦）、'New York'（纽约）、'Tokyo'（东京）。"
                        ),
                    },
                    "country_code": {
                        "type": "string",
                        "description": (
                            "可选。ISO 3166 国家代码，两位大写字母。"
                            "例如：'CN'（中国）、'US'（美国）、'GB'（英国）、'JP'（日本）。"
                            "当存在同名城市时，提供国家代码可减少歧义。"
                        ),
                    },
                    "units": {
                        "type": "string",
                        "enum": ["metric", "imperial", "standard"],
                        "description": (
                            "温度单位制。可选值："
                            "'metric'（公制，温度单位为 °C，默认）、"
                            "'imperial'（英制，温度单位为 °F）、"
                            "'standard'（标准制，温度单位为开尔文 K）。"
                        ),
                    },
                },
                "required": ["city"],
            },
        },
    },
]
