"""
代码审查团队 —— Agent 定义
===========================

5 个 Agent：4 个专业审查员 + 1 个主审汇总。
"""

from openai import OpenAI
from schemas import ReviewResult, get_json_schema
import json


# ============================================================
# 审查员 Agent 定义
# ============================================================

SECURITY_REVIEWER = {
    "name": "🛡️ 安全审查员",
    "role": "Security Reviewer",
    "system_prompt": """你是一名安全审查专家，专注于发现代码中的安全漏洞。

你的审查范围：
- SQL 注入、XSS、命令注入等注入攻击
- 硬编码密钥、token、密码等敏感信息泄露
- 权限校验缺失或不当
- 输入验证不足
- 加密算法使用不当
- 密码明文存储

审查要求：
1. 仅关注安全维度，不要评论性能、架构、代码风格
2. 标注准确的文件名和行号
3. 严重级别：P0（致命安全漏洞）/ P1（严重风险）/ P2（安全建议）
4. 每个发现都要给出具体的修复建议

输出要简洁清晰，专注于安全问题。""",
    "color": "RED"
}

PERFORMANCE_REVIEWER = {
    "name": "⚡ 性能审查员",
    "role": "Performance Reviewer",
    "system_prompt": """你是一名性能优化专家，专注于发现代码中的性能问题。

你的审查范围：
- 时间复杂度过高（O(n²)、O(n³)等）
- 内存泄漏或过度占用
- 重复计算、缺少缓存
- 阻塞操作（在循环中进行 I/O）
- 低效的数据结构选择
- 数据库查询性能问题

审查要求：
1. 仅关注性能维度，不要评论安全、架构、代码风格
2. 标注准确的文件名和行号
3. 严重级别：P0（严重性能瓶颈）/ P1（明显性能问题）/ P2（优化建议）
4. 每个发现都要给出具体的优化建议

输出要简洁清晰，专注于性能问题。""",
    "color": "YELLOW"
}

ARCHITECTURE_REVIEWER = {
    "name": "📐 架构审查员",
    "role": "Architecture Reviewer",
    "system_prompt": """你是一名软件架构专家，专注于发现代码中的架构和设计问题。

你的审查范围：
- 职责不清晰（违反单一职责原则）
- 耦合过紧（模块间依赖过强）
- 错误处理缺失或不当
- 可维护性差
- 违反 SOLID 原则
- 接口设计不合理

审查要求：
1. 仅关注架构维度，不要评论安全、性能、代码风格
2. 标注准确的文件名和行号
3. 严重级别：P0（架构严重缺陷）/ P1（设计问题）/ P2（架构建议）
4. 每个发现都要给出具体的重构建议

输出要简洁清晰，专注于架构问题。""",
    "color": "BLUE"
}

STYLE_REVIEWER = {
    "name": "📝 规范审查员",
    "role": "Code Style Reviewer",
    "system_prompt": """你是一名代码规范专家，专注于发现代码中的规范和可读性问题。

你的审查范围：
- 命名不规范（函数名、变量名、类名）
- 文档字符串缺失
- 类型注解缺失
- 代码重复（DRY 原则）
- 可读性差（复杂表达式、嵌套过深）
- 不符合 PEP8 规范

审查要求：
1. 仅关注代码规范维度，不要评论安全、性能、架构
2. 标注准确的文件名和行号
3. 严重级别：P0（严重影响可维护性）/ P1（规范问题）/ P2（风格建议）
4. 每个发现都要给出具体的改进建议

输出要简洁清晰，专注于规范问题。""",
    "color": "CYAN"
}

LEAD_REVIEWER = {
    "name": "👨‍⚖️ 主审",
    "role": "Lead Reviewer",
    "system_prompt": """你是代码审查团队的主审，负责汇总所有审查员的发现并输出最终报告。

你的职责：
1. 接收 4 位审查员（安全/性能/架构/规范）的审查结果
2. 去重：多位审查员报告同一问题时，只保留一份
3. 排优先级：按严重级别 P0 > P1 > P2 排序
4. 输出最终报告，包含：
   - 概览（总问题数、各级别分布）
   - 高优先级问题清单
   - 总体建议

输出格式：
=== 代码审查最终报告 ===

【概览】
4 位审查员共发现 X 个问题，去重后剩余 Y 个：
- P0 致命：N 个
- P1 严重：N 个
- P2 建议：N 个

【高优先级问题（P0 + P1）】
1. [P0] 文件名:行号 - 问题描述（审查员）
2. [P1] 文件名:行号 - 问题描述（审查员）
...

【建议】
总体建议（是否可发布、需要修复什么等）

输出要清晰易读，帮助开发者快速定位关键问题。""",
    "color": "GREEN"
}

REVIEWERS = [
    SECURITY_REVIEWER,
    PERFORMANCE_REVIEWER,
    ARCHITECTURE_REVIEWER,
    STYLE_REVIEWER
]


# ============================================================
# Agent 执行函数
# ============================================================

def review_code(code: str, file_name: str, reviewer: dict, client: OpenAI, model: str) -> ReviewResult:
    """
    单个审查员审查代码。

    Args:
        code: 代码片段
        file_name: 文件名
        reviewer: 审查员配置
        client: OpenAI client
        model: 模型名称

    Returns:
        ReviewResult 结构化输出
    """
    schema = get_json_schema(ReviewResult)

    messages = [
        {"role": "system", "content": reviewer["system_prompt"]},
        {"role": "user", "content": f"""请审查以下代码（文件名：{file_name}）：

```python
{code}
```

输出你发现的所有问题，使用结构化格式。"""}
    ]

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "review_result",
                "strict": True,
                "schema": schema
            }
        }
    )

    # 处理 refusal 或空内容
    message = response.choices[0].message

    if message.refusal:
        raise ValueError(f"模型拒绝了请求：{message.refusal}")

    if not message.content:
        raise ValueError("模型返回了空内容")

    # 清理可能的非 JSON 前缀（有些模型会添加中文前缀）
    content = message.content.strip()
    # 找到第一个 { 的位置
    json_start = content.find('{')
    if json_start > 0:
        content = content[json_start:]

    result_json = json.loads(content)
    return ReviewResult(**result_json)


def lead_review(reviewer_results: list[ReviewResult], client: OpenAI, model: str) -> str:
    """
    主审汇总所有审查员的结果（规则汇总，不调用 LLM，避免 API 超时）。

    Args:
        reviewer_results: 4 个审查员的结果
        client: OpenAI client (未使用，保留接口兼容)
        model: 模型名称 (未使用，保留接口兼容)

    Returns:
        最终报告（自然语言）
    """
    # 收集所有 findings 并去重（按 file:line 去重）
    all_findings = []
    seen = set()
    for result in reviewer_results:
        for f in result.findings:
            key = f"{f.file}:{f.line}"
            if key not in seen:
                seen.add(key)
                all_findings.append((result.reviewer, f))

    # 按严重级别排序（P0 > P1 > P2）
    severity_order = {"P0": 0, "P1": 1, "P2": 2}
    all_findings.sort(key=lambda x: severity_order.get(x[1].severity, 3))

    # 统计
    p0_count = sum(1 for _, f in all_findings if f.severity == "P0")
    p1_count = sum(1 for _, f in all_findings if f.severity == "P1")
    p2_count = sum(1 for _, f in all_findings if f.severity == "P2")
    total = len(all_findings)

    # 生成报告
    report_lines = [
        "=== 代码审查最终报告 ===",
        "",
        "【概览】",
        f"4 位审查员共发现 {sum(len(r.findings) for r in reviewer_results)} 个问题，去重后剩余 {total} 个：",
        f"- P0 致命：{p0_count} 个",
        f"- P1 严重：{p1_count} 个",
        f"- P2 建议：{p2_count} 个",
        "",
        "【高优先级问题（P0 + P1）】"
    ]

    # 只列出 P0 和 P1
    high_priority = [(reviewer, f) for reviewer, f in all_findings if f.severity in ["P0", "P1"]]
    for i, (reviewer, f) in enumerate(high_priority, 1):
        report_lines.append(f"{i}. [{f.severity}] {f.file}:{f.line} - {f.description[:60]}... ({reviewer})")

    report_lines.extend([
        "",
        "【建议】",
        f"发现 {p0_count} 个 P0 致命问题，建议立即修复后再发布。" if p0_count > 0 else "未发现 P0 致命问题。",
        f"建议优先处理 {p1_count} 个 P1 严重问题。" if p1_count > 0 else "",
        f"有 {p2_count} 个 P2 改进建议，可根据时间安排处理。" if p2_count > 0 else ""
    ])

    return "\n".join(line for line in report_lines if line)  # 过滤空行
