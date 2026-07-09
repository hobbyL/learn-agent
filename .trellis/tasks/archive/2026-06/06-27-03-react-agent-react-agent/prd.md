# 03-react-agent：实现 ReAct 推理模式

## Goal

手写实现 ReAct（Reasoning + Acting）模式的 Agent，体验"显式推理链"相比"直接工具调用"在复杂多步任务上的优势。通过虚构小世界知识库消除 LM 先验知识干扰，强迫 Agent 老实走 Thought → Action → Observation 循环。

## Requirements

### 核心循环
- 纯文本 ReAct 格式：prompt 引导 LM 输出 `Thought: / Action: / Observation:` 结构化文本
- 我们用正则解析提取 Action 和参数，执行工具后注入 Observation
- 循环终止条件：LM 输出 `Final Answer:` 或达到 max_steps 上限
- 格式容错：解析失败时提示 LM 重新输出正确格式（不直接崩）

### 双模式对比
- 环境变量 `AGENT_MODE=react | direct` 切换两种模式
- `react_agent.py`：完整 ReAct 循环（显式 Thought）
- `direct_agent.py`：01 风格直接工具调用（隐式推理，用 OpenAI Function Calling）
- 共享工具层（tools.py + knowledge_base.py）
- main.py 根据 AGENT_MODE 选择实例化哪个 Agent

### 虚构小世界知识库
- 自编一个小宇宙（几个王国/城市、角色、物品等），数据完全虚构
- LM 先验知识帮不上忙，必须调工具才能获取信息
- 数据量适中（20-30 条实体，每个实体 4-6 个属性），够支撑多步推理

### 工具集（4 个）
| 工具名 | 功能 | 参数 |
|--------|------|------|
| `search(query)` | 模糊搜索知识库，返回匹配条目摘要列表 | query: str |
| `lookup(entity, field)` | 精确查询实体的某个属性值 | entity: str, field: str |
| `calculate(expression)` | 计算数学表达式（安全 eval） | expression: str |
| `compare(entity_a, entity_b, field)` | 比较两个实体的同一属性 | entity_a: str, entity_b: str, field: str |

### 推理链可视化
- 运行时清晰打印每一步 Thought / Action / Observation（彩色/分隔符区分）
- 最终显示完整推理链步数、调用了哪些工具、耗时

### Action 格式约定
- 采用 `Action: tool_name(arg1, arg2, ...)` 单行式
- 参数用逗号分隔，字符串加引号
- 示例：`Action: lookup("星辰王国", "面积")`

## Acceptance Criteria

- [ ] ReAct 模式能完成 3 步以上的链式推理任务（如"A 的面积是 B 的几倍"）
- [ ] Direct 模式能完成同样任务，但无可见推理过程
- [ ] 同一个问题，两种模式的输出有明显结构差异（一个有 Thought 链，一个没有）
- [ ] 格式错误时 Agent 不崩溃，能提示 LM 重试
- [ ] max_steps 到达时优雅终止并告知用户
- [ ] 虚构数据问题 LM 不调工具则无法正确回答（验证工具依赖性）
- [ ] 推理链可视化清晰可读

## Definition of Done

- 代码注释完整（学习项目标准：每个文件有模块 docstring 解释设计意图）
- README 包含运行说明、架构图、示例输出
- notes.md 记录实现过程中的发现和教训
- 能跑通至少 5 个不同难度的测试问题

## Technical Approach

### 项目结构
```
projects/03-react-agent/
├── main.py              # 入口，根据 AGENT_MODE 切换
├── react_agent.py       # ReAct 循环实现（文本解析版）
├── direct_agent.py      # 直接工具调用（Function Calling 版，对照）
├── tools.py             # 4 个工具的实现
├── knowledge_base.py    # 虚构小世界数据 + 查询接口
├── parser.py            # ReAct 文本格式解析器（正则）
├── prompts.py           # system prompt（两种模式各一套）
├── requirements.txt     # 依赖
├── .env.example         # 配置说明
├── README.md            # 项目文档
└── notes.md             # 学习笔记
```

### 关键设计
1. **知识库**：Python dict/JSON 存储虚构数据，tools.py 的 search/lookup/compare 都查它
2. **解析器**：正则匹配 `Thought:`, `Action:`, `Final Answer:` 前缀，提取内容
3. **容错**：解析失败 → 追加一条消息"请按规定格式输出"→ 重试（最多 2 次）
4. **日志**：用 rich 或 ANSI 颜色区分 Thought（蓝）/ Action（黄）/ Observation（绿）/ Error（红）

## Decision (ADR-lite)

**Context**: 需要在学习 ReAct 的同时对比"有推理链"和"无推理链"的差异  
**Decision**: 环境变量切换 + 两个独立 agent 文件，共享工具层  
**Consequences**: 代码清晰分离便于学习，但工具层和 main.py 是共享的单一入口

## Out of Scope

- 反思层 / 自我纠正循环（留给 04-reflection）
- 动态工具加载 / MCP
- 流式输出
- Pydantic 参数校验（03 专注推理模式，工具参数简单）
- 多轮对话记忆（单问题单推理链）

## Technical Notes

- 独立项目，不复用 02 代码，从零开始
- 共享虚拟环境：复用 `01-simple-agent/.venv`（已有 openai, python-dotenv）
- Action 解析参考 ReAct 原论文格式，适度简化
- 虚构世界消除 LM 先验知识 → 最能暴露"不调工具就瞎编"的问题
