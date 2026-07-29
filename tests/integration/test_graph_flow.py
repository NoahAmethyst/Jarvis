import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage
from jarvis.agent.state import AgentState
from jarvis.tools.errors import ToolUnavailableError
from jarvis.tools.registry import (
    _REGISTRY,
    get_tool_registration,
    register_tool,
)


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


def test_graph_falls_back_after_tool_credential_failure(
    monkeypatch,
):
    monkeypatch.setenv("TAVILY_API_KEY", "configured")
    from jarvis.agent.graph import graph

    original = get_tool_registration("web_search")
    answer_tool_names = []

    @register_tool(
        name="web_search",
        description="Search",
        required_env_vars=("TAVILY_API_KEY",),
    )
    def failing_search(query: str) -> str:
        raise ToolUnavailableError("web_search", "credential")

    def fake_chat(profile, messages, tools, override=None):
        if profile == "reflection":
            return AIMessage(content="0.9")
        answer_tool_names.append([tool.name for tool in tools])
        if len(answer_tool_names) == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "web_search",
                        "args": {"query": "current information"},
                        "id": "call-1",
                    }
                ],
            )
        return AIMessage(
            content=(
                "I cannot search right now, but here is what I know."
            )
        )

    patches = [
        patch(
            "jarvis.agent.nodes.memory_load.conv_mem.load_history",
            return_value=[],
        ),
        patch(
            "jarvis.agent.nodes.agent_dispatch.load_agents",
            return_value=[],
        ),
        patch(
            "jarvis.agent.nodes.rag_retrieve.know_mem.retrieve_knowledge",
            return_value="",
        ),
        patch(
            "jarvis.agent.nodes.plan_and_call.llm.chat",
            side_effect=fake_chat,
        ),
        patch(
            "jarvis.tools.search.requests.post",
            side_effect=ToolUnavailableError(
                "web_search",
                "credential",
            ),
        ),
        patch(
            "jarvis.agent.nodes.memory_write.conv_mem.save_message"
        ),
        patch(
            "jarvis.agent.nodes.memory_write.know_mem.store_knowledge"
        ),
    ]
    for item in patches:
        item.start()

    try:
        initial_state: AgentState = {
            "messages": [HumanMessage(content="What happened today?")],
            "history": [],
            "user_id": "test_user",
            "query": "What happened today?",
            "rag_context": "",
            "reflection_score": 0.0,
            "retry_count": 0,
            "final_answer": "",
            "low_confidence": False,
            "llm_override": None,
            "reflect_llm_override": None,
            "active_agent": None,
            "agent_dispatch_score": 0.0,
            "unavailable_tools": [],
        }
        result = graph.invoke(initial_state)
    finally:
        for item in patches:
            item.stop()
        if original is None:
            _REGISTRY.pop("web_search", None)
        else:
            _REGISTRY["web_search"] = original

    assert "web_search" in answer_tool_names[0]
    assert "web_search" not in answer_tool_names[1]
    assert result["final_answer"] == (
        "I cannot search right now, but here is what I know."
    )
