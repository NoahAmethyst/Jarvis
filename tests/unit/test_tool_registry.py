import pytest
from jarvis.tools import registry
from jarvis.tools.registry import (
    _REGISTRY,
    get_tools,
    register_tool,
)


@pytest.fixture(autouse=True)
def preserve_tool_registry():
    original = _REGISTRY.copy()
    _REGISTRY.clear()
    try:
        yield
    finally:
        _REGISTRY.clear()
        _REGISTRY.update(original)


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


def test_tool_with_missing_requirement_is_filtered(monkeypatch):
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)

    @register_tool(
        name="search",
        description="Search",
        required_env_vars=("SEARCH_API_KEY",),
    )
    def search(query: str) -> str:
        return query

    assert get_tools() == []
    assert registry.get_tool_registration("search").missing_env_vars() == (
        "SEARCH_API_KEY",
    )


def test_tool_with_configured_requirement_is_available(monkeypatch):
    monkeypatch.setenv("SEARCH_API_KEY", "configured")

    @register_tool(
        name="search",
        description="Search",
        required_env_vars=("SEARCH_API_KEY",),
    )
    def search(query: str) -> str:
        return query

    assert [tool.name for tool in get_tools()] == ["search"]


def test_excluded_tool_is_filtered(monkeypatch):
    monkeypatch.setenv("SEARCH_API_KEY", "configured")

    @register_tool(
        name="search",
        description="Search",
        required_env_vars=("SEARCH_API_KEY",),
    )
    def search(query: str) -> str:
        return query

    assert get_tools(excluded_names={"search"}) == []
