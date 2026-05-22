from typing import Annotated
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    history: list[BaseMessage]
    user_id: str
    query: str
    rag_context: str
    reflection_score: float
    retry_count: int
    final_answer: str
    low_confidence: bool
    llm_override: str | None
    reflect_llm_override: str | None
