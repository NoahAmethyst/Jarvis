import logging
from jarvis.agent.state import AgentState
from jarvis.agents.loader import load_agents
from jarvis.agents.dispatcher import dispatch_agent
from jarvis.config import AGENTS_DIR, AGENT_DISPATCH_THRESHOLD, REFLECT_LLM

logger = logging.getLogger(__name__)


def agent_dispatch(state: AgentState) -> dict:
    try:
        agents = load_agents(AGENTS_DIR)
        if not agents:
            return {"active_agent": None, "agent_dispatch_score": 0.0}

        model_spec = state.get("reflect_llm_override") or REFLECT_LLM
        selected, score = dispatch_agent(
            query=state["query"],
            agents=agents,
            threshold=AGENT_DISPATCH_THRESHOLD,
            model_spec=model_spec,
        )
        return {"active_agent": selected, "agent_dispatch_score": score}
    except Exception as e:
        logger.warning("agent_dispatch node failed, falling back to default: %s", e)
        return {"active_agent": None, "agent_dispatch_score": 0.0}
