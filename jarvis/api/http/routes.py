from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from jarvis.agent.graph import graph
from jarvis.agent.state import AgentState
from jarvis.llm.router import ProviderNotFoundError, ProviderUnavailableError
from jarvis.memory import conversation as conv_mem
from jarvis.memory import knowledge as know_mem
from langchain_core.messages import HumanMessage

app = FastAPI(title="Jarvis", version="0.1.0")


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
    }
    try:
        result = graph.invoke(initial_state)
    except ProviderNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ProviderUnavailableError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return ChatResponse(answer=result["final_answer"], low_confidence=result["low_confidence"])


@app.post("/ingest")
def ingest(req: IngestRequest):
    know_mem.store_knowledge(req.content, req.source_url, req.user_id)
    return {"success": True}


@app.get("/memory/{uid}")
def get_memory(uid: str):
    return conv_mem.get_history_records(uid)


@app.delete("/memory/{uid}")
def delete_memory(uid: str):
    conv_mem.delete_history(uid)
    return {"success": True}
