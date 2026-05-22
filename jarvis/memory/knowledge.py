import logging
from datetime import datetime, timezone
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from langchain_openai import OpenAIEmbeddings
from jarvis.config import (
    QDRANT_URL, EMBED_MODEL, VECTOR_SIZE,
    SILICONFLOW_API_KEY, SILICONFLOW_BASE_URL,
)

logger = logging.getLogger(__name__)
COLLECTION_NAME = "jarvis_knowledge"


def _parse_embed_model(model_spec: str) -> tuple[str, str, str]:
    """Return (provider, model_id, base_url) from 'provider/model_id' spec."""
    parts = model_spec.split("/", 1)
    if len(parts) != 2:
        return ("siliconflow", model_spec, SILICONFLOW_BASE_URL)
    provider, model_id = parts
    if provider == "siliconflow":
        return (provider, model_id, SILICONFLOW_BASE_URL)
    return (provider, model_id, "")


def _get_embeddings() -> OpenAIEmbeddings:
    provider, model_id, base_url = _parse_embed_model(EMBED_MODEL)
    kwargs = dict(model=model_id, api_key=SILICONFLOW_API_KEY)
    if base_url:
        kwargs["base_url"] = base_url
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
    logger.info("Qdrant collection ready: %s", COLLECTION_NAME)


def store_knowledge(text: str, source_url: str, user_id: str):
    embeddings = _get_embeddings()
    vector = embeddings.embed_query(text)
    client = _get_client()
    point_id = abs(hash(f"{user_id}:{source_url}:{text[:100]}")) % (2**63)
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


def retrieve_knowledge(query: str, user_id: str, top_k: int = 5) -> str:
    embeddings = _get_embeddings()
    vector = embeddings.embed_query(query)
    client = _get_client()
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=vector,
        query_filter=Filter(
            must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        ),
        limit=top_k,
    )
    if not results:
        return ""
    return "\n\n---\n\n".join(r.payload["text"] for r in results)
