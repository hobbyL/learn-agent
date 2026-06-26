"""
8 个新工具 —— 全部本地计算，无需任何外部 API
================================================

为什么不复用 01 的工具？
------------------------
01 的工具你已经体会过痛点了，迁移它们只是机械搬运。换成全新的工具，
你才能完整经历「想清楚参数 → 写函数 → Schema 自动生成 → 看校验生效」的全过程。

这 8 个工具的参数类型是「精心挑选」的，刻意覆盖手搓 Schema 会遇到的所有典型场景：

    工具                    参数形态                          练的 Schema 场景
    ----------------------------------------------------------------------------
    qr_text_encoder         str + int(默认值)                 入门基准
    password_generator      int + bool(默认值)                bool + 可选参数
    random_picker           list[str] + int(默认值)           list 数组
    color_converter         str + Literal枚举                 单值枚举 + 非法值校验
    base_converter          str + int + int(全必填)           多必填参数
    text_case_converter     str + Literal枚举(5值)            多值密集枚举
    dice_roller             int(默认) + int(默认)             全可选(required 为空)
    hash_generator          str + Literal + bool(默认)        枚举+bool+默认值混合

--------------------------------------------------------------------
本文件用「纯类型注解」驱动 schema_gen 自动生成 Schema（路线 A 上半场）
--------------------------------------------------------------------
注意每个函数：
  - 参数都写了类型注解（str / int / bool / list[str] / Literal[...]）
  - @tool 的 params 补充每个参数的中文说明（函数签名表达不了"参数是干嘛的"）
  - 函数体自己做"业务校验"（比如 length 不能为负），返回 dict
  - 出错时返回 {"error": "..."}，错误信息写得让 LLM 能判断"是不是该重试"
    （呼应 01 的教训：error 信息会影响 Agent 的循环行为）

所有工具返回 dict，由 agent 统一 json.dumps 成字符串喂回 LLM。
"""

import hashlib
import random
import string
from typing import Any, Literal

from registry import tool


# ============================================================
# 1. qr_text_encoder —— 入门基准：str + int(默认值)
# ============================================================
@tool(
    name="qr_text_encoder",
    description="把一段短文本编码成 ASCII 字符画风格的伪二维码（仅用于趣味展示，不是真正可扫描的二维码）。",
    params={
        "text": "要编码的文本内容（建议 20 字以内，过长会被截断）",
        "size": "每个色块用几个字符宽来表示，越大图案越粗，默认 3",
    },
)
def qr_text_encoder(text: str, size: int = 3) -> dict[str, Any]:
    """把文本编码成字符画伪二维码。"""
    if not text:
        return {"error": "text 不能为空，请提供要编码的文本。"}
    if size < 1 or size > 10:
        return {"error": f"size 必须在 1~10 之间，收到 {size}。这是参数取值问题，请调整后重试。"}

    # 用文本的哈希生成一个确定性的 0/1 点阵（纯趣味，非真二维码标准）
    h = hashlib.md5(text.encode("utf-8")).hexdigest()
    bits = bin(int(h, 16))[2:].zfill(128)  # 128 位二进制
    grid_n = 11  # 11x11 点阵
    block = "█" * size
    space = " " * size

    lines = []
    for row in range(grid_n):
        line = []
        for col in range(grid_n):
            idx = (row * grid_n + col) % len(bits)
            line.append(block if bits[idx] == "1" else space)
        lines.append("".join(line))

    return {
        "text": text,
        "size": size,
        "art": "\n".join(lines),
        "note": "这是趣味字符画，并非真正可扫描的二维码。",
    }


# ============================================================
# 2. password_generator —— bool + 带默认值的可选参数
# ============================================================
@tool(
    name="password_generator",
    description="生成一个指定长度的随机密码，可选是否包含特殊符号。",
    params={
        "length": "密码长度（字符个数），建议 8~64",
        "use_symbols": "是否包含特殊符号（如 !@#$%），默认包含",
    },
)
def password_generator(length: int, use_symbols: bool = True) -> dict[str, Any]:
    """生成随机密码。"""
    if length < 4:
        return {"error": f"length 太短（收到 {length}），为安全起见至少 4 位。请调整后重试。"}
    if length > 128:
        return {"error": f"length 过长（收到 {length}），上限 128 位。请调整后重试。"}

    # 字符池：字母 + 数字（必含），符号按需加入
    pool = string.ascii_letters + string.digits
    if use_symbols:
        pool += "!@#$%^&*()-_=+"

    pwd = "".join(random.choice(pool) for _ in range(length))
    return {
        "password": pwd,
        "length": length,
        "use_symbols": use_symbols,
        "charset_size": len(pool),
    }


# ============================================================
# 3. random_picker —— list[str] 数组类型
# ============================================================
@tool(
    name="random_picker",
    description="从给定的选项列表里随机抽取若干个，用于抽奖、随机决策等。",
    params={
        "options": "候选项列表，例如 ['苹果', '香蕉', '橘子']",
        "count": "要抽取的数量，默认 1。不能超过选项总数",
    },
)
def random_picker(options: list[str], count: int = 1) -> dict[str, Any]:
    """从列表中随机抽取 count 个不重复的元素。"""
    if not options:
        return {"error": "options 列表为空，请至少提供一个候选项。"}
    if count < 1:
        return {"error": f"count 至少为 1，收到 {count}。请调整后重试。"}
    if count > len(options):
        return {
            "error": (
                f"count（{count}）超过候选项总数（{len(options)}）。"
                f"无法抽取比总数更多的不重复项，请把 count 调小到 {len(options)} 以内后重试。"
            )
        }

    picked = random.sample(options, count)
    return {
        "picked": picked,
        "count": count,
        "total_options": len(options),
    }


# ============================================================
# 4. color_converter —— 单值枚举 Literal + 非法值校验
# ============================================================
@tool(
    name="color_converter",
    description="把一个十六进制颜色值（如 #FF8800）转换成指定的颜色格式。",
    params={
        "value": "十六进制颜色值，形如 #RRGGBB 或 RRGGBB，例如 #FF8800",
        "to_format": "目标格式：hex（十六进制）、rgb（红绿蓝）、hsl（色相饱和度亮度）",
    },
)
def color_converter(value: str, to_format: Literal["hex", "rgb", "hsl"]) -> dict[str, Any]:
    """十六进制颜色 -> hex/rgb/hsl。"""
    hex_str = value.strip().lstrip("#")
    if len(hex_str) != 6 or any(c not in "0123456789abcdefABCDEF" for c in hex_str):
        return {
            "error": (
                f"value 不是合法的十六进制颜色（收到 '{value}'）。"
                f"应形如 #FF8800 或 FF8800。这是参数格式问题，请修正后重试。"
            )
        }

    r = int(hex_str[0:2], 16)
    g = int(hex_str[2:4], 16)
    b = int(hex_str[4:6], 16)

    if to_format == "hex":
        return {"input": value, "format": "hex", "result": f"#{hex_str.upper()}"}

    if to_format == "rgb":
        return {"input": value, "format": "rgb", "result": f"rgb({r}, {g}, {b})"}

    # to_format == "hsl"
    r_, g_, b_ = r / 255, g / 255, b / 255
    mx, mn = max(r_, g_, b_), min(r_, g_, b_)
    l = (mx + mn) / 2
    if mx == mn:
        h = s = 0.0
    else:
        d = mx - mn
        s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
        if mx == r_:
            h = (g_ - b_) / d + (6 if g_ < b_ else 0)
        elif mx == g_:
            h = (b_ - r_) / d + 2
        else:
            h = (r_ - g_) / d + 4
        h /= 6
    return {
        "input": value,
        "format": "hsl",
        "result": f"hsl({round(h * 360)}, {round(s * 100)}%, {round(l * 100)}%)",
    }


# ============================================================
# 5. base_converter —— 多个必填参数（required 列表）
# ============================================================
@tool(
    name="base_converter",
    description="把一个数字在不同进制之间转换（支持 2~36 进制）。",
    params={
        "number": "要转换的数字（用字符串表示，例如 'FF'、'1010'、'255'）",
        "from_base": "原始进制（2~36），例如 16 表示十六进制",
        "to_base": "目标进制（2~36），例如 2 表示二进制",
    },
)
def base_converter(number: str, from_base: int, to_base: int) -> dict[str, Any]:
    """任意进制互转。三个参数都没有默认值 → 全部必填。"""
    if not (2 <= from_base <= 36) or not (2 <= to_base <= 36):
        return {
            "error": (
                f"进制必须在 2~36 之间（收到 from_base={from_base}, to_base={to_base}）。"
                f"请调整后重试。"
            )
        }
    try:
        # 先把输入按 from_base 解析成十进制整数
        decimal_value = int(number.strip(), from_base)
    except ValueError:
        return {
            "error": (
                f"'{number}' 不是合法的 {from_base} 进制数。"
                f"例如 16 进制只能含 0-9A-F。这是参数问题，请修正后重试。"
            )
        }

    if decimal_value == 0:
        result = "0"
    else:
        digits = "0123456789abcdefghijklmnopqrstuvwxyz"
        neg = decimal_value < 0
        n = abs(decimal_value)
        out = []
        while n > 0:
            out.append(digits[n % to_base])
            n //= to_base
        result = ("-" if neg else "") + "".join(reversed(out))

    return {
        "input": number,
        "from_base": from_base,
        "to_base": to_base,
        "decimal": decimal_value,
        "result": result.upper(),
    }


# ============================================================
# 6. text_case_converter —— 多值密集枚举（5 个选项）
# ============================================================
@tool(
    name="text_case_converter",
    description="转换文本的大小写/命名风格。",
    params={
        "text": "要转换的原始文本",
        "mode": "转换模式：upper（全大写）、lower（全小写）、title（每词首字母大写）、"
                "snake（蛇形 snake_case）、camel（驼峰 camelCase）",
    },
)
def text_case_converter(
    text: str,
    mode: Literal["upper", "lower", "title", "snake", "camel"],
) -> dict[str, Any]:
    """文本大小写/命名风格转换。"""
    if not text:
        return {"error": "text 不能为空，请提供要转换的文本。"}

    if mode == "upper":
        result = text.upper()
    elif mode == "lower":
        result = text.lower()
    elif mode == "title":
        result = text.title()
    elif mode == "snake":
        # 以空格/连字符切词，用下划线连接，全小写
        words = text.replace("-", " ").split()
        result = "_".join(w.lower() for w in words)
    else:  # camel
        words = text.replace("-", " ").replace("_", " ").split()
        if not words:
            result = ""
        else:
            result = words[0].lower() + "".join(w.capitalize() for w in words[1:])

    return {"input": text, "mode": mode, "result": result}


# ============================================================
# 7. dice_roller —— 全部带默认值（required 为空的极端情况）
# ============================================================
@tool(
    name="dice_roller",
    description="掷骰子，返回每次的点数和总和。可指定骰子面数和投掷次数。",
    params={
        "sides": "骰子面数，默认 6（即普通六面骰）",
        "times": "投掷次数，默认 1",
    },
)
def dice_roller(sides: int = 6, times: int = 1) -> dict[str, Any]:
    """掷骰子。两个参数都有默认值 → required 为空，可无参调用。"""
    if sides < 2:
        return {"error": f"sides 至少为 2（收到 {sides}）。请调整后重试。"}
    if times < 1 or times > 100:
        return {"error": f"times 必须在 1~100 之间（收到 {times}）。请调整后重试。"}

    rolls = [random.randint(1, sides) for _ in range(times)]
    return {
        "sides": sides,
        "times": times,
        "rolls": rolls,
        "total": sum(rolls),
    }


# ============================================================
# 8. hash_generator —— 枚举 + bool + 默认值（混合复杂参数）
# ============================================================
@tool(
    name="hash_generator",
    description="计算一段文本的哈希值（摘要），支持多种算法。",
    params={
        "text": "要计算哈希的原始文本",
        "algorithm": "哈希算法：md5、sha1、sha256",
        "uppercase": "结果是否用大写字母，默认小写",
    },
)
def hash_generator(
    text: str,
    algorithm: Literal["md5", "sha1", "sha256"],
    uppercase: bool = False,
) -> dict[str, Any]:
    """计算文本哈希。这是最接近真实复杂工具的参数形态：枚举+bool+默认值。"""
    if not text:
        return {"error": "text 不能为空，请提供要计算哈希的文本。"}

    # 算法名到 hashlib 构造器的映射
    algo_map = {
        "md5": hashlib.md5,
        "sha1": hashlib.sha1,
        "sha256": hashlib.sha256,
    }
    digest = algo_map[algorithm](text.encode("utf-8")).hexdigest()
    result = digest.upper() if uppercase else digest

    return {
        "input": text,
        "algorithm": algorithm,
        "uppercase": uppercase,
        "result": result,
        "length": len(result),
    }
