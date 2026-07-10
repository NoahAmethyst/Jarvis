from unittest.mock import patch

import grpc
import pytest
from langchain_core.messages import HumanMessage

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
