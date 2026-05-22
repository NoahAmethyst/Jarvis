from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from jarvis.agent.state import AgentState
from jarvis.agent.nodes.memory_load import memory_load
from jarvis.agent.nodes.rag_retrieve import rag_retrieve
from jarvis.agent.nodes.plan_and_call import plan_and_call
from jarvis.agent.nodes.reflect import reflect
from jarvis.agent.nodes.memory_write import memory_write
from jarvis.config import REFLECTION_SCORE_THRESHOLD, REFLECTION_MAX_RETRIES
from langchain_core.messages import AIMessage

import jarvis.tools.search  # noqa: F401 — registers web_search
import jarvis.tools.scraper  # noqa: F401 — registers web_scrape

from jarvis.tools.registry import get_tools


def _route_after_plan(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tool_node"
    return "reflect"


def _route_after_reflect(state: AgentState) -> str:
    if (
        state["reflection_score"] < REFLECTION_SCORE_THRESHOLD
        and state["retry_count"] < REFLECTION_MAX_RETRIES
    ):
        return "plan_and_call"
    return "memory_write"


builder = StateGraph(AgentState)

builder.add_node("memory_load", memory_load)
builder.add_node("rag_retrieve", rag_retrieve)
builder.add_node("plan_and_call", plan_and_call)
builder.add_node("tool_node", ToolNode(get_tools()))
builder.add_node("reflect", reflect)
builder.add_node("memory_write", memory_write)

builder.set_entry_point("memory_load")
builder.add_edge("memory_load", "rag_retrieve")
builder.add_edge("rag_retrieve", "plan_and_call")
builder.add_conditional_edges("plan_and_call", _route_after_plan, {
    "tool_node": "tool_node",
    "reflect": "reflect",
})
builder.add_edge("tool_node", "plan_and_call")
builder.add_conditional_edges("reflect", _route_after_reflect, {
    "plan_and_call": "plan_and_call",
    "memory_write": "memory_write",
})
builder.add_edge("memory_write", END)

graph = builder.compile()
