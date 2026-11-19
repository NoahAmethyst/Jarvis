import math
import os
from dotenv import load_dotenv

load_dotenv()

HTTP_PORT = int(os.getenv("HTTP_PORT", "8080"))
GRPC_PORT = int(os.getenv("GRPC_PORT", "9090"))
LLM_CONFIG_PATH = os.getenv("LLM_CONFIG_PATH", "llm.yaml")

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

EMBED_MODEL = os.getenv("EMBED_MODEL", "siliconflow/Qwen/Qwen3-Embedding-8B")
VECTOR_SIZE = int(os.getenv("VECTOR_SIZE", "4096"))

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/jarvis")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

REFLECTION_SCORE_THRESHOLD = float(os.getenv("REFLECTION_SCORE_THRESHOLD", "0.7"))
REFLECTION_MAX_RETRIES = int(os.getenv("REFLECTION_MAX_RETRIES", "3"))
KNOWLEDGE_MIN_LENGTH = int(os.getenv("KNOWLEDGE_MIN_LENGTH", "40"))
if not 1 <= KNOWLEDGE_MIN_LENGTH <= 2400:
    raise ValueError("KNOWLEDGE_MIN_LENGTH must be between 1 and 2400")
RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.70"))
RAG_MAX_DOCUMENT_CHARS = int(os.getenv("RAG_MAX_DOCUMENT_CHARS", "1200"))
RAG_MAX_CONTEXT_CHARS = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "3000"))
if not math.isfinite(RAG_MIN_SCORE) or not 0 <= RAG_MIN_SCORE <= 1:
    raise ValueError("RAG_MIN_SCORE must be between 0 and 1")
if min(RAG_MAX_DOCUMENT_CHARS, RAG_MAX_CONTEXT_CHARS) < 1:
    raise ValueError("RAG character limits must be positive")

AGENTS_DIR = os.getenv("AGENTS_DIR", ".agents/skills")
AGENT_DISPATCH_THRESHOLD = float(os.getenv("AGENT_DISPATCH_THRESHOLD", "0.6"))

QQBOT_GRPC_TARGET = os.getenv("QQBOT_GRPC_TARGET", "qq-bot:9090")
LLM_ERROR_QQ_USER_ID = os.getenv("LLM_ERROR_QQ_USER_ID", "")
