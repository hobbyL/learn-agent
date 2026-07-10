"""
agent_langgraph.py —— LangGraph StateGraph Agent（零代码追踪）
=============================================================

从项目 12 的 agent_v2_stategraph.py 复用核心 StateGraph 构建。

可观测性特点：
- 使用 ChatOpenAI（LangChain 模块），LangSmith 环境变量开启后自动追踪
- 每个节点执行、LLM 调用、工具调用都会出现在 LangSmith trace 中
- 无需 @traceable 或 wrap_openai，零代码改动
"""

import os
from typing import Literal

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver

from tools import lc_tools

load_dotenv()


# ============================================================
# 构建图
# ============================================================

def build_graph(verbose: bool = False):
    """
    构建手动 StateGraph。

    图结构：
        START → agent → (有 tool_calls?) → tools → agent → ... → END
    """
    llm = ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
        temperature=0,
    )

    llm_with_tools = llm.bind_tools(lc_tools)

    def agent_node(state: MessagesState) -> dict:
        """调用 LLM，返回 AI 消息。"""
        if verbose:
            print(f"  [agent_node] messages 数量: {len(state['messages'])}")
        response = llm_with_tools.invoke(state["messages"])
        if verbose and response.tool_calls:
            print(f"  [agent_node] tool_calls: {[tc['name'] for tc in response.tool_calls]}")
        return {"messages": [response]}

    def should_continue(state: MessagesState) -> Literal["tools", "__end__"]:
        """根据最后一条消息决定走 tools 还是结束。"""
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return "__end__"

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(lc_tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent", should_continue,
        {"tools": "tools", "__end__": END},
    )
    builder.add_edge("tools", "agent")

    checkpointer = InMemorySaver()
    graph = builder.compile(checkpointer=checkpointer)
    return graph


# ============================================================
# 运行接口
# ============================================================

def run_langgraph(question: str, thread_id: str = "lg-default", verbose: bool = False) -> str:
    """
    用 LangGraph StateGraph 回答问题，返回答案字符串。

    参数：
        question: 用户问题
        thread_id: 会话 ID
        verbose: 是否打印节点执行信息

    返回：
        答案文本
    """
    graph = build_graph(verbose=verbose)
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {"messages": [{"role": "user", "content": question}]}

    result = graph.invoke(inputs, config=config)

    # 提取最终回答（最后一条无 tool_calls 的 AI 消息）
    messages = result["messages"]
    answer = ""
    for msg in reversed(messages):
        if hasattr(msg, "content") and msg.content and not getattr(msg, "tool_calls", None):
            # 跳过 ToolMessage
            from langchain_core.messages import AIMessage
            if isinstance(msg, AIMessage):
                answer = msg.content
                break

    return answer


def run_langgraph_full(question: str, thread_id: str = "lg-default", verbose: bool = False) -> dict:
    """
    运行 LangGraph Agent 并返回完整结果（含 messages）。

    返回：
        {
            "answer": str,
            "total_steps": int,
            "thread_id": str,
            "messages": list,
        }
    """
    graph = build_graph(verbose=verbose)
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {"messages": [{"role": "user", "content": question}]}

    result = graph.invoke(inputs, config=config)
    messages = result["messages"]

    from langchain_core.messages import AIMessage
    answer = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content and not getattr(msg, "tool_calls", None):
            answer = msg.content
            break

    ai_messages = [m for m in messages if isinstance(m, AIMessage)]
    total_steps = len(ai_messages)

    return {
        "answer": answer,
        "total_steps": total_steps,
        "thread_id": thread_id,
        "messages": messages,
    }
