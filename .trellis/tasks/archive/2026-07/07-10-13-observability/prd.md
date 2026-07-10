# 13-observability

## Goal

为 Agent 系统构建完整的可观测性体验：**链路追踪（tracing）+ 效果评估（eval）+ 自定义 tracer**。

通过对比"LangChain 模块零代码追踪"和"原生 openai SDK 手动接入追踪"两条路径，理解 Agent observability 的分层架构。通过混合评估（规则匹配 + LLM-as-Judge），理解不同评估方式的适用场景。

## Background

项目 12 已完成 LangSmith 的零代码集成（环境变量开启），但仅限于 LangChain 模块（ChatOpenAI / ToolNode）。本项目在此基础上深入三个层面：

1. **Tracing**：LangSmith 零代码（LangGraph Agent）vs `wrap_openai` + `@traceable`（手写 Agent）
2. **Eval**：构造测试数据集 + 规则匹配评分器 + LLM-as-Judge 评分器，批量评估 Agent 质量
3. **自定义 Tracer**：不依赖 LangSmith，手写 callback/tracer 输出到终端和 JSON 文件

被观测对象：
- 项目 12 的 LangGraph Agent（v2 StateGraph）——零代码追踪
- 项目 03 的手写 ReAct Agent——手动接入追踪

两者共享星云大陆知识库，eval 测试集通用。

## Requirements

### 1. Tracing 双路径

- **LangGraph Agent 零代码追踪**：复用项目 12 的 `agent_v2_stategraph.py`，LangSmith 环境变量开启即自动追踪
- **手写 Agent 手动接入追踪**：复用项目 03 的 `react_agent.py`，用 `wrap_openai(openai.Client())` 包装 client，工具函数加 `@traceable` 装饰器
- 有 LangSmith 时：trace 上传到 LangSmith 平台，输出查看链接
- 无 LangSmith 时：优雅降级，打印提示，切换到自定义 tracer 本地输出

### 2. Eval 双评分器

- **测试数据集**：6-8 个问题，JSON 文件持久化（`eval_dataset.json`）
  - 事实型（约一半）：有明确答案，如"星辰王国的人口是多少？"
  - 开放型（约一半）：需要综合判断，如"比较星辰王国和月影帝国的军事实力"
- **规则匹配评分器**：检查回答是否包含必要关键词/数值，返回 pass/fail + 匹配详情
- **LLM-as-Judge 评分器**：用 LLM 评估回答的正确性/完整性/相关性，返回 1-5 分 + 理由
- 对两个 Agent（LangGraph / 手写）都跑完整 eval，输出对比表格

### 3. 自定义 Tracer

- 手写一个 tracer/callback，不依赖 LangSmith SDK
- 捕获：LLM 调用（prompt/completion/token/耗时）、工具调用（名称/参数/结果/耗时）、Agent 步骤（step number/thought/action）
- 输出两种格式：
  - 终端 ANSI 着色实时展示（类似 debug 日志）
  - JSON 文件持久化（`trace_output.json`），可离线分析

### 4. CLI 入口

- `--trace`：运行单个问题，展示完整 trace 输出（自定义 tracer 终端渲染）
- `--eval`：批量运行 eval 数据集，输出评分表格
- `--compare`：对比 LangGraph Agent vs 手写 Agent 的 trace/eval 结果
- `--demo`：默认模式，依次演示 trace → eval → 对比总结

### 5. LangSmith 可选

- 检测 `LANGSMITH_TRACING` + `LANGSMITH_API_KEY` 环境变量
- 有：上传 trace + 在 eval 中使用 LangSmith Datasets API
- 无：所有功能正常运行，trace 输出到本地终端/文件，eval 结果在终端展示

## Acceptance Criteria

- [ ] `python main.py --demo` 无 LangSmith 时正常运行，展示自定义 tracer 输出 + eval 结果
- [ ] `python main.py --trace` 对手写 Agent 展示完整 trace（LLM 调用 + 工具调用 + 耗时）
- [ ] `python main.py --eval` 输出 6-8 个问题的评分表格（规则匹配 + LLM-as-Judge 两列）
- [ ] `python main.py --compare` 对比两个 Agent 的 eval 结果
- [ ] 设置 `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` 后，trace 上传到 LangSmith
- [ ] 未设置 LangSmith 时不报错，自动降级到本地输出
- [ ] `eval_dataset.json` 包含事实型和开放型混合问题
- [ ] 自定义 tracer 输出 `trace_output.json` 可用 JSON 解析
- [ ] `requirements.txt` 包含 `langsmith`、`langchain-openai`、`langgraph`、`openai`

## Definition of Done

- 所有 AC 通过 demo 运行验证
- `README.md` 含 tracing/eval/自定义 tracer 三层说明、对比表格、快速开始
- `notes.md` 记录踩坑
- `notes/observability-pattern.md` 知识笔记已写（根目录 `notes/`）
- 全局 `README.md` 和 `progress/2026-07.md` 已更新

## Technical Approach

### 文件结构

```
projects/13-observability/
├── knowledge_base.py         # 从 03 复制（星云大陆，不修改）
├── tools.py                  # 适配：原 execute_tool + @traceable 版本 + @tool 版本
├── agent_handwritten.py      # 从 03 复用，接入 wrap_openai + @traceable
├── agent_langgraph.py        # 从 12 复用 v2 StateGraph
├── custom_tracer.py          # 自定义 tracer（终端 ANSI + JSON 文件输出）
├── eval_runner.py            # 评估引擎：加载数据集 + 运行 Agent + 调用评分器
├── evaluators.py             # 规则匹配评分器 + LLM-as-Judge 评分器
├── eval_dataset.json         # 测试数据集（6-8 个问题 + 标准答案/关键词）
├── display.py                # ANSI 渲染（trace 视图 + eval 表格 + 对比）
├── main.py                   # CLI 入口
├── requirements.txt
├── .env.example
├── README.md
└── notes.md
```

### 自定义 Tracer 设计

```python
class AgentTracer:
    """不依赖 LangSmith 的轻量 tracer"""
    
    def on_llm_start(self, prompt, model): ...
    def on_llm_end(self, response, tokens, duration): ...
    def on_tool_start(self, tool_name, args): ...
    def on_tool_end(self, tool_name, result, duration): ...
    def on_agent_step(self, step, thought, action): ...
    
    def to_json(self) -> dict: ...      # 导出为 JSON
    def print_summary(self): ...         # 终端汇总
```

手写 Agent 在关键位置手动调用 tracer 方法（非装饰器模式），展示"tracer 的本质就是在代码关键点插入记录调用"。

### Eval 数据集格式

```json
[
  {
    "question": "星辰王国的人口是多少？",
    "type": "factual",
    "expected_keywords": ["120000", "12万"],
    "reference_answer": "星辰王国的人口为 120,000"
  },
  {
    "question": "比较星辰王国和月影帝国的军事实力",
    "type": "open",
    "reference_answer": "星辰王国以骑兵和城防见长..."
  }
]
```

### 依赖

```
openai>=1.12.0
langgraph>=0.2.57
langchain-openai>=0.2.0
langsmith>=0.1.0
python-dotenv>=1.0.0
```

## Out of Scope

- LangSmith Datasets API（在线数据集管理）——只用本地 JSON 文件
- LangGraph Studio / LangSmith Playground
- 持续集成 eval（CI/CD 集成）——只做单次批量运行
- A/B 测试 / 实验跟踪
- LangChain Callbacks 底层 API（用 `@traceable` 和 `wrap_openai` 高层接口）

## Technical Notes

- 项目 12 路径：`projects/12-framework-and-observability/`（agent_v2_stategraph.py / tools.py）
- 项目 03 路径：`projects/03-react-agent/`（react_agent.py / tools.py / knowledge_base.py）
- LangSmith 研究：`.trellis/tasks/archive/2026-07/07-09-12-framework-and-observability/research/langgraph-overview.md` §4
- `wrap_openai` 包装原生 client 后，LangSmith 可追踪所有 `chat.completions.create` 调用
- `@traceable(run_type="tool")` 装饰工具函数，trace 中会显示为 tool span
