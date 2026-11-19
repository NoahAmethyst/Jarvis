import inspect
import logging
import re

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
         patch("jarvis.memory.knowledge.store_web_knowledge"):
        from jarvis.api.http.routes import app
        yield TestClient(app)


def test_chat_returns_answer(client, caplog):
    caplog.set_level(logging.INFO)
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
    assert "【方法:HTTP.Chat】" in caplog.text
    assert "【评分:0.95】" in caplog.text
    ids = re.findall(r"【请求ID:([^】]+)】", caplog.text)
    assert len(ids) > 10 and len(set(ids)) == 1
    assert "Capital of France?" not in caplog.text
    assert "Paris is the capital of France." not in caplog.text


QQ_OUTPUT_POLICY = """QQ输出约束：
返回适合直接发送到QQ的普通文本。
可以使用emoji和普通中文标点、普通符号突出标题和重点。
不允许使用Markdown格式，不要使用Markdown标题、项目符号、加粗、斜体、删除线、代码块、表格、引用或Markdown链接。
可以用简短自然段组织内容。"""


@pytest.mark.parametrize(
    ("user_id", "query", "expected_search"),
    [
        ("user", "你好？", None),
        ("qq:private:100", "你好？\n\n" + QQ_OUTPUT_POLICY, None),
        ("qq:group:1:2", "你好，请帮我找项目文档\n\n" + QQ_OUTPUT_POLICY, "你好，请帮我找项目文档"),
        ("user", "你好这个词怎么翻译？", "你好这个词怎么翻译？"),
    ],
)
def test_chat_limits_context_for_standalone_greetings(client, caplog, user_id, query, expected_search):
    caplog.set_level(logging.INFO)
    with patch("jarvis.agent.nodes.memory_load.conv_mem.load_history", return_value=[
        HumanMessage(content="old history"),
    ]) as history, patch(
        "jarvis.agent.nodes.rag_retrieve.know_mem.retrieve_knowledge", return_value="related knowledge",
    ) as search, patch(
        "jarvis.agent.nodes.plan_and_call.llm.chat",
        side_effect=[AIMessage(content="你好！"), AIMessage(content="0.95")],
    ) as model:
        response = client.post("/chat", json={"message": query, "user_id": user_id})

    assert response.status_code == 200
    messages = model.call_args_list[0].kwargs["messages"]
    assert messages[-1].content == query
    if expected_search is None:
        history.assert_not_called()
        search.assert_not_called()
        assert len(messages) == 2
        assert "【原因:简单问候】" in caplog.text
    else:
        history.assert_called_once_with(user_id)
        search.assert_called_once_with(expected_search, user_id)
        assert "related knowledge" in messages[0].content


def test_liveness_is_available(client):
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_is_unavailable_before_startup(client):
    client.app.state.ready = False

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "not ready"}


def test_readiness_is_available_after_startup(client):
    client.app.state.ready = True

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_health_handlers_run_on_event_loop():
    from jarvis.api.http.routes import health_live, health_ready

    assert inspect.iscoroutinefunction(health_live)
    assert inspect.iscoroutinefunction(health_ready)


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


def test_chat_missing_llm_config_maps_safe_configuration_error(
    client, monkeypatch, tmp_path
):
    from jarvis.llm import get_llm

    monkeypatch.setattr(
        "jarvis.llm.config.LLM_CONFIG_PATH",
        str(tmp_path / "secret-path" / "missing.yaml"),
    )
    get_llm.cache_clear()
    try:
        response = client.post(
            "/chat",
            json={"message": "hello", "user_id": "u1"},
        )
    finally:
        get_llm.cache_clear()

    assert response.status_code == 500
    assert response.json() == {"detail": "LLM configuration is invalid"}
    assert "secret-path" not in response.text


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
