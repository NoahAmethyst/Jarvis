"""Exercise the real aio server's sync-handler context, not a fake context."""

import logging
from contextlib import nullcontext
from unittest.mock import patch

import grpc
import pytest

from jarvis.api.grpc import jarvis_pb2, jarvis_pb2_grpc
from jarvis.api.grpc.servicer import JarvisServicer
from jarvis.llm.errors import LLMInvalidRequestError


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["Chat", "Generate", "Ingest"])
async def test_real_grpc_errors_have_failed_request_summaries(method, caplog):
    caplog.set_level(logging.INFO, logger="jarvis.execution_logging")
    server = grpc.aio.server()
    jarvis_pb2_grpc.add_JarvisServiceServicer_to_server(JarvisServicer(), server)
    port = server.add_insecure_port("127.0.0.1:0")
    requests = {
        "Chat": jarvis_pb2.ChatRequest(message="private-question", user_id="u"),
        "Generate": jarvis_pb2.GenerateRequest(prompt="private-question", user_id="u"),
        "Ingest": jarvis_pb2.IngestRequest(content="private-content", user_id="u"),
    }
    targets = {
        "Chat": "jarvis.api.grpc.servicer.graph.invoke",
        "Generate": "jarvis.api.grpc.servicer._run_stateless_generate",
        "Ingest": "jarvis.api.grpc.servicer.know_mem.store_knowledge",
    }
    status = grpc.StatusCode.INTERNAL if method == "Ingest" else grpc.StatusCode.INVALID_ARGUMENT
    error = RuntimeError("private-error") if method == "Ingest" else LLMInvalidRequestError("invalid LLM request")
    try:
        await server.start()
        with patch("jarvis.api.grpc.servicer.model_session", nullcontext), patch(
            targets[method], side_effect=error,
        ):
            async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
                stub = jarvis_pb2_grpc.JarvisServiceStub(channel)
                with pytest.raises(grpc.aio.AioRpcError) as caught:
                    await getattr(stub, method)(requests[method], timeout=5)
                assert caught.value.code() == status
    finally:
        await server.stop(0)
    summaries = [record.getMessage() for record in caplog.records
                 if f"【方法:gRPC.{method}】" in record.getMessage()
                 and "【状态:开始】" not in record.getMessage()]
    assert summaries
    assert "【状态:失败】" in summaries[-1]
    assert f"【状态码:{status.name}】" in summaries[-1]
    assert next(record.levelno for record in reversed(caplog.records)
                if record.getMessage() == summaries[-1]) == logging.ERROR
    assert "private-error" not in caplog.text


@pytest.mark.asyncio
async def test_real_grpc_success_keeps_completed_summary(caplog):
    caplog.set_level(logging.INFO, logger="jarvis.execution_logging")
    server = grpc.aio.server()
    jarvis_pb2_grpc.add_JarvisServiceServicer_to_server(JarvisServicer(), server)
    port = server.add_insecure_port("127.0.0.1:0")
    try:
        await server.start()
        with patch("jarvis.api.grpc.servicer.model_session", nullcontext), patch(
            "jarvis.api.grpc.servicer._run_stateless_generate", return_value="OK",
        ):
            async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
                stub = jarvis_pb2_grpc.JarvisServiceStub(channel)
                response = await stub.Generate(jarvis_pb2.GenerateRequest(prompt="private"), timeout=5)
                assert response.text == "OK"
    finally:
        await server.stop(0)
    summary = next(record for record in reversed(caplog.records)
                   if "【方法:gRPC.Generate】" in record.getMessage())
    assert "【状态:完成】" in summary.getMessage()
    assert summary.levelno == logging.INFO
