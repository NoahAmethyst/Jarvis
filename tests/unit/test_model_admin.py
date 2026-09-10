from unittest.mock import MagicMock, patch

import psycopg2
import httpx
import pytest
from fastapi.testclient import TestClient

from jarvis.api.http.routes import app
from jarvis.api.http import admin
from jarvis.llm import get_llm, model_session, runtime
from jarvis.llm.errors import LLMUnavailableError


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LLM_RUNTIME_CONFIG_ENABLED", "true")
    monkeypatch.setenv("JARVIS_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-provider-key")
    get_llm.cache_clear()
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer test-admin-token"
        yield client
    get_llm.cache_clear()


def test_management_requires_token_and_explicit_enable(client, monkeypatch):
    for token in ("", "Bearer wrong"):
        with patch.object(runtime, "read_overrides") as read:
            assert client.get("/admin/api/models", headers={"Authorization": token}).status_code == 401
            read.assert_not_called()
    monkeypatch.delenv("JARVIS_ADMIN_TOKEN")
    assert client.get("/admin/api/models").status_code == 503
    monkeypatch.setenv("JARVIS_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("LLM_RUNTIME_CONFIG_ENABLED", "false")
    assert client.get("/admin/api/models").status_code == 503


def test_admin_does_not_expose_credentials(client):
    with patch.object(runtime, "read_overrides", return_value=(0, {})):
        result = client.get("/admin/api/models")
    assert result.status_code == 200
    assert result.json()["profiles"]["answer"]["model"] == "deepseek/deepseek-flash"
    assert "test-provider-key" not in result.text
    assert "api_key_env" not in result.text


def body(models):
    return {"revision": 2, "config_version": admin.config_version(), "models": models}


def all_models(model="deepseek/custom-future-model"):
    return {name: model for name in ("answer", "reflection", "agent_dispatch")}


def test_save_accepts_new_model_without_code_changes(client):
    with patch.object(runtime, "save_overrides", return_value=3) as save:
        result = client.put("/admin/api/models", json=body(all_models()))
    assert result.status_code == 200
    assert result.json()["revision"] == 3
    assert result.json()["profiles"]["answer"]["model"] == "deepseek/custom-future-model"
    save.assert_called_once_with(2, all_models())


@pytest.mark.parametrize("models", [
    {"answer": "deepseek/new"},
    all_models("missing/model"),
    all_models("deepseek/<script>alert(1)</script>"),
    all_models("openai/gpt-test"),
    all_models("deepseek/"),
    all_models("deepseek/" + "a" * 201),
])
def test_invalid_updates_never_persist(client, models):
    with patch.object(runtime, "save_overrides") as save:
        assert client.put("/admin/api/models", json=body(models)).status_code == 400
        save.assert_not_called()


def test_missing_provider_credential_cannot_be_saved(client, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    with patch.object(runtime, "save_overrides") as save:
        assert client.put("/admin/api/models", json=body(all_models())).status_code == 400
        save.assert_not_called()


def test_stale_revision_and_changed_base_are_conflicts(client):
    with patch.object(runtime, "save_overrides", side_effect=runtime.RevisionConflict):
        assert client.put("/admin/api/models", json=body(all_models())).status_code == 409
    stale = body(all_models()); stale["config_version"] = "0" * 64
    with patch.object(runtime, "save_overrides") as save:
        assert client.put("/admin/api/models", json=stale).status_code == 409
        save.assert_not_called()


def test_restore_defaults_clears_overrides(client):
    with patch.object(runtime, "save_overrides", return_value=3) as save:
        result = client.put("/admin/api/models", json=body({}))
    assert result.status_code == 200
    save.assert_called_once_with(2, {})
    assert result.json()["profiles"]["answer"]["model"] == "deepseek/deepseek-flash"


def test_runtime_pins_configuration_until_request_completes(client):
    with patch.object(runtime, "read_overrides", side_effect=[
        (1, {"answer": "deepseek/old"}), (2, {"answer": "deepseek/new"})
    ]) as read:
        with model_session():
            first = get_llm()
            with model_session():
                assert get_llm() is first
            assert first.settings.profiles["answer"].model == "deepseek/old"
            assert read.call_count == 1
        with model_session():
            assert get_llm().settings.profiles["answer"].model == "deepseek/new"
        assert read.call_count == 2
    assert admin._base_llm().settings.profiles["answer"].model == "deepseek/deepseek-flash"


def test_session_context_propagates_into_langgraph(client):
    from langgraph.graph import StateGraph, START, END
    from typing import TypedDict

    class State(TypedDict):
        model: str

    builder = StateGraph(State)
    builder.add_node("read", lambda state: {"model": get_llm().settings.profiles["answer"].model})
    builder.add_edge(START, "read"); builder.add_edge("read", END)
    graph = builder.compile()
    with patch.object(runtime, "read_overrides", return_value=(1, {"answer": "deepseek/pinned"})) as read:
        with model_session():
            assert graph.invoke({"model": ""})["model"] == "deepseek/pinned"
        read.assert_called_once()


@pytest.mark.parametrize("entry", ["http", "grpc-chat", "grpc-generate"])
def test_request_entries_pin_and_release_after_failure(client, entry):
    from jarvis.api.grpc import jarvis_pb2
    from jarvis.api.grpc import servicer
    def fail(*args):
        assert get_llm() is get_llm()
        assert get_llm().settings.profiles["answer"].model == "deepseek/pinned"
        raise LLMUnavailableError("test failure")
    with patch.object(runtime, "read_overrides", side_effect=[
        (1, {"answer": "deepseek/pinned"}), (2, {"answer": "deepseek/next"})
    ]) as read:
        if entry == "http":
            with patch("jarvis.api.http.routes.graph.invoke", side_effect=fail):
                assert client.post("/chat", json={"message": "hello", "user_id": "test"}).status_code == 503
        elif entry == "grpc-chat":
            with patch.object(servicer.graph, "invoke", side_effect=fail):
                servicer.JarvisServicer().Chat(jarvis_pb2.ChatRequest(message="hello"), MagicMock())
        else:
            with patch.object(servicer, "_run_stateless_generate", side_effect=fail):
                servicer.JarvisServicer().Generate(jarvis_pb2.GenerateRequest(prompt="hello"), MagicMock())
        assert read.call_count == 1
        assert get_llm().settings.profiles["answer"].model == "deepseek/next"


def test_concurrent_sessions_do_not_share_snapshots(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier = Barrier(2)
    def work():
        with model_session():
            gateway = get_llm()
            barrier.wait(timeout=5)
            assert get_llm() is gateway
            return gateway.settings.profiles["answer"].model
    with patch.object(runtime, "read_overrides", side_effect=[
        (1, {"answer": "deepseek/first"}), (2, {"answer": "deepseek/second"})
    ]):
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: work(), range(2)))
    assert set(results) == {"deepseek/first", "deepseek/second"}


def test_database_failure_does_not_fall_back_to_old_models(client):
    with patch.object(runtime, "_connect", side_effect=psycopg2.OperationalError("secret-dsn")):
        with pytest.raises(LLMUnavailableError, match="storage unavailable"):
            get_llm()
        result = client.get("/admin/api/models")
    assert result.status_code == 503
    assert "secret-dsn" not in result.text


def test_database_cas_is_parameterized_and_conflict_rolls_back():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = None
    with patch.object(runtime, "_connect", return_value=conn):
        with pytest.raises(runtime.RevisionConflict):
            runtime.save_overrides(8, {"answer": "deepseek/new"})
    sql, params = cur.execute.call_args.args
    assert "revision = %s" in sql and "RETURNING revision" in sql
    assert params[1] == 8
    assert conn.__exit__.call_args.args[0] is runtime.RevisionConflict
    conn.close.assert_called_once()


def test_catalog_uses_server_configuration_and_redacts_errors(client):
    status = 200
    def respond(request):
        assert request.url.path.endswith("/models")
        return httpx.Response(status, json={"data": [{"id": "future-model"}]})
    factory = httpx.AsyncClient
    with patch.object(admin.httpx, "AsyncClient", side_effect=lambda **kw: factory(transport=httpx.MockTransport(respond), **kw)) as get:
        assert client.get("/admin/api/providers/deepseek/models").json() == {"models": ["future-model"]}
        assert get.call_args.kwargs["follow_redirects"] is False
        status = 401
        error = client.get("/admin/api/providers/deepseek/models")
        assert error.status_code == 502
        assert "test-provider-key" not in error.text


def test_restore_checks_effective_credentials(client, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    with patch.object(runtime, "save_overrides") as save:
        assert client.put("/admin/api/models", json=body({})).status_code == 400
        save.assert_not_called()


def test_catalog_total_deadline_interrupts_stream_and_releases_slot(client, monkeypatch):
    import asyncio
    import time
    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.sleep(1)
            yield b'{"data": [{"id": "valid-model"}]}'
    factory = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=SlowStream()))
    monkeypatch.setattr(admin, "CATALOG_DEADLINE", 0.01)
    with patch.object(admin.httpx, "AsyncClient", side_effect=lambda **kw: factory(transport=transport, **kw)):
        for _ in range(3):
            started = time.monotonic()
            assert client.get("/admin/api/providers/deepseek/models").status_code == 502
            assert time.monotonic() - started < 0.5


def test_catalog_size_limit_and_busy_response(client):
    factory = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": [{"id": "x" * 262145}]}))
    with patch.object(admin.httpx, "AsyncClient", side_effect=lambda **kw: factory(transport=transport, **kw)):
        assert client.get("/admin/api/providers/deepseek/models").status_code == 502
    admin.catalog_slots.acquire(); admin.catalog_slots.acquire()
    try:
        assert client.get("/admin/api/providers/deepseek/models").status_code == 429
    finally:
        admin.catalog_slots.release(); admin.catalog_slots.release()


def test_put_and_discovery_require_authorization(client):
    headers = {"Authorization": "Bearer wrong"}
    with patch.object(runtime, "save_overrides") as save:
        assert client.put("/admin/api/models", json=body({}), headers=headers).status_code == 401
        save.assert_not_called()
    assert client.get("/admin/api/providers/deepseek/models", headers=headers).status_code == 401


def test_page_and_assets_are_packaged_with_csp(client):
    result = client.get("/admin/models")
    assert result.status_code == 200
    assert "frame-ancestors 'none'" in result.headers["content-security-policy"]
    assert client.get("/admin/assets/models.js").status_code == 200
    assert client.get("/admin/assets/config.py").status_code == 404
