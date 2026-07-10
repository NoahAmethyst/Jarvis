import re
import logging
from langchain_core.messages import HumanMessage
from jarvis.agents import AgentDefinition
from jarvis.llm import llm

logger = logging.getLogger(__name__)

_SCORE_PROMPT = (
    "Rate how well this user query matches the agent's capability description.\n\n"
    "Query: {query}\n"
    "Agent description: {description}\n\n"
    "Respond with ONLY a decimal number between 0.0 and 1.0."
)


def _score_agent(
    query: str,
    agent: AgentDefinition,
    model_override: str | None,
) -> float:
    prompt = _SCORE_PROMPT.format(query=query, description=agent.description)
    response = llm.chat(
        profile="agent_dispatch",
        messages=[HumanMessage(content=prompt)],
        tools=None,
        override=model_override,
    )
    match = re.search(r"\d+\.?\d*", response.content)
    if not match:
        return 0.0
    return max(0.0, min(1.0, float(match.group())))


def dispatch_agent(
    query: str,
    agents: list[AgentDefinition],
    threshold: float,
    model_override: str | None = None,
) -> tuple[AgentDefinition | None, float]:
    """Return (selected_agent, best_score). selected_agent is None if below threshold or on error."""
    if not agents:
        return None, 0.0
    try:
        scored = []
        for agent in agents:
            try:
                score = _score_agent(query, agent, model_override)
                scored.append((score, agent))
            except Exception as e:
                logger.warning("Failed to score agent %s: %s", agent.name, e)

        if not scored:
            return None, 0.0

        best_score, best_agent = max(scored, key=lambda x: x[0])
        if best_score < threshold:
            logger.debug("Best agent %s score %.2f below threshold %.2f", best_agent.name, best_score, threshold)
            return None, best_score

        logger.info("Dispatching to agent %s (score=%.2f)", best_agent.name, best_score)
        return best_agent, best_score

    except Exception as e:
        logger.warning("Agent dispatch failed, falling back to default: %s", e)
        return None, 0.0
