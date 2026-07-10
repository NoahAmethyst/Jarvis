import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from jarvis.llm.config import LLMSettings, load_llm_config
from jarvis.llm.errors import (
    LLMConfigurationError,
    LLMContextLimitError,
    LLMInvalidRequestError,
    LLMInvalidResponseError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from jarvis.llm.gateway import LLMGateway


ROOT = Path(__file__).resolve().parents[2]


@tool
def fake_tool(query: str) -> str:
    """Return a deterministic result."""
    return query


@dataclass
class AdapterCall:
    model_id: str
    thinking_mode: str
    thinking_effort: str | None


class FakeAdapter:
    def __init__(self, responses=None):
        self.calls: list[AdapterCall] = []
        self.model = MagicMock()
        self.model.bind_tools.return_value = self.model
        self.model.invoke.side_effect = responses

    def create_model(self, provider, model_id, thinking):
        self.calls.append(
            AdapterCall(
                model_id=model_id,
                thinking_mode=thinking.mode,
                thinking_effort=thinking.effort,
            )
        )
        return self.model


@pytest.fixture
def settings() -> LLMSettings:
    return load_llm_config(ROOT / "llm.yaml").model_copy(deep=True)


@pytest.fixture
def fake_adapters():
    deepseek = FakeAdapter([AIMessage(content="deepseek answer")])
    openai_adapter = FakeAdapter([AIMessage(content="openai answer")])
    anthropic = FakeAdapter([AIMessage(content="claude answer")])
    return SimpleNamespace(
        deepseek=deepseek,
        openai=openai_adapter,
        anthropic=anthropic,
        registry={
            "deepseek": deepseek,
            "openai_compatible": openai_adapter,
            "anthropic": anthropic,
        },
    )


def _gateway(settings, fake_adapters, sleep=None):
    return LLMGateway(
        settings=settings,
        adapters=fake_adapters.registry,
        sleep=sleep or (lambda _: None),
    )


def _tool_ai(tool_id: str = "call-1", *, reasoning: str | None = "reasoning"):
    additional_kwargs = {}
    if reasoning is not None:
        additional_kwargs["reasoning_content"] = reasoning
    return AIMessage(
        content="",
        tool_calls=[{"name": "fake_tool", "args": {"query": "x"}, "id": tool_id}],
        additional_kwargs=additional_kwargs,
    )


def test_answer_profile_uses_deepseek_v4_pro(settings, fake_adapters):
    gateway = _gateway(settings, fake_adapters)

    response = gateway.chat(
        profile="answer",
        messages=[HumanMessage(content="hello")],
        tools=[fake_tool],
    )

    assert response.content == "deepseek answer"
    call = fake_adapters.deepseek.calls[0]
    assert call.model_id == "deepseek-v4-pro"
    assert call.thinking_mode == "enabled"
    assert call.thinking_effort == "high"
    fake_adapters.deepseek.model.bind_tools.assert_called_once_with([fake_tool])


def test_reflection_profile_does_not_bind_tools(settings, fake_adapters):
    gateway = _gateway(settings, fake_adapters)

    gateway.chat(
        profile="reflection",
        messages=[HumanMessage(content="score")],
    )

    call = fake_adapters.deepseek.calls[0]
    assert call.model_id == "deepseek-v4-flash"
    assert call.thinking_mode == "disabled"
    fake_adapters.deepseek.model.bind_tools.assert_not_called()


def test_non_thinking_answer_override_falls_back_explicitly(settings, fake_adapters):
    gateway = _gateway(settings, fake_adapters)

    response = gateway.chat(
        profile="answer",
        messages=[HumanMessage(content="hello")],
        tools=[fake_tool],
        override="openai/gpt-4o",
    )

    assert response.content == "openai answer"
    call = fake_adapters.openai.calls[0]
    assert call.model_id == "gpt-4o"
    assert call.thinking_mode == "disabled"
    assert call.thinking_effort is None


def test_default_model_cannot_fall_back_from_required_thinking(settings, fake_adapters):
    settings.providers["deepseek"].capabilities.thinking = False
    gateway = _gateway(settings, fake_adapters)

    with pytest.raises(LLMInvalidRequestError, match="thinking capability"):
        gateway.chat(
            profile="answer",
            messages=[HumanMessage(content="hello")],
            tools=[fake_tool],
        )


def test_answer_override_without_tools_is_rejected(settings, fake_adapters):
    settings.providers["openai"].capabilities.tools = False
    gateway = _gateway(settings, fake_adapters)

    with pytest.raises(LLMInvalidRequestError, match="tool capability"):
        gateway.chat(
            profile="answer",
            messages=[HumanMessage(content="hello")],
            tools=[fake_tool],
            override="openai/gpt-4o",
        )

    assert not fake_adapters.openai.calls


def test_unknown_profile_is_rejected(settings, fake_adapters):
    gateway = _gateway(settings, fake_adapters)

    with pytest.raises(LLMInvalidRequestError, match="unknown LLM profile"):
        gateway.chat("missing", [HumanMessage(content="hello")])


def test_unknown_override_provider_is_rejected(settings, fake_adapters):
    gateway = _gateway(settings, fake_adapters)

    with pytest.raises(LLMInvalidRequestError, match="unknown LLM provider"):
        gateway.chat(
            "answer",
            [HumanMessage(content="hello")],
            tools=[fake_tool],
            override="missing/model",
        )


@pytest.mark.parametrize(
    "messages",
    [
        [HumanMessage(content="hi"), ToolMessage(content="x", tool_call_id="orphan")],
        [
            HumanMessage(content="hi"),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "a", "args": {}, "id": "same"},
                    {"name": "b", "args": {}, "id": "same"},
                ],
                additional_kwargs={"reasoning_content": "r"},
            ),
            ToolMessage(content="x", tool_call_id="same"),
        ],
        [HumanMessage(content="hi"), _tool_ai("missing")],
        [
            HumanMessage(content="hi"),
            _tool_ai("expected"),
            ToolMessage(content="x", tool_call_id="different"),
        ],
    ],
    ids=["orphan", "duplicate", "missing-result", "mismatched-result"],
)
def test_invalid_tool_sequences_are_rejected_before_invoke(
    messages, settings, fake_adapters
):
    gateway = _gateway(settings, fake_adapters)

    with pytest.raises(LLMInvalidRequestError, match="invalid tool message sequence"):
        gateway.chat("answer", messages, tools=[fake_tool])

    assert fake_adapters.deepseek.model.invoke.call_count == 0


def test_siliconflow_limit_drops_oldest_complete_groups(settings, fake_adapters):
    gateway = _gateway(settings, fake_adapters)
    messages = [SystemMessage(content="system")]
    for index in range(4):
        messages.extend(
            [
                HumanMessage(content=f"old-user-{index}"),
                AIMessage(content=f"old-ai-{index}"),
            ]
        )
    messages.extend(
        [
            HumanMessage(content="current-user"),
            _tool_ai("call-current", reasoning=None),
            ToolMessage(content="current-result", tool_call_id="call-current"),
        ]
    )

    gateway.chat(
        "answer",
        messages,
        tools=[fake_tool],
        override="siliconflow/model",
    )

    sent = fake_adapters.openai.model.invoke.call_args.args[0]
    assert len(sent) == 10
    contents = [message.content for message in sent]
    assert "system" in contents
    assert "old-user-0" not in contents
    assert "old-ai-0" not in contents
    assert "old-user-1" in contents
    assert contents[-3:] == ["current-user", "", "current-result"]


def test_mandatory_group_over_provider_limit_is_rejected(settings, fake_adapters):
    gateway = _gateway(settings, fake_adapters)
    tool_calls = [
        {"name": "fake_tool", "args": {"query": str(index)}, "id": f"call-{index}"}
        for index in range(8)
    ]
    messages = [
        SystemMessage(content="system"),
        HumanMessage(content="current-user"),
        AIMessage(content="", tool_calls=tool_calls),
        *[
            ToolMessage(content=str(index), tool_call_id=f"call-{index}")
            for index in range(8)
        ],
    ]

    with pytest.raises(LLMContextLimitError, match="LLM context limit exceeded"):
        gateway.chat(
            "answer",
            messages,
            tools=[fake_tool],
            override="siliconflow/model",
        )


def test_deepseek_input_tool_call_requires_reasoning(settings, fake_adapters):
    gateway = _gateway(settings, fake_adapters)
    messages = [
        HumanMessage(content="current-user"),
        _tool_ai(reasoning=None),
        ToolMessage(content="result", tool_call_id="call-1"),
    ]

    with pytest.raises(LLMInvalidRequestError, match="missing reasoning content"):
        gateway.chat("answer", messages, tools=[fake_tool])


def test_deepseek_tool_response_requires_reasoning(settings, fake_adapters):
    fake_adapters.deepseek.model.invoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[{"name": "fake_tool", "args": {}, "id": "call-1"}],
        )
    ]
    gateway = _gateway(settings, fake_adapters)

    with pytest.raises(LLMInvalidResponseError, match="invalid response"):
        gateway.chat(
            "answer",
            [HumanMessage(content="hello")],
            tools=[fake_tool],
        )

    assert fake_adapters.deepseek.model.invoke.call_count == 1


def test_transient_error_retries_up_to_profile_limit(settings, fake_adapters):
    fake_adapters.deepseek.model.invoke.side_effect = [
        LLMTimeoutError("LLM request timed out"),
        AIMessage(content="recovered"),
    ]
    sleeps = []
    gateway = _gateway(settings, fake_adapters, sleep=sleeps.append)

    response = gateway.chat(
        "answer",
        [HumanMessage(content="hello")],
        tools=[fake_tool],
    )

    assert response.content == "recovered"
    assert fake_adapters.deepseek.model.invoke.call_count == 2
    assert sleeps == [0.25]


def test_invalid_response_is_not_retried(settings, fake_adapters):
    fake_adapters.deepseek.model.invoke.side_effect = ["not an AIMessage"]
    gateway = _gateway(settings, fake_adapters)

    with pytest.raises(LLMInvalidResponseError, match="invalid response"):
        gateway.chat(
            "answer",
            [HumanMessage(content="hello")],
            tools=[fake_tool],
        )

    assert fake_adapters.deepseek.model.invoke.call_count == 1


def test_raw_timeout_is_normalized_and_redacted(settings, fake_adapters):
    request = httpx.Request("POST", "https://api.example/chat")
    fake_adapters.deepseek.model.invoke.side_effect = openai.APITimeoutError(
        request=request
    )
    gateway = _gateway(settings, fake_adapters)

    with pytest.raises(LLMTimeoutError) as exc_info:
        gateway.chat(
            "answer",
            [HumanMessage(content="hello")],
            tools=[fake_tool],
        )

    assert str(exc_info.value) == "LLM request timed out"


def test_raw_rate_limit_is_normalized_and_redacted(settings, fake_adapters):
    request = httpx.Request("POST", "https://api.example/chat")
    response = httpx.Response(429, request=request)
    fake_adapters.deepseek.model.invoke.side_effect = openai.RateLimitError(
        "secret sk-test",
        response=response,
        body=None,
    )
    gateway = _gateway(settings, fake_adapters)

    with pytest.raises(LLMRateLimitError) as exc_info:
        gateway.chat(
            "answer",
            [HumanMessage(content="hello")],
            tools=[fake_tool],
        )

    assert str(exc_info.value) == "LLM rate limit exceeded"
    assert "sk-test" not in str(exc_info.value)


def test_unknown_provider_exception_is_redacted(settings, fake_adapters):
    fake_adapters.deepseek.model.invoke.side_effect = RuntimeError("secret sk-test")
    gateway = _gateway(settings, fake_adapters)

    with pytest.raises(LLMUnavailableError) as exc_info:
        gateway.chat(
            "answer",
            [HumanMessage(content="hello")],
            tools=[fake_tool],
        )

    assert str(exc_info.value) == "LLM provider unavailable"
    assert "sk-test" not in str(exc_info.value)


def test_configuration_error_is_not_retried(settings, fake_adapters):
    fake_adapters.deepseek.create_model = MagicMock(
        side_effect=LLMConfigurationError("selected LLM provider is not configured")
    )
    gateway = _gateway(settings, fake_adapters)

    with pytest.raises(LLMConfigurationError):
        gateway.chat(
            "answer",
            [HumanMessage(content="hello")],
            tools=[fake_tool],
        )

    assert fake_adapters.deepseek.create_model.call_count == 1


def test_legacy_router_import_does_not_load_yaml(tmp_path):
    env = os.environ.copy()
    env["LLM_CONFIG_PATH"] = str(tmp_path / "missing.yaml")

    result = subprocess.run(
        [sys.executable, "-c", "import jarvis.llm.router"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
