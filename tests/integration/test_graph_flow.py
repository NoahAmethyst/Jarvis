import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage
from jarvis.agent.state import AgentState


def _make_graph_with_mocks():
    patches = [
        patch("jarvis.agent.nodes.memory_load.conv_mem.load_history", return_value=[]),
        patch("jarvis.agent.nodes.agent_dispatch.load_agents", return_value=[]),
        patch("jarvis.agent.nodes.rag_retrieve.know_mem.retrieve_knowledge", return_value=""),
        patch(
            "jarvis.agent.nodes.plan_and_call.llm.chat",
            side_effect=[
                AIMessage(content="The answer is 42."),
                AIMessage(content="0.9"),
            ],
        ),
        patch("jarvis.agent.nodes.memory_write.conv_mem.save_message"),
        patch("jarvis.agent.nodes.memory_write.know_mem.store_knowledge"),
    ]
    return patches


def test_graph_completes_single_turn():
    patches = _make_graph_with_mocks()
    for p in patches:
        p.start()

    try:
        from jarvis.agent.graph import graph
        initial_state: AgentState = {
            "messages": [HumanMessage(content="What is 6 times 7?")],
            "history": [],
            "user_id": "test_user",
            "query": "What is 6 times 7?",
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
        result = graph.invoke(initial_state)
        assert result["final_answer"] == "The answer is 42."
        assert result["reflection_score"] == pytest.approx(0.9)
    finally:
        for p in patches:
            p.stop()


def test_graph_retries_on_low_score():
    patches = [
        patch("jarvis.agent.nodes.memory_load.conv_mem.load_history", return_value=[]),
        patch("jarvis.agent.nodes.agent_dispatch.load_agents", return_value=[]),
        patch("jarvis.agent.nodes.rag_retrieve.know_mem.retrieve_knowledge", return_value=""),
        patch(
            "jarvis.agent.nodes.plan_and_call.llm.chat",
            side_effect=[
                AIMessage(content="I don't know."),
                AIMessage(content="0.2"),
                AIMessage(content="6 times 7 is 42."),
                AIMessage(content="0.95"),
            ],
        ),
        patch("jarvis.agent.nodes.memory_write.conv_mem.save_message"),
        patch("jarvis.agent.nodes.memory_write.know_mem.store_knowledge"),
    ]
    for p in patches:
        p.start()

    try:
        from jarvis.agent.graph import graph
        initial_state: AgentState = {
            "messages": [HumanMessage(content="What is 6 times 7?")],
            "history": [],
            "user_id": "test_user",
            "query": "What is 6 times 7?",
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
        result = graph.invoke(initial_state)
        assert result["final_answer"] == "6 times 7 is 42."
        assert result["retry_count"] == 2
    finally:
        for p in patches:
            p.stop()
