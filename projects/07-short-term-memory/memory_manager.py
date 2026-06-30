"""
记忆管理器 —— 4 种短期记忆策略
==================================

本模块是项目的核心学习内容。
定义 MemoryManager 抽象基类，并实现 4 种 context 管理策略：

1. BaselineMemory     — 无管理，messages 无限增长
2. SlidingWindowMemory — 滑动窗口，保留最近 N 轮
3. TokenLimitMemory   — Token 限额，超出时删旧消息
4. SummaryMemory      — LLM 摘要压缩，最大程度保留信息

各策略的核心差异体现在 get_messages() 方法中。
Agent 每次 API 调用前都调用 get_messages() 获取传入 LLM 的消息列表。

关键概念：
- _history 存储完整历史（不含 system prompt），永远追加
- get_messages() 按策略截断/压缩后返回实际传给 API 的列表
- system prompt 始终是第一条消息（role="system"）
"""

from abc import ABC, abstractmethod

import tiktoken

# ============================================================
# Token 计数工具
# ============================================================

# cl100k_base 编码兼容 gpt-4o、gpt-4o-mini、text-embedding-ada-002 等主流模型
ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(messages: list) -> int:
    """
    计算 messages 列表的近似 token 数。

    每条消息 = 内容 token 数 + 4 overhead（role、分隔符等）。
    这是 OpenAI cookbook 推荐的估算方式，误差 < 1%。

    参数：
        messages: OpenAI 格式的消息列表。
            每条可以是 dict，也可以是 OpenAI SDK 的 Pydantic 消息对象
            （工具调用时 _history 中会混入 ChatCompletionMessage 对象）。

    返回：
        近似 token 总数（int）
    """
    total = 0
    for msg in messages:
        # 兼容 dict 和 Pydantic 对象（ChatCompletionMessage）
        if isinstance(msg, dict):
            content = msg.get("content") or ""
        else:
            # OpenAI Pydantic 对象：用 getattr 安全获取 content
            content = getattr(msg, "content", None) or ""
        # +4 是每条消息的固定 overhead（role token + 分隔符）
        total += 4 + len(ENCODING.encode(content))
    return total


# ============================================================
# 抽象基类
# ============================================================

class MemoryManager(ABC):
    """
    短期记忆管理器抽象基类。

    设计意图：
    - _history 永远保存完整对话历史（策略不同只影响 get_messages() 的输出）
    - get_messages() 是核心接口，各策略在此实现截断 / 压缩逻辑
    - token_count() 和 messages_count() 供 display 层实时展示指标

    子类继承后只需实现 get_messages()，其余方法统一由基类提供。
    """

    def __init__(self, system_prompt: str):
        self._system_prompt = system_prompt
        # _history 仅包含 user / assistant / tool 消息，不含 system
        self._history: list[dict] = []

    @abstractmethod
    def get_messages(self) -> list[dict]:
        """
        返回本次 API 调用使用的完整 messages 列表（含 system prompt）。
        这是各策略差异的核心所在。
        """
        ...

    def add_user(self, content: str) -> None:
        """追加一条用户消息到历史。"""
        self._history.append({"role": "user", "content": content})

    def add_assistant(self, content: str) -> None:
        """追加一条 assistant 消息到历史（可为空，工具调用时 content 可为 None）。"""
        self._history.append({"role": "assistant", "content": content or ""})

    def add_tool_call_message(self, message_obj) -> None:
        """
        追加 LLM 请求工具调用时的 assistant 消息对象。
        这条消息必须原样保存（包含 tool_calls 字段），不能简单转为字符串。
        """
        self._history.append(message_obj)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        """追加工具执行结果消息（role="tool"）。"""
        self._history.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })

    def reset(self) -> None:
        """清空对话历史，重置为初始状态。"""
        self._history.clear()

    def token_count(self) -> int:
        """
        返回当前 get_messages() 输出的近似 token 数。
        用于 display 层展示实时 context 压力。
        """
        return count_tokens(self.get_messages())

    def messages_count(self) -> int:
        """返回当前 get_messages() 输出的消息条数（含 system）。"""
        return len(self.get_messages())

    @property
    def name(self) -> str:
        """策略类名，用于 display 层标识。"""
        return self.__class__.__name__

    @property
    def history_size(self) -> int:
        """原始历史条数（未截断，用于调试对比）。"""
        return len(self._history)


# ============================================================
# 策略 1：Baseline —— 无限增长
# ============================================================

class BaselineMemory(MemoryManager):
    """
    基准策略：messages 无限增长，不做任何截断或压缩。

    优点：信息完整，永远不会遗忘
    缺点：随轮数增加，token 消耗线性增长，最终触发 context_length_exceeded

    用途：作为对照组，展示"不管理 context"的后果。
    """

    def get_messages(self) -> list[dict]:
        # 直接返回 system + 完整历史，不做任何处理
        return [{"role": "system", "content": self._system_prompt}] + self._history


# ============================================================
# 策略 2：SlidingWindow —— 滑动窗口
# ============================================================

class SlidingWindowMemory(MemoryManager):
    """
    滑动窗口策略：仅保留最近 N 轮对话。

    实现逻辑：
    - 每轮对话 = user + assistant（工具调用时还有 assistant + tool × N 条）
    - 用 max_turns * 3 作为消息数上限（*3 是留给工具调用消息的余量）
    - 超出部分从最旧消息开始丢弃

    优点：token 消耗可预期，实现简单
    缺点：硬截断丢失信息，跨轮依赖追问时会答错
    """

    def __init__(self, system_prompt: str, max_turns: int = 6):
        super().__init__(system_prompt)
        # max_turns = 保留多少轮对话（每轮约含 2~4 条消息）
        self._max_turns = max_turns

    def get_messages(self) -> list[dict]:
        # 粗略按条数截断：每轮最多 3 条（user + assistant + tool），
        # max_turns 轮就是 max_turns * 3 条
        limit = self._max_turns * 3
        recent = self._history[-limit:] if len(self._history) > limit else self._history
        return [{"role": "system", "content": self._system_prompt}] + recent


# ============================================================
# 策略 3：TokenLimit —— Token 限额截断
# ============================================================

class TokenLimitMemory(MemoryManager):
    """
    Token 限额策略：超出 token 阈值时从最旧消息开始删除。

    与 SlidingWindow 的区别：
    - SlidingWindow 按"条数"截断（粗粒度）
    - TokenLimit 按"token 数"截断（精细控制），更准确

    实现逻辑：
    - 每次 get_messages() 时动态检查当前 token 数
    - 如果超出 max_tokens，从历史最旧条目开始删，直到达标
    - system prompt 的 token 占用始终被计入并保留

    优点：精确控制 token 消耗，不会浪费 context 窗口
    缺点：依然是丢弃信息（只是比滑动窗口更精准）
    """

    def __init__(self, system_prompt: str, max_tokens: int = 3000):
        super().__init__(system_prompt)
        self._max_tokens = max_tokens

    def get_messages(self) -> list[dict]:
        system_msg = {"role": "system", "content": self._system_prompt}
        # 计算 system prompt 占用多少 token，剩余预算分配给历史消息
        system_tokens = count_tokens([system_msg])
        budget = self._max_tokens - system_tokens

        # 复制一份历史，避免直接修改 _history
        history = list(self._history)

        # 从最旧的消息开始删，直到历史消息的 token 总数不超过预算
        while history and count_tokens(history) > budget:
            history.pop(0)  # 删除最旧的一条消息

        return [system_msg] + history


# ============================================================
# 策略 4：Summary —— LLM 摘要压缩
# ============================================================

class SummaryMemory(MemoryManager):
    """
    LLM 摘要压缩策略：超出阈值时调用 LLM 将旧对话压缩为摘要。

    与前两种策略的本质区别：
    - SlidingWindow / TokenLimit 是"丢弃"旧信息
    - SummaryMemory 是"压缩"旧信息 —— 通过摘要保留关键事实

    实现逻辑：
    1. 每次 add_user() 后，agent 调用 compress_if_needed()
    2. 如果当前 token 数超过阈值（max_tokens * threshold_ratio），触发压缩
    3. 取 _history 最旧的一半，发给 LLM 生成摘要（max_tokens=200）
    4. 将摘要注入到 system prompt 末尾（[对话摘要] 标记）
    5. 旧的一半历史从 _history 中删除，只保留摘要

    优点：在 token 受限的情况下最大程度保留信息语义
    缺点：增加一次额外 LLM 调用（触发压缩时），成本略高

    注意：compress_if_needed() 由 MemoryAgent 在 add_user 之后主动调用，
    而非在 get_messages() 内部调用（保持 get_messages() 无副作用）。
    """

    def __init__(
        self,
        system_prompt: str,
        max_tokens: int = 3000,
        threshold_ratio: float = 0.7,
        client=None,
        model: str = "gpt-4o-mini",
    ):
        super().__init__(system_prompt)
        self._max_tokens = max_tokens
        # 超过 max_tokens * threshold_ratio 时触发压缩
        self._threshold = int(max_tokens * threshold_ratio)
        # OpenAI 客户端（压缩时调用 LLM）
        self._client = client
        self._model = model
        # 累积摘要文本（可能经过多次压缩）
        self._summary: str = ""

    def get_messages(self) -> list[dict]:
        # 将摘要注入到 system prompt 末尾
        system_content = self._system_prompt
        if self._summary:
            system_content += f"\n\n[对话摘要] 之前的对话要点：{self._summary}"

        return [{"role": "system", "content": system_content}] + self._history

    def compress_if_needed(self) -> bool:
        """
        检查当前 token 数，超过阈值时压缩最旧的一半历史。

        返回：
            True —— 触发了压缩
            False —— 未触发（token 数未超阈值）

        设计细节：
        - 至少需要 4 条历史消息才触发压缩（太少压缩没有意义）
        - 压缩失败时静默跳过，不影响主流程（宁可 token 超出，也不崩溃）
        - 摘要是累积的：新摘要追加到旧摘要后面（用"；"分隔）
        """
        # 检查是否达到阈值
        current_tokens = count_tokens(self.get_messages())
        if current_tokens < self._threshold:
            return False

        # 历史消息太少，不压缩
        if not self._client or len(self._history) < 4:
            return False

        # 取最旧的一半历史做摘要
        half = len(self._history) // 2
        to_compress = self._history[:half]
        self._history = self._history[half:]  # 保留较新的一半

        # 调用 LLM 生成摘要
        try:
            compress_messages = [
                {
                    "role": "system",
                    "content": (
                        "请将以下星际学院对话历史压缩为简洁摘要（100字以内）。"
                        "保留所有出现的实体名称（人名、院系名、机构名）和关键事实。"
                        "用中文输出。"
                    ),
                },
            ] + [
                # 只传 role 和 content，跳过工具调用格式的消息
                {"role": m.get("role", "user"), "content": m.get("content") or ""}
                for m in to_compress
                if isinstance(m, dict) and m.get("content")
            ]

            resp = self._client.chat.completions.create(
                model=self._model,
                messages=compress_messages,
                max_tokens=200,
            )
            new_summary = resp.choices[0].message.content.strip()

            # 累积摘要：多次压缩时用"；"拼接
            if self._summary:
                self._summary = self._summary + "；" + new_summary
            else:
                self._summary = new_summary

            return True

        except Exception:
            # 压缩失败（网络、API 限流等）静默处理
            # 将已删除的历史放回，避免信息永久丢失
            self._history = to_compress + self._history
            return False


# ============================================================
# 工厂函数
# ============================================================

def create_memory_manager(
    strategy: str,
    system_prompt: str,
    client=None,
    model: str = "gpt-4o-mini",
    **kwargs,
) -> MemoryManager:
    """
    根据策略名创建对应的 MemoryManager 实例。

    参数：
        strategy: "baseline" | "sliding" | "token" | "summary"
        system_prompt: 系统提示词
        client: OpenAI 客户端（summary 策略需要）
        model: 模型名（summary 策略调 LLM 压缩时使用）
        **kwargs: 透传给具体策略的额外参数（如 max_turns、max_tokens）

    返回：
        对应策略的 MemoryManager 实例
    """
    strategy = strategy.lower().strip()

    if strategy == "baseline":
        return BaselineMemory(system_prompt)

    elif strategy == "sliding":
        max_turns = kwargs.get("max_turns", 6)
        return SlidingWindowMemory(system_prompt, max_turns=max_turns)

    elif strategy == "token":
        max_tokens = kwargs.get("max_tokens", 3000)
        return TokenLimitMemory(system_prompt, max_tokens=max_tokens)

    elif strategy == "summary":
        max_tokens = kwargs.get("max_tokens", 3000)
        threshold_ratio = kwargs.get("threshold_ratio", 0.7)
        return SummaryMemory(
            system_prompt,
            max_tokens=max_tokens,
            threshold_ratio=threshold_ratio,
            client=client,
            model=model,
        )

    else:
        raise ValueError(
            f"未知策略 '{strategy}'。可选：baseline / sliding / token / summary"
        )


# ============================================================
# 快速验证
# ============================================================

if __name__ == "__main__":
    from knowledge_base import KNOWLEDGE_BASE

    print("=== memory_manager 快速验证 ===\n")

    # 验证 token 计数
    msgs = [
        {"role": "system", "content": "你是星际学院助手"},
        {"role": "user", "content": "林晨是谁"},
        {"role": "assistant", "content": "林晨是量子院的学员，导师是苏明哲"},
    ]
    print(f"count_tokens 示例: {count_tokens(msgs)} tokens")

    # 验证各策略实例化
    sp = "你是星际学院助手。"
    managers = [
        BaselineMemory(sp),
        SlidingWindowMemory(sp, max_turns=2),
        TokenLimitMemory(sp, max_tokens=200),
    ]

    for mgr in managers:
        mgr.add_user("林晨是哪个院系的？")
        mgr.add_assistant("林晨是量子院的学员。")
        mgr.add_user("她的导师是谁？")
        mgr.add_assistant("她的导师是苏明哲。")
        print(f"\n[{mgr.name}]")
        print(f"  get_messages() 返回 {mgr.messages_count()} 条")
        print(f"  token_count() = {mgr.token_count()}")

    print("\n工厂函数测试:")
    for name in ["baseline", "sliding", "token", "summary"]:
        m = create_memory_manager(name, sp)
        print(f"  create_memory_manager('{name}') -> {m.name}")

    print("\n所有验证通过 ✓")
