import logging
from jarvis.agent.query_context import is_standalone_greeting, retrieval_query
from jarvis.agent.state import AgentState
from jarvis.memory import knowledge as know_mem
from jarvis.logging_config import format_log_tags
from jarvis.execution_logging import traced_node, node_feedback

logger = logging.getLogger(__name__)


@traced_node("rag_retrieve")
def rag_retrieve(state: AgentState) -> dict:
    query = retrieval_query(state["query"], state["user_id"])
    if not query or is_standalone_greeting(query):
        node_feedback(状态="跳过", 原因="简单问候" if query else "空查询")
        return {"rag_context": ""}
    try:
        context = know_mem.retrieve_knowledge(query, state["user_id"])
        return {"rag_context": context}
    except Exception as error:
        node_feedback(状态="降级")
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
