import os
from dotenv import load_dotenv

load_dotenv()

HTTP_PORT = int(os.getenv("HTTP_PORT", "8080"))
GRPC_PORT = int(os.getenv("GRPC_PORT", "9090"))

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

ANSWER_LLM = os.getenv("ANSWER_LLM", "siliconflow/deepseek-ai/DeepSeek-V4-Pro")
REFLECT_LLM = os.getenv("REFLECT_LLM", "siliconflow/moonshotai/Kimi-K2.6")
EMBED_MODEL = os.getenv("EMBED_MODEL", "siliconflow/Qwen/Qwen3-Embedding-8B")
VECTOR_SIZE = int(os.getenv("VECTOR_SIZE", "4096"))

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/jarvis")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

REFLECTION_SCORE_THRESHOLD = float(os.getenv("REFLECTION_SCORE_THRESHOLD", "0.7"))
REFLECTION_MAX_RETRIES = int(os.getenv("REFLECTION_MAX_RETRIES", "3"))
KNOWLEDGE_MIN_LENGTH = int(os.getenv("KNOWLEDGE_MIN_LENGTH", "200"))
