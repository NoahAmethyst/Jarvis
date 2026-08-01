import logging

from langchain_core.messages import SystemMessage
from jarvis.agent.state import AgentState
from jarvis.llm import llm
from jarvis.logging_config import format_log_tags
from jarvis.tools.registry import get_tools


logger = logging.getLogger(__name__)


def plan_and_call(state: AgentState) -> dict:
    try:
        system_content = "You are Jarvis, a helpful AI assistant. Answer questions accurately and completely."
        if state.get("rag_context"):
            system_content += f"\n\nRelevant knowledge from memory:\n{state['rag_context']}"
        if state.get("active_agent"):
            system_content += f"\n\n{state['active_agent'].instructions}"

        all_messages = [SystemMessage(content=system_content)] + state["history"] + state["messages"]
        tools = (
            get_tools(excluded_names=state.get("unavailable_tools", []))
            if state.get("tools_enabled", True)
            else []
        )
        response = llm.chat(
            profile="answer",
            messages=all_messages,
            tools=tools,
            override=state.get("llm_override"),
        )
        return {"messages": [response]}
    except Exception as error:
        logger.error(
            "%s Answer node failed",
            format_log_tags(
                ("节点", "plan_and_call"),
                ("状态", "失败"),
                ("错误", type(error).__name__),
            ),
        )
        raise
