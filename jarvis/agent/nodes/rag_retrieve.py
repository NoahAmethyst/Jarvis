import logging
from jarvis.agent.state import AgentState
from jarvis.memory import knowledge as know_mem

logger = logging.getLogger(__name__)


def rag_retrieve(state: AgentState) -> dict:
    try:
        context = know_mem.retrieve_knowledge(state["query"], state["user_id"])
        return {"rag_context": context}
    except Exception as e:
        logger.warning("Qdrant unavailable, skipping RAG retrieval: %s", e)
        return {"rag_context": ""}
