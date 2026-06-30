# 07-short-term-memory 开发笔记

## 学习要点

### 1. MemoryManager 的核心设计决策

**将 _history 和 get_messages() 分离**是这个设计的精华：
- `_history` 永远追加完整历史（所有策略相同）
- `get_messages()` 按策略截断后才是真正传给 API 的内容
- 这样 token_count() 统计的是"实际传给 LLM 的 token"，而不是历史总量

### 2. SummaryMemory 的 compress_if_needed() 位置

最初考虑在 `get_messages()` 内部触发压缩，但这有副作用（修改 _history），
违反"get 方法无副作用"的原则。最终改为在 `MemoryAgent.ask()` 的
`add_user()` 之后主动调用，分离了查询和修改。

### 3. 工具调用消息的存储格式

普通 assistant 消息只需存 `{"role": "assistant", "content": "..."}` 即可。
但当 LLM 请求工具调用时（`finish_reason == "tool_calls"`），
必须将整个 `message` 对象原样存入 _history，
因为 OpenAI API 要求后续的 `role: "tool"` 消息必须能找到对应的 `tool_call_id`。

如果只存 content 字符串，会丢失 tool_calls 字段，导致后续 API 调用报错：
```
BadRequestError: tool message is not associated with an existing tool call
```

### 4. tiktoken cl100k_base vs model-specific encoding

`tiktoken.get_encoding("cl100k_base")` 对 gpt-4o-mini / gpt-4o 都适用，
比 `encoding_for_model()` 更健壮（不会因模型名变化而失败）。
token 计数有约 ±5% 误差，对于"是否触发压缩"的判断已经足够。

### 5. SlidingWindowMemory 的 max_turns 乘数

每"轮"对话包含：user 消息 + assistant 消息，简单对话是 2 条。
但如果涉及工具调用：user + assistant(tool_calls) + tool × N + assistant = N+3 条。
所以 `limit = max_turns * 3` 给了足够余量，避免截断一半工具调用消息。

### 6. context_length_exceeded 的捕获

OpenAI SDK v2 中，`context_length_exceeded` 是 `BadRequestError`（400），
不是 `APIError` 的子类。需要：
```python
from openai import BadRequestError
except BadRequestError as e:
    err_body = getattr(e, "body", {}) or {}
    if err_body.get("code") == "context_length_exceeded":
        ...
```
字符串匹配 `"context_length_exceeded" in str(e)` 作为兜底。

---

## 踩坑记录

### 坑 1：知识库中 数据院 的院长字段重复赋值

```python
"数据院": {
    ...
    "院长": "方若冰",  # 这行被下面覆盖了
    "院长": "谢云飞",  # 实际生效的值
}
```
Python dict 中重复 key 只保留最后一个，不会报错。
调试时看到 `数据院 → 院长: 谢云飞` 才发现。
教训：dict literal 中避免重复 key，用 linter 可以检测（`E741`）。

### 坑 2：OpenAI SDK 返回 Pydantic 对象，不是 dict

工具调用时，LLM 返回的 `message` 是 `ChatCompletionMessage`（Pydantic 对象），
不是 dict。存入 `_history` 后，`count_tokens()` 用 `msg.get("content")` 会报
`AttributeError: 'ChatCompletionMessage' object has no attribute 'get'`。

修复：`count_tokens()` 中兼容两种类型：
```python
if isinstance(msg, dict):
    content = msg.get("content") or ""
else:
    content = getattr(msg, "content", None) or ""
```

### 坑 3：第三方代理服务偶发 429/404 HTML 响应

真机验证时，代理服务偶尔返回 HTML 格式的错误页面（非 JSON），
OpenAI SDK 将其作为错误字符串抛出（APIError）。
代码中用 `except Exception as e: answer = f"(API 错误: {e})"` 捕获，
compare 模式不会崩溃，继续运行其他策略。
这是代理侧的偶发问题，不是代码逻辑缺陷。

### 坑 4：compare 模式中各策略共享同一个 client 对象

多个 MemoryManager 可以安全共享同一个 `OpenAI` client 实例，
因为 OpenAI SDK 的 client 是无状态的（不存储 session）。
但各 MemoryManager 必须是独立实例，不能共享，否则 _history 会互相污染。

### 坑 3：display 层的 ANSI 转义在 CI/非 TTY 环境下乱码

当前实现未做 TTY 检测，在管道输出（如 `| grep`）时会出现乱码。
生产级实现应加 `sys.stdout.isatty()` 判断，或提供 `--no-color` 开关。
暂不处理（学习项目场景）。

---

## 待探索

- [ ] 异步并发 API 调用（目前 compare 模式是顺序的，4x 耗时）
- [ ] 摘要质量评估（当前只做定性观察）
- [ ] 向量数据库持久化（→ 08-long-term-memory）
- [ ] 多轮对话中工具结果是否也需要纳入摘要（目前摘要只处理 user/assistant）
