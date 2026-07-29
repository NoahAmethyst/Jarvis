import re
import logging
from langchain_core.messages import HumanMessage
from jarvis.agents import AgentDefinition
from jarvis.llm import llm
from jarvis.logging_config import format_log_tags

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
        logger.info(
            "%s No Agents configured",
            format_log_tags(("节点", "agent_dispatch"), ("状态", "跳过")),
        )
        return None, 0.0
    try:
        scored = []
        for agent in agents:
            try:
                score = _score_agent(query, agent, model_override)
                scored.append((score, agent))
            except Exception as error:
                logger.warning(
                    "%s Could not score Agent",
                    format_log_tags(
                        ("节点", "agent_dispatch"),
                        ("Agent", agent.name),
                        ("状态", "评分失败"),
                        ("错误", type(error).__name__),
                    ),
                )

        if not scored:
            logger.warning(
                "%s No Agent scores available, using default behavior",
                format_log_tags(
                    ("节点", "agent_dispatch"),
                    ("状态", "降级"),
                ),
            )
            return None, 0.0

        best_score, best_agent = max(scored, key=lambda x: x[0])
        if best_score < threshold:
            logger.info(
                "%s Best Agent is below threshold",
                format_log_tags(
                    ("节点", "agent_dispatch"),
                    ("Agent", best_agent.name),
                    ("评分", f"{best_score:.2f}"),
                    ("阈值", f"{threshold:.2f}"),
                    ("状态", "跳过"),
                ),
            )
            return None, best_score

        logger.info(
            "%s Agent selected",
            format_log_tags(
                ("节点", "agent_dispatch"),
                ("Agent", best_agent.name),
                ("评分", f"{best_score:.2f}"),
            ),
        )
        return best_agent, best_score

    except Exception as error:
        logger.warning(
            "%s Agent dispatch failed, using default behavior",
            format_log_tags(
                ("节点", "agent_dispatch"),
                ("状态", "降级"),
                ("错误", type(error).__name__),
            ),
        )
        return None, 0.0
