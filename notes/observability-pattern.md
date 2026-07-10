# Agent 可观测性模式知识笔记

> 基于项目 13 实践整理

---

## 1. 可观测性三层架构

Agent 系统的可观测性分为三层，从外到内：

```
Layer 1: 平台级 Tracing（LangSmith / Langfuse / Phoenix）
         → 零代码（LangChain 模块）或半自动（wrap_openai + @traceable）
         → 适合生产环境监控

Layer 2: 自定义 Tracer（手写 callback/event handler）
         → 不依赖外部服务，本地终端/文件输出
         → 适合开发调试、离线分析、自建平台

Layer 3: Eval（效果评估）
         → 规则匹配 + LLM-as-Judge
         → 适合质量回归、版本对比、数据集驱动开发
```

---

## 2. Tracing 接入方式对比

### LangSmith 零代码（LangChain 模块）

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=<key>
```

使用 `ChatOpenAI`、`ToolNode` 等 LangChain 模块时，设置环境变量即可。
LangSmith 自动捕获每个节点执行、LLM 调用、工具调用。

### wrap_openai + @traceable（原生 openai SDK）

```python
from langsmith.wrappers import wrap_openai
from langsmith import traceable

client = wrap_openai(OpenAI())

@traceable(run_type="tool", name="my_tool")
def my_tool(query: str) -> str:
    ...
```

- `wrap_openai` 包装 client 后，所有 `chat.completions.create` 调用自动上传 trace
- `@traceable` 装饰工具函数，trace 中显示为 tool span
- 未开启 LangSmith 时两者都是 no-op

### 自定义 Tracer（不依赖外部）

```python
class AgentTracer:
    def on_llm_start(self, prompt, model): ...
    def on_llm_end(self, response, tokens, duration): ...
    def on_tool_start(self, tool_name, args): ...
    def on_tool_end(self, tool_name, result, duration): ...
    def on_agent_step(self, step, thought, action): ...
```

在 Agent 代码关键位置手动调用，记录到内存列表，输出到终端或 JSON 文件。
本质就是在代码关键点插入记录调用——不需要任何框架。

| 方式 | 依赖 | 代码改动 | 适用场景 |
|------|------|---------|---------|
| 零代码 | langsmith + 环境变量 | 无 | LangChain 生态，生产监控 |
| wrap_openai | langsmith | 1 行包装 | 原生 SDK，生产监控 |
| @traceable | langsmith | 装饰器 | 自定义函数追踪 |
| 自定义 Tracer | 无 | 手动调用 | 开发调试，离线分析 |

---

## 3. Eval 评估模式

### 规则匹配评分器

```python
def rule_evaluator(answer, expected_keywords) -> {"pass": bool, "score": float}
```

- 检查回答是否包含必要关键词/数值
- 确定性、零成本、即时
- 适合事实型问题（"人口是多少"）

### LLM-as-Judge 评分器

```python
def llm_judge_evaluator(question, answer, reference, client) -> {"score": 1-5, "reasoning": str}
```

- 用 LLM 评估正确性/完整性/相关性
- 灵活、有 token 成本
- 适合开放型问题（"比较综合国力"）

### 评估策略

| 问题类型 | 规则匹配 | LLM-as-Judge | 组合策略 |
|---------|---------|-------------|---------|
| 事实型 | 主要（判对错） | 辅助（评表述） | 规则 pass 是底线，LLM 评质量 |
| 开放型 | 不适用 | 主要 | 只用 LLM 评分 |
| 计算型 | 主要（验数值） | 辅助 | 规则验算数值准确性 |

---

## 4. 数据集设计原则

评估数据集构造要点：

1. **事实型与开放型混合**：约各半，覆盖不同评估维度
2. **关键词精确性**：expected_keywords 必须匹配知识库实际数据
3. **多步推理覆盖**：包含需要多次工具调用的问题（"A 的老师住在哪里"）
4. **计算型问题**：需要 calculate 工具的问题，验证工具调用链完整性
5. **参考答案质量**：reference_answer 要详细但不冗余，为 LLM-as-Judge 提供对照基准

---

## 5. 降级设计模式

可观测性工具不应该影响核心功能：

```python
# 模式 1：try-except import
try:
    from langsmith import traceable
except ImportError:
    def traceable(**kwargs):
        def decorator(func): return func
        return decorator

# 模式 2：环境变量检测
import os
LANGSMITH_ENABLED = (
    os.environ.get("LANGSMITH_TRACING", "").lower() in ("true", "1", "yes")
    and os.environ.get("LANGSMITH_API_KEY", "")
)

# 模式 3：可选参数
def run(question, tracer=None):
    if tracer:
        tracer.on_llm_start(...)
    # ... 核心逻辑 ...
    if tracer:
        tracer.on_llm_end(...)
```

三种模式可以组合使用，确保：
- 包未安装 → 不报错
- 环境变量未设 → 不上传
- tracer 未传入 → 不记录

---

## 6. wrap_openai 工作原理

`wrap_openai` 返回一个 proxy client，拦截 `chat.completions.create` 等方法：

```
原始调用流程：
  client.chat.completions.create(messages=...) → OpenAI API → response

wrap_openai 后：
  wrapped_client.chat.completions.create(messages=...)
    → [记录 prompt + 参数] → OpenAI API → response → [记录 completion + tokens + 耗时]
    → 上传 span 到 LangSmith
    → 返回原始 response（不修改）
```

关键：返回值不变，调用方无感知。LangSmith 未开启时 proxy 不做任何记录，性能损耗可忽略。
