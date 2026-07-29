import logging
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from jarvis.agent.state import AgentState
from jarvis.config import KNOWLEDGE_MIN_LENGTH
from jarvis.logging_config import format_log_tags
from jarvis.memory import conversation as conv_mem
from jarvis.memory import knowledge as know_mem

logger = logging.getLogger(__name__)


def memory_write(state: AgentState) -> dict:
    user_id = state["user_id"]

    try:
        for msg in state["messages"]:
            if isinstance(msg, HumanMessage):
                conv_mem.save_message(user_id, "human", msg.content)
            elif isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                conv_mem.save_message(user_id, "ai", msg.content)
    except Exception as error:
        logger.warning(
            "%s Could not save conversation history",
            format_log_tags(
                ("节点", "memory_write"),
                ("组件", "PostgreSQL"),
                ("状态", "降级"),
                ("错误", type(error).__name__),
            ),
        )

    try:
        for msg in state["messages"]:
            if isinstance(msg, ToolMessage):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if len(content) > KNOWLEDGE_MIN_LENGTH:
                    know_mem.store_knowledge(content, f"tool:{msg.name}", user_id)
    except Exception as error:
        logger.warning(
            "%s Could not store tool results as knowledge",
            format_log_tags(
                ("节点", "memory_write"),
                ("组件", "Qdrant"),
                ("状态", "降级"),
                ("错误", type(error).__name__),
            ),
        )

    return {}
