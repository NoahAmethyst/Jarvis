from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from jarvis.agent.state import AgentState
from jarvis.agents import AgentDefinition


ROOT = Path(__file__).resolve().parents[2]


def _state(**overrides) -> AgentState:
    state: AgentState = {
        "messages": [HumanMessage(content="current question")],
        "history": [HumanMessage(content="old question"), AIMessage(content="old answer")],
        "user_id": "u1",
        "query": "current question",
        "rag_context": "retrieved context",
        "reflection_score": 0.0,
        "retry_count": 0,
        "final_answer": "",
        "low_confidence": False,
        "llm_override": "openai/gpt-4o",
        "reflect_llm_override": "claude/claude-opus-4-1",
        "active_agent": None,
        "agent_dispatch_score": 0.0,
    }
    state.update(overrides)
    return state


def _agent(name: str, description: str) -> AgentDefinition:
    return AgentDefinition(
        name=name,
        description=description,
        instructions=f"Act as {name}",
        source_file="test",
    )


def test_plan_and_call_uses_answer_profile():
    from jarvis.agent.nodes import plan_and_call as module

    response = AIMessage(content="answer")
    fake_tools = [MagicMock(name="tool")]
    with patch.object(module.llm, "chat", return_value=response) as chat, patch.object(
        module, "get_tools", return_value=fake_tools
    ):
        result = module.plan_and_call(_state())

    assert result == {"messages": [response]}
    call = chat.call_args.kwargs
    assert call["profile"] == "answer"
    assert call["tools"] == fake_tools
    assert call["override"] == "openai/gpt-4o"
    assert isinstance(call["messages"][0], SystemMessage)
    assert "retrieved context" in call["messages"][0].content
    assert [message.content for message in call["messages"][1:]] == [
        "old question",
        "old answer",
        "current question",
    ]


def test_reflect_uses_reflection_profile():
    from jarvis.agent.nodes import reflect as module

    state = _state(
        messages=[
            HumanMessage(content="current question"),
            AIMessage(content="current answer"),
        ],
        retry_count=0,
    )
    with patch.object(
        module.llm,
        "chat",
        return_value=AIMessage(content="0.9"),
    ) as chat:
        result = module.reflect(state)

    assert result["reflection_score"] == pytest.approx(0.9)
    call = chat.call_args.kwargs
    assert call["profile"] == "reflection"
    assert call["override"] == "claude/claude-opus-4-1"
    assert call["tools"] is None
    assert len(call["messages"]) == 1
    assert isinstance(call["messages"][0], HumanMessage)


def test_dispatch_agent_uses_agent_dispatch_profile_for_each_agent():
    from jarvis.agents import dispatcher as module

    agents = [_agent("A", "low match"), _agent("B", "high match")]
    responses = [AIMessage(content="0.2"), AIMessage(content="0.9")]
    with patch.object(module.llm, "chat", side_effect=responses) as chat:
        selected, score = module.dispatch_agent(
            query="billing help",
            agents=agents,
            threshold=0.6,
            model_override="openai/gpt-4o-mini",
        )

    assert selected is agents[1]
    assert score == pytest.approx(0.9)
    assert chat.call_count == 2
    for call in chat.call_args_list:
        assert call.kwargs["profile"] == "agent_dispatch"
        assert call.kwargs["override"] == "openai/gpt-4o-mini"
        assert call.kwargs["tools"] is None


def test_agent_dispatch_node_forwards_reflection_override():
    from jarvis.agent.nodes import agent_dispatch as module

    agent = _agent("Billing", "billing help")
    with patch.object(module, "load_agents", return_value=[agent]), patch.object(
        module,
        "dispatch_agent",
        return_value=(agent, 0.9),
    ) as dispatch:
        result = module.agent_dispatch(_state())

    assert result == {"active_agent": agent, "agent_dispatch_score": 0.9}
    assert dispatch.call_args.kwargs["model_override"] == "claude/claude-opus-4-1"


@pytest.mark.parametrize(
    "relative_path",
    [
        "jarvis/agent/nodes/plan_and_call.py",
        "jarvis/agent/nodes/reflect.py",
        "jarvis/agent/nodes/agent_dispatch.py",
        "jarvis/agents/dispatcher.py",
    ],
)
def test_production_callers_do_not_import_legacy_router(relative_path):
    source = (ROOT / relative_path).read_text(encoding="utf-8")

    assert "jarvis.llm.router" not in source
    assert "get_model" not in source
