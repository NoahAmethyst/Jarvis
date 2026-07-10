import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage
from fastapi.testclient import TestClient
from jarvis.llm.errors import (
    LLMConfigurationError,
    LLMContextLimitError,
    LLMInvalidRequestError,
    LLMInvalidResponseError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)


@pytest.fixture
def client():
    with patch("jarvis.agent.nodes.memory_load.conv_mem.load_history", return_value=[]), \
         patch("jarvis.agent.nodes.agent_dispatch.load_agents", return_value=[]), \
         patch("jarvis.agent.nodes.rag_retrieve.know_mem.retrieve_knowledge", return_value=""), \
         patch("jarvis.agent.nodes.memory_write.conv_mem.save_message"), \
         patch("jarvis.agent.nodes.memory_write.know_mem.store_knowledge"):
        from jarvis.api.http.routes import app
        yield TestClient(app)


def test_chat_returns_answer(client):
    with patch(
        "jarvis.agent.nodes.plan_and_call.llm.chat",
        side_effect=[
            AIMessage(content="Paris is the capital of France."),
            AIMessage(content="0.95"),
        ],
    ):
        resp = client.post("/chat", json={"message": "Capital of France?", "user_id": "u1"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "Paris is the capital of France."
    assert data["low_confidence"] is False


def test_chat_missing_user_id_returns_422(client):
    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 422


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (LLMInvalidRequestError("invalid LLM request"), 400),
        (LLMContextLimitError("LLM context limit exceeded"), 400),
        (LLMConfigurationError("selected LLM provider is not configured"), 500),
        (LLMRateLimitError("LLM rate limit exceeded"), 429),
        (LLMTimeoutError("LLM request timed out"), 504),
        (LLMUnavailableError("LLM provider unavailable"), 503),
        (LLMInvalidResponseError("LLM provider returned an invalid response"), 502),
    ],
)
def test_chat_maps_normalized_llm_errors(client, error, status_code):
    error.__cause__ = RuntimeError("raw provider secret sk-test")
    with patch("jarvis.api.http.routes.graph.invoke", side_effect=error):
        response = client.post(
            "/chat",
            json={"message": "hello", "user_id": "u1"},
        )

    assert response.status_code == status_code
    assert response.json() == {"detail": str(error)}
    assert "sk-test" not in response.text


def test_ingest_stores_knowledge(client):
    with patch("jarvis.api.http.routes.know_mem.store_knowledge") as mock_store:
        resp = client.post("/ingest", json={
            "content": "LangGraph is a graph-based framework for LLM agents.",
            "source_url": "https://docs.langchain.com/langgraph",
            "user_id": "u1",
        })
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    mock_store.assert_called_once_with(
        "LangGraph is a graph-based framework for LLM agents.",
        "https://docs.langchain.com/langgraph",
        "u1",
    )


def test_get_memory_returns_history(client):
    with patch("jarvis.memory.conversation.get_history_records") as mock_hist:
        mock_hist.return_value = [
            {"role": "human", "content": "hi", "created_at": "2026-01-01T00:00:00"},
        ]
        resp = client.get("/memory/u1")
    assert resp.status_code == 200
    assert resp.json()[0]["role"] == "human"


def test_delete_memory(client):
    with patch("jarvis.memory.conversation.delete_history") as mock_del:
        resp = client.delete("/memory/u1")
    assert resp.status_code == 200
    mock_del.assert_called_once_with("u1")
