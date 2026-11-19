import logging
from langchain_core.messages import HumanMessage, AIMessage
from jarvis.agent.query_context import retrieval_query
from jarvis.agent.state import AgentState
from jarvis.logging_config import format_log_tags
from jarvis.execution_logging import traced_node, action_trace, node_feedback
from jarvis.memory import conversation as conv_mem
from jarvis.memory.web_knowledge import IngestionStats, ingest_web_knowledge

logger = logging.getLogger(__name__)


@traced_node("memory_write")
def memory_write(state: AgentState) -> dict:
    user_id = state["user_id"]
    saved = 0
    stats = IngestionStats()

    try:
        with action_trace("对话落库", 组件="PostgreSQL") as feedback:
            feedback["写入数"] = 0
            for msg in state["messages"]:
                if isinstance(msg, HumanMessage):
                    conv_mem.save_message(user_id, "human", msg.content)
                    saved += 1
                elif isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                    conv_mem.save_message(user_id, "ai", msg.content)
                    saved += 1
                feedback["写入数"] = saved
    except Exception as error:
        node_feedback(状态="降级")
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
        ingest_web_knowledge(
            state["messages"], retrieval_query(state.get("query", ""), user_id),
            user_id, state.get("reflect_llm_override"), stats,
        )
    except Exception as error:
        node_feedback(状态="降级")
        logger.warning(
            "%s Could not store tool results as knowledge",
            format_log_tags(
                ("节点", "memory_write"),
                ("组件", "知识入库"),
                ("状态", "降级"),
                ("错误", type(error).__name__),
            ),
        )

    node_feedback(历史落库数=saved, 知识落库数=stats.stored, 知识跳过数=stats.skipped)
    return {}
