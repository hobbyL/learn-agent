# HITL Agent（Human-in-the-Loop）

## 核心思想

AI 不完全自主——在**高风险决策点**主动暂停，把控制权交还给人类。

```
[Agent 自主推理] → [高风险 Action] → ⏸ HITL 检查点
                                         │
                              人类审批（approve / reject / provide_info）
                                         │
                              [approve] → 执行，继续
                              [reject ] → 注入替代指令，LM 重新推理
                              [info   ] → 注入补充信息，LM 重新推理
```

## 触发方式

### 1. Rule-based（本项目采用）

在工具 schema 里打标记：
```python
{"name": "dispatch_team", "requires_approval": True, "approval_type": "life_risk"}
```

优点：确定性强，可测试，适合安全敏感场景
缺点：需手动枚举高风险工具，不够灵活

### 2. LM 自判断

让 LM 在 Thought 里决定"我需要人类确认"，再调用专用 `request_approval` 工具

优点：灵活，可捕捉 rule 未覆盖的场景
缺点：不稳定，LM 可能跳过确认

### 3. 置信度阈值 + rule 组合

rule 兜底 + LM 对不确定操作主动请求确认（两层防护）

## 人类反馈处理

### approve
直接执行原工具调用，继续 ReAct 循环

### reject + 替代指令
**不执行工具，把否决信息注入 messages：**
```
role: tool
content: "⚠️ 操作被否决。指挥官指令：先撤离再搜救。请重新规划。"
```
LM 看到这条消息后，在下一步 Thought 中重新推理

### provide_info
**不执行工具，把补充信息注入 messages：**
```
role: tool
content: "📋 补充信息：东侧通道已开通，可从那里进入。"
```
LM 可以利用新信息决定继续/修改原计划

## 容错设计

- **连续 reject 上限**：3 次连续被否决 → 优雅终止（不是无限循环）
- **ScriptedHandler 耗尽 fallback**：剧本消费完后默认 approve，不报错
- **approve_type 可扩展**：`life_risk / irreversible / resource_conflict / high_risk`

## 与其他 Agent 模式的关系

| 模式 | 人类参与程度 | 适用场景 |
|------|------------|---------|
| 全自主 Agent | 无 | 低风险、可逆操作 |
| HITL Agent | 关键节点确认 | 高风险、部分不可逆 |
| 全监督 Agent | 每步确认 | 超高风险、全程追责 |

## 实现要点

1. **ReAct 循环结构不变**，HITL 是在 Action 执行前插入的**拦截层**
2. **消息注入** 是处理 reject/info 的关键——让 LM 感知到人类的介入
3. **tick() 在 continue 之前调用**——每个步骤（无论 approve/reject）都要推进时间
4. **工具层 → Agent 层** 的结果格式需明确约定（dict 的 `message` 字段 → str）

## 参考项目

- `projects/11-hitl-agent/` — 明川市灾害应急指挥 Demo
- ReAct 基础：`projects/03-react-agent/`
