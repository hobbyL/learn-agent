# 06-streaming-react 学习笔记

## 核心概念：流式 ReAct 的挑战

### 非流式 vs 流式 ReAct

```python
# 非流式（03 的方式）：
response = client.chat.completions.create(stream=False, ...)
text = response.choices[0].message.content
# → 正则一次性解析完整文本
thought = RE_THOUGHT.search(text).group(1)
action = RE_ACTION.search(text).group(1)

# 流式（06 的方式）：
stream = client.chat.completions.create(stream=True, ...)
for chunk in stream:
    text_fragment = chunk.choices[0].delta.content or ""
    events = parser.feed(text_fragment)  # 状态机增量解析
    # 每个 fragment 可能只是 "Tho"，要等下一个 chunk 才能确认是 "Thought:"
```

### 标签跨 Chunk —— 核心挑战

LLM 输出 `\nThought: 我需要查询` 时，可能被切成：

```
chunk 1: "\nTho"       ← 只有 "Thought:" 的一部分
chunk 2: "ught: 我"    ← 剩余标签 + 内容开头
chunk 3: "需要查询"
```

状态机在 chunk 1 到达时不能判断这是 "Thought:" 还是普通文本（如 "There are..."）。

**解决方案：小 buffer 回溯**

维护 ≤20 字符 buffer，新 chunk 到达后：
1. 拼接 buffer + 新文本
2. 扫描是否有完整标签 → 有则切换状态
3. 检查尾部是否是某标签的前缀 → 是则暂缓，等下一 chunk
4. 否则安全刷出 buffer 内容

---

## 状态机设计

```
Section.IDLE → Section.THOUGHT → Section.ACTION → Section.ACTION_INPUT
                    ↓
              Section.FINAL_ANSWER（终止）
```

ParseEvent 类型：
- `SectionStart(section)` — 检测到新 section
- `TextChunk(text, section)` — 文本片段，应实时展示
- `ActionReady(tool_name, tool_input_str)` — 工具调用就绪，可以执行
- `FinalAnswerReady(text)` — 最终答案完整
- `SkipStepDetected(thought_text)` — 检测到跳步

---

## 踩坑记录

### 1. chunk.choices 可能为空列表

streaming 时某些 chunk（如心跳包或流结束信号）的 `choices` 可能是空列表。
直接 `chunk.choices[0].delta.content` 会 `list index out of range`。

**修复**：
```python
for chunk in stream:
    if not chunk.choices:   # 必须先判断！
        continue
    delta_text = chunk.choices[0].delta.content or ""
```

### 2. ActionReady 只在 flush() 时才能确认发出

最初设计：`ActionReady` 在切换到新 section（下一个 Thought 或 Final Answer）时发出。
但 LLM 的 ReAct 输出每步只有一个 `Action + Action Input`，输出完就结束（流结束），
不会跟着新 section——所以 `ActionReady` 必须在 `flush()` 里发出，而不是等切换触发。

**修复**：`flush()` 检查 `_section == ACTION_INPUT` → 发 `ActionReady`

### 3. 属性名大小写/措辞导致查询失败

Agent 在查询"驻扎站"时失败（知识库字段名是"驻站"），自动切换用"驻站"重试成功。
这是 ReAct 的自我纠错能力——工具返回的 `可用属性` 错误提示帮助 Agent 调整。

**启示**：工具错误返回信息要包含"可用属性"列表，让 LLM 能自主纠正参数。

---

## 学习要点

### 1. 流式 ReAct 的核心挑战

非流式（03）可以等完整文本后一次正则解析。
流式（06）必须边流边解析，核心挑战是**标签跨 chunk**：

```
chunk1: "\nTho"        ← 不完整，不能判断是 "Thought:" 还是其他
chunk2: "ught: 我需要"  ← 拼接后才知道是 "Thought:"
```

**解决方案**：小 buffer 回溯（≤20 字符），暂存尾部可能是标签前缀的部分，
等下一 chunk 到达后再判断。

### 2. 状态机驱动 vs 正则驱动

| | 03 非流式（正则） | 06 流式（状态机） |
|--|-----------------|----------------|
| 时机 | 完整文本一次性解析 | 逐字增量解析 |
| 结果 | 结构化字典 | ParseEvent 事件流 |
| 展示 | 解析完才能显示 | 边解析边实时显示 |
| 实现复杂度 | 低（正则直接匹配） | 高（需处理跨 chunk） |

### 3. ActionReady 的触发时机设计

ReAct 每步的输出结构：`Thought + Action + Action Input` → 流结束。
`ActionReady` 不能等"看到下一个 Thought"再发，因为流到 `Action Input` 结束就停了。
必须在 `flush()` 时检查是否停在 `ACTION_INPUT` 状态来确认工具调用就绪。

### 4. 流式 ReAct vs 流式 FC 的本质差异

| | 05 流式 FC | 06 流式 ReAct |
|--|-----------|--------------|
| 工具调用格式 | JSON（Function Calling） | 文本（Action + Action Input） |
| 传 tools= 参数 | ✅ 是 | ❌ 否 |
| 解析方式 | delta.tool_calls 拼接 | 状态机文本解析 |
| 推理可见性 | 黑盒 | Thought 逐字可见 |
| 标签跨 chunk | 不涉及（JSON 拼接） | **核心挑战** |

### 5. 步数一致性验证

`--compare` 模式验证了流式和非流式 ReAct 的逻辑等价性——
同一问题两种模式都是 2 步，答案完全一致。
说明 streaming 只影响"展示方式"，不影响 ReAct 的推理逻辑本身。
