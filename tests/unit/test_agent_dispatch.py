import json
import os
import pytest
import tempfile
from pathlib import Path
from langchain_core.messages import AIMessage
from jarvis.agents import AgentDefinition


# ── loader tests ────────────────────────────────────────────────────────────

def test_load_agents_empty_dir():
    from jarvis.agents.loader import load_agents
    with tempfile.TemporaryDirectory() as d:
        result = load_agents(d)
    assert result == []


def test_load_agents_nonexistent_dir():
    from jarvis.agents.loader import load_agents
    result = load_agents("/tmp/does_not_exist_xyz")
    assert result == []


def test_load_agent_json_format(tmp_path):
    from jarvis.agents.loader import load_agents
    agent_dir = tmp_path / "my-agent"
    agent_dir.mkdir()
    (agent_dir / "agent.json").write_text(json.dumps({
        "name": "MyAgent",
        "description": "Handles billing questions",
        "instructions": "You are a billing specialist.",
        "tools": [],
    }))
    result = load_agents(str(tmp_path))
    assert len(result) == 1
    a = result[0]
    assert a.name == "MyAgent"
    assert a.description == "Handles billing questions"
    assert a.instructions == "You are a billing specialist."
    assert "agent.json" in a.source_file


def test_load_agent_yaml_format(tmp_path):
    from jarvis.agents.loader import load_agents
    agent_dir = tmp_path / "yaml-agent"
    agent_dir.mkdir()
    (agent_dir / "agent.yaml").write_text(
        "name: YamlAgent\ndescription: Handles YAML stuff\ninstructions: Be helpful with YAML.\n"
    )
    result = load_agents(str(tmp_path))
    assert len(result) == 1
    a = result[0]
    assert a.name == "YamlAgent"
    assert a.description == "Handles YAML stuff"
    assert a.instructions == "Be helpful with YAML."


def test_load_agent_claude_format(tmp_path):
    from jarvis.agents.loader import load_agents
    agent_dir = tmp_path / "claude-agent"
    agent_dir.mkdir()
    agents_subdir = agent_dir / "agents"
    agents_subdir.mkdir()
    (agent_dir / "SKILL.md").write_text(
        "---\nname: ClaudeAgent\ndescription: A Claude-style agent\n---\n\nYou are a Claude-style mentor.\n"
    )
    (agents_subdir / "openai.yaml").write_text(
        "interface:\n  display_name: Claude Agent\n  short_description: A Claude agent\npolicy:\n  allow_implicit_invocation: true\n"
    )
    result = load_agents(str(tmp_path))
    assert len(result) == 1
    a = result[0]
    assert a.name == "ClaudeAgent"
    assert a.description == "A Claude-style agent"
    assert "You are a Claude-style mentor." in a.instructions


def test_load_agent_claude_format_uses_openai_yaml_metadata_fallback(tmp_path):
    from jarvis.agents.loader import load_agents
    agent_dir = tmp_path / "claude-agent"
    agent_dir.mkdir()
    agents_subdir = agent_dir / "agents"
    agents_subdir.mkdir()
    (agent_dir / "SKILL.md").write_text(
        "---\nversion: 1\n---\n\nYou are a Claude-style mentor.\n"
    )
    (agents_subdir / "openai.yaml").write_text(
        "interface:\n"
        "  display_name: Claude Agent\n"
        "  short_description: A Claude agent\n"
    )

    result = load_agents(str(tmp_path))

    assert len(result) == 1
    a = result[0]
    assert a.name == "Claude Agent"
    assert a.description == "A Claude agent"
    assert "You are a Claude-style mentor." in a.instructions


def test_load_agent_json_takes_priority_over_yaml(tmp_path):
    from jarvis.agents.loader import load_agents
    agent_dir = tmp_path / "both-formats"
    agent_dir.mkdir()
    (agent_dir / "agent.json").write_text(json.dumps({
        "name": "JsonAgent", "description": "from json", "instructions": "json instructions",
    }))
    (agent_dir / "agent.yaml").write_text(
        "name: YamlAgent\ndescription: from yaml\ninstructions: yaml instructions\n"
    )
    result = load_agents(str(tmp_path))
    assert result[0].name == "JsonAgent"


def test_load_agents_skips_malformed_file(tmp_path):
    from jarvis.agents.loader import load_agents
    agent_dir = tmp_path / "bad-agent"
    agent_dir.mkdir()
    (agent_dir / "agent.json").write_text("not valid json {{{{")
    result = load_agents(str(tmp_path))
    assert result == []


def test_load_agents_multiple_agents(tmp_path):
    from jarvis.agents.loader import load_agents
    for i in range(3):
        d = tmp_path / f"agent-{i}"
        d.mkdir()
        (d / "agent.yaml").write_text(
            f"name: Agent{i}\ndescription: desc{i}\ninstructions: instr{i}\n"
        )
    result = load_agents(str(tmp_path))
    assert len(result) == 3
    names = {a.name for a in result}
    assert names == {"Agent0", "Agent1", "Agent2"}


# ── dispatcher tests ─────────────────────────────────────────────────────────

def _make_agent(name="TestAgent", description="Handles test queries", instructions="Be a tester."):
    return AgentDefinition(name=name, description=description, instructions=instructions, source_file="test")


def test_dispatch_no_agents_returns_none():
    from jarvis.agents.dispatcher import dispatch_agent
    agent, score = dispatch_agent(
        "what is 2+2?", [], threshold=0.6, model_override="siliconflow/test"
    )
    assert agent is None
    assert score == 0.0


def test_dispatch_above_threshold_returns_agent():
    from unittest.mock import MagicMock, patch
    from jarvis.agents.dispatcher import dispatch_agent

    agent = _make_agent()
    with patch(
        "jarvis.agents.dispatcher.llm.chat",
        return_value=AIMessage(content="0.9"),
    ):
        result, score = dispatch_agent(
            "test query", [agent], threshold=0.6, model_override="siliconflow/test"
        )

    assert result is agent
    assert score == pytest.approx(0.9)


def test_dispatch_below_threshold_returns_none():
    from unittest.mock import MagicMock, patch
    from jarvis.agents.dispatcher import dispatch_agent

    agent = _make_agent()
    with patch(
        "jarvis.agents.dispatcher.llm.chat",
        return_value=AIMessage(content="0.3"),
    ):
        result, score = dispatch_agent(
            "test query", [agent], threshold=0.6, model_override="siliconflow/test"
        )

    assert result is None
    assert score == pytest.approx(0.3)


def test_dispatch_picks_highest_score():
    from unittest.mock import MagicMock, patch
    from jarvis.agents.dispatcher import dispatch_agent

    agents = [
        _make_agent("A", "Low match agent"),
        _make_agent("B", "High match agent"),
        _make_agent("C", "Medium match agent"),
    ]
    with patch(
        "jarvis.agents.dispatcher.llm.chat",
        side_effect=[
            AIMessage(content="0.4"),
            AIMessage(content="0.85"),
            AIMessage(content="0.6"),
        ],
    ):
        result, score = dispatch_agent(
            "test query", agents, threshold=0.6, model_override="siliconflow/test"
        )

    assert result is not None
    assert result.name == "B"
    assert score == pytest.approx(0.85)


def test_dispatch_llm_failure_returns_none():
    from unittest.mock import MagicMock, patch
    from jarvis.agents.dispatcher import dispatch_agent

    agent = _make_agent()
    with patch(
        "jarvis.agents.dispatcher.llm.chat",
        side_effect=Exception("LLM timeout"),
    ):
        result, score = dispatch_agent(
            "test query", [agent], threshold=0.6, model_override="siliconflow/test"
        )

    assert result is None
    assert score == 0.0


def test_dispatch_malformed_score_excluded():
    from unittest.mock import MagicMock, patch
    from jarvis.agents.dispatcher import dispatch_agent

    agent = _make_agent()
    with patch(
        "jarvis.agents.dispatcher.llm.chat",
        return_value=AIMessage(content="I cannot score this."),
    ):
        result, score = dispatch_agent(
            "test query", [agent], threshold=0.6, model_override="siliconflow/test"
        )

    assert result is None


# ── agent_dispatch node tests ─────────────────────────────────────────────────

def test_agent_dispatch_node_no_agents_sets_none(tmp_path):
    from unittest.mock import patch
    from jarvis.agent.nodes.agent_dispatch import agent_dispatch
    from jarvis.agent.state import AgentState
    from langchain_core.messages import HumanMessage

    state: AgentState = {
        "messages": [HumanMessage(content="hello")],
        "history": [],
        "user_id": "u1",
        "query": "hello",
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

    with patch("jarvis.agent.nodes.agent_dispatch.AGENTS_DIR", str(tmp_path)):
        result = agent_dispatch(state)

    assert result["active_agent"] is None
    assert result["agent_dispatch_score"] == 0.0


def test_agent_dispatch_node_injects_agent(tmp_path):
    from unittest.mock import MagicMock, patch
    from jarvis.agent.nodes.agent_dispatch import agent_dispatch
    from jarvis.agent.state import AgentState
    from langchain_core.messages import HumanMessage

    agent_dir = tmp_path / "billing-agent"
    agent_dir.mkdir()
    (agent_dir / "agent.yaml").write_text(
        "name: BillingAgent\ndescription: Handles billing\ninstructions: Be a billing expert.\n"
    )

    state: AgentState = {
        "messages": [HumanMessage(content="I have a billing question")],
        "history": [],
        "user_id": "u1",
        "query": "I have a billing question",
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

    with patch("jarvis.agent.nodes.agent_dispatch.AGENTS_DIR", str(tmp_path)), \
         patch(
             "jarvis.agents.dispatcher.llm.chat",
             return_value=AIMessage(content="0.9"),
         ):
        result = agent_dispatch(state)

    assert result["active_agent"] is not None
    assert result["active_agent"].name == "BillingAgent"
    assert result["agent_dispatch_score"] == 0.9


def test_plan_and_call_injects_active_agent_instructions():
    from unittest.mock import MagicMock, patch
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    from jarvis.agent.nodes.plan_and_call import plan_and_call
    from jarvis.agent.state import AgentState

    active = AgentDefinition(
        name="BillingAgent",
        description="Handles billing",
        instructions="You are a billing specialist. Always verify invoice numbers.",
        source_file="test",
    )

    state: AgentState = {
        "messages": [HumanMessage(content="billing question")],
        "history": [],
        "user_id": "u1",
        "query": "billing question",
        "rag_context": "",
        "reflection_score": 0.0,
        "retry_count": 0,
        "final_answer": "",
        "low_confidence": False,
        "llm_override": None,
        "reflect_llm_override": None,
        "active_agent": active,
        "agent_dispatch_score": 0.9,
    }

    with patch(
        "jarvis.agent.nodes.plan_and_call.llm.chat",
        return_value=AIMessage(content="Invoice processed."),
    ) as mock_chat:
        plan_and_call(state)

    call_args = mock_chat.call_args.kwargs["messages"]
    system_msg = call_args[0]
    assert isinstance(system_msg, SystemMessage)
    assert "You are a billing specialist." in system_msg.content


def test_plan_and_call_no_active_agent_uses_default_prompt():
    from unittest.mock import MagicMock, patch
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    from jarvis.agent.nodes.plan_and_call import plan_and_call
    from jarvis.agent.state import AgentState

    state: AgentState = {
        "messages": [HumanMessage(content="hello")],
        "history": [],
        "user_id": "u1",
        "query": "hello",
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

    with patch(
        "jarvis.agent.nodes.plan_and_call.llm.chat",
        return_value=AIMessage(content="Hello there."),
    ) as mock_chat:
        plan_and_call(state)

    call_args = mock_chat.call_args.kwargs["messages"]
    system_msg = call_args[0]
    assert isinstance(system_msg, SystemMessage)
    assert "You are Jarvis" in system_msg.content
    assert "billing specialist" not in system_msg.content
