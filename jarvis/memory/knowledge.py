import hashlib
import logging
from datetime import datetime, timezone
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from langchain_openai import OpenAIEmbeddings
from jarvis.config import (
    QDRANT_URL, EMBED_MODEL, VECTOR_SIZE,
    SILICONFLOW_API_KEY, SILICONFLOW_BASE_URL,
)
from jarvis.llm.errors import LLMConfigurationError, LLMCredentialError
from jarvis.logging_config import format_log_tags
from jarvis.execution_logging import action_trace

logger = logging.getLogger(__name__)
COLLECTION_NAME = "jarvis_knowledge"


def _parse_embed_model(model_spec: str) -> tuple[str, str, str]:
    """Return (provider, model_id, base_url) from 'provider/model_id' spec."""
    parts = model_spec.split("/", 1)
    if len(parts) != 2:
        raise LLMConfigurationError("embedding model configuration is invalid")
    provider, model_id = (part.strip() for part in parts)
    if not provider or not model_id:
        raise LLMConfigurationError("embedding model configuration is invalid")
    if provider == "siliconflow":
        return (provider, model_id, SILICONFLOW_BASE_URL)
    if provider == "openai":
        return (provider, model_id, "")
    raise LLMConfigurationError("embedding model configuration is invalid")


def _get_embeddings(
    model_spec: str | None = None,
    request_timeout: float | None = None,
    max_retries: int | None = None,
) -> OpenAIEmbeddings:
    from jarvis.config import OPENAI_API_KEY
    selected_model = EMBED_MODEL if model_spec is None else model_spec
    provider, model_id, base_url = _parse_embed_model(selected_model)
    if provider == "siliconflow":
        api_key = SILICONFLOW_API_KEY
    else:
        api_key = OPENAI_API_KEY
    if not api_key:
        raise LLMCredentialError("embedding provider credential is missing")
    kwargs: dict = dict(model=model_id, api_key=api_key)
    if base_url:
        kwargs["base_url"] = base_url
    if request_timeout is not None:
        kwargs["request_timeout"] = request_timeout
    if max_retries is not None:
        kwargs["max_retries"] = max_retries
    return OpenAIEmbeddings(**kwargs)


def _get_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def init_collection():
    client = _get_client()
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
    logger.info(
        "%s Knowledge collection initialized",
        format_log_tags(
            ("组件", "Qdrant"),
            ("集合", COLLECTION_NAME),
            ("状态", "就绪"),
        ),
    )


def store_knowledge(text: str, source_url: str, user_id: str):
    with action_trace("知识向量生成", 模型=EMBED_MODEL, 字符数=len(text)) as feedback:
        embeddings = _get_embeddings()
        vector = embeddings.embed_query(text)
        feedback["向量维度"] = len(vector)
    client = _get_client()
    key = f"{user_id}:{source_url}:{text}"
    point_id = int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2**63)
    with action_trace("知识落库", 组件="Qdrant", 集合=COLLECTION_NAME) as feedback:
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "text": text,
                    "source_url": source_url,
                    "user_id": user_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )],
        )
        feedback["写入数"] = 1


def retrieve_knowledge(query: str, user_id: str, top_k: int = 5) -> str:
    with action_trace("检索向量生成", 模型=EMBED_MODEL) as feedback:
        embeddings = _get_embeddings()
        vector = embeddings.embed_query(query)
        feedback["向量维度"] = len(vector)
    client = _get_client()
    with action_trace("查询知识库", 组件="Qdrant", TopK=top_k) as feedback:
        response = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            query_filter=Filter(
                must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
            ),
            limit=top_k,
        )
        results = response.points
        feedback["命中数"] = len(results)
        context = "\n\n---\n\n".join(r.payload["text"] for r in results)
        feedback["知识字符数"] = len(context)
        return context
