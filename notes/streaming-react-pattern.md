# 流式 ReAct 模式（Streaming ReAct Pattern）

流式 ReAct 是将 streaming API 与 ReAct 推理链结合的 Agent 设计模式，
通过状态机增量解析让推理过程实时可见。

---

## 核心思想

**在 streaming 输出中实时识别 ReAct 格式边界，边流边展示推理链。**

```
传统 ReAct（03）：等完整响应 → 正则解析 → 一次性展示推理链
流式 ReAct（06）：逐 chunk 到达 → 状态机识别边界 → 实时着色展示
```

---

## 为什么难？标签跨 Chunk 问题

非流式 ReAct 用正则一次性解析完整文本，简单直接。
流式 ReAct 必须面对 **标签跨 chunk** 问题：

```
LLM 输出: "\nThought: 我需要查询..."

实际到达:
  chunk 1: "\nTho"          ← 不完整，无法判断
  chunk 2: "ught: 我需"     ← 拼接后才确认是 Thought:
  chunk 3: "要查询..."
```

状态机在 chunk 1 到达时不能误判（可能是普通文本的一部分），
必须等下一 chunk 才能确认。

---

## 解决方案：小 Buffer 回溯

```python
class StreamParser:
    _buf: str = ""         # ≤20 字符 buffer
    _section: Section      # 当前状态

    def feed(self, text: str) -> list[ParseEvent]:
        self._buf += text
        return self._process_buffer()

    def _process_buffer(self):
        # 1. 扫描 buffer，找最早的完整标签
        # 2. 找到 → 切换状态，发出 SectionStart 事件
        # 3. 没找到 → 检查尾部是否是标签前缀
        # 4. 是前缀 → 暂缓，等下一 chunk
        # 5. 否则 → 安全刷出 buffer 内容（发出 TextChunk 事件）
```

**核心权衡**：buffer 越大，延迟越高但越安全；buffer 越小，延迟越低但需更精确的前缀检测。
实践中 ≤20 字符足够（最长标签 `\nAction Input:` 约 14 字符）。

---

## 状态机设计

```
    Section.IDLE
         │ "Thought:"
         ▼
    Section.THOUGHT ──── "Final Answer:" ──▶ Section.FINAL_ANSWER → 结束
         │
         │ "Action:"
         ▼
    Section.ACTION
         │
         │ "Action Input:"
         ▼
    Section.ACTION_INPUT
         │ (flush → ActionReady 事件)
         │
         └──▶ 执行工具 → Observation → 追加 messages → 回到 IDLE
```

### ParseEvent 事件类型

| 事件 | 触发时机 | 用途 |
|------|---------|------|
| `SectionStart(section)` | 检测到新标签 | display 层打印 section 标题 |
| `TextChunk(text, section)` | 安全刷出 buffer | 实时着色打印文本 |
| `ActionReady(tool, args)` | `flush()` 检测到 ACTION_INPUT | 执行工具调用 |
| `FinalAnswerReady(text)` | `flush()` 检测到 FINAL_ANSWER | 返回最终答案 |
| `SkipStepDetected(thought)` | FINAL_ANSWER 时 Thought 含计划词 | 拦截跳步 |

### 关键设计：ActionReady 在 flush() 发出

ReAct 每步输出结构：`Thought + Action + Action Input` → 流结束（不跟新 section）。

❌ 错误设计：等"遇到下一个 Thought:"时才发出 ActionReady
→ ReAct 每步流就停了，根本不会有下一个 Thought 来触发

✅ 正确设计：在 `flush()` 里检查 `_section == ACTION_INPUT` → 发出 ActionReady

```python
def flush(self) -> list[ParseEvent]:
    events = []
    if self._buf:
        events.extend(self._emit_text(self._buf))
    # 流结束时停在 ACTION_INPUT → 工具调用完整
    if self._section == Section.ACTION_INPUT and self._action_input_buf:
        events.append(ActionReady(self._action_name, self._action_input_buf))
    # 流结束时停在 FINAL_ANSWER → 最终答案完整
    elif self._section == Section.FINAL_ANSWER and self._thought_buf:
        events.append(FinalAnswerReady(self._thought_buf))
    return events
```

---

## 流式 ReAct Agent 循环

```python
class StreamingReActAgent:
    def run(self, question: str) -> str:
        self.messages.append({"role": "user", "content": f"问题：{question}"})

        for step in range(max_steps):
            parser = StreamParser()

            # 关键：stream=True，但不传 tools=（不用 Function Calling）
            stream = client.chat.completions.create(
                model=model,
                messages=self.messages,
                stream=True,
                # tools= 不传！ReAct 靠 prompt 约束文本格式
            )

            assistant_parts = []
            for chunk in stream:
                if not chunk.choices:   # 防止空列表 IndexError
                    continue
                text = chunk.choices[0].delta.content or ""
                if text:
                    assistant_parts.append(text)
                    events = parser.feed(text)
                    handle_events(events)  # 实时展示

            # 流结束后刷出 buffer
            flush_events = parser.flush()
            handle_events(flush_events)

            # 把本轮 LLM 输出存入 messages
            self.messages.append({"role": "assistant", "content": "".join(assistant_parts)})

            # 根据事件决定下一步
            if got_final_answer:
                return final_answer_text
            if got_action_ready:
                result = execute_tool(tool_name, tool_args)
                # Observation 作为 user 消息追加（ReAct 标准）
                self.messages.append({"role": "user", "content": f"Observation: {result}"})
```

---

## 与相关模式的对比

| | 03 非流式 ReAct | 05 流式 FC | **06 流式 ReAct** |
|--|---------------|-----------|-----------------|
| 输出格式 | 纯文本 | Function Calling JSON | 纯文本 |
| API 参数 | stream=False | stream=True, tools= | **stream=True（无 tools=）** |
| 解析方式 | 正则（完整文本） | delta.tool_calls 拼接 | **状态机（增量文本）** |
| 推理可见性 | 有（事后展示） | 无 | **有（实时流出）** |
| 标签跨 chunk | 不涉及 | 不涉及 | **核心挑战** |
| 实现复杂度 | 低 | 中 | **高** |

---

## 实战教训

### 1. chunk.choices 可能为空

某些 streaming chunk（心跳包、流结束信号）的 `choices` 为空列表：

```python
# ❌ 直接索引会 IndexError
delta_text = chunk.choices[0].delta.content

# ✅ 先判断
if not chunk.choices:
    continue
delta_text = chunk.choices[0].delta.content or ""
```

### 2. Observation 作为 user 消息（不是 tool 消息）

ReAct 是纯文本格式，工具结果追加方式与 Function Calling 不同：

```python
# Function Calling（05）的方式：
messages.append({"role": "tool", "tool_call_id": tc_id, "content": result})

# ReAct（06）的方式：
messages.append({"role": "user", "content": f"Observation: {result}"})
```

### 3. 工具错误返回信息要包含可用属性

Agent 用"驻扎站"查询失败，工具返回：
```
实体 '周明远' 没有 '驻扎站' 属性。可用属性：类型, 职位, 年龄, 驻站, 导师, 专长
```

Agent 看到"可用属性: 驻站"后自动改用"驻站"重试成功。
**设计启示**：工具的错误信息要具体且有引导性，帮助 Agent 自我纠正。

### 4. 跳步检测（从 03 移植）

在 `_switch_section(FINAL_ANSWER)` 时检查 thought_buf 是否含未完成计划词：

```python
_UNFINISHED_PLAN_PATTERNS = ["接下来", "还需要", "然后查", "再计算", ...]

def _on_final_answer_start(self):
    for pattern in _UNFINISHED_PLAN_PATTERNS:
        if pattern in self._thought_buf:
            return SkipStepDetected(thought_text=self._thought_buf)
    return None
```

流式下跳步检测更及时——Final Answer 标签刚被识别就立即触发，而不用等完整文本。

---

## 步数一致性验证

同一问题同一模型，流式 ReAct 和非流式 ReAct 的步数应一致：

```
问题：极光站的站长是谁？
流式 ReAct：2 步（lookup → Final Answer）
非流式 ReAct：2 步（lookup → Final Answer）
✓ 步数一致
```

这验证了 streaming 只改变"展示方式"，不影响 ReAct 推理逻辑本身。

---

**最后更新**：2026-06-30  
**来源项目**：06-streaming-react
