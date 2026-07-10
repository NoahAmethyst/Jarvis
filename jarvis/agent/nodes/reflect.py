import re
import logging
from langchain_core.messages import HumanMessage, AIMessage
from jarvis.agent.state import AgentState
from jarvis.config import REFLECTION_SCORE_THRESHOLD, REFLECTION_MAX_RETRIES
from jarvis.llm import llm

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

    try:
        match = re.search(r"\d+\.?\d*", response.content)
        score = float(match.group()) if match else 0.5
        score = max(0.0, min(1.0, score))
    except (AttributeError, ValueError):
        score = 0.5
        logger.warning("Could not parse reflection score from: %s", response.content)

    retry_count = state["retry_count"] + 1
    low_confidence = retry_count >= REFLECTION_MAX_RETRIES and score < REFLECTION_SCORE_THRESHOLD

    return {
        "reflection_score": score,
        "retry_count": retry_count,
        "final_answer": answer,
        "low_confidence": low_confidence,
    }
