"""
agent_v2_stategraph.py —— 手动 StateGraph + ToolNode（~35 行核心逻辑）
========================================================================

用 LangGraph 手动构建 ReAct 图：
- 两个节点：agent_node（调 LLM）+ tools（ToolNode 自动执行所有 tool_calls）
- 一条条件边：有 tool_calls → tools，否则 → END
- MessagesState：内置 add_messages reducer，自动合并消息
- InMemorySaver：每步快照，支持同一 thread 的多轮对话

和 v1 的核心区别：
- 不需要手写 for 循环——图的条件边自动控制循环/终止
- 不需要手写 messages.append——add_messages reducer 自动处理
- 不需要手写 execute_tool——ToolNode 自动解析并执行所有 tool_calls
- 状态持久化内置，同一 thread_id 可跨 invoke 连续对话

和 v3 的核心区别：
- v2 能看到图结构（节点/边），学习价值更高
- v3 是 5 行的 prebuilt，结构完全隐藏
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
                                         ↘ END（无 tool_calls）

    参数：
        verbose: 是否在节点执行时打印调试信息

    返回：
        CompiledStateGraph（带 InMemorySaver）
    """
    # 1. 初始化 LLM（读取环境变量，兼容自定义端点）
    llm = ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
        temperature=0,
    )

    # bind_tools：告诉 LLM 可以调用哪些工具（注入 tool schemas 到请求）
    llm_with_tools = llm.bind_tools(lc_tools)

    # 2. 定义节点函数
    def agent_node(state: MessagesState) -> dict:
        """调用 LLM，返回 AI 消息（可能包含 tool_calls）。"""
        if verbose:
            print(f"  [agent_node] messages 数量: {len(state['messages'])}")
        response = llm_with_tools.invoke(state["messages"])
        if verbose and response.tool_calls:
            print(f"  [agent_node] tool_calls: {[tc['name'] for tc in response.tool_calls]}")
        return {"messages": [response]}

    # 3. 定义条件路由函数
    def should_continue(state: MessagesState) -> Literal["tools", "__end__"]:
        """根据最后一条消息决定走 tools 节点还是结束。"""
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return "__end__"

    # 4. 构建图
    builder = StateGraph(MessagesState)

    # 添加节点
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(lc_tools))  # ToolNode 自动执行所有 tool_calls

    # 连接边
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "__end__": END},
    )
    builder.add_edge("tools", "agent")  # 工具执行后回到 agent 节点

    # 5. 编译（必须有 checkpointer 才能支持多轮对话）
    checkpointer = InMemorySaver()
    graph = builder.compile(checkpointer=checkpointer)

    return graph


# ============================================================
# 运行接口
# ============================================================

def run_v2(question: str, thread_id: str = "v2-default", verbose: bool = True) -> dict:
    """
    用 v2（手动 StateGraph）回答问题。

    参数：
        question: 用户问题
        thread_id: 会话 ID（同一 thread_id 可多轮对话，利用 checkpointer）
        verbose: 是否打印节点执行信息

    返回：
        {
            "answer": str,
            "total_steps": int,  # 调用 LLM 的次数（agent_node 执行次数）
            "thread_id": str,
        }
    """
    graph = build_graph(verbose=verbose)
    config = {"configurable": {"thread_id": thread_id}}

    inputs = {"messages": [{"role": "user", "content": question}]}

    if verbose:
        print(f"\n  [v2 StateGraph] thread_id={thread_id}")

    result = graph.invoke(inputs, config=config)

    # 提取最终回答（最后一条 AI 消息的文本内容）
    messages = result["messages"]
    answer = ""
    for msg in reversed(messages):
        if hasattr(msg, "content") and msg.content and not getattr(msg, "tool_calls", None):
            answer = msg.content
            break

    # 统计步数：AI 消息数量（每次 agent_node 执行产生一条 AI 消息）
    from langchain_core.messages import AIMessage
    ai_messages = [m for m in messages if isinstance(m, AIMessage)]
    # 排除包含 tool_calls 的（中间步），统计总的 agent_node 执行次数
    total_steps = len(ai_messages)

    return {
        "answer": answer,
        "total_steps": total_steps,
        "thread_id": thread_id,
        "messages": messages,  # 完整消息历史，供 display 使用
    }


def get_graph_for_display(verbose: bool = False):
    """返回图对象，供 main.py 展示 Mermaid 图。"""
    return build_graph(verbose=verbose)
