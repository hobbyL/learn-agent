# Agent 基础概念

本笔记整理 Agent 的核心概念和基础知识。

---

## 什么是 Agent？

**Agent（智能体）** 是一个能够感知环境、自主决策并采取行动以实现目标的系统。

### 与传统程序的区别

| 特性 | 传统程序 | Agent |
|------|---------|-------|
| 执行方式 | 指令驱动 | 目标驱动 |
| 决策 | 固定逻辑 | 动态推理 |
| 适应性 | 静态 | 自适应 |
| 用户交互 | 精确指令 | 自然语言 |

---

## Agent 的核心架构

```
┌─────────────────────────────────────┐
│           Agent 系统                 │
│                                     │
│  ┌──────────┐    ┌──────────┐     │
│  │ 感知层    │───▶│ 决策层    │     │
│  │Perception│    │Decision   │     │
│  └──────────┘    └──────────┘     │
│       ▲               │            │
│       │               ▼            │
│  ┌──────────┐    ┌──────────┐     │
│  │ 环境     │◀───│ 执行层    │     │
│  │Environment│    │Action     │     │
│  └──────────┘    └──────────┘     │
└─────────────────────────────────────┘
```

### 1. 感知层（Perception）
- 接收用户输入
- 观察环境状态
- 获取工具执行反馈

### 2. 决策层（Decision）
- **推理（Reasoning）**：分析当前状态，思考下一步
- **规划（Planning）**：分解任务，制定行动计划
- **记忆（Memory）**：存储和检索历史信息

### 3. 执行层（Action）
- 调用工具（Tool Calling）
- 生成代码或内容
- 与外部系统交互

---

## Agent 的关键能力

### 1. 自主性（Autonomy）
- 无需人类每一步指导
- 能自主选择行动路径

### 2. 反应性（Reactivity）
- 感知环境变化
- 及时调整策略

### 3. 主动性（Proactivity）
- 不仅被动响应，还主动采取行动
- 朝着目标前进

### 4. 社交能力（Social Ability）
- 与其他 Agent 或人类协作
- 理解和生成自然语言

---

## Agent 的工作循环

```python
# 伪代码
context = initial_state()

while not goal_achieved():
    # 1. 感知
    observation = perceive(environment)
    
    # 2. 推理
    thought = reason(observation, context)
    
    # 3. 决策
    action = decide(thought, available_actions)
    
    # 4. 执行
    result = execute(action)
    
    # 5. 更新上下文
    context.update(observation, thought, action, result)
    
    # 6. 检查是否达成目标
    if is_goal_met(result):
        break
```

---

## 核心组件

### 1. LLM（大语言模型）
- Agent 的"大脑"
- 负责理解、推理、生成

### 2. Tools（工具）
- Agent 能调用的外部功能
- 例如：搜索、计算、文件操作、API 调用

### 3. Memory（记忆）
- **短期记忆**：对话历史
- **长期记忆**：持久化的知识库

### 4. Prompt（提示词）
- 指导 Agent 的行为规范
- 定义 Agent 的角色和能力

---

## 常见 Agent 模式

### 1. ReAct（Reasoning + Acting）
交替进行推理和行动

```
Thought: 我需要知道今天的天气
Action: 调用天气 API
Observation: 北京，晴，25°C
Thought: 天气不错，适合户外活动
Action: 返回建议给用户
```

### 2. Chain-of-Thought（思维链）
逐步推理，拆解复杂问题

```
问题：23 * 47 = ?
Step 1: 23 * 40 = 920
Step 2: 23 * 7 = 161
Step 3: 920 + 161 = 1081
答案：1081
```

### 3. Self-Reflection（自我反思）
Agent 检查自己的输出是否正确

```
Action: 计算结果
Output: 1081
Reflection: 让我验证一下... 是的，正确
```

---

## 学习资源

- 待从 `resources/` 中补充

---

**最后更新**：2026-06-25  
**来源项目**：无（初始笔记）
