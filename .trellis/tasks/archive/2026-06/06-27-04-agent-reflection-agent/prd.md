# 04-agent-reflection：自我反思 Agent

## Goal

实现 Reflexion 模式的 Agent——在 ReAct 循环外层包裹"试错→评估→反思→重试"闭环。
Agent 执行完一轮任务后，自动评估结果质量，识别错误原因，生成反思摘要，
然后将反思注入 system prompt 作为额外上下文重试，直到答案达标或重试次数耗尽。

核心学习目标：理解"试错 + 反思 + 重试"如何系统性提升 Agent 任务完成率，
体会 Reflexion 相比"无脑重试"的结构性优势——反思提供了方向性修正而非随机重试。

## What I already know

* 03 已实现完整的 ReAct 循环（Thought → Action → Observation → Final Answer）
* 03 的跳步检测是"代码护栏"式的硬规则，04 的反思是"LLM 自我评估"式的软改进
* 项目使用 OpenAI API（通过 python-dotenv 配置），复用虚拟环境
* 虚构知识库已验证能有效强迫 Agent 调工具
* 项目风格：单目录平铺文件，不做深层子目录，注释详尽

## Design Decisions (confirmed)

### 1. 反思粒度：整轮反思（Reflexion 论文风格）

外层循环在内层 ReAct 跑完一整轮后才触发评估+反思。
结构清晰，外层和内层职责分离，和论文一致。

### 2. 评估器：双轨制

- **Ground Truth 评估器**：预定义标准答案，程序自动比对。用于自动化测试、可重复验证。
- **LLM-as-Judge 评估器**：额外 LLM 调用评估答案质量。用于演示模式、展示真实场景。
- 通过 .env 配置切换：`EVALUATOR_MODE=ground_truth | llm_judge`

### 3. 内层执行器：04 内部重写轻量 ReAct 循环

每个项目功能独立，自包含。04 重写一个聚焦于"反思"的 ReAct 循环，
不依赖 03 的代码。可以简化（比如不做跳步检测），让 Agent 更容易犯错以触发反思。

### 4. 反思记忆传递：注入 system prompt（论文标准做法）

维护 `reflections: list[str]` 缓冲区，每次重试时把历次反思拼接后
追加到 system prompt 末尾。LLM 在推理第一步就能看到之前的教训。

### 5. 知识库：新建虚构世界

设计一套全新的虚构世界（比如"深海联盟"），实体关系更复杂、
设计"容易犯错"的推理链（名字相似的实体、需要 3+ 步才能推出的关系），
让弱模型更容易在第一轮出错以触发反思。

### 6. 配置化

- `MAX_TRIALS`：最大反思轮数，默认 3，通过 .env 配置
- `EVALUATOR_MODE`：评估器模式，通过 .env 配置
- 其他配置复用 03 模式（OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL 等）

## Requirements

* 实现外层 Reflexion 循环（trial → evaluate → reflect → retry）
* 双轨评估器（Ground Truth + LLM-as-Judge），通过配置切换
* 反思器生成有价值的经验总结，注入下一轮 system prompt
* 内层轻量 ReAct 循环（04 内部独立实现）
* 新建虚构知识库，设计容易触发反思的复杂实体关系
* `--compare` 模式：同一问题跑"无反思（单轮 ReAct）" vs "有反思（Reflexion 多轮）"并排对比
* `--demo` 模式：预设测试问题演示
* 3 轮反思后仍错，优雅终止并输出"反思历程摘要"供人类审阅
* 彩色可视化输出（Trial / Evaluation / Reflection / Final Result 分层展示）

## Acceptance Criteria

* [ ] Agent 能在首次犯错后通过反思在后续轮次改正答案
* [ ] Ground Truth 评估器能准确判断答案正确性
* [ ] LLM-as-Judge 评估器能给出有意义的质量评分和反馈
* [ ] 反思摘要能明确指出"哪里错了→为什么错→下次怎么改"
* [ ] `--compare` 模式直观展示反思带来的改进
* [ ] max_trials 到达时优雅终止，输出反思历程摘要
* [ ] 新知识库的"陷阱问题"能有效触发第一轮失败
* [ ] 所有配置通过 .env 管理

## Definition of Done

* 5 个以上测试问题验证通过（覆盖不同难度和反思场景）
* README 文档完整（和 03 同等质量：架构图、流程图、快速开始、设计决策）
* notes.md 记录关键发现和踩坑

## Out of Scope (explicit)

* 不做跨问题的长期记忆持久化（那是 05-memory-system）
* 不做多 Agent 辩论式反思（那是 09 的内容）
* 不做步级微反思（04 只做整轮反思）
* 反思记忆不持久化到文件（仅运行时内存）

## Technical Approach

### 架构

```
┌──────────────────────────────────────────────────────────┐
│                    main.py（入口）                          │
│  --demo / --compare / 交互式                              │
└──────────────┬───────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│              reflexion_agent.py（外层循环）                  │
│                                                          │
│  reflections = []                                        │
│  for trial in range(max_trials):                         │
│      result = react_agent.run(question, reflections)     │
│      evaluation = evaluator.evaluate(question, result)   │
│      if evaluation.is_correct: break                     │
│      reflection = reflector.reflect(question, result,    │
│                                     evaluation)          │
│      reflections.append(reflection)                      │
│  return final_result + reflection_history                │
└──────────────┬───────────────────────────────────────────┘
               │
       ┌───────┼───────────┐
       ▼       ▼           ▼
┌──────────┐ ┌──────────┐ ┌──────────────┐
│react_loop│ │evaluator │ │  reflector   │
│  .py     │ │  .py     │ │    .py       │
│          │ │          │ │              │
│轻量 ReAct│ │Ground    │ │LLM 生成反思  │
│循环      │ │Truth +   │ │摘要          │
│          │ │LLM Judge │ │              │
└──────────┘ └──────────┘ └──────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│  tools.py + knowledge_base.py（新虚构世界）                  │
└──────────────────────────────────────────────────────────┘
```

### 文件结构

```
04-agent-reflection/
├── README.md              # 项目文档
├── main.py                # 入口（--demo / --compare / 交互）
├── reflexion_agent.py     # 外层 Reflexion 循环
├── react_loop.py          # 内层轻量 ReAct 循环
├── evaluator.py           # 双轨评估器（Ground Truth + LLM Judge）
├── reflector.py           # 反思器（生成反思摘要）
├── tools.py               # 工具集
├── knowledge_base.py      # 新虚构世界（含陷阱设计）
├── test_questions.py      # 预设测试问题 + 标准答案
├── notes.md               # 学习笔记
├── requirements.txt       # 依赖
├── .env.example           # 环境变量说明
└── .env                   # 真实配置（不提交）
```

## Technical Notes

* Reflexion 论文：https://arxiv.org/abs/2303.11366
* 前置项目：03-react-agent（已完成）
* 知识库"陷阱设计"思路：
  - 名字相似实体（如"深渊城"vs"深渊堡"）
  - 需要 3-4 步链式推理才能得到的答案
  - 字段间存在隐含矛盾需要交叉验证的数据
  - 容易混淆的数值（人口 vs 面积单位不同）
