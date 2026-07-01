# 短期记忆管理（Short-Term Memory）

Agent 的短期记忆就是 `messages` 列表。随着对话轮次增加，
messages 无限增长最终会超出 context window。短期记忆管理的核心问题：
**如何在有限上下文中保留最大信息量？**

---

## 核心矛盾

```
信息完整性                    context 窗口限制
   ↑                              ↑
   │   ← 短期记忆管理的权衡 →      │
   │                              │
保留越多 → token 越多 → 越可能超限
截断越多 → token 越少 → 越可能丢关键信息
```

---

## 四种策略对比

| 策略 | 原理 | 信息损失 | 实现复杂度 | 适用场景 |
|------|------|---------|-----------|---------|
| **Baseline** | 无管理，messages 无限增长 | 无（直到崩溃） | 无 | 短对话、测试基线 |
| **滑动窗口** | 只保留最近 N 轮 | 早期对话全丢 | 低 | 闲聊、无跨轮依赖 |
| **Token 截断** | 按 token 数从旧到新截断 | 早期对话按量丢 | 中 | 精确控制成本 |
| **LLM 摘要** | 超阈值时调 LLM 压缩旧对话为摘要 | 细节丢、要点保留 | 高 | 需要保留历史要点 |

---

## 关键设计：_history 与 get_messages() 分离

```python
class MemoryManager(ABC):
    def __init__(self, system_prompt: str):
        self._system_prompt = system_prompt
        self._history: list = []       # 永远追加完整历史

    def add(self, message):
        self._history.append(message)  # 所有策略相同

    @abstractmethod
    def get_messages(self) -> list:
        """按策略截断后返回——这才是传给 LLM 的内容"""
        ...
```

**为什么分离？**
- `_history` 是"记忆的全部"，策略无关
- `get_messages()` 是"能看到的记忆"，策略决定
- token_count() 统计的是"实际传给 LLM 的 token"，不是历史总量
- 切换策略不影响已积累的历史（策略是视角，不是存储）

---

## 滑动窗口策略

最简单的截断：只保留最近 `max_turns` 轮对话。

```python
class SlidingWindowMemory(MemoryManager):
    def get_messages(self) -> list:
        system = [{"role": "system", "content": self._system_prompt}]
        limit = self._max_turns * 3   # 每轮 ≈ 3 条（含工具调用）
        recent = self._history[-limit:] if len(self._history) > limit else self._history
        return system + recent
```

**乘数为什么是 3？**

每轮对话不只是 user + assistant = 2 条。涉及工具调用时：
```
user + assistant(tool_calls) + tool_result + assistant(final) = 4 条
```
用 `max_turns * 3` 给足余量，避免截断一半工具调用消息（截断后 tool 消息找不到对应的 tool_call_id 会报错）。

---

## Token 截断策略

比滑动窗口更精确：按实际 token 数截断。

```python
class TokenLimitMemory(MemoryManager):
    def get_messages(self) -> list:
        system = [{"role": "system", "content": self._system_prompt}]
        system_tokens = count_tokens(system)
        budget = self._max_tokens - system_tokens

        # 从最新消息开始向前累加，直到超预算
        selected = []
        for msg in reversed(self._history):
            msg_tokens = count_tokens([msg])
            if budget - msg_tokens < 0:
                break
            selected.append(msg)
            budget -= msg_tokens

        return system + list(reversed(selected))
```

**tiktoken 选型**：`cl100k_base` encoding 对 gpt-4o/gpt-4o-mini 通用，
比 `encoding_for_model()` 更健壮（不会因模型名变化而失败），误差 ±5%。

---

## LLM 摘要压缩策略

最复杂但信息保留最好：超阈值时调 LLM 将旧对话压缩为摘要。

```python
class SummaryMemory(MemoryManager):
    def compress_if_needed(self, client):
        current_tokens = self.token_count()
        if current_tokens <= self._compress_threshold:
            return

        # 把前 N 条旧消息压缩为摘要
        old_messages = self._history[:self._compress_point]
        summary = client.chat.completions.create(
            messages=[{
                "role": "user",
                "content": f"请将以下对话压缩为简洁摘要，保留关键事实：\n{format(old_messages)}"
            }],
            max_tokens=200,
        )

        # 替换旧消息为一条摘要消息
        self._history = [
            {"role": "system", "content": f"[历史摘要] {summary}"},
            *self._history[self._compress_point:]
        ]
```

**关键设计决策**：
- `compress_if_needed()` 放在 `agent.ask()` 中主动调用，不在 `get_messages()` 里
- 原因：get 方法不应有副作用（修改 _history）
- 摘要有 `max_tokens` 上限，防止摘要本身太长适得其反

---

## context_length_exceeded 优雅降级

Baseline 策略必然会在长对话后超限，需要优雅处理：

```python
from openai import BadRequestError

try:
    response = client.chat.completions.create(...)
except BadRequestError as e:
    err_body = getattr(e, "body", {}) or {}
    if err_body.get("code") == "context_length_exceeded":
        return "⚠️ context 溢出，本轮跳过"
    raise
```

**注意**：OpenAI SDK v2 中这是 `BadRequestError`（HTTP 400），不是 `APIError`。

---

## 工具调用消息的存储陷阱

LLM 请求工具调用时，必须将整个 `message` 对象原样存入 _history：

```python
# ❌ 错误：只存 content
self._history.append({"role": "assistant", "content": response.content})
# 后续 tool 消息找不到 tool_call_id → API 报错

# ✅ 正确：存完整 message 对象
self._history.append(response)  # ChatCompletionMessage，含 tool_calls 字段
```

由此带来第二个陷阱：`_history` 里混合了 dict 和 Pydantic 对象，
token 计数时必须兼容：

```python
if isinstance(msg, dict):
    content = msg.get("content") or ""
else:
    content = getattr(msg, "content", None) or ""
```

---

## 并排对比的学习价值

`--compare` 模式同一追问序列 4 策略并行，核心观察：

```
轮次 1-4：四种策略答案一致（对话短，无截断触发）
轮次 5-6：sliding 开始丢失早期信息，回答出错
轮次 7-8：token_limit 也开始截断，只有 summary 仍能答对
```

**信息损失的可见化**：不是"策略 A 比策略 B 好"这种抽象结论，
而是"第 6 轮追问第 1 轮的内容，sliding 答错了因为第 1 轮已被截掉"——
失败路径清晰可见。

---

## 与后续项目的关系

| 主题 | 07 短期记忆 | 08 长期记忆（下一步） |
|------|-----------|-------------------|
| 存储位置 | 内存（messages 列表） | 外部存储（向量数据库） |
| 生命周期 | 单次 session | 跨 session 持久化 |
| 检索方式 | 全量传入 / 截断 | 语义相似度检索 |
| 核心挑战 | context 窗口限制 | 检索相关性 + 去重 |

07 的 `MemoryManager` 抽象基类为 08 预留了扩展接口：
08 可以实现 `VectorMemory` 子类，复用 `add()` / `get_messages()` 接口。

---

**最后更新**：2026-07-01  
**来源项目**：07-short-term-memory
