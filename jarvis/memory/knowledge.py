import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import unquote_plus, urlsplit, urlunsplit
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue,
    MatchAny, UpdateMode, UpdateStatus,
)
from langchain_openai import OpenAIEmbeddings
from jarvis.config import (
    QDRANT_URL, EMBED_MODEL, VECTOR_SIZE,
    SILICONFLOW_API_KEY, SILICONFLOW_BASE_URL,
    RAG_MIN_SCORE, RAG_MAX_DOCUMENT_CHARS, RAG_MAX_CONTEXT_CHARS,
)
from jarvis.llm.errors import LLMConfigurationError, LLMCredentialError
from jarvis.logging_config import format_log_tags
from jarvis.execution_logging import action_trace

logger = logging.getLogger(__name__)
COLLECTION_NAME = "jarvis_knowledge"
_CONTEXT_SEPARATOR = "\n\n---\n\n"
_LEGACY_SEARCH_HEADER = re.compile(r"(?:\A|\n\n)Title: [^\r\n]*\r?\nURL: ([^\s]+)[ \t]*\r?\n")
_TRACKING_PARAMS = {"fbclid", "gclid", "msclkid"}
_CREDENTIAL_PARAMS = {"api_key", "apikey", "key", "access_token", "token", "signature", "sig", "password", "auth", "authorization"}


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


def canonical_web_url(url: str) -> str:
    url = url.strip()
    if not url or len(url) > 2048 or any(c.isspace() for c in url) or "\\" in url:
        return ""
    try:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username is not None:
            return ""
        host = parts.hostname.lower()
        port = parts.port
    except ValueError:
        return ""
    netloc = f"[{host}]" if ":" in host else host
    if port is not None and (parts.scheme, port) not in {("http", 80), ("https", 443)}:
        netloc += f":{port}"
    query = []
    for param in parts.query.split("&"):
        name = unquote_plus(param.partition("=")[0]).casefold()
        if name in _CREDENTIAL_PARAMS or name.startswith(("x-amz-", "x-goog-")):
            return ""
        if param and name not in _TRACKING_PARAMS and not name.startswith("utm_"):
            query.append(param)
    return urlunsplit((parts.scheme, netloc, parts.path or "/", "&".join(query), ""))


def _normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def content_digest(text: str) -> str:
    return hashlib.sha256(_normalize_text(text).encode()).hexdigest()


def _legacy_search_sources(text: str):
    headers = list(_LEGACY_SEARCH_HEADER.finditer(text))
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        yield canonical_web_url(header[1]), text[header.end():end].strip()


@dataclass
class ExistingWebKnowledge:
    urls: set[str] = field(default_factory=set)
    hashes: set[str] = field(default_factory=set)
    quarantined_texts: set[str] = field(default_factory=set)

    def contains_quarantined_excerpt(self, excerpt: str) -> bool:
        normalized = _normalize_text(excerpt)
        return bool(normalized) and any(
            normalized in text or (len(text) >= 24 and text in normalized)
            for text in self.quarantined_texts
        )


def existing_web_knowledge(user_id: str, urls: set[str], digests: set[str]) -> ExistingWebKnowledge:
    """Look up matching identities and this user's quarantined entries."""
    conditions = [FieldCondition(key="rag_quarantined", match=MatchValue(value=True))]
    if urls:
        conditions.extend(FieldCondition(key=key, match=MatchAny(any=sorted(urls)))
                          for key in ("source_url", "canonical_url"))
    if digests:
        conditions.extend(FieldCondition(key=key, match=MatchAny(any=sorted(digests)))
                          for key in ("content_hash", "raw_hash"))
    existing = ExistingWebKnowledge()
    client = _get_client()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=Filter(
                must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))],
                should=conditions,
            ),
            offset=offset, limit=64, with_vectors=False,
            with_payload=["source_url", "content_hash", "raw_hash", "rag_quarantined", "text"],
        )
        for point in points:
            payload = point.payload or {}
            source_url = payload.get("source_url")
            if isinstance(source_url, str):
                canonical_url = canonical_web_url(source_url)
                if canonical_url:
                    existing.urls.add(canonical_url)
            existing.hashes.update(payload[key] for key in ("raw_hash", "content_hash")
                                   if isinstance(payload.get(key), str))
            raw = payload.get("text")
            if not isinstance(raw, str) or not raw:
                continue
            existing.hashes.add(content_digest(raw))
            if payload.get("rag_quarantined") is not True:
                continue
            existing.quarantined_texts.add(_normalize_text(raw))
            if source_url == "tool:web_search":
                for legacy_url, legacy_text in _legacy_search_sources(raw):
                    if legacy_url:
                        existing.urls.add(legacy_url)
                    existing.hashes.add(content_digest(legacy_text))
                    if legacy_text:
                        existing.quarantined_texts.add(_normalize_text(legacy_text))
        if offset is None:
            return existing


def _point_id(key: str) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2**63)


def _insert_knowledge(text: str, payload: dict, point_id: int) -> bool:
    client = _get_client()
    if client.retrieve(collection_name=COLLECTION_NAME, ids=[point_id], with_payload=False):
        return False
    # Older servers could ignore the unknown update_mode field and overwrite a point.
    version = re.match(r"^(\d+)\.(\d+)\.", client.info().version)
    if not version or tuple(map(int, version.groups())) < (1, 17):
        raise RuntimeError("Knowledge writes require Qdrant 1.17 or newer")
    with action_trace("知识向量生成", 模型=EMBED_MODEL, 字符数=len(text)) as feedback:
        embeddings = _get_embeddings()
        vector = embeddings.embed_query(text)
        feedback["向量维度"] = len(vector)
    with action_trace("知识落库", 组件="Qdrant", 集合=COLLECTION_NAME) as feedback:
        write_id = uuid4().hex
        result = client.upsert(
            collection_name=COLLECTION_NAME,
            wait=True,
            update_mode=UpdateMode.INSERT_ONLY,
            points=[PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "text": text,
                    "content_hash": content_digest(text),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "write_id": write_id,
                    **payload,
                },
            )],
        )
        if result.status != UpdateStatus.COMPLETED:
            raise RuntimeError("Qdrant did not confirm knowledge insert")
        points = client.retrieve(collection_name=COLLECTION_NAME, ids=[point_id], with_payload=["write_id"])
        if not points:
            raise RuntimeError("Qdrant returned no point after insert")
        inserted = (points[0].payload or {}).get("write_id") == write_id
        feedback["写入数"] = int(inserted)
        return inserted


def store_knowledge(text: str, source_url: str, user_id: str) -> bool:
    """Explicit ingestion preserves the existing point identity and audit payload."""
    canonical_url = canonical_web_url(source_url)
    quarantined = existing_web_knowledge(user_id, set(), set())
    if (canonical_url in quarantined.urls or content_digest(text) in quarantined.hashes
            or quarantined.contains_quarantined_excerpt(text)):
        with action_trace("知识落库", 组件="Qdrant", 集合=COLLECTION_NAME) as feedback:
            feedback.update(状态="跳过", 原因="已隔离", 写入数=0)
        return False
    return _insert_knowledge(
        text,
        {"source_url": source_url, "user_id": user_id, "canonical_url": canonical_url},
        _point_id(f"{user_id}:{source_url}:{text}"),
    )


def store_web_knowledge(text: str, source_url: str, user_id: str, raw_hash: str) -> bool:
    """One automatic record per user and canonical source, immutable on re-ingest."""
    return _insert_knowledge(
        text,
        {"source_url": source_url, "user_id": user_id, "raw_hash": raw_hash},
        _point_id(f"web:{len(user_id)}:{user_id}:{source_url}"),
    )


def retrieve_knowledge(query: str, user_id: str, top_k: int = 5) -> str:
    with action_trace("检索向量生成", 模型=EMBED_MODEL) as feedback:
        embeddings = _get_embeddings()
        vector = embeddings.embed_query(query)
        feedback["向量维度"] = len(vector)
    client = _get_client()
    with action_trace("查询知识库", 组件="Qdrant", TopK=top_k, 最低相似度=RAG_MIN_SCORE) as feedback:
        response = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            query_filter=Filter(
                must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))],
                must_not=[FieldCondition(key="rag_quarantined", match=MatchValue(value=True))],
            ),
            limit=top_k,
            score_threshold=RAG_MIN_SCORE,
        )
        results = response.points
        feedback["命中数"] = len(results)
        snippets = []
        remaining = RAG_MAX_CONTEXT_CHARS
        for result in results:
            payload = result.payload or {}
            if not result.score >= RAG_MIN_SCORE or payload.get("rag_quarantined") is True:
                continue
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            separator_chars = len(_CONTEXT_SEPARATOR) if snippets else 0
            budget = min(RAG_MAX_DOCUMENT_CHARS, remaining - separator_chars)
            if budget <= 0:
                break
            snippet = text.strip()[:budget]
            snippets.append(snippet)
            remaining -= len(snippet) + separator_chars
        context = _CONTEXT_SEPARATOR.join(snippets)
        feedback["注入条数"] = len(snippets)
        feedback["知识字符数"] = len(context)
        return context
