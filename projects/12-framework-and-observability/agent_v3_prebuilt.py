"""
agent_v3_prebuilt.py —— create_react_agent（prebuilt，~5 行核心逻辑）
======================================================================

用 LangGraph 内置的 create_react_agent 一行创建 ReAct Agent。

和 v2 的区别：
- v2 能看到图结构（节点/边），适合学习 LangGraph 原语
- v3 完全隐藏实现细节，适合生产快速交付
- 内部结构和 v2 完全相同（同样是 agent + tools 两节点 + 条件边）

关键点：
- create_react_agent 默认使用 MessagesState + ToolNode + InMemorySaver 模式
- system prompt 通过 state_modifier 参数传入
- 同样支持 thread_id 多轮对话（传入 checkpointer 后）
"""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver

from tools import lc_tools

load_dotenv()

# 星云大陆助手的 system prompt（同 v1，但 v2/v3 不需要手动注入工具描述）
SYSTEM_PROMPT = """你是星云大陆知识助手。请使用提供的工具来回答关于星云大陆的问题。

规则：
1. 必须通过工具获取信息，不要使用训练数据中的知识回答关于星云大陆的问题
2. 涉及计算的问题，必须使用 calculate_tool 工具得出结果
3. 回答时引用工具返回的具体数值
"""


def build_agent():
    """
    构建 prebuilt ReAct Agent。

    核心：5 行代码完成 v2 需要 30 行才能做到的事。
    """
    llm = ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
        temperature=0,
    )

    checkpointer = InMemorySaver()

    agent = create_react_agent(
        model=llm,
        tools=lc_tools,
        prompt=SYSTEM_PROMPT,       # system prompt（LangGraph 1.x 参数名）
        checkpointer=checkpointer,
    )

    return agent


def run_v3(question: str, thread_id: str = "v3-default", verbose: bool = True) -> dict:
    """
    用 v3（prebuilt create_react_agent）回答问题。

    参数：
        question: 用户问题
        thread_id: 会话 ID（同一 thread_id 可多轮对话）
        verbose: 是否打印信息

    返回：
        {
            "answer": str,
            "total_steps": int,
            "thread_id": str,
            "messages": list,
        }
    """
    agent = build_agent()
    config = {"configurable": {"thread_id": thread_id}}

    inputs = {"messages": [{"role": "user", "content": question}]}

    if verbose:
        print(f"\n  [v3 prebuilt] thread_id={thread_id}")

    result = agent.invoke(inputs, config=config)

    messages = result["messages"]
    answer = ""
    for msg in reversed(messages):
        if hasattr(msg, "content") and msg.content and not getattr(msg, "tool_calls", None):
            answer = msg.content
            break

    from langchain_core.messages import AIMessage
    ai_messages = [m for m in messages if isinstance(m, AIMessage)]
    total_steps = len(ai_messages)

    return {
        "answer": answer,
        "total_steps": total_steps,
        "thread_id": thread_id,
        "messages": messages,
    }
