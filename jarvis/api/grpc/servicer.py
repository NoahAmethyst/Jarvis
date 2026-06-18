import grpc
from jarvis.api.grpc import jarvis_pb2, jarvis_pb2_grpc
from jarvis.agent.graph import graph
from jarvis.agent.state import AgentState
from jarvis.llm.router import ProviderNotFoundError, ProviderUnavailableError
from jarvis.memory import conversation as conv_mem
from jarvis.memory import knowledge as know_mem
from langchain_core.messages import HumanMessage


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
        }
        try:
            result = graph.invoke(initial_state)
        except ProviderNotFoundError as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return jarvis_pb2.ChatResponse()
        except ProviderUnavailableError as e:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details(str(e))
            return jarvis_pb2.ChatResponse()
        return jarvis_pb2.ChatResponse(
            answer=result["final_answer"],
            low_confidence=result["low_confidence"],
        )

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
