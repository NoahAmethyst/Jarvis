import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from jarvis.llm.adapters import ADAPTERS
from jarvis.llm.adapters.anthropic import AnthropicAdapter
from jarvis.llm.adapters.deepseek import DeepSeekAdapter, JarvisChatDeepSeek
from jarvis.llm.adapters.openai_compatible import OpenAICompatibleAdapter
from jarvis.llm.config import Capabilities, ProviderSettings, ThinkingSettings
from jarvis.llm.errors import LLMConfigurationError


@tool
def fake_web_search(query: str) -> str:
    """Return a deterministic search result."""
    return f"result for {query}"


def _provider(
    adapter: str,
    *,
    key_env: str = "TEST_API_KEY",
    base_url: str | None = "https://default.example/v1",
    base_url_env: str | None = None,
    tools: bool = True,
    thinking: bool = False,
) -> ProviderSettings:
    return ProviderSettings(
        adapter=adapter,
        api_key_env=key_env,
        base_url=base_url,
        base_url_env=base_url_env,
        capabilities=Capabilities(tools=tools, thinking=thinking),
    )


def _deepseek_model(monkeypatch, http_client=None) -> JarvisChatDeepSeek:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    return JarvisChatDeepSeek(
        model="deepseek-flash",
        api_key="test-key",
        base_url="https://api.deepseek.com",
        max_retries=0,
        http_client=http_client,
        reasoning_effort="high",
        extra_body={"thinking": {"type": "enabled"}},
    )


def _tool_call_response(reasoning_content: str, tool_call_id: str) -> dict:
    return {
        "id": "chatcmpl-tool",
        "object": "chat.completion",
        "created": 1,
        "model": "deepseek-flash",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "reasoning_content": reasoning_content,
                    "tool_calls": [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": "fake_web_search",
                                "arguments": '{"query":"Jarvis"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _final_response(content: str) -> dict:
    return {
        "id": "chatcmpl-final",
        "object": "chat.completion",
        "created": 2,
        "model": "deepseek-flash",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "reasoning_content": "final reasoning",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def test_adapter_registry_is_fixed():
    assert set(ADAPTERS) == {"deepseek", "openai_compatible", "anthropic"}


def test_deepseek_adapter_maps_enabled_thinking(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    provider = _provider(
        "deepseek",
        key_env="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
        thinking=True,
    )

    model = DeepSeekAdapter().create_model(
        provider=provider,
        model_id="deepseek-flash",
        thinking=ThinkingSettings(mode="enabled", effort="high"),
    )

    assert isinstance(model, JarvisChatDeepSeek)
    assert model.max_retries == 0
    assert model.reasoning_effort == "high"
    assert model.extra_body == {"thinking": {"type": "enabled"}}
    assert model.temperature is None
    assert model.top_p is None


def test_deepseek_adapter_maps_disabled_thinking(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    provider = _provider(
        "deepseek",
        key_env="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
        thinking=True,
    )

    model = DeepSeekAdapter().create_model(
        provider=provider,
        model_id="deepseek-flash",
        thinking=ThinkingSettings(mode="disabled"),
        request_timeout=10.0,
    )

    assert model.reasoning_effort is None
    assert model.extra_body == {"thinking": {"type": "disabled"}}
    assert model.request_timeout == 10.0


def test_deepseek_payload_replays_reasoning_content(monkeypatch):
    model = _deepseek_model(monkeypatch)
    assistant = AIMessage(
        content="",
        tool_calls=[{"name": "fake_web_search", "args": {"query": "x"}, "id": "call-1"}],
        additional_kwargs={"reasoning_content": "must replay"},
    )

    payload = model._get_request_payload(
        [
            HumanMessage(content="search"),
            assistant,
            ToolMessage(content="result", tool_call_id="call-1"),
        ]
    )

    assert payload["messages"][1]["reasoning_content"] == "must replay"
    assert payload["messages"][1]["content"] == ""


def test_deepseek_transport_parses_and_replays_reasoning_content(monkeypatch):
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        response = (
            _tool_call_response("must replay", "call-1")
            if len(requests) == 1
            else _final_response("done")
        )
        return httpx.Response(200, json=response)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    model = _deepseek_model(monkeypatch, http_client=http_client)
    bound = model.bind_tools([fake_web_search])

    first = bound.invoke([HumanMessage(content="search")])

    assert first.additional_kwargs["reasoning_content"] == "must replay"
    bound.invoke(
        [
            HumanMessage(content="search"),
            first,
            ToolMessage(content="result", tool_call_id="call-1"),
        ]
    )
    assert requests[1]["messages"][1]["reasoning_content"] == "must replay"
    assert requests[1]["messages"][1]["content"] == ""


def test_openai_compatible_adapter_uses_env_base_url_override(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "test-key")
    monkeypatch.setenv("TEST_BASE_URL", "https://override.example/v1")
    provider = _provider(
        "openai_compatible",
        base_url_env="TEST_BASE_URL",
    )

    with patch("jarvis.llm.adapters.openai_compatible.ChatOpenAI") as model_class:
        model_class.return_value = MagicMock()
        OpenAICompatibleAdapter().create_model(
            provider=provider,
            model_id="model-a",
            thinking=ThinkingSettings(mode="disabled"),
            request_timeout=10.0,
        )

    assert model_class.call_args.kwargs["base_url"] == "https://override.example/v1"
    assert model_class.call_args.kwargs["max_retries"] == 0
    assert model_class.call_args.kwargs["request_timeout"] == 10.0


def test_openai_compatible_adapter_falls_back_to_literal_base_url(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "test-key")
    monkeypatch.setenv("TEST_BASE_URL", "")
    provider = _provider(
        "openai_compatible",
        base_url_env="TEST_BASE_URL",
    )

    with patch("jarvis.llm.adapters.openai_compatible.ChatOpenAI") as model_class:
        model_class.return_value = MagicMock()
        OpenAICompatibleAdapter().create_model(
            provider=provider,
            model_id="model-a",
            thinking=ThinkingSettings(mode="disabled"),
        )

    assert model_class.call_args.kwargs["base_url"] == "https://default.example/v1"


def test_anthropic_adapter_constructs_without_protocol_leak(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = _provider(
        "anthropic",
        key_env="ANTHROPIC_API_KEY",
        base_url=None,
    )

    with patch("jarvis.llm.adapters.anthropic.ChatAnthropic") as model_class:
        model_class.return_value = MagicMock()
        AnthropicAdapter().create_model(
            provider=provider,
            model_id="claude-opus-4-1",
            thinking=ThinkingSettings(mode="disabled"),
            request_timeout=10.0,
        )

    assert model_class.call_args.kwargs == {
        "model_name": "claude-opus-4-1",
        "api_key": "test-key",
        "max_retries": 0,
        "default_request_timeout": 10.0,
    }


def test_selected_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = _provider(
        "anthropic",
        key_env="ANTHROPIC_API_KEY",
        base_url=None,
    )

    with pytest.raises(
        LLMConfigurationError,
        match="selected LLM provider is not configured",
    ):
        AnthropicAdapter().create_model(
            provider=provider,
            model_id="claude-opus-4-1",
            thinking=ThinkingSettings(mode="disabled"),
        )
