# 04-agent-reflection —— 自我反思 Agent（Reflexion）

## 项目目标

实现 **Reflexion** 模式：在 ReAct 循环外层包裹"试错 → 评估 → 反思 → 重试"闭环。

Agent 执行完一轮任务后，自动评估结果质量，识别错误原因，生成反思摘要，
然后将反思注入 system prompt 作为额外上下文重试，直到答案达标或重试次数耗尽。

**核心学习目标**：理解"试错 + 反思 + 重试"如何系统性提升 Agent 任务完成率，
体会 Reflexion 相比"无脑重试"的结构性优势——反思提供了方向性修正而非随机重试。

---

## 架构

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
│      result = react_loop.run(question, reflections)      │
│      evaluation = evaluator.evaluate(question, result)   │
│      if evaluation.is_correct: break                     │
│      reflection = reflector.reflect(...)                  │
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
│  tools.py + knowledge_base.py（深海联盟虚构世界）            │
└──────────────────────────────────────────────────────────┘
```

---

## Reflexion 工作流程

```
问题输入
    │
    ▼
┌─────────────────────────────┐
│  Trial 1: 内层 ReAct 循环    │
│  Thought → Action → Obs...  │
│  → Final Answer             │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  评估（Evaluate）            │  ← Ground Truth 或 LLM Judge
│  正确？ → 返回答案           │
│  错误？ → 继续反思           │
└──────────┬──────────────────┘
           │ 错误
           ▼
┌─────────────────────────────┐
│  反思（Reflect）             │  ← LLM 分析：哪里错→为什么→怎么改
│  生成反思摘要                │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  Trial 2: 带反思的 ReAct     │  ← 反思注入 system prompt
│  （有了上次教训的加持）        │
└──────────┬──────────────────┘
           │
           ▼
         ...（最多 MAX_TRIALS 轮）
```

---

## 快速开始

### 1. 环境准备

```bash
cd projects/04-agent-reflection
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY
```

### 2. 演示模式

```bash
# 预设问题演示（展示反思效果）
python main.py --demo

# 对比模式：同一问题"无反思" vs "有反思"
python main.py --compare

# 交互模式
python main.py
```

### 3. 配置选项

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `OPENAI_MODEL` | 使用的模型 | gpt-4o-mini |
| `MAX_TRIALS` | 最大反思轮数 | 3 |
| `MAX_STEPS` | 每轮 ReAct 最大步数 | 10 |
| `EVALUATOR_MODE` | 评估器模式 | ground_truth |

---

## 知识库：深海联盟

全新虚构水下世界，包含 32 个实体：

- **海洋国度**：珊瑚帝国、深渊王国、极光联邦、潮汐共和国、冰渊部落
- **深海城市**：珊瑚城、珊瑚礁堡（易混淆！）、暗流堡、极光港等
- **人物**：各国统治者、学者、工匠，带有师承和亲缘关系
- **神器**：各种深海法器，附带持有者和来源地信息

### 陷阱设计（故意让 Agent 犯错）

1. **名字相似**："珊瑚城"vs"珊瑚礁堡"——Agent 容易查错实体
2. **多步链式推理**：需要 3-4 步才能得到的答案（A 的导师 → 导师的武器 → 武器的产地）
3. **字段容易混淆**：面积/人口数值接近，单位不同
4. **隐含关联**：需要交叉验证的信息

---

## ✅ 完成标准

| 标准 | 状态 |
|------|------|
| 外层 Reflexion 循环：trial → evaluate → reflect → retry | ✅ |
| 内层轻量 ReAct 循环（去掉跳步检测，让错误自然发生） | ✅ |
| 反思摘要注入 system prompt 尾部（论文标准做法） | ✅ |
| 双轨评估器：GroundTruth（程序比对）+ LLMJudge（LLM 评估） | ✅ |
| `EVALUATOR_MODE` 环境变量切换两种评估器 | ✅ |
| 反思器（Reflector）生成"哪里错→为什么→怎么改"摘要 | ✅ |
| `--demo` 模式运行预设题展示完整反思循环 | ✅ |
| `--compare` 模式并排对比"无反思 vs 有反思"效果 | ✅ |
| max_steps / max_trials 到达时优雅终止 | ✅ |
| 深海联盟知识库 32 个实体，含陷阱设计（易混淆实体名） | ✅ |
| 10 道预设测试题，答案路径全部经 `lookup_entity()` 验证可达 | ✅ |

---

## 设计决策

### 1. 为什么要内层重写 ReAct 而不复用 03？

04 的内层 ReAct 故意**不做跳步检测**——让 Agent 更容易犯错，
这样才能触发反思循环。如果内层太严格（像 03 那样有护栏），
Agent 很难犯错，反思机制就无从施展。

### 2. 双轨评估器的取舍

| | Ground Truth | LLM Judge |
|--|-------------|-----------|
| 确定性 | 高（程序比对） | 低（LLM 主观判断） |
| 灵活性 | 低（需预定义答案） | 高（任意问题） |
| API 开销 | 无 | 额外一次 LLM 调用 |
| 适用场景 | 自动化测试 | 开放性问题 |

### 3. 反思注入位置

反思摘要追加到 system prompt 末尾（不是 user 消息），
这样 LLM 在推理第一步就能看到所有历史教训。

### 4. 为什么 MAX_TRIALS 默认 3？

Reflexion 论文实验表明 2-3 轮反思后改进趋于饱和，
超过 3 轮通常说明问题本身超出模型能力，继续反思只会浪费 token。

---

## 文件说明

| 文件 | 职责 |
|------|------|
| `main.py` | 入口，--demo / --compare / 交互模式 |
| `reflexion_agent.py` | 外层 Reflexion 循环编排 |
| `react_loop.py` | 内层轻量 ReAct（Thought → Action → Observation） |
| `evaluator.py` | 双轨评估器（Ground Truth + LLM Judge） |
| `reflector.py` | 反思生成器（LLM 分析错误原因） |
| `tools.py` | 工具层（search / lookup / calculate / compare） |
| `knowledge_base.py` | 深海联盟虚构世界知识库 |
| `test_questions.py` | 预设测试问题 + 标准答案（10 道，含答案路径验证） |

---

## 与 03 的关系

| | 03-react-agent | 04-agent-reflection |
|--|---------------|---------------------|
| 核心模式 | ReAct | Reflexion（ReAct + 反思外层） |
| 错误处理 | 代码护栏（跳步检测） | LLM 自我反思 |
| 重试 | 无（一次性） | 有（最多 3 轮） |
| 知识库 | 星云大陆 | 深海联盟（新） |
| 学习重点 | 显式推理链 | 试错改进循环 |

---

## 经典论文

**Reflexion: Language Agents with Verbal Reinforcement Learning**
- 作者：Noah Shinn et al.
- 发表：2023
- 链接：https://arxiv.org/abs/2303.11366

---

**最后更新**：2026-06-28
