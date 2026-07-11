# 多 Agent 辩论知识笔记

> 基于项目 15 实践整理

---

## 1. 多 Agent 协作核心模式

```
独立推理 → 交叉质疑 → 收敛共识
```

这是结构化辩论的经典三阶段模式，每个阶段的信息可见性递增：

| 阶段 | 可见信息 | 目的 |
|------|---------|------|
| 独立推理 | 只看知识库 + 自己的工具 | 避免锚定效应，获得独立观点 |
| 交叉质疑 | + 其他人第一轮发言 | 发现盲点，质疑薄弱论点 |
| 收敛共识 | + 所有历史发言 | 综合信息，做出最终决策 |

---

## 2. 信息隔离与注入

多 Agent 辩论的关键技术点：**控制每个 Agent 在每个阶段看到什么**。

```python
# 信息隔离（第一轮）
response = run_agent(role, phase="独立立论")  # 无 context

# 信息注入（第二轮）
context = format_others_arguments(role, round1_args)
response = run_agent(role, phase="交叉质疑", context=context)

# 全量注入（第三轮）
context = format_all_arguments(role)  # 所有轮次
response = run_agent(role, phase="总结投票", context=context)
```

信息隔离不需要复杂的权限系统，核心就是**控制 messages 列表里有什么**。

---

## 3. Agent 角色设计

### System Prompt 要素

有效的角色 system prompt 需要：

1. **身份定位**：明确角色名称和职能
2. **关注维度**：列出 3-5 个核心关注点（具体到可操作）
3. **立场声明**：明确价值优先级（让 Agent 有鲜明立场）
4. **工具说明**：告知可用工具（共享 + 专属）

```python
"你是星际殖民委员会的首席科学顾问。\n"
"核心关注点：1. 宜居性 2. 生态系统 3. 科研价值 4. 可持续性\n"
"你的立场：科学价值和宜居性是第一优先级。"
```

### 共享 + 专属工具

```python
ROLE_TOOLS = {
    "科学官": SHARED_TOOLS + [TOOL_ANALYZE_HABITABILITY],
    "军事官": SHARED_TOOLS + [TOOL_ASSESS_DEFENSE],
    "经济官": SHARED_TOOLS + [TOOL_EVALUATE_ECONOMICS],
}
```

- 共享工具 = 基础查询能力（所有人都能查数据）
- 专属工具 = 专业分析能力（只有专家才有的深度分析）

这创造了"共同的事实基础 + 不同的分析视角"。

---

## 4. 辩论编排器

### Orchestrator 模式

编排器负责：
1. **阶段控制**：按顺序执行三个阶段
2. **消息路由**：决定每个 Agent 看到什么
3. **结果收集**：收集每轮发言和最终投票
4. **立场追踪**：对比 round1 vs round3 推荐

```python
class DebateOrchestrator:
    round1_arguments: dict[str, str]     # 第一轮发言
    round2_arguments: dict[str, str]     # 第二轮发言
    round3_arguments: dict[str, str]     # 第三轮发言
    round1_recommendations: dict[str, str]  # 第一轮推荐
    votes: list[dict]                    # 最终投票
```

### 投票解析

结构化投票要求 Agent 在回答末尾输出 JSON：

```json
{"vote": "蓝晶星", "confidence": 85, "reason": "宜居性最高"}
```

解析策略（三级降级）：
1. 正则匹配 ```json 代码块
2. 正则匹配裸 JSON
3. 启发式关键词提取
4. 最后提到的星球名

---

## 5. 共识判断

```python
if len(vote_counts) == 1:
    # 全票通过 → 强共识
elif max_count > total / 2:
    # 多数通过 → 弱共识
else:
    # 票数分散 → 无共识
```

扩展思路：
- 加入信心加权（confidence × vote）
- 多轮投票直到收敛
- 引入仲裁 Agent（参考所有论据做最终裁决）

---

## 6. 多 Agent 模式对比

| 模式 | 特点 | 适用场景 |
|------|------|---------|
| 辩论 + 投票 | 独立推理 → 质疑 → 投票 | 多角度决策 |
| 分工协作 | 拆分任务 → 各自执行 → 合并 | 并行处理 |
| 主从委托 | 主 Agent 分发 → 子 Agent 执行 | 任务编排 |
| 专家咨询 | 主 Agent 按需问专家 | 知识检索 |

本项目实现的是**辩论 + 投票**模式，后续项目将涉及分工协作（16）和工作流编排（17）。

---

## 7. 与单 Agent 多轮对话的区别

| 维度 | 单 Agent 多轮 | 多 Agent 辩论 |
|------|-------------|--------------|
| 视角 | 一个视角自我迭代 | 多个独立视角交叉 |
| 偏见 | 容易自我强化 | 被其他角色质疑纠正 |
| 覆盖面 | 受 system prompt 影响 | 角色分工覆盖更全面 |
| 成本 | 低（单线程） | 高（N 个 Agent × M 轮） |
| 复杂度 | 低 | 高（编排 + 路由 + 解析） |

多 Agent 的核心价值：**用多个有偏见的视角合成一个更全面的决策**。

---

## 8. 实践经验

1. **立场要鲜明**：system prompt 里的立场声明越明确，辩论越有张力
2. **数据要充分**：知识库数据量决定了辩论深度，太少则论点雷同
3. **工具要有分化**：专属工具让每个角色有独特的信息源
4. **投票要容错**：LLM 输出不稳定，投票解析必须有多级降级
5. **立场变化是价值**：Agent 被说服改变立场 = 辩论机制有效的信号
