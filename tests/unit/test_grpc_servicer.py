import logging
from unittest.mock import patch

import grpc
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from jarvis.api.grpc import jarvis_pb2
from jarvis.api.grpc.servicer import JarvisServicer
from jarvis.llm.errors import (
    LLMConfigurationError,
    LLMContextLimitError,
    LLMInvalidRequestError,
    LLMInvalidResponseError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)


class FakeContext:
    def __init__(self):
        self.code = None
        self.details = None

    def set_code(self, code):
        self.code = code

    def set_details(self, details):
        self.details = details


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (LLMInvalidRequestError("invalid LLM request"), grpc.StatusCode.INVALID_ARGUMENT),
        (LLMContextLimitError("LLM context limit exceeded"), grpc.StatusCode.INVALID_ARGUMENT),
        (
            LLMConfigurationError("selected LLM provider is not configured"),
            grpc.StatusCode.FAILED_PRECONDITION,
        ),
        (LLMRateLimitError("LLM rate limit exceeded"), grpc.StatusCode.RESOURCE_EXHAUSTED),
        (LLMTimeoutError("LLM request timed out"), grpc.StatusCode.DEADLINE_EXCEEDED),
        (LLMUnavailableError("LLM provider unavailable"), grpc.StatusCode.UNAVAILABLE),
        (
            LLMInvalidResponseError("LLM provider returned an invalid response"),
            grpc.StatusCode.INTERNAL,
        ),
    ],
)
def test_grpc_chat_maps_normalized_llm_errors(error, status_code):
    error.__cause__ = RuntimeError("raw provider secret sk-test")
    context = FakeContext()
    request = jarvis_pb2.ChatRequest(message="hello", user_id="u1")

    with patch("jarvis.api.grpc.servicer.graph.invoke", side_effect=error):
        response = JarvisServicer().Chat(request, context)

    assert response.answer == ""
    assert context.code == status_code
    assert context.details == str(error)
    assert "sk-test" not in context.details


def test_grpc_chat_success_preserves_response_shape():
    context = FakeContext()
    request = jarvis_pb2.ChatRequest(message="hello", user_id="u1")

    with patch(
        "jarvis.api.grpc.servicer.graph.invoke",
        return_value={"final_answer": "hi", "low_confidence": False},
    ):
        response = JarvisServicer().Chat(request, context)

    assert response.answer == "hi"
    assert response.low_confidence is False
    assert context.code is None


def test_grpc_chat_logs_unexpected_errors_and_returns_internal(caplog):
    context = FakeContext()
    request = jarvis_pb2.ChatRequest(message="hello", user_id="u1")

    with caplog.at_level(logging.ERROR, logger="jarvis.api.grpc.servicer"):
        with patch(
            "jarvis.api.grpc.servicer.graph.invoke",
            side_effect=RuntimeError("secret-response-body"),
        ):
            response = JarvisServicer().Chat(request, context)

    assert response.answer == ""
    assert context.code == grpc.StatusCode.INTERNAL
    assert context.details == "internal Jarvis Chat error"
    assert "【方法:Chat】【结果:失败】【错误:RuntimeError】" in caplog.text
    assert "Unexpected gRPC request failure" in caplog.text
    assert "secret-response-body" not in caplog.text


def test_grpc_missing_llm_config_maps_failed_precondition(monkeypatch, tmp_path):
    from jarvis.llm import get_llm

    monkeypatch.setattr(
        "jarvis.llm.config.LLM_CONFIG_PATH",
        str(tmp_path / "secret-path" / "missing.yaml"),
    )
    get_llm.cache_clear()
    context = FakeContext()
    request = jarvis_pb2.ChatRequest(message="hello", user_id="u1")

    def invoke(_state):
        get_llm().chat(
            profile="answer",
            messages=[HumanMessage(content="hello")],
        )

    try:
        with patch("jarvis.api.grpc.servicer.graph.invoke", side_effect=invoke):
            response = JarvisServicer().Chat(request, context)
    finally:
        get_llm.cache_clear()

    assert response.answer == ""
    assert context.code == grpc.StatusCode.FAILED_PRECONDITION
    assert context.details == "LLM configuration is invalid"
    assert "secret-path" not in context.details


def test_grpc_generate_runs_tool_chain_without_conversation_memory():
    context = FakeContext()
    request = jarvis_pb2.GenerateRequest(
        prompt="what is today's weather",
        user_id="go-cqhttp:wallstreet",
        llm="openai/gpt-4o",
        operation="weather_lookup",
    )

    with patch("jarvis.api.grpc.servicer.graph.invoke") as graph_invoke, patch(
        "jarvis.api.grpc.servicer.conv_mem.load_history"
    ) as load_history, patch(
        "jarvis.api.grpc.servicer.conv_mem.save_message"
    ) as save_message, patch(
        "jarvis.api.grpc.servicer.rag_retrieve",
        return_value={"rag_context": ""},
    ) as rag, patch(
        "jarvis.api.grpc.servicer.plan_and_call",
        side_effect=[
            {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "web_search",
                                "args": {"query": "today weather"},
                                "id": "call-1",
                            }
                        ],
                    )
                ]
            },
            {"messages": [AIMessage(content="Sunny today.")]},
        ],
    ) as plan, patch(
        "jarvis.api.grpc.servicer.execute_tools",
        return_value={
            "messages": [
                ToolMessage(
                    content="Weather result",
                    tool_call_id="call-1",
                    name="web_search",
                )
            ],
            "unavailable_tools": [],
        },
    ) as execute:
        response = JarvisServicer().Generate(request, context)

    assert response.text == "Sunny today."
    assert context.code is None
    graph_invoke.assert_not_called()
    load_history.assert_not_called()
    save_message.assert_not_called()
    rag.assert_called_once()
    assert plan.call_count == 2
    execute.assert_called_once()
    first_state = plan.call_args_list[0].args[0]
    assert first_state["history"] == []
    assert first_state["query"] == "what is today's weather"
    assert first_state["llm_override"] == "openai/gpt-4o"
    assert first_state["tools_enabled"] is True
    second_state = plan.call_args_list[1].args[0]
    assert any(isinstance(message, ToolMessage) for message in second_state["messages"])


def test_grpc_generate_can_disable_tools_for_plain_generation():
    context = FakeContext()
    request = jarvis_pb2.GenerateRequest(
        prompt="return exactly five chapter markers",
        user_id="go-cqhttp:wallstreet",
        operation="wallstreet_summary_v2",
        disable_tools=True,
    )

    with patch(
        "jarvis.api.grpc.servicer.rag_retrieve",
        return_value={"rag_context": "summary context"},
    ) as rag, patch(
        "jarvis.api.grpc.servicer.plan_and_call",
        return_value={"messages": [AIMessage(content="<<<CHAPTER_1>>>\ncontent")]},
    ) as plan, patch("jarvis.api.grpc.servicer.execute_tools") as execute:
        response = JarvisServicer().Generate(request, context)

    assert response.text == "<<<CHAPTER_1>>>\ncontent"
    assert context.code is None
    rag.assert_called_once()
    execute.assert_not_called()
    state = plan.call_args.args[0]
    assert state["tools_enabled"] is False
    assert state["rag_context"] == "summary context"


def test_grpc_generate_uses_rag_by_default_without_conversation_memory():
    context = FakeContext()
    request = jarvis_pb2.GenerateRequest(
        prompt="summarize stored policy",
        user_id="u1",
        operation="policy_summary",
    )

    with patch(
        "jarvis.api.grpc.servicer.rag_retrieve",
        return_value={"rag_context": "retrieved policy"},
    ) as rag, patch(
        "jarvis.api.grpc.servicer.plan_and_call",
        return_value={"messages": [AIMessage(content="Policy summary")]},
    ) as plan, patch(
        "jarvis.api.grpc.servicer.conv_mem.load_history"
    ) as load_history, patch(
        "jarvis.api.grpc.servicer.conv_mem.save_message"
    ) as save_message:
        response = JarvisServicer().Generate(request, context)

    assert response.text == "Policy summary"
    assert context.code is None
    rag.assert_called_once()
    load_history.assert_not_called()
    save_message.assert_not_called()
    state = plan.call_args.args[0]
    assert state["rag_context"] == "retrieved policy"


def test_grpc_generate_can_disable_rag():
    context = FakeContext()
    request = jarvis_pb2.GenerateRequest(
        prompt="summarize only this prompt",
        user_id="u1",
        operation="prompt_only",
        disable_rag=True,
        disable_tools=True,
    )

    with patch("jarvis.api.grpc.servicer.rag_retrieve") as rag, patch(
        "jarvis.api.grpc.servicer.plan_and_call",
        return_value={"messages": [AIMessage(content="Prompt summary")]},
    ) as plan:
        response = JarvisServicer().Generate(request, context)

    assert response.text == "Prompt summary"
    assert context.code is None
    rag.assert_not_called()
    state = plan.call_args.args[0]
    assert state["rag_context"] == ""


def test_grpc_generate_maps_llm_errors():
    context = FakeContext()
    request = jarvis_pb2.GenerateRequest(
        prompt="return exactly five chapter markers",
        user_id="go-cqhttp:wallstreet",
        operation="wallstreet_summary_v2",
    )

    with patch(
        "jarvis.api.grpc.servicer.rag_retrieve",
        return_value={"rag_context": ""},
    ), patch(
        "jarvis.api.grpc.servicer.plan_and_call",
        side_effect=LLMInvalidRequestError("invalid LLM request"),
    ):
        response = JarvisServicer().Generate(request, context)

    assert response.text == ""
    assert context.code == grpc.StatusCode.INVALID_ARGUMENT
    assert context.details == "invalid LLM request"
