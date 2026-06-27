# 项目 03：ReAct 推理模式 — 学习笔记

> 在实现过程中遇到的问题、踩的坑、想通的点，随手记在这里。
> 完成后再把通用知识提炼到主目录 `notes/`。

---

## 实现日志

### 2026-06-27 从零新建 ReAct Agent 项目

本项目不复用 02 代码，独立实现，聚焦于 ReAct 推理模式本身。

- **knowledge_base.py**：自编"星云大陆"虚构世界，共 24 个实体（王国、城市、英雄、物品），
  每个实体 4-6 个属性，数据完全虚构。核心目标：LLM 先验知识帮不上忙，
  必须老老实实调工具才能作答。

- **tools.py**：4 个工具，全部基于知识库：
  - `search(query)`：模糊搜索，返回匹配实体摘要列表
  - `lookup(entity, field)`：精确查询实体的某个属性值
  - `calculate(expression)`：安全 eval，支持数学表达式
  - `compare(entity_a, entity_b, field)`：比较两个实体的同一属性

- **parser.py**：正则解析器，从 LLM 输出文本中提取 `Thought:` / `Action:` / `Final Answer:` 结构

- **react_agent.py**：纯文本 ReAct 循环。核心逻辑：
  1. LLM 输出一段包含 `Thought:` 和 `Action:` 的文本
  2. 解析器提取工具名和参数，执行工具
  3. 把 `Observation:` 结果追加到对话历史
  4. 重复，直到出现 `Final Answer:` 或达到 max_steps

- **direct_agent.py**：Function Calling 对照组，用 OpenAI 的 `tool_calls` 机制，
  推理过程隐式，只看到最终答案。

- **main.py**：入口，读取 `AGENT_MODE=react|direct` 环境变量，切换实例化哪个 Agent。
  支持 `--compare` 命令同时跑两种模式，对比输出差异。

---

## 遇到的问题

### ⭐ LLM 跳步编数据（03 最有价值的发现）

**现象**：LLM 在 Thought 里写"接下来查月影王国面积"，
然后**没有执行工具就直接给出 Final Answer**，月影王国面积 = 6200（实际 5200），
这个数字是凭空编出来的。

推理链看起来是这样的：
```
Thought: 已知星辰王国面积 8500。接下来需要查月影王国的面积。
Final Answer: 星辰王国面积是月影王国的 1.37 倍（8500 / 6200）
```
Step 3 的 Observation 里从来没有出现过 6200 这个数字，LLM 自己编的。

---

**第一次修法（纯 prompt）**：

在 system prompt 里加约束：
```
绝对禁止在没有调用工具的情况下给出涉及虚构世界数据的答案。
```
**结果**：无效。模型忽视约束，照样跳步。
这印证了 02 笔记的教训：prompt 约束是概率性的，不是确定性的。

---

**第二次修法（代码护栏）**：

检测 Thought 中的计划性语言（"接下来"、"还需要"、"然后"、"先查"等关键词），
如果发现 Final Answer 前 Thought 里存在这类语言，就拒绝该 Final Answer，
在对话里追加一条消息：
```
你在最后的 Thought 中提到还需要查询更多信息（检测到计划性语言），
但直接给出了 Final Answer。请继续调用工具完成剩余步骤，
已收集的数据：{已观察到的数据摘要}
```
然后让 LLM 继续推理。

**结果**：部分有效。能拦截"Thought 说要查，Action 没执行就直接 Final Answer"这类
结构性矛盾，但无法处理 Thought 内部的幻觉。

---

**仍存在的问题（Thought 内幻觉）**：

LLM 在 Thought 里对已收集数据产生混淆——把查到的 `星辰王国面积=8500`，
在下一步 Thought 里说成"月影王国=8500"（张冠李戴）。
这不是跳步，而是 **Thought 内部的实体混淆**，代码护栏无法检测到：
```
Step 2 Observation: 星辰王国 → 面积: 8500 平方千米
Step 3 Thought: 已知月影王国面积 8500...  ← 数字对，但主语换人了
```

**根本原因**：使用的模型推理能力有限，在多步骤多实体问题上容易混淆实体。
换用更强的模型（GPT-4o、Claude Sonnet）可大幅改善。

---

**核心学习点：ReAct 让幻觉可审计**

- **Direct 模式**：只看到一个错误答案"1.37 倍"，完全不知道哪步出了问题，
  也不知道是调工具前就错了还是计算错了。
- **ReAct 模式**：能精确定位到"Step 3 的 Thought 里月影王国=8500 是幻觉，
  因为从未有 Observation 返回过这个数据给月影王国"。
  只需对照推理链和 Observation 记录，bug 一目了然。

**这是 ReAct 相比黑盒工具调用的最大价值：推理过程可追溯，错误有迹可查。**
就算 LLM 出错，我们也知道错在哪一步，能针对性地修复（换模型/改 prompt/加护栏）。

---

### LLM 输出格式不一致

**现象**：LLM 有时输出 markdown 加粗格式：

```
**Thought:** 我需要先搜索...
**Action:** lookup("星辰王国", "面积")
```

而不是预期的纯文本：

```
Thought: 我需要先搜索...
Action: lookup("星辰王国", "面积")
```

导致正则 `^Thought:` 无法匹配，解析失败，触发容错重试。

**修法**：正则兼容 `\*{0,2}` 前缀，同时识别两种格式：
```python
THOUGHT_RE = re.compile(r"^\*{0,2}Thought:\*{0,2}\s*(.+)", re.MULTILINE)
ACTION_RE  = re.compile(r"^\*{0,2}Action:\*{0,2}\s*(.+)",  re.MULTILINE)
```
这样两种格式都能正确解析，避免不必要的重试消耗。

---

### search 工具返回重复结果

**现象**：`search('星辰王国')` 的返回列表里同一个实体（如"霜雪部落"）出现了两次。

**原因**：knowledge_base.py 里 search 逻辑的双重循环，内层 `break` 只跳出字段循环，
不跳出实体循环，导致同一个实体因匹配了两个字段而被加入两次：

```python
for entity in KB:
    for field in entity.values():
        if query in str(field):
            results.append(entity["name"])
            break  # 只跳出字段循环，实体循环继续！
```

**修法**：加 `matched` 标记，确保每个实体最多被添加一次：

```python
for entity in KB:
    matched = False
    for field in entity.values():
        if not matched and query in str(field):
            results.append(entity["name"])
            matched = True
```

---

## 学到的内容

### 1. ReAct 的核心价值不是"让 LLM 推理更好"

ReAct 的本质贡献是：**让推理过程对我们可见、可审计、可追溯**。

显式的 Thought 链不会神奇地让 LLM 不犯错——弱模型依然会跳步、幻觉。
但它把错误从"黑盒里不知道的错"变成了"推理链里能定位的错"，
这对调试、优化、信任建立都有巨大价值。

### 2. prompt 约束是概率性的，代码护栏才是确定性的

加了"禁止编造"的 prompt，模型还是会跳步编数据。
从 02 到 03，这个教训被一再验证：

| 层次 | 机制 | 可靠性 |
|------|------|--------|
| prompt 约束 | 文字规则 | 概率性（模型可能忽略） |
| 代码护栏 | 结构检测 + 拒绝 | 确定性（但只能检测可观测的结构矛盾） |
| 模型能力 | 更强的基座 | 提高上限，但不消除问题 |

三层结合使用，才能把错误概率压到可接受范围。

### 3. 虚构数据是验证工具依赖性的关键设计

用真实数据（真实国家、真实历史）时，LLM 会凭记忆直接给出答案，
跳过工具调用——这让测试失去意义，无法区分"LLM 调工具推理出来的"和"LLM 背出来的"。

虚构的"星云大陆"彻底消除这种干扰：月影王国的面积是 5200 还是 6200，
LLM 的训练数据里根本没有，它**必须**调工具。
这是 ReAct 学习项目的标准设计模式。

### 4. 模型能力是 ReAct 效果的天花板

同样的 ReAct 框架：
- 强模型（GPT-4o、Claude Sonnet）：老实执行每一步，Thought 准确反映已知信息
- 弱模型（推理能力不足）：跳步、实体混淆、Thought 内幻觉

ReAct 是放大镜——会把模型的能力上限放大，也会把局限暴露得更清楚。
选对模型，是 ReAct 稳定工作的前提条件。

### 5. Function Calling 是工程化的 ReAct

OpenAI 的 `tool_calls` 帮你做了格式解析（省去写正则）、保证了工具调用的原子性，
但代价是推理过程不可见——Thought 被封装在了模型内部，我们只看到 Action 和结果。

手动实现 ReAct 文本解析，保留了完整的可观测性，代价是要处理格式不一致、解析失败等问题。
两者各有取舍，工程项目用 Function Calling，学习/可解释性场景用 ReAct 文本格式。

### 6. 容错设计是 ReAct 循环的必要组成

格式解析失败不能让程序崩溃，要给 LLM 一次重试机会：

```
[解析失败] 请严格按照以下格式输出（注意不要使用 markdown 加粗）：
Thought: 你的推理过程
Action: tool_name("arg1", "arg2")
```

实践中设置"最多 2 次重试"：第一次失败给提示，第二次失败放弃该步骤，记录错误后终止。
这个策略平衡了"给 LLM 改正机会"和"避免无限重试消耗 token"。
