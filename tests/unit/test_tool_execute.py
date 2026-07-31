import importlib
import logging

import pytest
from langchain_core.messages import AIMessage

from jarvis.tools.errors import ToolUnavailableError
from jarvis.tools.registry import _REGISTRY, register_tool


@pytest.fixture(autouse=True)
def preserve_tool_registry():
    original = _REGISTRY.copy()
    _REGISTRY.clear()
    try:
        yield
    finally:
        _REGISTRY.clear()
        _REGISTRY.update(original)


def _execute_tools(state):
    module = importlib.import_module(
        "jarvis.agent.nodes.tool_execute"
    )
    return module.execute_tools(state)


def _tool_call_state(name: str, args: dict) -> dict:
    return {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": name,
                        "args": args,
                        "id": "call-1",
                    }
                ],
            )
        ],
        "unavailable_tools": [],
    }


def test_tool_outage_returns_message_and_disables_tool(caplog):
    @register_tool(name="search", description="Search")
    def search(query: str) -> str:
        raise ToolUnavailableError("search", "timeout")

    with caplog.at_level(
        logging.WARNING,
        logger="jarvis.agent.nodes.tool_execute",
    ):
        result = _execute_tools(
            _tool_call_state("search", {"query": "x"})
        )

    assert result["unavailable_tools"] == ["search"]
    assert result["messages"][0].tool_call_id == "call-1"
    assert result["messages"][0].name == "search"
    assert "Do not retry" in result["messages"][0].content
    assert (
        "【节点:tool_node】【工具:search】【状态:降级】"
        "【类别:timeout】 Tool unavailable"
    ) in caplog.text


def test_unexpected_tool_bug_logs_and_propagates(caplog):
    @register_tool(name="broken", description="Broken")
    def broken(value: str) -> str:
        raise ValueError("programming bug")

    with caplog.at_level(logging.ERROR, logger="jarvis.agent.nodes.tool_execute"):
        with pytest.raises(ValueError, match="programming bug"):
            _execute_tools(
                _tool_call_state("broken", {"value": "x"})
            )

    assert (
        "【节点:tool_node】【工具:broken】【状态:失败】"
        "【错误:ValueError】 Tool execution failed"
    ) in caplog.text
    assert "programming bug" not in caplog.text


def test_successful_and_unavailable_tools_return_independent_results():
    @register_tool(name="available", description="Available")
    def available(value: str) -> str:
        return f"result:{value}"

    @register_tool(name="unavailable", description="Unavailable")
    def unavailable(value: str) -> str:
        raise ToolUnavailableError("unavailable", "provider")

    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "available",
                        "args": {"value": "ok"},
                        "id": "call-1",
                    },
                    {
                        "name": "unavailable",
                        "args": {"value": "x"},
                        "id": "call-2",
                    },
                ],
            )
        ],
        "unavailable_tools": [],
    }

    result = _execute_tools(state)

    assert [message.name for message in result["messages"]] == [
        "available",
        "unavailable",
    ]
    assert result["messages"][0].content == "result:ok"
    assert "Do not retry" in result["messages"][1].content
    assert result["unavailable_tools"] == ["unavailable"]


def test_missing_tool_requirement_skips_invocation(monkeypatch):
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)
    calls = []

    @register_tool(
        name="search",
        description="Search",
        required_env_vars=("SEARCH_API_KEY",),
    )
    def search(query: str) -> str:
        calls.append(query)
        return query

    result = _execute_tools(
        _tool_call_state("search", {"query": "x"})
    )

    assert calls == []
    assert result["unavailable_tools"] == ["search"]
    assert "Do not retry" in result["messages"][0].content
