# 05-streaming-agent 学习笔记

## 核心概念：Streaming 协议

### 非流式 vs 流式

```python
# 非流式：等待完整响应
response = client.chat.completions.create(model=..., messages=...)
# response.choices[0].message.content → 完整文本
# response.choices[0].message.tool_calls → 完整 tool_calls 列表

# 流式：逐 chunk 迭代
stream = client.chat.completions.create(model=..., messages=..., stream=True)
for chunk in stream:
    # chunk.choices[0].delta.content → 文本片段（可能为 None）
    # chunk.choices[0].delta.tool_calls → tool_call delta（可能为 None）
    # chunk.choices[0].finish_reason → None / "stop" / "tool_calls"
```

### tool_calls Delta 拼接规则

streaming 模式下，tool_calls 不是一次性完整返回，而是分块到达：

```
chunk 1: tool_calls=[{index:0, id:"call_abc", function:{name:"search", arguments:""}}]
chunk 2: tool_calls=[{index:0, function:{arguments:'{"q'}}]
chunk 3: tool_calls=[{index:0, function:{arguments:'uery'}}]
chunk 4: tool_calls=[{index:0, function:{arguments:'": "'}}]
chunk 5: tool_calls=[{index:0, function:{arguments:'极光'}}]
chunk 6: tool_calls=[{index:0, function:{arguments:'"}'}}]
chunk 7: finish_reason="tool_calls"
```

拼接规则：
1. 按 `index` 分组（支持并行工具调用：index=0, index=1, ...）
2. `id` 和 `function.name` 只在第一个 delta 出现
3. `function.arguments` 需要逐块字符串拼接
4. 拼接完成后 `json.loads(arguments)` 得到参数字典

---

## 踩坑记录

### 1. 大量空 chunk 前缀

实际运行观察：前 28~44 个 chunk 的 `delta.content` 和 `delta.tool_calls` 都是 `None`。
这是模型"思考"阶段，尚未决定输出内容。

**影响**：
- timeline 中前几十条记录可能都是"空事件"
- StreamCollector 需要正确跳过空 delta，不能假设每个 chunk 都有内容

**处理方式**：`feed()` 中对 `delta.content` 和 `delta.tool_calls` 都做了 `if` 判断。

### 2. MODEL_NAME vs OPENAI_MODEL 环境变量

从 01 项目复制的 `.env` 文件中变量名是 `MODEL_NAME=gpt-oss-120b`（自定义模型），
但代码最初只读 `OPENAI_MODEL`，导致 fallback 到 `gpt-4o-mini` 后报 503 model_not_found。

**修复**：`os.environ.get("OPENAI_MODEL") or os.environ.get("MODEL_NAME", "gpt-4o-mini")`

### 3. search 函数空格查询未命中

Agent 尝试 `search("深红站 站长")`，但知识库的模糊搜索是 `query.lower() in text.lower()`，
空格会导致精确子串匹配失败。

**Agent 表现**：第一次搜索失败后，自行改用 `search("深红站")` 重试成功。
说明多轮 Agent 有自我纠正能力——这不是 bug 而是一个自然的学习观察点。

### 4. macOS 无 `timeout` 命令

测试脚本用了 `timeout 30 python3 main.py`，macOS 默认没有 GNU coreutils 的 timeout。
使用 `gtimeout`（brew install coreutils）或直接去掉 timeout wrapper。

### 5. system prompt 里的实体名称让模型"跳步"

问"天琴站站长多大了？"，预期两步：先查站长名 → 再查年龄。
实际 timeline 只有一步：直接调 `lookup("林夜霜", "年龄")`。

**原因**：system prompt 列出了 5 位人物姓名，模型推断出"林夜霜是天琴站站长"，
没有经过工具，直接拿记忆里的名字去查年龄。

**影响**：
- 看起来像"省了一步"，实则是模型用了训练/上下文中的知识而非知识库数据
- 如果 system prompt 里没有人物列表，就会乖乖走两步
- 对测试设计有启发：要测"真正的多步链式推理"，需要 system prompt 不提前泄露答案

**验证方法**：`reset` 后换一个 system prompt 不包含人物姓名的版本，重问同一题，
应该会出现 `lookup("天琴站", "站长")` → `lookup("林夜霜", "年龄")` 两步。

---

## 学习要点

### 1. Streaming 的核心模式

```python
stream = client.chat.completions.create(stream=True, ...)
for chunk in stream:
    delta = chunk.choices[0].delta
    # delta.content: 文本片段 (str | None)
    # delta.tool_calls: tool_call delta 列表 (list | None)
    # chunk.choices[0].finish_reason: None | "stop" | "tool_calls"
```

**关键理解**：streaming 不改变 Agent 循环结构，只改变每次 LLM 调用的"消费方式"。

### 2. tool_calls delta 拼接的精确规则

1. 按 `index` 分组（支持并行工具调用）
2. 第一个 delta 带 `id` + `function.name`
3. 后续 delta 只带 `function.arguments` 字符串片段
4. `finish_reason="tool_calls"` 表示所有工具调用的 delta 传输完成
5. 拼接后 `json.loads(accumulated_arguments)` 得到完整参数

### 3. 实际观察到的 chunk 分布

典型一次工具调用的 chunk 序列（以 `search("极光站")` 为例）：
```
chunk[ 1~44]: 空 delta（模型思考中）
chunk[45]:    tool_call_delta → index=0, id=xxx, name="search"
chunk[46~55]: tool_call_delta → arguments 片段: '{\n', '  "', 'query', '":', ...
chunk[56]:    finish_reason="tool_calls"
```

文本回复的 chunk 序列：
```
chunk[ 1~28]: 空 delta
chunk[29~54]: content 片段: '极', '光', '站', '的', ...
chunk[55]:    finish_reason="stop"
```

### 4. Streaming vs Non-Streaming 对比观察

| 指标 | Streaming | Non-Streaming |
|------|-----------|---------------|
| 首字节到达 | 快（空 chunk 也算） | 慢（等完整响应） |
| 用户感知 | 逐字出现，有"活着"的感觉 | 卡顿后一次性出现 |
| 总处理时间 | 略长（chunk 逐个处理开销） | 略短 |
| 调试可观测性 | 高（raw timeline 可审查每个 delta） | 低 |
| 代码复杂度 | 高（需要 delta 拼接逻辑） | 低 |

### 5. 设计决策收获

- **StreamCollector 独立于 Agent**：收集/拼接逻辑与 Agent 循环解耦，便于测试
- **TimelineEntry 记录一切**：事后可以完整回放协议细节
- **C2 展示模式（先 raw 后 final）**：学习时先看底层协议再看合成结果，理解更深

### 6. 并行工具调用实际触发（实测）

问"天琴站和天琴号有什么区别？"时，第一轮 API 调用的 timeline：

```
[  1]   2243ms 🔧 tool_call_delta  [0] id=b13c511a name=lookup args='{"entity":"天琴站"}'
[  2]   2243ms 🔧 tool_call_delta  [1] id=1a42263b name=lookup args='{"entity":"天琴号"}'
[  3]   2243ms 🏁 finish           finish_reason=tool_calls
```

**观察**：
- index=0 和 index=1 **同时出现在同一个 API 调用里**（3个 chunk 就完成）
- 这是 `ToolCallAccumulator` 按 index 分组逻辑被真实触发的场景
- 两个 lookup 并行发出，只需一次 API 往返，效率翻倍

**对比**：如果是串行调用，应该会有两次独立的 `finish_reason=tool_calls`，
但这里只有 1 次 → 确认是真正的并行。

### 7. Streaming 中途思考停顿（实测）

回答长文本时，chunk 间可能出现几秒的空白——不是网络问题，是模型在"想下一段怎么说"。

实测（第二题回答生成表格后的停顿）：

```
[ 87]  19665ms  '"船'
[ 88]  20997ms  '"。'     ← 表格+两个 bullet 写完
[ 89]  28062ms  '天琴号的' ← 停顿约 7 秒，开始写最后一段
```

**对用户体验的意义**：
- Non-streaming：用户盯着空屏等 28 秒，最后才看到完整内容
- Streaming：用户 13 秒时就看到表格出来，20 秒时看到 bullet 点，7 秒停顿发生时屏幕已经有内容了
- 这正是 streaming 的核心价值：**把"等待"变成"渐进呈现"**，即使总时间相同，感知体验完全不同
