import logging
from jarvis.agent.state import AgentState
from jarvis.memory import conversation as conv_mem

logger = logging.getLogger(__name__)


def memory_load(state: AgentState) -> dict:
    try:
        history = conv_mem.load_history(state["user_id"])
        return {"history": history}
    except Exception as e:
        logger.warning("PostgreSQL unavailable, skipping history load: %s", e)
        return {"history": []}
