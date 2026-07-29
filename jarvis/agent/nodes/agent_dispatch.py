import logging
from jarvis.agent.state import AgentState
from jarvis.agents.loader import load_agents
from jarvis.agents.dispatcher import dispatch_agent
from jarvis.config import AGENTS_DIR, AGENT_DISPATCH_THRESHOLD
from jarvis.logging_config import format_log_tags

logger = logging.getLogger(__name__)


def agent_dispatch(state: AgentState) -> dict:
    try:
        agents = load_agents(AGENTS_DIR)
        if not agents:
            return {"active_agent": None, "agent_dispatch_score": 0.0}

        selected, score = dispatch_agent(
            query=state["query"],
            agents=agents,
            threshold=AGENT_DISPATCH_THRESHOLD,
            model_override=state.get("reflect_llm_override"),
        )
        return {"active_agent": selected, "agent_dispatch_score": score}
    except Exception as error:
        logger.warning(
            "%s Agent dispatch node failed, using default behavior",
            format_log_tags(
                ("节点", "agent_dispatch"),
                ("状态", "降级"),
                ("错误", type(error).__name__),
            ),
        )
        return {"active_agent": None, "agent_dispatch_score": 0.0}
