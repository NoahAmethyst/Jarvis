import pytest
from jarvis.tools.registry import register_tool, get_tools, _REGISTRY


def setup_function():
    _REGISTRY.clear()


def test_register_tool_adds_to_registry():
    @register_tool(name="my_tool", description="A test tool")
    def my_tool(query: str) -> str:
        return f"result: {query}"

    tools = get_tools()
    names = [t.name for t in tools]
    assert "my_tool" in names


def test_get_tools_returns_callable_tools():
    @register_tool(name="echo_tool", description="Echoes input")
    def echo_tool(text: str) -> str:
        return text

    tools = get_tools()
    echo = next(t for t in tools if t.name == "echo_tool")
    assert echo.invoke({"text": "hello"}) == "hello"


def test_register_tool_preserves_original_function():
    @register_tool(name="passthrough", description="Passthrough")
    def passthrough(x: str) -> str:
        return x

    assert passthrough("test") == "test"


def test_multiple_tools_registered():
    @register_tool(name="tool_a", description="A")
    def tool_a(x: str) -> str:
        return x

    @register_tool(name="tool_b", description="B")
    def tool_b(x: str) -> str:
        return x

    assert len(get_tools()) == 2
