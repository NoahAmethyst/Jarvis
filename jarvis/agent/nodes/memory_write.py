import logging
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from jarvis.agent.state import AgentState
from jarvis.config import KNOWLEDGE_MIN_LENGTH
from jarvis.logging_config import format_log_tags
from jarvis.execution_logging import traced_node, action_trace, node_feedback
from jarvis.memory import conversation as conv_mem
from jarvis.memory import knowledge as know_mem

logger = logging.getLogger(__name__)


@traced_node("memory_write")
def memory_write(state: AgentState) -> dict:
    user_id = state["user_id"]
    saved = 0
    stored = 0
    skipped = 0

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
        for msg in state["messages"]:
            if isinstance(msg, ToolMessage):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                with action_trace("知识长度校验", 工具=msg.name or "unknown") as feedback:
                    eligible = len(content) > KNOWLEDGE_MIN_LENGTH
                    feedback.update(
                        字符数=len(content), 阈值=KNOWLEDGE_MIN_LENGTH,
                        结果="通过" if eligible else "跳过",
                    )
                if eligible:
                    know_mem.store_knowledge(content, f"tool:{msg.name}", user_id)
                    stored += 1
                else:
                    skipped += 1
    except Exception as error:
        node_feedback(状态="降级")
        logger.warning(
            "%s Could not store tool results as knowledge",
            format_log_tags(
                ("节点", "memory_write"),
                ("组件", "Qdrant"),
                ("状态", "降级"),
                ("错误", type(error).__name__),
            ),
        )

    node_feedback(历史落库数=saved, 知识落库数=stored, 知识跳过数=skipped)
    return {}
