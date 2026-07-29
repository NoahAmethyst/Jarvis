import logging
from jarvis.agent.state import AgentState
from jarvis.memory import knowledge as know_mem
from jarvis.logging_config import format_log_tags

logger = logging.getLogger(__name__)


def rag_retrieve(state: AgentState) -> dict:
    try:
        context = know_mem.retrieve_knowledge(state["query"], state["user_id"])
        return {"rag_context": context}
    except Exception as error:
        logger.warning(
            "%s Retrieval unavailable",
            format_log_tags(
                ("节点", "rag_retrieve"),
                ("组件", "Qdrant"),
                ("状态", "降级"),
                ("错误", type(error).__name__),
            ),
        )
        return {"rag_context": ""}
