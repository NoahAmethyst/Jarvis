from typing import Annotated, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from jarvis.agents import AgentDefinition


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
    llm_override: Optional[str]
    reflect_llm_override: Optional[str]
    active_agent: Optional[AgentDefinition]
    agent_dispatch_score: float
