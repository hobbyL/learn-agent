"""
LongMemoryAgent —— 注入长期记忆的对话 Agent
============================================

与 07-short-term-memory/agent.py 的核心区别：
- 07：MemoryManager 管理 messages 列表（全量或截断），策略在 get_messages() 中实现
- 08：LongMemoryAgent 通过语义检索从向量库取出相关历史，注入 system prompt

工作流程：
1. 用户提问 → 检索长期记忆（语义相似度）
2. 将相关记忆注入 system prompt 末尾
3. 执行 Function Calling 循环（与 07 工具调用完全相同）
4. 获得回答后存入长期记忆（供后续 session 检索）

关键设计：
- _short_term：当前 session 内的短期 messages（session 结束即清空）
- long_term_memory：跨 session 持久化的向量库
- new_session()：开始新 session，清空短期记忆，保留长期记忆
"""

import json
import os

from openai import OpenAI, BadRequestError

from long_term_memory import LongTermMemory
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
# LongMemoryAgent
# ============================================================

class LongMemoryAgent:
    """
    注入长期记忆的对话 Agent。

    核心接口：
        new_session(session_id) — 开始新 session（清空短期，保留长期）
        ask(question)           — 发出提问，返回 (answer, retrieved_memories)

    retrieved_memories 供 display 层展示检索到了哪些历史对话，
    以及注入了什么内容到 system prompt 中。
    """

    # 单次提问的最大工具调用步数（防止无限循环）
    MAX_STEPS = 8

    def __init__(
        self,
        long_term_memory: LongTermMemory,
        client: OpenAI,
        model: str,
        tools_schema: list | None = None,
        base_system_prompt: str = SYSTEM_PROMPT,
        top_k: int = 3,
        threshold: float = 0.7,
    ):
        self._ltm = long_term_memory
        self._client = client
        self._model = model
        self._tools_schema = tools_schema or TOOLS_SCHEMA
        self._base_system_prompt = base_system_prompt
        self._top_k = top_k
        self._threshold = threshold

        # 当前 session 的短期记忆（session 结束即清空，不同于长期记忆）
        self._short_term: list[dict] = []
        self._session_id: str = "default"
        self._turn_id: int = 0

    @property
    def long_term_memory(self) -> LongTermMemory:
        """暴露长期记忆对象，供外部查询条数等指标。"""
        return self._ltm

    def new_session(self, session_id: str) -> None:
        """
        开始新 session。

        清空当前 session 的短期 messages，
        但长期记忆（ChromaDB）不受影响 —— 这是跨 session 记忆的核心。

        参数：
            session_id — 新 session 的唯一标识
        """
        self._short_term = []
        self._session_id = session_id
        self._turn_id = 0

    def ask(self, question: str) -> tuple[str, list[dict]]:
        """
        发出一次提问，执行工具调用循环，返回最终答案。

        流程：
        1. 检索长期记忆（语义相似度）
        2. 构建带记忆注入的 system prompt
        3. 拼接短期 messages + 当前问题，调 LLM
        4. 执行 Function Calling 循环直到得到最终答案
        5. 更新短期记忆 + 存入长期记忆
        6. 返回答案和检索到的记忆（供 display 展示）

        参数：
            question — 用户问题

        返回：
            (answer, retrieved_memories)
            - answer: 最终回答文本
            - retrieved_memories: 本次检索到并注入的记忆列表
        """
        # 1. 检索长期记忆（用当前问题作为查询向量）
        memories = self._ltm.retrieve(question, self._top_k, self._threshold)

        # 2. 构建注入了历史记忆的 system prompt
        system_content = self._base_system_prompt
        if memories:
            memory_lines = []
            for m in memories:
                meta = m["metadata"]
                sim = m["similarity"]
                memory_lines.append(
                    f"- [Session {meta['session_id']} · 第{meta['turn_id']}轮 · 相似度{sim}] "
                    f"用户问：{meta['user_query']}  助手答：{meta['assistant_answer']}"
                )
            memory_text = "\n".join(memory_lines)
            system_content += (
                f"\n\n[长期记忆] 以下是过去对话中的相关内容：\n{memory_text}"
            )

        # 3. 拼接完整 messages（system + 短期历史 + 当前问题）
        messages = (
            [{"role": "system", "content": system_content}]
            + self._short_term
            + [{"role": "user", "content": question}]
        )

        # 4. 执行 Agent 工具调用循环
        answer = self._run_agent_loop(messages)

        # 5. 更新短期记忆（仅保留 user + assistant，不含工具调用细节）
        self._short_term.append({"role": "user", "content": question})
        self._short_term.append({"role": "assistant", "content": answer})

        # 6. 存入长期记忆（供后续 session 检索）
        self._turn_id += 1
        self._ltm.store(self._session_id, self._turn_id, question, answer)

        return answer, memories

    def _run_agent_loop(self, messages: list[dict]) -> str:
        """
        Function Calling 循环。

        参考 07-short-term-memory/agent.py 的完整工具调用实现：
        - finish_reason == "tool_calls"：执行工具，追加结果，继续循环
        - finish_reason == "stop"：返回最终答案
        - context_length_exceeded：优雅降级，返回错误提示
        - 超过 MAX_STEPS：返回兜底提示

        参数：
            messages — 完整的 messages 列表（含 system、短期历史、当前问题）

        返回：
            最终回答文本（str）
        """
        # 注意：messages 在循环中会动态追加工具调用消息
        # 需要创建一份局部副本，不影响 _short_term
        local_messages = list(messages)

        for step in range(self.MAX_STEPS):
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=local_messages,
                    tools=self._tools_schema,
                    tool_choice="auto",
                )
            except BadRequestError as e:
                # 捕获 context_length_exceeded，避免崩溃
                err_body = getattr(e, "body", {}) or {}
                err_code = err_body.get("code", "") or ""
                err_msg = str(e)
                is_context_exceeded = (
                    err_code == "context_length_exceeded"
                    or "context_length_exceeded" in err_msg
                    or "maximum context length" in err_msg
                )
                if is_context_exceeded:
                    return "⚠️ context 溢出，本轮跳过"
                raise

            choice = resp.choices[0]
            msg = choice.message

            if choice.finish_reason == "tool_calls":
                # ── 工具调用分支 ──
                # 将 LLM 请求工具调用的 assistant 消息加入本地 messages
                # 注意：必须存整个 message 对象（含 tool_calls 字段），不能只存 content
                local_messages.append(msg)

                # 执行每个工具调用，追加结果
                for tc in msg.tool_calls:
                    tool_name = tc.function.name
                    try:
                        tool_args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        tool_args = {}

                    tool_result = execute_tool(tool_name, tool_args)

                    # 工具结果必须以 role="tool" 追加，且 tool_call_id 要对应
                    local_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result,
                    })

                # 继续循环，让 LLM 根据工具结果继续推理
                continue

            elif choice.finish_reason == "stop":
                # ── 最终回答分支 ──
                return msg.content or ""

            else:
                # 其他 finish_reason（length 等）尽量返回已有内容
                return msg.content or f"(finish_reason={choice.finish_reason})"

        # 超过最大步数，兜底返回
        return f"(超过最大工具调用步数 {self.MAX_STEPS}，未能给出回答)"

    def reset_short_term(self) -> None:
        """
        清空当前 session 的短期记忆。

        interactive 模式下用户输入 'reset' 时调用。
        长期记忆不受影响。
        """
        self._short_term = []

    def clear_long_term(self) -> None:
        """清空所有长期记忆（ChromaDB collection）。"""
        self._ltm.clear()


# ============================================================
# 工厂函数
# ============================================================

def create_agent(
    session_id: str = "default",
) -> "LongMemoryAgent":
    """
    从环境变量读取配置，创建 LongMemoryAgent 实例。

    自动配置：
    - OpenAI 客户端（聊天模型）
    - Embedding 函数（OpenAICompatibleEF）
    - LongTermMemory（ChromaDB 持久化）

    参数：
        session_id — 初始 session ID

    返回：
        配置好的 LongMemoryAgent 实例
    """
    from dotenv import load_dotenv
    from long_term_memory import OpenAICompatibleEF

    load_dotenv()

    # 聊天模型配置
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    model = (
        os.environ.get("OPENAI_MODEL")
        or os.environ.get("MODEL_NAME", "gpt-4o-mini")
    ).strip()

    if not api_key:
        raise ValueError("未找到 OPENAI_API_KEY，请配置 .env 文件")

    client = OpenAI(api_key=api_key, base_url=base_url)

    # Embedding 配置（必须配置，不使用本地模型）
    emb_base_url = os.environ.get("EMBEDDING_BASE_URL", "").strip()
    emb_api_key = os.environ.get("EMBEDDING_API_KEY", "").strip()
    emb_model = os.environ.get("EMBEDDING_MODEL", "").strip()

    if not all([emb_base_url, emb_api_key, emb_model]):
        raise ValueError(
            "Embedding 配置不完整，请在 .env 中设置：\n"
            "  EMBEDDING_BASE_URL, EMBEDDING_API_KEY, EMBEDDING_MODEL"
        )

    embedding_fn = OpenAICompatibleEF(
        base_url=emb_base_url,
        api_key=emb_api_key,
        model=emb_model,
    )

    # ChromaDB 持久化配置
    persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_db").strip()
    top_k = int(os.environ.get("MEMORY_TOP_K", "3"))
    threshold = float(os.environ.get("MEMORY_THRESHOLD", "0.7"))

    ltm = LongTermMemory(
        persist_dir=persist_dir,
        collection_name="conversation_memory",
        embedding_fn=embedding_fn,
    )

    agent = LongMemoryAgent(
        long_term_memory=ltm,
        client=client,
        model=model,
        top_k=top_k,
        threshold=threshold,
    )
    agent.new_session(session_id)

    return agent


# ============================================================
# 快速验证（不调用真实 API）
# ============================================================

if __name__ == "__main__":
    from long_term_memory import LongTermMemory, OpenAICompatibleEF

    print("=== LongMemoryAgent 结构验证 ===\n")

    # 验证能正确实例化（不发起真实 API 调用）
    class MockClient:
        """模拟 OpenAI 客户端（仅用于结构验证）"""
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("Mock: 不发起真实 API 调用")

    class MockLTM:
        """模拟 LongTermMemory（仅用于结构验证）"""
        def retrieve(self, *args, **kwargs): return []
        def store(self, *args, **kwargs): pass
        def count(self): return 0
        def clear(self): pass

    mock_client = MockClient()
    mock_ltm = MockLTM()

    agent = LongMemoryAgent(
        long_term_memory=mock_ltm,
        client=mock_client,
        model="gpt-4o-mini",
    )

    print(f"  LongMemoryAgent 创建成功 ✓")
    print(f"  top_k={agent._top_k}, threshold={agent._threshold}")

    agent.new_session("test_session")
    print(f"  new_session('test_session') ✓, session_id={agent._session_id}")

    print("\nLongMemoryAgent 结构验证通过 ✓")
