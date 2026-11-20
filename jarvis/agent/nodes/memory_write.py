import logging
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
    question = state.get("query", "")
    final_answer = state.get("final_answer")
    saved = 0
    stats = IngestionStats()

    try:
        with action_trace("对话落库", 组件="PostgreSQL") as feedback:
            feedback["写入数"] = 0
            if question.strip() and isinstance(final_answer, str) and final_answer.strip():
                conv_mem.save_turn(user_id, question, final_answer)
                saved = 2
                feedback["写入数"] = saved
            else:
                feedback.update(状态="跳过", 原因="缺少完整问答")
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
            state["messages"], retrieval_query(question, user_id),
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
