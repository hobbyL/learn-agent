# ReAct 模式详解

ReAct（Reasoning and Acting）是 Agent 领域最重要的设计模式之一。

---

## 核心思想

**交替进行推理（Reasoning）和行动（Acting）**，而非分离思考和执行。

---

## 为什么需要 ReAct？

### 传统方法的问题

**方法1：只有行动（Action-only）**
```
用户：帮我查一下北京的天气
Agent：[直接调用天气API]
问题：没有推理过程，缺乏可解释性
```

**方法2：只有推理（Reason-only）**
```
用户：帮我查一下北京的天气
Agent：我需要调用天气API，然后返回结果
问题：只说不做，没有实际行动
```

### ReAct 的优势

```
用户：帮我查一下北京的天气
Agent：
  Thought: 用户想知道北京的天气，我需要调用天气API
  Action: call_weather_api(city="北京")
  Observation: {"city": "北京", "weather": "晴", "temp": 25}
  Thought: 已获取天气信息，现在返回给用户
  Action: return_to_user("北京今天晴天，气温25°C")
```

**优势**：
- 推理过程可见
- 行动有依据
- 错误易追踪
- 可中途调整

---

## ReAct 循环

```
┌──────────────────────────────────┐
│   用户输入（Task）                  │
└──────────┬───────────────────────┘
           │
           ▼
    ┌──────────────┐
    │  Thought     │  ← 推理：分析当前状态
    │  (推理)      │    决定下一步做什么
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │  Action      │  ← 行动：调用工具
    │  (行动)      │    或生成内容
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ Observation  │  ← 观察：获取行动结果
    │  (观察)      │
    └──────┬───────┘
           │
           │  是否完成任务？
           ├─── 否 ───▶ 回到 Thought
           │
           └─── 是 ───▶ 返回最终答案
```

---

## 实际案例

### 案例 1：信息查询

**任务**：查找"OpenAI 成立于哪一年"

```
Thought 1: 我需要搜索 OpenAI 的成立时间
Action 1: search("OpenAI 成立时间")
Observation 1: OpenAI 是一家人工智能研究公司，成立于2015年12月...

Thought 2: 找到了答案，OpenAI 成立于 2015 年
Action 2: finish("2015年")
```

### 案例 2：复杂任务

**任务**：找出"北京和上海哪个城市今天更温暖"

```
Thought 1: 需要分别查询北京和上海的天气
Action 1: call_weather_api(city="北京")
Observation 1: {"city": "北京", "temp": 25}

Thought 2: 北京是25°C，现在查上海
Action 2: call_weather_api(city="上海")
Observation 2: {"city": "上海", "temp": 28}

Thought 3: 上海28°C，比北京25°C更温暖
Action 3: finish("上海今天更温暖，28°C（北京25°C）")
```

---

## Prompt 模板

```
你是一个能使用工具的 AI Agent。

你有以下工具可用：
- search(query): 搜索信息
- calculate(expression): 计算数学表达式
- get_weather(city): 获取天气信息

请使用以下格式回答：

Thought: [你的推理过程]
Action: [工具名称(参数)]
Observation: [工具返回的结果]
... (重复 Thought/Action/Observation 直到任务完成)
Thought: 我现在知道最终答案了
Final Answer: [最终答案]

开始！

Question: {user_question}
Thought:
```

---

## 实现要点

### 1. 解析 LLM 输出
需要从 LLM 的输出中提取：
- Thought（推理）
- Action（行动）
- Final Answer（最终答案）

### 2. 工具调用
- 解析 Action 中的工具名称和参数
- 执行工具
- 将结果作为 Observation 反馈给 LLM

### 3. 循环控制
- 设置最大步数（防止无限循环）
- 检测是否出现 "Final Answer"
- 处理工具调用失败

---

## 常见问题

### 1. Agent 陷入循环
**原因**：重复相同的 Thought/Action
**解决**：
- 在 prompt 中添加"不要重复之前的行动"
- 检测循环并强制终止

### 2. 工具调用错误
**原因**：LLM 生成的参数格式不对
**解决**：
- 在 prompt 中给出工具使用示例
- 添加参数验证和错误提示

### 3. 推理不充分
**原因**：Thought 太简短，缺乏逻辑
**解决**：
- 在 prompt 中要求"详细说明推理过程"
- 使用 Chain-of-Thought 技巧

---

## 进阶话题

### 1. Self-Consistency
多次运行 ReAct，选择最一致的答案

### 2. ReAct + Reflection
在每个 Action 后增加反思步骤，检查行动是否合理

### 3. Multi-Agent ReAct
多个 Agent 各自执行 ReAct，然后协作

---

## 经典论文

**ReAct: Synergizing Reasoning and Acting in Language Models**
- 作者：Shunyu Yao et al.
- 发表：2022
- 链接：https://arxiv.org/abs/2210.03629

---

**最后更新**：2026-06-25  
**来源项目**：无（初始笔记）
