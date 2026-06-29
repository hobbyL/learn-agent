# 流式输出协议（Streaming Protocol）

OpenAI Streaming API（`stream=True`）是让 Agent 实现"边生成边输出"的核心机制。

---

## 核心思想

**把一次完整响应拆分为连续的增量片段（chunk）流式返回**，而非等待全部生成完毕才返回。

---

## 为什么需要 Streaming？

### 传统非流式的问题

```
用户发问
    ↓
[等待 5~30 秒，空屏]
    ↓
一次性接收完整回答
```

**问题**：长回复下用户长时间盯着空屏，感知体验差；若网络中断，全部内容丢失。

### Streaming 的优势

```
用户发问
    ↓
chunk 1: "深"      → 立刻显示
chunk 2: "红"      → 继续显示
chunk 3: "站"      → ...
...
chunk N: finish_reason="stop"
```

**优势**：
- 首字节延迟极低（几十毫秒内开始显示内容）
- 用户感知"Agent 在思考"，有生命感
- 长停顿时屏幕已有内容，不是空白等待

---

## API 调用模式

### 非流式

```python
response = client.chat.completions.create(
    model=model,
    messages=messages,
    tools=tools,
)
# response.choices[0].message.content → 完整文本
# response.choices[0].message.tool_calls → 完整 tool_calls 列表
# response.choices[0].finish_reason → "stop" | "tool_calls"
```

### 流式

```python
stream = client.chat.completions.create(
    model=model,
    messages=messages,
    tools=tools,
    stream=True,          # 关键参数
)

for chunk in stream:
    delta = chunk.choices[0].delta
    # delta.content      → 文本片段 (str | None)
    # delta.tool_calls   → tool_call delta 列表 (list | None)
    # chunk.choices[0].finish_reason → None | "stop" | "tool_calls"
```

**关键理解**：`stream=True` 不改变 Agent 循环结构，只改变每次 LLM 调用的"消费方式"。
循环外壳（tool_call → execute → 再调 LLM）完全不变。

---

## Chunk 的三种类型

| 类型 | 特征 | 含义 |
|------|------|------|
| 空 chunk | `delta.content=None`, `delta.tool_calls=None` | 模型"思考中"，尚未输出 |
| 文本 chunk | `delta.content` 为字符串片段 | 模型正在生成文本回答 |
| tool_call chunk | `delta.tool_calls` 不为 None | 模型正在生成工具调用 |
| finish chunk | `finish_reason` 不为 None | 本轮生成结束 |

**注意**：前 10~50 个 chunk 通常都是空 chunk（模型决策阶段），代码必须容错跳过。

---

## tool_calls Delta 拼接

Streaming 模式下，`tool_calls` 不是一次性完整返回，而是**分块到达**：

```
chunk 1: tool_calls=[{index:0, id:"call_abc", function:{name:"search", arguments:""}}]
chunk 2: tool_calls=[{index:0, function:{arguments:'{"q'}}]
chunk 3: tool_calls=[{index:0, function:{arguments:'uery'}}]
chunk 4: tool_calls=[{index:0, function:{arguments:'": "'}}]
chunk 5: tool_calls=[{index:0, function:{arguments:'极光'}}]
chunk 6: tool_calls=[{index:0, function:{arguments:'"}'}}]
chunk 7: finish_reason="tool_calls"
```

**拼接规则**：

1. **按 `index` 分组**：`index=0` 对应第一个工具调用，`index=1` 对应第二个（并行调用时）
2. **`id` 和 `function.name` 只在第一个 delta 出现**：后续 delta 只有 arguments 片段
3. **`function.arguments` 逐块字符串拼接**：`acc += delta.arguments`
4. **拼接完成后解析**：`json.loads(accumulated_arguments)` 得到参数字典
5. **`finish_reason="tool_calls"` 收尾**：所有工具调用的 delta 全部传输完成

---

## 并行工具调用（Parallel Tool Calls）

当模型决定同时调用多个工具时，多个 tool_call delta 会在同一次 API 调用中出现：

```
chunk 1: tool_calls=[
    {index:0, id:"call_aaa", function:{name:"lookup", arguments:'{"entity":"天琴站"}'}},
    {index:1, id:"call_bbb", function:{name:"lookup", arguments:'{"entity":"天琴号"}'}}
]
chunk 2: finish_reason="tool_calls"
```

**实际观察**（问"天琴站和天琴号的区别"）：

```
[1]  2243ms 🔧 [0] id=b13c511a name=lookup args='{"entity":"天琴站"}'
[2]  2243ms 🔧 [1] id=1a42263b name=lookup args='{"entity":"天琴号"}'
[3]  2243ms 🏁 finish_reason=tool_calls
```

仅 3 个 chunk，两次查询在一次 API 往返内完成——效率是串行的 2 倍。

**识别方法**：只有 1 次 `finish_reason=tool_calls` → 确认是并行。
串行调用会有多次 `finish_reason=tool_calls`。

---

## Streaming 的 Agent 循环

```python
for iteration in range(1, max_iterations + 1):
    # 1. 流式 API 调用（替代非流式的一次性调用）
    collector = StreamCollector()
    stream = client.chat.completions.create(stream=True, ...)
    for chunk in stream:
        new_text = collector.feed(chunk)
        if new_text:
            print(new_text, end="", flush=True)  # 实时输出

    result = collector.build()

    # 2. 判断终止条件（与非流式完全相同）
    if result.finish_reason == "stop":
        return result.content           # 文本回答，循环结束

    if result.finish_reason == "tool_calls":
        # 3. 执行工具（与非流式完全相同）
        for tc in result.tool_calls:
            tool_result = execute_tool(tc["function"]["name"], tc["function"]["arguments"])
            messages.append({"role": "tool", "content": tool_result, ...})
        # 继续下一轮
```

**核心差异**：只有第 1 步（API 调用方式）不同，其余逻辑不变。

---

## 实际观察到的 Chunk 分布

典型工具调用序列（`search("极光站")`）：

```
chunk[ 1~44]: 空 delta（模型决策中）
chunk[45]:    tool_call_delta → index=0, id=xxx, name="search"
chunk[46~55]: tool_call_delta → arguments 片段
chunk[56]:    finish_reason="tool_calls"
```

典型文本回复序列：

```
chunk[ 1~28]: 空 delta
chunk[29~54]: content 片段（逐字/逐词）
chunk[55]:    finish_reason="stop"
```

**规律**：
- 空 chunk 数量差异大（10~50个），取决于模型和问题复杂度
- tool_call 的 arguments 以字符为单位逐片传输（中文字符也是逐字）
- 文本内容有时多字同 chunk（`'站长是 **'`），有时单字（`'陈'`）

---

## Streaming 中途停顿

回答长文本时，两个 content chunk 之间可能出现数秒空白，这是**模型在段落间"思考"**，
不是网络问题。

实测（回答一个需要生成表格+总结的问题）：

```
[ 87]  19665ms  '"船'
[ 88]  20997ms  '"。'      ← 表格和 bullet 写完
[ 89]  28062ms  '天琴号的'  ← 停顿约 7 秒，开始写总结段落
```

**对用户体验的意义**：

| | Non-Streaming | Streaming |
|--|--------------|-----------|
| 表格出现时刻 | 28 秒后（全部完成才显示） | 13 秒时（实时） |
| 7 秒停顿感知 | 无感知（还在空屏等） | 屏幕已有内容，停顿可接受 |
| 总体感知 | "好慢" | "在逐步完成" |

**结论**：即使总时间相同，Streaming 把"等待"变成了"渐进呈现"，显著改善用户感知。

---

## 设计要点

### StreamCollector 模式

把 delta 收集、拼接、记录逻辑封装为独立组件，与 Agent 循环解耦：

```python
class StreamCollector:
    def feed(self, chunk) -> str | None:
        """处理一个 chunk，返回新增的文本片段（如有）"""
        ...
    def build(self) -> StreamResult:
        """流结束后，构建完整结果"""
        ...
```

**优势**：
- Agent 循环只关心"有没有工具调用"和"最终文本是什么"，不关心 delta 细节
- StreamCollector 可独立测试（喂合成 chunk，验证拼接逻辑）
- TimelineEntry 记录每个 chunk 的时间戳和内容，事后可完整回放

### 原始 Delta Timeline

记录每个 chunk 的原始内容，是调试 streaming 问题的最佳工具：

```
[  1]    45ms 🔧 tool_call_delta  [0] id=xxx name=search
[  2]    46ms 🔧 tool_call_delta  [0] args+='{"query":'
[  3]    47ms 🔧 tool_call_delta  [0] args+='"极光站"}'
[  4]    89ms 🏁 finish           finish_reason=tool_calls
```

能清楚看到：参数分几次到达、并行调用的 index、到底是哪个 chunk 触发了问题。

---

## 常见陷阱

### 1. 假设每个 chunk 都有内容

❌ 错误：`text += chunk.choices[0].delta.content`（content 可能为 None，触发 TypeError）

✅ 正确：`if delta.content: text += delta.content`

### 2. 忽略空 chunk 导致误判

❌ 错误：第一个 chunk 没有 tool_calls 就认为是文本回复

✅ 正确：等到 `finish_reason` 不为 None 才判断本轮是文本还是工具调用

### 3. tool_calls arguments 未完整拼接就 parse

❌ 错误：每个 delta 都调用 `json.loads(delta.arguments)`（片段不是合法 JSON）

✅ 正确：等 `finish_reason="tool_calls"` 后，对完整拼接的字符串调用 `json.loads`

### 4. System prompt 泄露知识导致 Agent 跳步

问"天琴站站长多大了？"时，若 system prompt 已列出"林夜霜是天琴站站长"，
模型会直接推断姓名，跳过第一步工具调用——这不是 bug，是模型正确使用上下文。

**影响测试设计**：要验证"真正的多步链式推理"，system prompt 不应提前泄露答案。
可以用虚构知识库（模型训练数据中不存在），强迫 Agent 真正走工具调用路径。

---

## Streaming vs Non-Streaming 对比

| 指标 | Streaming | Non-Streaming |
|------|-----------|---------------|
| 首字节延迟 | 低（几十毫秒内开始） | 高（等全部生成完） |
| 用户感知 | 逐字显示，有"活"的感觉 | 等待 → 一次性出现 |
| 总处理时间 | 略长（chunk 处理开销） | 略短 |
| 调试可观测性 | 高（raw timeline 可审查） | 低（只看最终结果） |
| 代码复杂度 | 高（需 delta 拼接逻辑） | 低 |
| 中断恢复 | 可展示已收到的部分内容 | 全部丢失 |
| 适用场景 | 用户交互、长文本、学习调试 | 批处理、内部调用、简单脚本 |

---

**最后更新**：2026-06-29  
**来源项目**：05-streaming-agent
