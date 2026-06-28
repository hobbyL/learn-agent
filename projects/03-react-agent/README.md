# 项目 03：ReAct 推理模式（Reasoning + Acting）

手写实现显式推理链 Agent，体验"先想再做"相比"直接调工具"在复杂多步任务上的差异。
通过虚构小世界知识库消除 LLM 先验知识干扰，强迫 Agent 老实走 Thought → Action → Observation 循环。

---

## 📋 项目信息

**难度**：⭐⭐⭐⭐☆
**预计时间**：3-4 天
**前置项目**：[02-tool-calling](../02-tool-calling/)（已完成）

**学习目标**：
- 理解 ReAct 论文的核心思想：把"推理"和"行动"交织在一起、让推理过程可审计
- 掌握纯文本 ReAct 格式：正则解析 LLM 输出、手动注入 Observation
- 对比 ReAct（显式推理）vs Function Calling（隐式推理）的结构差异与适用场景
- 体会"代码护栏比 prompt 约束更可靠"——跳步检测是本项目最有价值的工程实践

---

## 🤔 为什么需要 03？（02 暴露的痛点）

02 使用 OpenAI Function Calling，推理是**黑盒的**：

```
用户：星辰王国面积是月影王国的多少倍？

[内部发生了什么我们看不到]

Agent：答案是 1.63 倍。（对了吗？为什么？哪步算错了？不知道。）
```

当 Agent 给出错误答案时，我们完全无从定位原因——
是工具没调到？数据理解错了？还是计算出错？

03 要解决这个"黑盒调试"问题：**让推理链显式输出，错误有迹可查。**

---

## 🧠 核心概念：ReAct 是什么

### Thought → Action → Observation 循环

ReAct（Reasoning + Acting）的核心思想是：
**强迫 LLM 在每次"行动"前先写出思考过程**，把推理和工具调用交织在一起。

```
用户：星辰王国面积是月影王国的多少倍？

[Step 1]
Thought: 我需要分别查询两个王国的面积，然后计算比值。先查星辰王国。
Action: lookup
Action Input: {"entity": "星辰王国", "field": "面积"}
Observation: 星辰王国 → 面积: 8500 平方千米

[Step 2]
Thought: 得到星辰王国面积 8500。现在查月影王国的面积。
Action: lookup
Action Input: {"entity": "月影王国", "field": "面积"}
Observation: 月影王国 → 面积: 5200 平方千米

[Step 3]
Thought: 两个面积都已获得。计算比值：8500 / 5200。
Action: calculate
Action Input: {"expression": "8500 / 5200"}
Observation: 计算结果: 1.634615384615385

[Step 4]
Thought: 比值约为 1.63，数据完整，可以回答了。
Final Answer: 星辰王国面积（8500 平方千米）是月影王国（5200 平方千米）的约 1.63 倍。
```

### 和 01/02 的根本区别

| 维度 | 01/02（Function Calling） | 03（ReAct 文本格式）|
|------|--------------------------|---------------------|
| 推理过程 | 黑盒，LLM 内部决策 | 显式输出 Thought，可读可审 |
| 工具调用方式 | 结构化 JSON（`tool_calls`） | 纯文本，我们自己正则解析 |
| 格式保证 | OpenAI 强制（不会格式错误） | 需要容错处理（LLM 可能格式不规范） |
| 可调试性 | 看不到中间推理 | 每步 Thought 都记录了"为什么" |
| 并行调用 | 支持同轮多个 `tool_calls` | 串行，每步一个 Action |

---

## 🏗️ 系统架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                       main.py（双模式入口）                            │
│  AGENT_MODE=react → ReactAgent                                      │
│  AGENT_MODE=direct → DirectAgent                                    │
│  --demo / --compare / 交互式命令                                     │
└──────────────┬────────────────────────────┬────────────────────────┘
               │                            │
               ▼                            ▼
┌──────────────────────────┐   ┌──────────────────────────────────┐
│   react_agent.py         │   │   direct_agent.py                │
│                          │   │                                  │
│  纯文本 ReAct 循环：      │   │  OpenAI Function Calling：       │
│  LLM 输出文本             │   │  LLM 返回 tool_calls JSON        │
│  → 正则解析 Thought/      │   │  → 直接 dispatch                 │
│    Action/Final Answer   │   │  → 收工，无显式推理               │
│  → execute_tool()        │   │  → execute_tool()                │
│  → Observation 注入消息   │   │                                  │
│  → 循环                  │   │                                  │
└──────────────┬───────────┘   └──────────────┬───────────────────┘
               │                              │
               └──────────────┬───────────────┘
                              │（共享工具层）
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          tools.py（4 个工具）                          │
│                                                                     │
│  search(query)          — 模糊搜索，返回匹配实体摘要列表               │
│  lookup(entity, field)  — 精确查询实体的某个属性                       │
│  calculate(expression)  — 安全数学表达式求值                           │
│  compare(a, b, field)   — 比较两个实体的同一属性                       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    knowledge_base.py（星云大陆）                        │
│                                                                     │
│  24 个实体（王国、城市、英雄、道具等），每个实体 4-6 个属性              │
│  数据完全虚构 → LLM 先验知识无效 → 必须调工具才能作答                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 ReAct 调用流程图

```
用户: "星辰王国国王的导师现在住在哪里？"
         │
         ▼
┌─ ReactAgent.run() ──────────────────────────────────────────────────┐
│                                                                     │
│  Step 1：                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ messages = [system, user]                                   │   │
│  │ → LLM 输出文本：                                             │   │
│  │   Thought: 需要先查星辰王国的国王是谁。                         │   │
│  │   Action: lookup                                            │   │
│  │   Action Input: {"entity": "星辰王国", "field": "国王"}       │   │
│  └────────────────────┬────────────────────────────────────────┘   │
│                       │ 正则解析提取 Action + Action Input           │
│                       ▼                                            │
│               execute_tool("lookup", {...})                        │
│               → "星辰王国 → 国王: 艾瑞克三世"                       │
│                       │                                            │
│                       ▼                                            │
│  messages.append("Observation: 星辰王国 → 国王: 艾瑞克三世")         │
│                                                                     │
│  Step 2：                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ messages = [system, user, assistant(step1), obs1]           │   │
│  │ → LLM 输出文本：                                             │   │
│  │   Thought: 国王是艾瑞克三世。现在查他的导师。                  │   │
│  │   Action: lookup                                            │   │
│  │   Action Input: {"entity": "艾瑞克三世", "field": "导师"}    │   │
│  └────────────────────┬────────────────────────────────────────┘   │
│                       │                                            │
│               execute_tool("lookup", {...})                        │
│               → "艾瑞克三世 → 导师: 莫里安法师"                     │
│                       │                                            │
│  messages.append("Observation: 艾瑞克三世 → 导师: 莫里安法师")       │
│                                                                     │
│  Step 3：                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ → LLM 输出文本：                                             │   │
│  │   Thought: 导师是莫里安法师。查他的居住地。                    │   │
│  │   Action: lookup                                            │   │
│  │   Action Input: {"entity": "莫里安法师", "field": "居住地"}   │   │
│  └────────────────────┬────────────────────────────────────────┘   │
│                       │                                            │
│               execute_tool("lookup", {...})                        │
│               → "莫里安法师 → 居住地: 翡翠联邦绿冠城"               │
│                                                                     │
│  Step 4：                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ → LLM 输出文本：                                             │   │
│  │   Thought: 三步链式查询完成，信息充足，可以回答。               │   │
│  │   Final Answer: 星辰王国国王艾瑞克三世的导师莫里安法师，       │   │
│  │                 现在住在翡翠联邦的绿冠城。                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
返回 {"answer": "...", "steps": [...], "total_steps": 4, "terminated_by": "final_answer"}
```

---

## 📦 项目结构

```
03-react-agent/
├── README.md              # 本文件
├── main.py                # 入口，AGENT_MODE 切换 + 交互循环 + compare 对比
├── react_agent.py         # ReAct 循环（纯文本 Thought/Action/Observation）
├── direct_agent.py        # Function Calling 对照组（推理黑盒）
├── tools.py               # 4 个工具 + execute_tool 分发 + get_tool_descriptions
├── knowledge_base.py      # 虚构"星云大陆"（24 个实体，数据完全虚构）
├── notes.md               # 学习笔记（含踩坑记录、关键发现）
├── requirements.txt       # 依赖（openai, python-dotenv）
├── .env.example           # 环境变量说明
└── .env                   # 真实配置（不提交）
```

> 说明：parser.py 和 prompts.py 合并进了各自的 agent 文件，
> 保持目录干净，避免文件碎片化。

---

## 🚀 快速开始

```bash
# 1. 进入项目目录
cd projects/03-react-agent

# 2. 激活虚拟环境（复用 01 已建好的环境）
source ../01-simple-agent/.venv/bin/activate

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入以下内容：
# OPENAI_API_KEY=sk-xxxxxxxx
# OPENAI_BASE_URL=https://...   （如使用代理，否则保留默认）
# OPENAI_MODEL=gpt-4o-mini      （建议使用 gpt-4o 以获得更稳定的推理效果）
# AGENT_MODE=react              （react / direct，默认 react）
# LOG_LEVEL=INFO                （DEBUG 显示完整 API 交互）
# MAX_STEPS=10                  （最大推理步数）

# 4. 启动交互模式（默认 react 模式）
python main.py

# 5. 运行预设演示题（5个不同难度的问题）
python main.py --demo

# 6. 直接运行双模式对比
python main.py --compare "星辰王国面积是月影王国的多少倍？"
```

### 交互命令

启动后，在提示符处可以输入：

| 命令 | 说明 |
|------|------|
| 直接输入问题 | 按当前模式运行 |
| `switch` | 在 react / direct 模式之间切换 |
| `compare 问题` | 同一问题跑双模式，并排对比输出 |
| `compare` | 用默认问题（星辰王国面积对比）跑双模式 |
| `exit` | 退出程序 |

---

## ⚙️ AGENT_MODE 配置

通过环境变量（`.env` 或命令行前缀）切换两种模式：

| 值 | 说明 | 推理可见 | 工具调用 |
|----|------|---------|---------|
| `react`（默认） | 显式 Thought → Action → Observation 循环，每步推理可读 | ✅ | 文本格式，自行解析 |
| `direct` | OpenAI Function Calling，LLM 内部决策，只看到最终答案 | ❌ | 结构化 JSON |

```bash
# 临时切换（不修改 .env）
AGENT_MODE=direct python main.py
AGENT_MODE=react python main.py
```

---

## 🔬 ReAct vs Direct 对比

| 维度 | ReAct | Direct |
|------|-------|--------|
| 推理过程可见 | ✅ 每步 Thought 可读、可审 | ❌ 黑盒，只看最终答案 |
| 并行工具调用 | ❌ 串行，每步一个 Action | ✅ 支持同轮多个 `tool_calls` |
| 推理步数 | 较多（每步显式输出） | 较少（并行合并步骤） |
| 格式可靠性 | 依赖 LLM 遵守文本格式，需要容错 | OpenAI 强制 JSON，格式稳定 |
| 调试定位 | 能精确定位错误发生在哪步 Thought | 只能知道最终答案对或错 |
| 适用场景 | 复杂多步推理、需要可解释性 | 简单并行查询、效率优先 |

---

## 🌍 虚构知识库：星云大陆

知识库包含 24 个实体，分为四类：

| 类别 | 示例实体 | 典型字段 |
|------|---------|---------|
| 王国 | 星辰王国、月影王国、翡翠联邦、烈焰帝国 | 面积、人口、首都、国王、建国年份 |
| 城市 | 银光城、幽蓝港、绿冠城 | 人口、所属王国、特色 |
| 英雄 / 人物 | 艾瑞克三世、塞琳娜女王、莫里安法师 | 年龄、职业、师承、居住地 |
| 道具 / 物品 | 星铁之剑、月光法杖 | 属性、持有者、产地 |

**为什么用虚构数据？**

LLM 训练时见过大量真实世界事实。如果用"中国面积是法国的多少倍"，
LLM 可能凭训练记忆直接作答，跳过工具调用——这让测试失去意义。

虚构的"星云大陆"彻底消除这种干扰：
月影王国的面积是 5200 还是 6200，LLM 的训练数据里根本没有，
它**必须**调工具，推理链才有意义。

---

## 🛠️ 4 个工具

| 工具 | 功能 | 参数 | 典型用途 |
|------|------|------|---------|
| `search(query)` | 模糊搜索，返回匹配实体摘要列表 | `query: str` | 不知道完整名字时先搜索 |
| `lookup(entity, field)` | 精确查询某实体的某个属性 | `entity: str, field: str` | 知道名字、想查具体字段 |
| `calculate(expression)` | 安全数学表达式求值（eval 沙箱） | `expression: str` | 比值/差值/人口密度等计算 |
| `compare(entity_a, entity_b, field)` | 比较两个实体的同一属性 | `entity_a, entity_b, field: str` | 谁更大/更多/更老 |

---

## 🛡️ 关键设计决策

### 1. 为什么用纯文本格式而不是 Function Calling

Function Calling 是工程化的 ReAct——OpenAI 帮你做了格式解析，
但代价是推理过程被封装在模型内部，我们只看到 Action 和结果。

03 的学习目标正是体验"显式推理"的价值：
- 手动实现文本解析，才能体会 Thought 的设计意图
- 格式不一致时自己处理容错，才能理解 ReAct 的工程难点
- 推理链完整可见，错误有迹可查——这是本项目最核心的体验

### 2. 跳步检测（_UNFINISHED_PLAN_PATTERNS）

ReAct 的经典 bug：LLM 在 Thought 里写"接下来要查 X"，
然后**没有执行工具就直接给出 Final Answer**（编造假数字）。

代码护栏：检测 Thought 中的计划性关键词（"接下来"、"还需要"、"然后查"等），
如果 Final Answer 出现时检测到这类语言，说明 LLM "计划"了但没"执行"，
直接拒绝该 Final Answer，强制它先走工具。

```python
_UNFINISHED_PLAN_PATTERNS = [
    "接下来", "还需要", "再查", "再查询", "需要再", "然后查", "然后再",
    "继续查", "分别查询", "查询每个", "查完", "再计算", "然后计算",
]
```

这是 03 最有价值的工程实践：**prompt 约束是概率性的，代码护栏才是确定性的**。

### 3. 格式容错

LLM 有时会输出 markdown 加粗格式（`**Thought:**`）而非纯文本（`Thought:`），
导致正则解析失败。

修法：正则兼容 `\*{0,2}` 前缀：

```python
RE_THOUGHT = re.compile(r"\*{0,2}Thought:?\*{0,2}\s*(.+?)", re.DOTALL)
```

解析失败时给 LLM 一次重试机会（附带格式提示），最多重试 2 次后终止。
这平衡了"给 LLM 改正机会"和"避免无限重试消耗 token"。

---

## 🎯 5 个预设测试问题（不同难度）

```python
# 单步：直接查一个字段（验证基础能力）
"星辰王国的国王是谁？"

# 两步：查面积 + 算比值（验证链式工具调用）
"星辰王国的面积是月影王国的多少倍？"

# 三步：链式推理（查国王 → 查导师 → 查居住地）
"星辰王国国王的导师现在住在哪里？"

# 比较 + 计算：两个实体同一字段（验证 compare 工具）
"艾瑞克三世和塞琳娜女王谁年龄更大？大多少岁？"

# 多步混合：查 + 算 + 推理（最复杂）
"翡翠联邦的人口密度（人口/面积）是多少？和星辰王国比谁更密集？"
```

---

## ✅ 完成标准

| 标准 | 状态 |
|------|------|
| ReAct 模式能完成 3 步以上的链式推理任务 | ✅ |
| Direct 模式完成同样任务，但无可见推理过程 | ✅ |
| 双模式输出有明显结构差异（一个有 Thought 链，一个没有） | ✅ |
| 格式错误时 Agent 不崩溃，能提示 LLM 重试（最多 2 次） | ✅ |
| max_steps 到达时优雅终止并告知用户 | ✅ |
| 虚构数据问题 LLM 不调工具则无法正确回答（验证工具依赖性） | ✅ |
| 推理链可视化彩色输出（Thought 青色 / Action 黄色 / Observation 绿色） | ✅ |
| 跳步检测护栏（_UNFINISHED_PLAN_PATTERNS）防止 LLM 编造数据 | ✅ |
| compare 模式双模式并排对比输出 | ✅ |
| 5 个不同难度的预设测试问题全部跑通 | ✅ |

---

## 🔗 相关

- 上一项目：[02-tool-calling](../02-tool-calling/)
- 下一项目：[04-reflection（计划中）](../04-reflection/)
- 学习笔记：[notes.md](./notes.md)
- 主学习笔记：[../../notes/](../../notes/)
- ReAct 原论文：[ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)

---

**创建时间**：2026-06-27
**完成时间**：2026-06-27
**状态**：✅ 完成
