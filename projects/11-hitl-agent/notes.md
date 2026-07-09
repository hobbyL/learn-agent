# 11-hitl-agent 实现笔记

## 遇到的坑

### 1. 状态 dict vs list 迭代陷阱

knowledge_base 的世界状态全部用 **dict（以名称为 key）**，但 tools.py 初稿把所有集合当 list 迭代：

```python
# ❌ 错误：state["zones"] 是 dict，迭代得到的是 key（字符串），不是 zone 对象
for zone in state["disaster_zones"]:
    if zone["name"] == target:   # TypeError：str 无法用 ["name"] 取值
```

正确做法——直接用 key 查找：

```python
# ✅ 正确
if target in state["zones"]:
    zone = state["zones"][target]
```

或遍历：

```python
for name, zone in state["zones"].items():
    ...
```

**教训**：设计世界状态时，尽早决定"list of objects"还是"dict keyed by name"，并在实体定义文件里写清楚——两种格式的迭代、查找、修改接口完全不同。

---

### 2. 字段名不一致（数据结构定义 vs 业务逻辑）

knowledge_base 的字段名：
- `trapped_people`（不是 `trapped`）
- `severity`（不是 `risk_level`）
- `water_level_m`（不是 `water_level`，单位是米，不是百分比）
- `current_occupants`（不是 `current_occupancy`）
- `damage_level`（不是 `damage`）

tools.py 初稿全部用了错误名称，运行时 KeyError 才暴露。

**教训**：在 knowledge_base 定义完成后，立即写一份字段速查表或 TypedDict，让所有使用方强制对齐，而不是靠记忆。

---

### 3. execute_tool 返回 dict，但 agent.py 把它当 string 传给 OpenAI

```python
# ❌ 初稿
observation = execute_tool(tool_name, tool_args)
# observation 是 dict，OpenAI messages "content" 只接受 str
messages.append({"role": "tool", "content": observation})   # 运行时 TypeError
```

修复：

```python
tool_result = execute_tool(tool_name, tool_args)
observation = tool_result["message"]
if tool_result.get("alerts"):
    observation += "\n" + "\n".join(tool_result["alerts"])
```

**教训**：工具层 → Agent 层的"结果"格式要提前约定（dict 还是 str），并写接口注释。本项目工具层返回 `{success, message, alerts}`，Agent 层负责把 `message` 和 `alerts` 拼接成 LM 可用的字符串。

---

### 4. HITLRequest（Pydantic）vs HITLCheckpoint（dataclass）

schemas.py 定义的 `HITLRequest` 是计划外的遗留物（原设计想用它做 LM 结构化输出，后来改为直接用 `HITLCheckpoint` dataclass 传递检查点数据）。

display.py 初稿把参数类型写成 `HITLRequest`，但实际传入的是 `HITLCheckpoint`，字段名不匹配（`description`、`risk_level`、`context` 都不存在）。

修复：把 `print_hitl_request` 的参数改为接受 `HITLCheckpoint`（duck typing，不再标注类型），对齐字段访问。

---

### 5. 构造函数参数名拼写错误

```python
# ❌ 初稿
HITLAgent(hitl_handler=handler, ...)   # 参数名不存在

# ✅ 修复
HITLAgent(handler=handler, ...)
```

这类错误只有运行时才报 `TypeError: __init__() got an unexpected keyword argument`，写代码时容易忽略。

---

### 6. ReAct 中 tick() 在不同分支的位置

最初只有 normal path 调用 `tick()`，reject 和 provide_info 分支 `continue` 之前忘记调用。

导致：被否决或补充信息时，灾害不恶化，失去"拖延有代价"的设计效果。

修复：在每个 `continue` 之前都调用 `tick()`，确保每个"步骤"（不论 approve/reject/info）都推进时间。

---

## 关键设计决策

### 为什么用 rule-based 触发，而不是 LM 自判断？

LM 可以在 Thought 里说"这个操作有风险，我需要确认"，但实际上：
- LM 的判断不稳定（不同 prompt、不同模型可能跳过）
- 人命/不可逆操作需要**确定性**保证，不能依赖 LM "情绪"
- rule-based 的 `requires_approval` flag 可以做单元测试、可以审计

代价是：需要提前枚举哪些工具高风险，不够灵活。但对安全敏感场景，这是合理取舍。

### 为什么 reject 选择"注入 messages"而不是"修改 tool_args"？

直接修改 `tool_args` 并重跑工具调用是一种做法，但它绕过了 LM 的 Thought 步骤——LM 不知道操作被改了。

注入 messages 的做法让 LM 知道"我的计划被否定了，以及原因是什么"，再生成新的 Thought 和 Action。这样 LM 的推理链更完整，后续步骤的上下文也更准确。

### ScriptedHandler 的 fallback 设计

剧本耗尽后默认 approve，不抛异常。这样 demo 即使超出预设步数也能运行到终止条件（report_result 或 max_steps），而不是中途报错。
