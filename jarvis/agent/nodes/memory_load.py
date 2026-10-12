import logging
from jarvis.agent.state import AgentState
from jarvis.memory import conversation as conv_mem
from jarvis.logging_config import format_log_tags
from jarvis.execution_logging import traced_node, node_feedback

logger = logging.getLogger(__name__)


@traced_node("memory_load")
def memory_load(state: AgentState) -> dict:
    try:
        history = conv_mem.load_history(state["user_id"])
        return {"history": history}
    except Exception as error:
        node_feedback(状态="降级")
        logger.warning(
            "%s History unavailable",
            format_log_tags(
                ("节点", "memory_load"),
                ("组件", "PostgreSQL"),
                ("状态", "降级"),
                ("错误", type(error).__name__),
            ),
        )
        return {"history": []}
