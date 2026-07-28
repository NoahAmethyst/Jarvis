import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis import main


class StorageInitializationReached(Exception):
    pass


@pytest.mark.asyncio
async def test_model_check_failure_does_not_stop_startup(monkeypatch, caplog):
    monkeypatch.setattr(main, "configure_logging", lambda: None)

    def fail_model_checks():
        raise RuntimeError("secret-response-body")

    def stop_at_storage():
        raise StorageInitializationReached

    monkeypatch.setattr(main, "run_model_startup_checks", fail_model_checks)
    monkeypatch.setattr(main, "init_db", stop_at_storage)

    with caplog.at_level(logging.ERROR, logger="jarvis.main"):
        with pytest.raises(StorageInitializationReached):
            await main.serve()

    assert "Model startup checks failed category=internal" in caplog.text
    assert "secret-response-body" not in caplog.text


@pytest.mark.asyncio
async def test_uvicorn_uses_the_root_logging_configuration(monkeypatch):
    grpc_server = MagicMock()
    grpc_server.start = AsyncMock()
    grpc_server.wait_for_termination = AsyncMock()
    http_server = MagicMock()
    http_server.serve = AsyncMock()
    uvicorn_config = object()
    config_factory = MagicMock(return_value=uvicorn_config)

    monkeypatch.setattr(main, "configure_logging", lambda: None)
    monkeypatch.setattr(main, "run_model_startup_checks", lambda: None)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "init_collection", lambda: None)
    monkeypatch.setattr(
        main, "create_grpc_server", AsyncMock(return_value=grpc_server)
    )
    monkeypatch.setattr(main.uvicorn, "Config", config_factory)
    monkeypatch.setattr(
        main.uvicorn, "Server", MagicMock(return_value=http_server)
    )

    await main.serve()

    config_factory.assert_called_once_with(
        main.app,
        host="0.0.0.0",
        port=main.HTTP_PORT,
        log_level="info",
        log_config=None,
    )
