from langchain_core.messages import SystemMessage
from jarvis.agent.state import AgentState
from jarvis.config import ANSWER_LLM
from jarvis.llm.router import get_model
from jarvis.tools.registry import get_tools


def plan_and_call(state: AgentState) -> dict:
    model_spec = state.get("llm_override") or ANSWER_LLM
    llm = get_model(model_spec).bind_tools(get_tools())

    system_content = "You are Jarvis, a helpful AI assistant. Answer questions accurately and completely."
    if state.get("rag_context"):
        system_content += f"\n\nRelevant knowledge from memory:\n{state['rag_context']}"
    if state.get("active_agent"):
        system_content += f"\n\n{state['active_agent'].instructions}"

    all_messages = [SystemMessage(content=system_content)] + state["history"] + state["messages"]
    response = llm.invoke(all_messages)
    return {"messages": [response]}
