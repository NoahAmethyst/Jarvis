import re
import logging
from langchain_core.messages import HumanMessage, AIMessage
from jarvis.agent.state import AgentState
from jarvis.config import REFLECTION_SCORE_THRESHOLD, REFLECTION_MAX_RETRIES
from jarvis.llm import llm
from jarvis.logging_config import format_log_tags

logger = logging.getLogger(__name__)


def _extract_last_ai_answer(state: AgentState) -> str:
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            return msg.content
    return ""


def reflect(state: AgentState) -> dict:
    answer = _extract_last_ai_answer(state)

    prompt = (
        f"Rate this answer from 0.0 to 1.0 based on accuracy, completeness, "
        f"and whether it directly answers the question.\n\n"
        f"Question: {state['query']}\n"
        f"Answer: {answer}\n\n"
        f"Respond with ONLY a decimal number between 0.0 and 1.0."
    )
    response = llm.chat(
        profile="reflection",
        messages=[HumanMessage(content=prompt)],
        tools=None,
        override=state.get("reflect_llm_override"),
    )

    match = re.search(r"\d+\.?\d*", response.content)
    try:
        if match is None:
            raise ValueError("reflection score is missing")
        score = float(match.group())
        score = max(0.0, min(1.0, score))
    except (AttributeError, ValueError):
        score = 0.5
        logger.warning(
            "%s Could not parse reflection score",
            format_log_tags(
                ("节点", "reflect"),
                ("状态", "解析失败"),
                ("默认评分", "0.50"),
            ),
        )

    retry_count = state["retry_count"] + 1
    low_confidence = retry_count >= REFLECTION_MAX_RETRIES and score < REFLECTION_SCORE_THRESHOLD
    if score < REFLECTION_SCORE_THRESHOLD:
        status = "低置信度" if low_confidence else "重试"
        event = (
            "Reflection remained below threshold"
            if low_confidence
            else "Reflection requested another answer"
        )
        logger.info(
            "%s %s",
            format_log_tags(
                ("节点", "reflect"),
                ("评分", f"{score:.2f}"),
                ("重试", f"{retry_count}/{REFLECTION_MAX_RETRIES}"),
                ("状态", status),
            ),
            event,
        )

    return {
        "reflection_score": score,
        "retry_count": retry_count,
        "final_answer": answer,
        "low_confidence": low_confidence,
    }
