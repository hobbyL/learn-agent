# 13 · Observability

> Agent 可观测性：链路追踪（tracing）+ 效果评估（eval）+ 自定义 tracer

---

## 目标

为 Agent 系统构建完整的可观测性体验，通过三层递进理解 observability 的分层架构：

```
Layer 1: Tracing      → 零代码追踪（LangGraph）vs 手动接入（wrap_openai + @traceable）
Layer 2: Eval          → 规则匹配评分器 + LLM-as-Judge 评分器
Layer 3: Custom Tracer → 不依赖 LangSmith，手写 tracer 输出到终端/JSON
```

---

## 三层可观测性对比

| 层 | 方式 | 适用场景 | 依赖 |
|----|------|---------|------|
| Tracing (零代码) | LangSmith 环境变量 | LangChain 模块（ChatOpenAI、ToolNode） | langsmith + 环境变量 |
| Tracing (手动) | `wrap_openai` + `@traceable` | 原生 openai SDK | langsmith |
| Tracing (自定义) | `AgentTracer` 手写类 | 任何场景，不依赖外部服务 | 无 |
| Eval (规则) | 关键词匹配 | 事实型问题，快速确定性判断 | 无 |
| Eval (LLM-as-Judge) | LLM 评估 1-5 分 | 开放型问题，综合质量评估 | openai |

---

## 被观测对象

| Agent | 实现方式 | Tracing 接入 |
|-------|---------|-------------|
| 手写 ReAct Agent | 纯文本格式 + 正则解析（来自项目 03） | `wrap_openai` + `@traceable` + 自定义 tracer |
| LangGraph Agent | StateGraph + ToolNode（来自项目 12） | LangSmith 零代码追踪 |

两者共享星云大陆知识库，eval 测试集通用。

---

## 文件结构

```
projects/13-observability/
├── knowledge_base.py       # 星云大陆虚构知识库（从 03 复制，不修改）
├── tools.py                # 三套接口：execute_tool + @traceable 版本 + @tool 版本
├── agent_handwritten.py    # 手写 ReAct Agent（接入 wrap_openai + custom_tracer）
├── agent_langgraph.py      # LangGraph StateGraph Agent（零代码追踪）
├── custom_tracer.py        # 自定义 tracer（终端 ANSI + JSON 文件输出）
├── eval_runner.py          # 评估引擎：加载数据集 + 运行 Agent + 调用评分器
├── evaluators.py           # 规则匹配评分器 + LLM-as-Judge 评分器
├── eval_dataset.json       # 测试数据集（8 个问题：5 事实型 + 3 开放型）
├── display.py              # ANSI 渲染（trace 视图 + eval 表格 + 对比）
├── main.py                 # CLI 入口
├── requirements.txt
├── .env.example
├── README.md
└── notes.md
```

---

## 快速开始

### 1. 安装依赖

```bash
cd projects/13-observability
uv venv .venv --python 3.13
source .venv/bin/activate
uv pip install -r requirements.txt
```

### 2. 配置环境

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY（必需）和 OPENAI_BASE_URL（可选）
```

### 3. 运行

```bash
# 推荐首次运行：trace 演示 + eval 精简版 + 总结
python main.py --demo

# 手写 Agent + 自定义 tracer（展示完整 trace 输出）
python main.py --trace

# 手写 Agent 完整 eval（8 个问题）
python main.py --eval

# 手写 Agent vs LangGraph Agent 对比 eval
python main.py --compare
```

---

## LangSmith Tracing（可选）

无 LangSmith 时所有功能正常运行，自动降级到本地输出。

开启方法：

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=<your-key>
export LANGSMITH_PROJECT=13-observability
```

开启后：
- LangGraph Agent 的 trace 自动上传（零代码）
- 手写 Agent 的 LLM 调用通过 `wrap_openai` 自动追踪
- 工具调用通过 `@traceable` 自动追踪

在 [smith.langchain.com](https://smith.langchain.com) 查看完整 trace 视图。

---

## 自定义 Tracer

`custom_tracer.py` 实现了不依赖 LangSmith 的轻量 tracer：

```python
from custom_tracer import AgentTracer

tracer = AgentTracer(verbose=True)
tracer.on_llm_start("...", "gpt-4o-mini")
tracer.on_llm_end("...", tokens=150, duration_ms=1200)
tracer.on_tool_start("lookup", {"entity": "星辰王国", "field": "人口"})
tracer.on_tool_end("lookup", "120000", duration_ms=5)
tracer.on_agent_step(1, "我需要查找人口", "lookup")

tracer.print_summary()       # 终端汇总
tracer.to_json("trace.json") # 持久化
```

输出 `trace_output.json` 包含每个 span 的完整信息，可离线分析。

---

## Eval 数据集

`eval_dataset.json` 包含 8 个问题（5 事实型 + 3 开放型），基于星云大陆知识库构造：

- 事实型：有明确答案和关键词，用规则匹配评分
- 开放型：需要综合判断，用 LLM-as-Judge 评分

双评分器互补：规则匹配快速判断对错，LLM-as-Judge 评估表述质量。

---

## 关键学习点

1. **Tracing 分层**：零代码（LangChain 模块 + 环境变量）→ 手动接入（wrap_openai + @traceable）→ 自定义（手写 tracer），三种方式各有适用场景

2. **自定义 Tracer 的本质**：就是在代码关键点插入记录调用（on_llm_start/end、on_tool_start/end），不需要任何框架

3. **Eval 双评分器**：规则匹配（确定性、零成本）+ LLM-as-Judge（灵活、有成本），事实型问题优先规则匹配，开放型问题必须 LLM 评估

4. **LangSmith 可选降级**：所有功能设计为 LangSmith 可选。`@traceable` 和 `wrap_openai` 在未开启时是 no-op，不影响功能

5. **wrap_openai 的价值**：一行代码让原生 openai SDK 获得 LangSmith 追踪能力，无需改动业务逻辑

---

## 知识库场景

复用项目 03 的"星云大陆"虚构知识库（~25 个实体），包含王国、城市、人物、物品等。

经典 eval 问题示例：
- 事实型："星辰王国的人口是多少？"（关键词匹配 120000）
- 计算型："星辰王国的面积是月影王国的多少倍？"（需要工具调用 + 计算）
- 开放型："比较星辰王国和烈焰帝国的综合国力"（需要 LLM-as-Judge 评估）
