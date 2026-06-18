import json
import os
import pytest
import tempfile
from pathlib import Path
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
