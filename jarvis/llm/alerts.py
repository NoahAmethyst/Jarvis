"""Best-effort private QQ notifications for failed LLM provider calls."""

import logging

import grpc

from jarvis import config
from jarvis.llm.qqbot_pb2 import Resp, SendMsgReq

logger = logging.getLogger(__name__)


def notify_llm_failure(message: str) -> None:
    """Send a pre-sanitized alert; notification failures never replace LLM errors."""
    if not config.LLM_ERROR_QQ_USER_ID.strip():
        return
    try:
        recipient = int(config.LLM_ERROR_QQ_USER_ID)
        if recipient <= 0:
            raise ValueError("recipient must be positive")
        request = SendMsgReq(content=message, chat=recipient, group=False)
        with grpc.insecure_channel(config.QQBOT_GRPC_TARGET) as channel:
            send = channel.unary_unary(
                "/proto.QQBotService/SendMsg",
                request_serializer=SendMsgReq.SerializeToString,
                response_deserializer=Resp.FromString,
            )
            send(request, timeout=3.0)
    except Exception as error:
        # Transport details can contain credentials; log only the exception type.
        logger.warning("QQbot alert failed error=%s", type(error).__name__)
