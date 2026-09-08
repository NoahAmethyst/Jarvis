from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import grpc
import pytest

from jarvis import config
from jarvis.llm import alerts
from jarvis.llm.qqbot_pb2 import Resp, SendMsgReq


@pytest.fixture
def qqbot(monkeypatch):
    received = []

    def send(request, context):
        received.append(request)
        return Resp(message="ok")

    server = grpc.server(ThreadPoolExecutor(max_workers=1))
    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(
        "proto.QQBotService", {"SendMsg": grpc.unary_unary_rpc_method_handler(
            send, request_deserializer=SendMsgReq.FromString,
            response_serializer=Resp.SerializeToString,
        )},
    ),))
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    monkeypatch.setattr(config, "QQBOT_GRPC_TARGET", f"127.0.0.1:{port}")
    monkeypatch.setattr(config, "LLM_ERROR_QQ_USER_ID", "1066840101")
    yield received
    server.stop(0).wait()


def test_sends_private_message_to_configured_user(qqbot, monkeypatch):
    monkeypatch.setattr(config, "LLM_ERROR_QQ_USER_ID", "123456789")
    alerts.notify_llm_failure("deepseek 402 Insufficient Balance")
    assert len(qqbot) == 1
    assert qqbot[0].chat == 123456789
    assert qqbot[0].group is False
    assert "402 Insufficient Balance" in qqbot[0].content


def test_unconfigured_recipient_disables_alerts(qqbot, monkeypatch):
    monkeypatch.setattr(config, "LLM_ERROR_QQ_USER_ID", "")
    alerts.notify_llm_failure("failure")
    assert qqbot == []


@pytest.mark.parametrize("recipient", ["abc", "0", "-1", str(2**64)])
def test_invalid_recipient_is_contained(qqbot, monkeypatch, recipient, caplog):
    monkeypatch.setattr(config, "LLM_ERROR_QQ_USER_ID", recipient)
    alerts.notify_llm_failure("failure")
    assert qqbot == []
    assert "QQbot alert failed" in caplog.text


def test_transport_failure_is_bounded_and_does_not_leak_details(monkeypatch, caplog):
    monkeypatch.setattr(config, "LLM_ERROR_QQ_USER_ID", "1066840101")
    channel = MagicMock()
    rpc = channel.__enter__.return_value.unary_unary.return_value
    rpc.side_effect = RuntimeError("token=sensitive-test-value")
    monkeypatch.setattr(alerts.grpc, "insecure_channel", lambda _: channel)
    alerts.notify_llm_failure("failure")
    assert rpc.call_args.kwargs["timeout"] == 3.0
    assert "QQbot alert failed" in caplog.text
    assert "sensitive-test-value" not in caplog.text
