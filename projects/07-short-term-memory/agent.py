"""
MemoryAgent —— 注入记忆策略的单轮对话 Agent
=============================================

MemoryAgent 是对 MemoryManager 的封装层。
它不关心记忆策略的内部实现，只负责：
1. 调用 memory.get_messages() 获取传给 LLM 的消息列表
2. 执行工具调用循环（Function Calling 模式）
3. 把每轮的 user / assistant / tool 消息追加回 memory
4. 捕获 context_length_exceeded 并优雅降级（不崩溃）

与 01-simple-agent/agent.py 的区别：
- 01 的 Agent 内部维护 messages 列表（无策略）
- 07 的 MemoryAgent 把 messages 管理完全委托给注入的 MemoryManager
- 这使得切换记忆策略只需更换 MemoryManager 实例，Agent 代码无需变动
"""

import json
import os

from openai import OpenAI, BadRequestError

from memory_manager import MemoryManager, SummaryMemory
from tools import TOOLS_SCHEMA, execute_tool


# ============================================================
# 系统提示词
# ============================================================

SYSTEM_PROMPT = """你是星际学院的智能助手，拥有以下工具查询学院知识库：

- search(query)：搜索实体（院系、人物、机构等）
- lookup(entity, field)：精确查询某实体的某属性
- calculate(expression)：计算数学表达式（如年份差、人数求和）
- compare(entity_a, entity_b, field)：比较两实体同一属性

工具使用原则：
- 需要事实信息时主动使用工具，不猜测
- 先 search 确认实体名称，再 lookup 获取详细属性
- 多步关系链（如"学员的导师的院系的院长"）需要多次 lookup 逐步追踪
- 计算年限时使用 calculate（当前年份 2026 年）

回答要求：简洁、准确，直接给出结论，关键实体名称保持原文。
"""


# ============================================================
# MemoryAgent
# ============================================================

class MemoryAgent:
    """
    注入记忆策略的对话 Agent。

    核心设计：
    - memory: MemoryManager 接口，策略通过依赖注入传入
    - ask() 是主接口：接收问题，返回 (answer, messages_count, token_count)
    - 工具调用循环参考 01-simple-agent 的实现模式
    - context_length_exceeded 时优雅降级，返回特殊标记字符串

    使用示例：
        memory = SlidingWindowMemory(SYSTEM_PROMPT, max_turns=6)
        agent = MemoryAgent(memory, client, model)
        answer, msg_cnt, tok_cnt = agent.ask("林晨的导师是谁？")
    """

    # 单次提问的最大工具调用步数（防止无限循环）
    MAX_STEPS = 8

    def __init__(
        self,
        memory: MemoryManager,
        client: OpenAI,
        model: str,
        tools_schema: list | None = None,
    ):
        self._memory = memory
        self._client = client
        self._model = model
        # 工具 schema，默认使用 tools.py 中定义的 TOOLS_SCHEMA
        self._tools_schema = tools_schema or TOOLS_SCHEMA

    @property
    def memory(self) -> MemoryManager:
        """暴露 memory 对象，供外部查看 token/messages 指标。"""
        return self._memory

    def ask(self, question: str) -> tuple[str, int, int]:
        """
        发出一次提问，执行工具调用循环，返回最终答案。

        参数：
            question: 用户问题

        返回：
            (answer, messages_count, token_count)
            - answer: 最终回答文本（context 溢出时为特殊提示字符串）
            - messages_count: 本次 API 调用时的 messages 条数
            - token_count: 本次 API 调用时的近似 token 数

        错误处理：
            context_length_exceeded → 返回溢出提示，不抛异常
            其他 API 错误 → 抛出，由调用方处理
        """
        # 1. 将问题追加到记忆
        self._memory.add_user(question)

        # 2. 摘要压缩检查（仅 SummaryMemory 有此方法）
        #    在每轮用户问题加入后立即检查，避免 API 调用时 token 超限
        if isinstance(self._memory, SummaryMemory):
            self._memory.compress_if_needed()

        # 3. 工具调用循环
        for step in range(self.MAX_STEPS):
            # 获取当前策略处理后的 messages 列表
            messages = self._memory.get_messages()

            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=self._tools_schema,
                    tool_choice="auto",
                )
            except BadRequestError as e:
                # 捕获 context_length_exceeded
                # OpenAI 的错误结构：error.code == "context_length_exceeded"
                err_body = getattr(e, "body", {}) or {}
                err_code = err_body.get("code", "") or ""
                err_msg = str(e)
                is_context_exceeded = (
                    err_code == "context_length_exceeded"
                    or "context_length_exceeded" in err_msg
                    or "maximum context length" in err_msg
                )
                if is_context_exceeded:
                    # 优雅降级：不崩溃，返回提示信息
                    overflow_msg = "⚠️ context 溢出，本轮跳过"
                    self._memory.add_assistant(overflow_msg)
                    return (
                        overflow_msg,
                        self._memory.messages_count(),
                        self._memory.token_count(),
                    )
                raise  # 其他 BadRequestError 继续抛出

            choice = resp.choices[0]
            msg = choice.message

            if choice.finish_reason == "tool_calls":
                # ── 工具调用分支 ──
                # 将带有 tool_calls 的 assistant 消息存入 memory
                # 注意：不能只存 content（content 此时可能为 None），
                # 需要存整个 message 对象供后续 tool 结果配对
                self._memory.add_tool_call_message(msg)

                # 执行每个工具调用，追加结果
                for tc in msg.tool_calls:
                    tool_name = tc.function.name
                    try:
                        tool_args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        tool_args = {}

                    tool_result = execute_tool(tool_name, tool_args)
                    self._memory.add_tool_result(tc.id, tool_result)

                # 继续循环，让 LLM 根据工具结果继续推理
                continue

            elif choice.finish_reason == "stop":
                # ── 最终回答分支 ──
                answer = msg.content or ""
                self._memory.add_assistant(answer)
                return (
                    answer,
                    self._memory.messages_count(),
                    self._memory.token_count(),
                )

            else:
                # 其他 finish_reason（length 等）尽量返回已有内容
                partial = msg.content or f"(finish_reason={choice.finish_reason})"
                self._memory.add_assistant(partial)
                return (
                    partial,
                    self._memory.messages_count(),
                    self._memory.token_count(),
                )

        # 超过最大步数
        fallback = f"(超过最大步数 {self.MAX_STEPS}，未能给出回答)"
        self._memory.add_assistant(fallback)
        return (
            fallback,
            self._memory.messages_count(),
            self._memory.token_count(),
        )

    def reset(self) -> None:
        """重置记忆，开始全新对话。"""
        self._memory.reset()


# ============================================================
# 快捷工厂函数
# ============================================================

def create_agents(
    strategies: list[str] | None = None,
) -> dict[str, "MemoryAgent"]:
    """
    批量创建多个策略的 MemoryAgent，供 compare 模式使用。

    从环境变量读取 API 配置，返回 {策略名: MemoryAgent} 字典。

    参数：
        strategies: 要创建的策略列表，默认为全部 4 种

    返回：
        dict，key 为策略简称（baseline/sliding/token/summary）
    """
    from dotenv import load_dotenv
    from memory_manager import (
        BaselineMemory,
        SlidingWindowMemory,
        TokenLimitMemory,
        SummaryMemory,
        create_memory_manager,
    )

    load_dotenv()

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    model = (
        os.environ.get("OPENAI_MODEL")
        or os.environ.get("MODEL_NAME", "gpt-4o-mini")
    ).strip()

    if not api_key:
        raise ValueError("未找到 OPENAI_API_KEY 环境变量，请配置 .env 文件")

    client = OpenAI(api_key=api_key, base_url=base_url)

    if strategies is None:
        strategies = ["baseline", "sliding", "token", "summary"]

    # 从环境变量读取策略参数
    sliding_turns = int(os.environ.get("SLIDING_WINDOW_TURNS", "6"))
    token_limit = int(os.environ.get("TOKEN_LIMIT", "3000"))
    summary_ratio = float(os.environ.get("SUMMARY_THRESHOLD_RATIO", "0.7"))

    agents = {}
    for name in strategies:
        memory = create_memory_manager(
            name,
            SYSTEM_PROMPT,
            client=client,
            model=model,
            max_turns=sliding_turns,
            max_tokens=token_limit,
            threshold_ratio=summary_ratio,
        )
        agents[name] = MemoryAgent(memory, client, model)

    return agents


# ============================================================
# 快速验证（不调用真实 API）
# ============================================================

if __name__ == "__main__":
    from memory_manager import BaselineMemory, SlidingWindowMemory, TokenLimitMemory

    print("=== MemoryAgent 结构验证 ===\n")

    # 验证能正确实例化（不发起真实 API 调用）
    class MockClient:
        """模拟 OpenAI 客户端（仅用于结构验证）"""
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("Mock: 不发起真实 API 调用")

    mock_client = MockClient()
    sp = SYSTEM_PROMPT

    for cls in [BaselineMemory, SlidingWindowMemory, TokenLimitMemory]:
        memory = cls(sp)
        agent = MemoryAgent(memory, mock_client, "gpt-4o-mini")
        print(f"  MemoryAgent({cls.__name__}) 创建成功 ✓")
        print(f"    memory.name = {agent.memory.name}")

    print("\nMemoryAgent 结构验证通过 ✓")
