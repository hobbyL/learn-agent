# 13-observability · 开发笔记

## 架构设计决策

### 1. tools.py 三套接口的层次关系

三套接口共享相同的底层业务函数（search/lookup/calculate/compare）：

```
业务函数 search()
  ├── @traceable 装饰器（LangSmith 可用时记录 tool span）
  │
  ├── execute_tool("search", args)  → 手写 Agent 使用
  │
  ├── @tool search_tool()          → LangGraph Agent 使用
  │       └── 内部调用 search()
  │
  └── lc_tools = [search_tool, ...]  → 传给 bind_tools / ToolNode
```

关键设计：`@traceable` 直接装饰业务函数而不是 `execute_tool`，
这样无论从哪个入口调用，LangSmith 都能捕获工具执行的 span。

### 2. 自定义 Tracer 的手动调用模式

PRD 明确要求"手动调用"而非自动注入，展示 tracer 的本质：

```python
# agent_handwritten.py 中的关键调用点
tracer.on_llm_start(...)     # LLM 调用前
tracer.on_llm_end(...)       # LLM 调用后
tracer.on_tool_start(...)    # 工具执行前
tracer.on_tool_end(...)      # 工具执行后
tracer.on_agent_step(...)    # 每步 Thought/Action 解析后
```

这和 LangSmith 的 `@traceable` 装饰器模式形成对比：
- 装饰器模式：代码侵入小，自动捕获函数入参和返回值
- 手动调用模式：灵活，可以记录任意中间状态（如 Thought 内容）

### 3. LangSmith 可选降级策略

```python
# wrap_openai 降级
try:
    from langsmith.wrappers import wrap_openai
except ImportError:
    def wrap_openai(client): return client  # identity

# @traceable 降级
try:
    from langsmith import traceable
except ImportError:
    def traceable(**kwargs):
        def decorator(func): return func
        return decorator
```

langsmith 包不可用时，所有装饰器和包装器退化为 no-op，
程序功能完全不受影响。

### 4. Eval 双评分器设计

规则匹配和 LLM-as-Judge 的互补：

| 维度 | 规则匹配 | LLM-as-Judge |
|------|---------|-------------|
| 速度 | 即时 | 需要 LLM 调用 |
| 成本 | 零 | token 消耗 |
| 适用 | 事实型（关键词/数值） | 开放型（综合判断） |
| 可靠性 | 确定性 | 有一定随机性 |
| 评分维度 | pass/fail | 1-5 分 + 多维度 |

事实型问题两者都跑：规则匹配判断基本对错，LLM-as-Judge 评估表述质量。
开放型问题只跑 LLM-as-Judge（无法预定义关键词）。

---

## 踩坑记录

### wrap_openai 的 import 时机

`wrap_openai` 必须在创建 client 时使用，不能事后包装：

```python
# 正确
raw_client = OpenAI()
wrapped_client = wrap_openai(raw_client)

# 使用 wrapped_client 进行所有 LLM 调用
```

### @traceable 的 run_type 参数

`@traceable(run_type="tool")` 让工具调用在 LangSmith trace 中
显示为 tool span 而不是 chain span，视觉上更清晰。

### eval_dataset.json 关键词精度

expected_keywords 必须准确对应知识库中的实际数据：
- 星辰王国人口 = 120000（不是 12 万，除非两种都写上）
- 翡翠联邦面积 = 12000
- 熔岩战锤重量 = 8.7

开放型问题的 expected_keywords 设为空列表，规则匹配自动返回 pass。

### LLM-as-Judge 的输出解析

LLM 评估结果需要 JSON 格式，但 LLM 可能输出：
- 纯 JSON
- markdown 代码块包裹的 JSON
- 文字 + JSON 混合

`evaluators.py` 的 `_extract_json()` 用三种策略依次尝试。

---

## 和项目 12 的关系

项目 12 完成了 LangSmith 零代码集成（环境变量开启），但只涉及 LangGraph 模块。
项目 13 在此基础上深入三个层面：

1. 对比两条 tracing 路径（零代码 vs 手动接入）
2. 增加了 eval 评估维度（规则匹配 + LLM-as-Judge）
3. 实现了不依赖 LangSmith 的自定义 tracer

本质上，12 是"用框架"，13 是"理解框架背后的原理并手写替代方案"。
