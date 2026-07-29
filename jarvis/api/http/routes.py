from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from jarvis.agent.graph import graph
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
from jarvis.memory import conversation as conv_mem
from jarvis.memory import knowledge as know_mem
from langchain_core.messages import HumanMessage

app = FastAPI(title="Jarvis", version="0.1.0")
app.state.ready = False


class ChatRequest(BaseModel):
    message: str
    user_id: str
    llm: str | None = None
    reflect_llm: str | None = None


class ChatResponse(BaseModel):
    answer: str
    low_confidence: bool


class IngestRequest(BaseModel):
    content: str
    source_url: str
    user_id: str


@app.get("/health/live", include_in_schema=False)
async def health_live():
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
async def health_ready():
    if not app.state.ready:
        raise HTTPException(status_code=503, detail="not ready")
    return {"status": "ready"}


def _llm_http_status(error: LLMError) -> int:
    if isinstance(error, (LLMContextLimitError, LLMInvalidRequestError)):
        return 400
    if isinstance(error, LLMConfigurationError):
        return 500
    if isinstance(error, LLMRateLimitError):
        return 429
    if isinstance(error, LLMTimeoutError):
        return 504
    if isinstance(error, LLMUnavailableError):
        return 503
    if isinstance(error, LLMInvalidResponseError):
        return 502
    return 500


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    initial_state: AgentState = {
        "messages": [HumanMessage(content=req.message)],
        "history": [],
        "user_id": req.user_id,
        "query": req.message,
        "rag_context": "",
        "reflection_score": 0.0,
        "retry_count": 0,
        "final_answer": "",
        "low_confidence": False,
        "llm_override": req.llm,
        "reflect_llm_override": req.reflect_llm,
        "active_agent": None,
        "agent_dispatch_score": 0.0,
    }
    try:
        result = graph.invoke(initial_state)
    except LLMError as error:
        raise HTTPException(
            status_code=_llm_http_status(error),
            detail=str(error),
        ) from None
    return ChatResponse(answer=result["final_answer"], low_confidence=result["low_confidence"])


@app.post("/ingest")
def ingest(req: IngestRequest):
    try:
        know_mem.store_knowledge(req.content, req.source_url, req.user_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memory/{uid}")
def get_memory(uid: str):
    try:
        return conv_mem.get_history_records(uid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/memory/{uid}")
def delete_memory(uid: str):
    try:
        conv_mem.delete_history(uid)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
