import logging
import traceback

import grpc
from jarvis.api.grpc import jarvis_pb2, jarvis_pb2_grpc
from jarvis.agent.graph import graph
from jarvis.agent.nodes.plan_and_call import plan_and_call
from jarvis.agent.nodes.rag_retrieve import rag_retrieve
from jarvis.agent.nodes.tool_execute import execute_tools
from jarvis.agent.state import AgentState
from jarvis.llm.errors import (
    LLMConfigurationError,
    LLMContextLimitError,
    LLMError,
    LLMInvalidRequestError,
    LLMInvalidResponseError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from jarvis.logging_config import format_log_tags
from jarvis.memory import conversation as conv_mem
from jarvis.memory import knowledge as know_mem
from langchain_core.messages import AIMessage, HumanMessage


logger = logging.getLogger(__name__)
GENERATE_MAX_TOOL_ROUNDS = 6


def _error_location(error: Exception) -> str:
    traceback_frames = traceback.extract_tb(error.__traceback__)
    if not traceback_frames:
        return "unknown"
    frame = traceback_frames[-1]
    return f"{frame.filename}:{frame.lineno}"


def _llm_grpc_status(error: LLMError):
    if isinstance(error, (LLMContextLimitError, LLMInvalidRequestError)):
        return grpc.StatusCode.INVALID_ARGUMENT
    if isinstance(error, LLMConfigurationError):
        return grpc.StatusCode.FAILED_PRECONDITION
    if isinstance(error, LLMRateLimitError):
        return grpc.StatusCode.RESOURCE_EXHAUSTED
    if isinstance(error, LLMTimeoutError):
        return grpc.StatusCode.DEADLINE_EXCEEDED
    if isinstance(error, LLMUnavailableError):
        return grpc.StatusCode.UNAVAILABLE
    if isinstance(error, LLMInvalidResponseError):
        return grpc.StatusCode.INTERNAL
    return grpc.StatusCode.INTERNAL


def _generate_initial_state(request) -> AgentState:
    return {
        "messages": [HumanMessage(content=request.prompt)],
        "history": [],
        "user_id": request.user_id,
        "query": request.prompt,
        "rag_context": "",
        "reflection_score": 0.0,
        "retry_count": 0,
        "final_answer": "",
        "low_confidence": False,
        "llm_override": request.llm or None,
        "reflect_llm_override": None,
        "active_agent": None,
        "agent_dispatch_score": 0.0,
        "unavailable_tools": [],
        "tools_enabled": not request.disable_tools,
    }


def _append_state_messages(state: AgentState, update: dict) -> None:
    state["messages"].extend(update.get("messages", []))
    if "unavailable_tools" in update:
        state["unavailable_tools"] = update["unavailable_tools"]


def _run_stateless_generate(request) -> str:
    state = _generate_initial_state(request)
    if not request.disable_rag:
        state.update(rag_retrieve(state))

    for _ in range(GENERATE_MAX_TOOL_ROUNDS + 1):
        plan_update = plan_and_call(state)
        _append_state_messages(state, plan_update)

        last_message = state["messages"][-1]
        if not isinstance(last_message, AIMessage):
            raise LLMInvalidResponseError("LLM provider returned an invalid response")
        if not getattr(last_message, "tool_calls", None):
            return last_message.content
        if not state.get("tools_enabled", True):
            raise LLMInvalidResponseError("LLM provider returned an invalid response")

        tool_update = execute_tools(state)
        _append_state_messages(state, tool_update)

    raise LLMInvalidResponseError("LLM provider returned an invalid response")


class JarvisServicer(jarvis_pb2_grpc.JarvisServiceServicer):

    def Chat(self, request, context):
        initial_state: AgentState = {
            "messages": [HumanMessage(content=request.message)],
            "history": [],
            "user_id": request.user_id,
            "query": request.message,
            "rag_context": "",
            "reflection_score": 0.0,
            "retry_count": 0,
            "final_answer": "",
            "low_confidence": False,
            "llm_override": request.llm or None,
            "reflect_llm_override": request.reflect_llm or None,
            "active_agent": None,
            "agent_dispatch_score": 0.0,
            "unavailable_tools": [],
        }
        try:
            result = graph.invoke(initial_state)
        except LLMError as error:
            context.set_code(_llm_grpc_status(error))
            context.set_details(str(error))
            return jarvis_pb2.ChatResponse()
        except Exception as error:
            logger.error(
                "%s Unexpected gRPC request failure",
                format_log_tags(
                    ("方法", "Chat"),
                    ("结果", "失败"),
                    ("错误", type(error).__name__),
                    ("位置", _error_location(error)),
                ),
            )
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("internal Jarvis Chat error")
            return jarvis_pb2.ChatResponse()
        return jarvis_pb2.ChatResponse(
            answer=result["final_answer"],
            low_confidence=result["low_confidence"],
        )

    def Generate(self, request, context):
        try:
            text = _run_stateless_generate(request)
        except LLMError as error:
            context.set_code(_llm_grpc_status(error))
            context.set_details(str(error))
            return jarvis_pb2.GenerateResponse()
        except Exception as error:
            logger.error(
                "%s Unexpected gRPC request failure",
                format_log_tags(
                    ("方法", "Generate"),
                    ("操作", request.operation or "unspecified"),
                    ("结果", "失败"),
                    ("错误", type(error).__name__),
                    ("位置", _error_location(error)),
                ),
            )
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("internal Jarvis Generate error")
            return jarvis_pb2.GenerateResponse()
        return jarvis_pb2.GenerateResponse(text=text)

    def Ingest(self, request, context):
        try:
            know_mem.store_knowledge(request.content, request.source_url, request.user_id)
            return jarvis_pb2.IngestResponse(success=True)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return jarvis_pb2.IngestResponse()

    def GetMemory(self, request, context):
        try:
            records = conv_mem.get_history_records(request.user_id)
            entries = [
                jarvis_pb2.ConversationEntry(
                    role=r["role"],
                    content=r["content"],
                    created_at=r.get("created_at", ""),
                )
                for r in records
            ]
            return jarvis_pb2.MemoryResponse(entries=entries)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return jarvis_pb2.MemoryResponse()

    def DeleteMemory(self, request, context):
        try:
            conv_mem.delete_history(request.user_id)
            return jarvis_pb2.DeleteResponse(success=True)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return jarvis_pb2.DeleteResponse()
