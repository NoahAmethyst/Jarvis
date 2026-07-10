import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage
from jarvis.agent.state import AgentState


def _base_state(**overrides) -> AgentState:
    state: AgentState = {
        "messages": [HumanMessage(content="What is 2+2?"), AIMessage(content="2+2 equals 4.")],
        "history": [],
        "user_id": "test_user",
        "query": "What is 2+2?",
        "rag_context": "",
        "reflection_score": 0.0,
        "retry_count": 0,
        "final_answer": "",
        "low_confidence": False,
        "llm_override": None,
        "reflect_llm_override": None,
        "active_agent": None,
        "agent_dispatch_score": 0.0,
    }
    state.update(overrides)
    return state


def test_reflect_high_score_no_retry():
    with patch(
        "jarvis.agent.nodes.reflect.llm.chat",
        return_value=AIMessage(content="0.9"),
    ):
        from jarvis.agent.nodes.reflect import reflect
        result = reflect(_base_state())

    assert result["reflection_score"] == pytest.approx(0.9)
    assert result["final_answer"] == "2+2 equals 4."
    assert result["retry_count"] == 1
    assert result["low_confidence"] is False


def test_reflect_low_score_sets_low_confidence_after_max_retries():
    with patch(
        "jarvis.agent.nodes.reflect.llm.chat",
        return_value=AIMessage(content="0.3"),
    ):
        from jarvis.agent.nodes.reflect import reflect
        result = reflect(_base_state(retry_count=2))

    assert result["low_confidence"] is True
    assert result["retry_count"] == 3


def test_reflect_low_score_below_max_retries_not_low_confidence():
    with patch(
        "jarvis.agent.nodes.reflect.llm.chat",
        return_value=AIMessage(content="0.3"),
    ):
        from jarvis.agent.nodes.reflect import reflect
        result = reflect(_base_state(retry_count=0))

    assert result["low_confidence"] is False
    assert result["retry_count"] == 1


def test_reflect_malformed_score_defaults_to_half():
    with patch(
        "jarvis.agent.nodes.reflect.llm.chat",
        return_value=AIMessage(content="I cannot score this."),
    ):
        from jarvis.agent.nodes.reflect import reflect
        result = reflect(_base_state())

    assert result["reflection_score"] == pytest.approx(0.5)
