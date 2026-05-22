# Jarvis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a LangGraph-based LLM assistant backend with tool chain, Memory, RAG, and Self-critique Reflection, exposing FastAPI (HTTP :8080) and gRPC (:9090) services.

**Architecture:** LangGraph state machine with 5 nodes (memory_load → rag_retrieve → plan_and_call ⇄ tool_node → reflect → memory_write). A pluggable LLM Provider layer (SiliconFlow/OpenAI/Claude) and a decorator-based tool registry allow extension without touching the graph.

**Tech Stack:** Python 3.11+, LangGraph 0.2+, LangChain 0.3+, FastAPI, gRPC/protobuf, Qdrant, PostgreSQL, psycopg2, requests, BeautifulSoup4.

---

## File Map

```
jarvis/
├── __init__.py
├── config.py
├── main.py
├── llm/
│   ├── __init__.py
│   ├── base.py              # BaseLLMProvider ABC
│   ├── siliconflow.py       # SiliconFlow provider
│   ├── openai.py            # OpenAI provider
│   ├── claude.py            # Claude provider
│   └── router.py            # "provider/model_id" routing
├── tools/
│   ├── __init__.py
│   ├── registry.py          # @register_tool decorator
│   ├── search.py            # web_search tool
│   └── scraper.py           # web_scrape tool
├── memory/
│   ├── __init__.py
│   ├── conversation.py      # PostgreSQL conversation history
│   └── knowledge.py         # Qdrant vector knowledge store
├── agent/
│   ├── __init__.py
│   ├── state.py             # AgentState TypedDict
│   ├── graph.py             # LangGraph graph definition
│   └── nodes/
│       ├── __init__.py
│       ├── memory_load.py
│       ├── rag_retrieve.py
│       ├── plan_and_call.py
│       ├── reflect.py
│       └── memory_write.py
├── api/
│   ├── __init__.py
│   ├── http/
│   │   ├── __init__.py
│   │   └── routes.py        # FastAPI app + endpoints
│   └── grpc/
│       ├── __init__.py
│       ├── jarvis.proto
│       ├── server.py        # gRPC server factory
│       └── servicer.py      # JarvisServicer implementation
└── tests/
    ├── unit/
    │   ├── test_llm_router.py
    │   ├── test_reflect_node.py
    │   └── test_tool_registry.py
    ├── integration/
    │   ├── test_graph_flow.py
    │   └── test_rag_pipeline.py
    └── e2e/
        └── test_api.py
```

---

## Task 1: Project Setup

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `jarvis/__init__.py`
- Create: `jarvis/config.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "jarvis"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "langchain>=0.3",
    "langgraph>=0.2",
    "langchain-openai>=0.2",
    "langchain-anthropic>=0.3",
    "langchain-core>=0.3",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "grpcio>=1.62",
    "grpcio-tools>=1.62",
    "protobuf>=4.25",
    "qdrant-client>=1.9",
    "psycopg2-binary>=2.9",
    "requests>=2.31",
    "beautifulsoup4>=4.12",
    "python-dotenv>=1.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["jarvis*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: Create `.env.example`**

```
HTTP_PORT=8080
GRPC_PORT=9090

SILICONFLOW_API_KEY=your_key_here
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here

ANSWER_LLM=siliconflow/deepseek-ai/DeepSeek-V4-Pro
REFLECT_LLM=siliconflow/moonshotai/Kimi-K2.6
EMBED_MODEL=siliconflow/Qwen/Qwen3-Embedding-8B
VECTOR_SIZE=4096

QDRANT_URL=http://localhost:6333
POSTGRES_DSN=postgresql://postgres:postgres@localhost:5432/jarvis

TAVILY_API_KEY=your_key_here

REFLECTION_SCORE_THRESHOLD=0.7
REFLECTION_MAX_RETRIES=3
KNOWLEDGE_MIN_LENGTH=200
```

- [ ] **Step 3: Create `jarvis/config.py`**

```python
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
```

- [ ] **Step 4: Create empty `jarvis/__init__.py`**

```python
```

- [ ] **Step 5: Install dependencies**

```bash
pip install -e ".[dev]"
```

Expected: no errors, all packages installed.

- [ ] **Step 6: Verify import**

```bash
python -c "from jarvis.config import HTTP_PORT; print(HTTP_PORT)"
```

Expected: `8080`

- [ ] **Step 7: Commit**

```bash
git init
git add pyproject.toml .env.example jarvis/__init__.py jarvis/config.py
git commit -m "ADD: project setup, config, and dependencies"
```

---

## Task 2: LLM Provider Layer

**Files:**
- Create: `jarvis/llm/__init__.py`
- Create: `jarvis/llm/base.py`
- Create: `jarvis/llm/siliconflow.py`
- Create: `jarvis/llm/openai.py`
- Create: `jarvis/llm/claude.py`
- Create: `jarvis/llm/router.py`
- Create: `tests/__init__.py`, `tests/unit/__init__.py`
- Create: `tests/unit/test_llm_router.py`

- [ ] **Step 1: Write failing tests**

Create `tests/__init__.py`, `tests/unit/__init__.py` (both empty), then:

```python
# tests/unit/test_llm_router.py
import pytest
from unittest.mock import patch, MagicMock
from jarvis.llm.router import get_model, ProviderNotFoundError, ProviderUnavailableError


def test_get_model_unknown_provider():
    with pytest.raises(ProviderNotFoundError) as exc_info:
        get_model("nonexistent/some-model")
    assert str(exc_info.value) == "provider not exist"


def test_get_model_invalid_format():
    with pytest.raises(ProviderNotFoundError) as exc_info:
        get_model("no-slash-here")
    assert str(exc_info.value) == "provider not exist"


def test_get_model_provider_unavailable():
    with patch("jarvis.llm.router.REGISTRY") as mock_registry:
        mock_provider = MagicMock()
        mock_provider.get_chat_model.side_effect = Exception("connection refused")
        mock_registry.__contains__ = MagicMock(return_value=True)
        mock_registry.__getitem__ = MagicMock(return_value=mock_provider)
        with pytest.raises(ProviderUnavailableError) as exc_info:
            get_model("siliconflow/some-model")
        assert "provider not working:connection refused" in str(exc_info.value)


def test_get_model_siliconflow_returns_chat_model():
    with patch("jarvis.llm.siliconflow.ChatOpenAI") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        result = get_model("siliconflow/deepseek-ai/DeepSeek-V4-Pro")
        mock_cls.assert_called_once()
        assert result is mock_instance


def test_get_model_model_id_with_slash():
    with patch("jarvis.llm.siliconflow.ChatOpenAI") as mock_cls:
        mock_cls.return_value = MagicMock()
        get_model("siliconflow/deepseek-ai/DeepSeek-V4-Pro")
        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["model"] == "deepseek-ai/DeepSeek-V4-Pro"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_llm_router.py -v
```

Expected: `ModuleNotFoundError: No module named 'jarvis.llm.router'`

- [ ] **Step 3: Create `jarvis/llm/__init__.py`** (empty)

- [ ] **Step 4: Create `jarvis/llm/base.py`**

```python
from abc import ABC, abstractmethod
from langchain_core.language_models import BaseChatModel


class BaseLLMProvider(ABC):
    @abstractmethod
    def get_chat_model(self, model_id: str, **kwargs) -> BaseChatModel: ...
```

- [ ] **Step 5: Create `jarvis/llm/siliconflow.py`**

```python
from langchain_openai import ChatOpenAI
from jarvis.config import SILICONFLOW_API_KEY, SILICONFLOW_BASE_URL
from jarvis.llm.base import BaseLLMProvider
from langchain_core.language_models import BaseChatModel


class SiliconFlowProvider(BaseLLMProvider):
    def get_chat_model(self, model_id: str, **kwargs) -> BaseChatModel:
        return ChatOpenAI(
            model=model_id,
            api_key=SILICONFLOW_API_KEY,
            base_url=SILICONFLOW_BASE_URL,
            **kwargs,
        )
```

- [ ] **Step 6: Create `jarvis/llm/openai.py`**

```python
from langchain_openai import ChatOpenAI
from jarvis.config import OPENAI_API_KEY
from jarvis.llm.base import BaseLLMProvider
from langchain_core.language_models import BaseChatModel


class OpenAIProvider(BaseLLMProvider):
    def get_chat_model(self, model_id: str, **kwargs) -> BaseChatModel:
        return ChatOpenAI(
            model=model_id,
            api_key=OPENAI_API_KEY,
            **kwargs,
        )
```

- [ ] **Step 7: Create `jarvis/llm/claude.py`**

```python
from langchain_anthropic import ChatAnthropic
from jarvis.config import ANTHROPIC_API_KEY
from jarvis.llm.base import BaseLLMProvider
from langchain_core.language_models import BaseChatModel


class ClaudeProvider(BaseLLMProvider):
    def get_chat_model(self, model_id: str, **kwargs) -> BaseChatModel:
        return ChatAnthropic(
            model=model_id,
            api_key=ANTHROPIC_API_KEY,
            **kwargs,
        )
```

- [ ] **Step 8: Create `jarvis/llm/router.py`**

```python
import logging
from langchain_core.language_models import BaseChatModel
from jarvis.llm.siliconflow import SiliconFlowProvider
from jarvis.llm.openai import OpenAIProvider
from jarvis.llm.claude import ClaudeProvider

logger = logging.getLogger(__name__)

REGISTRY: dict = {
    "siliconflow": SiliconFlowProvider(),
    "openai": OpenAIProvider(),
    "claude": ClaudeProvider(),
}


class ProviderNotFoundError(ValueError):
    pass


class ProviderUnavailableError(RuntimeError):
    pass


def get_model(model_spec: str, **kwargs) -> BaseChatModel:
    parts = model_spec.split("/", 1)
    if len(parts) != 2:
        logger.error(f"Invalid model spec: {model_spec}")
        raise ProviderNotFoundError("provider not exist")

    provider_name, model_id = parts
    if provider_name not in REGISTRY:
        logger.error(f"Provider not found: {provider_name}")
        raise ProviderNotFoundError("provider not exist")

    try:
        return REGISTRY[provider_name].get_chat_model(model_id=model_id, **kwargs)
    except (ProviderNotFoundError, ProviderUnavailableError):
        raise
    except Exception as e:
        logger.error(f"Provider unavailable: {provider_name}, reason: {e}")
        raise ProviderUnavailableError(f"provider not working:{e}")
```

- [ ] **Step 9: Run tests**

```bash
pytest tests/unit/test_llm_router.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 10: Commit**

```bash
git add jarvis/llm/ tests/__init__.py tests/unit/
git commit -m "ADD: LLM provider layer with SiliconFlow, OpenAI, Claude and router"
```

---

## Task 3: Tool Registry + Built-in Tools

**Files:**
- Create: `jarvis/tools/__init__.py`
- Create: `jarvis/tools/registry.py`
- Create: `jarvis/tools/search.py`
- Create: `jarvis/tools/scraper.py`
- Create: `tests/unit/test_tool_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_tool_registry.py
import pytest
from jarvis.tools.registry import register_tool, get_tools, _REGISTRY


def setup_function():
    _REGISTRY.clear()


def test_register_tool_adds_to_registry():
    @register_tool(name="my_tool", description="A test tool")
    def my_tool(query: str) -> str:
        return f"result: {query}"

    tools = get_tools()
    names = [t.name for t in tools]
    assert "my_tool" in names


def test_get_tools_returns_callable_tools():
    @register_tool(name="echo_tool", description="Echoes input")
    def echo_tool(text: str) -> str:
        return text

    tools = get_tools()
    echo = next(t for t in tools if t.name == "echo_tool")
    assert echo.invoke({"text": "hello"}) == "hello"


def test_register_tool_preserves_original_function():
    @register_tool(name="passthrough", description="Passthrough")
    def passthrough(x: str) -> str:
        return x

    assert passthrough("test") == "test"


def test_multiple_tools_registered():
    @register_tool(name="tool_a", description="A")
    def tool_a(x: str) -> str:
        return x

    @register_tool(name="tool_b", description="B")
    def tool_b(x: str) -> str:
        return x

    assert len(get_tools()) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_tool_registry.py -v
```

Expected: `ModuleNotFoundError: No module named 'jarvis.tools'`

- [ ] **Step 3: Create `jarvis/tools/__init__.py`** (empty)

- [ ] **Step 4: Create `jarvis/tools/registry.py`**

```python
from typing import Callable
from langchain_core.tools import StructuredTool

_REGISTRY: dict[str, StructuredTool] = {}


def register_tool(name: str, description: str):
    def decorator(func: Callable) -> Callable:
        _REGISTRY[name] = StructuredTool.from_function(
            func=func,
            name=name,
            description=description,
        )
        return func
    return decorator


def get_tools() -> list[StructuredTool]:
    return list(_REGISTRY.values())
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/unit/test_tool_registry.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Create `jarvis/tools/search.py`**

```python
import requests
from jarvis.config import TAVILY_API_KEY
from jarvis.tools.registry import register_tool


@register_tool(name="web_search", description="Search the web for up-to-date information. Input: search query string.")
def web_search(query: str) -> str:
    resp = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": TAVILY_API_KEY, "query": query, "max_results": 5},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return "\n\n".join(
        f"Title: {r['title']}\nURL: {r['url']}\n{r['content']}" for r in results
    )
```

- [ ] **Step 7: Create `jarvis/tools/scraper.py`**

```python
import requests
from bs4 import BeautifulSoup
from jarvis.tools.registry import register_tool


@register_tool(name="web_scrape", description="Fetch and extract text content from a URL. Input: full URL string.")
def web_scrape(url: str) -> str:
    resp = requests.get(
        url,
        timeout=10,
        headers={"User-Agent": "Mozilla/5.0 (compatible; Jarvis/1.0)"},
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return text[:5000]
```

- [ ] **Step 8: Verify tools auto-register on import**

```python
# quick manual check
python -c "
import jarvis.tools.search
import jarvis.tools.scraper
from jarvis.tools.registry import get_tools
print([t.name for t in get_tools()])
"
```

Expected: `['web_search', 'web_scrape']`

- [ ] **Step 9: Commit**

```bash
git add jarvis/tools/ tests/unit/test_tool_registry.py
git commit -m "ADD: tool registry with @register_tool decorator, web_search and web_scrape tools"
```

---

## Task 4: Memory — Conversation (PostgreSQL)

**Files:**
- Create: `jarvis/memory/__init__.py`
- Create: `jarvis/memory/conversation.py`

> Requires a running PostgreSQL instance. For local dev: `docker run -d -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16`

- [ ] **Step 1: Create `jarvis/memory/__init__.py`** (empty)

- [ ] **Step 2: Create `jarvis/memory/conversation.py`**

```python
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from jarvis.config import POSTGRES_DSN

logger = logging.getLogger(__name__)


def _get_conn():
    return psycopg2.connect(POSTGRES_DSN)


def init_db():
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
            """)
        conn.commit()
    logger.info("Conversation DB initialized")


def load_history(user_id: str, limit: int = 20) -> list[BaseMessage]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT role, content FROM conversations
                   WHERE user_id = %s ORDER BY created_at DESC LIMIT %s""",
                (user_id, limit),
            )
            rows = cur.fetchall()
    messages: list[BaseMessage] = []
    for row in reversed(rows):
        if row["role"] == "human":
            messages.append(HumanMessage(content=row["content"]))
        else:
            messages.append(AIMessage(content=row["content"]))
    return messages


def save_message(user_id: str, role: str, content: str):
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO conversations (user_id, role, content) VALUES (%s, %s, %s)",
                (user_id, role, content),
            )
        conn.commit()


def delete_history(user_id: str):
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE user_id = %s", (user_id,))
        conn.commit()


def get_history_records(user_id: str) -> list[dict]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT role, content, created_at::text FROM conversations
                   WHERE user_id = %s ORDER BY created_at""",
                (user_id,),
            )
            return [dict(row) for row in cur.fetchall()]
```

- [ ] **Step 3: Smoke-test with running Postgres**

```bash
python -c "
from jarvis.memory.conversation import init_db, save_message, load_history, delete_history
init_db()
save_message('user1', 'human', 'hello')
save_message('user1', 'ai', 'hi there')
msgs = load_history('user1')
print([m.content for m in msgs])
delete_history('user1')
"
```

Expected: `['hello', 'hi there']`

- [ ] **Step 4: Commit**

```bash
git add jarvis/memory/
git commit -m "ADD: conversation memory with PostgreSQL (load/save/delete history)"
```

---

## Task 5: Memory — Knowledge (Qdrant)

**Files:**
- Create: `jarvis/memory/knowledge.py`

> Requires a running Qdrant instance. For local dev: `docker run -d -p 6333:6333 qdrant/qdrant`

- [ ] **Step 1: Create `jarvis/memory/knowledge.py`**

```python
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
```

- [ ] **Step 2: Write integration test**

Create `tests/integration/__init__.py` (empty), then:

```python
# tests/integration/test_rag_pipeline.py
import pytest
from unittest.mock import patch, MagicMock


def test_store_and_retrieve_knowledge():
    mock_embeddings = MagicMock()
    mock_embeddings.embed_query.return_value = [0.1] * 4096

    mock_client = MagicMock()
    mock_client.get_collections.return_value.collections = []
    mock_result = MagicMock()
    mock_result.payload = {"text": "Paris is the capital of France."}
    mock_client.search.return_value = [mock_result]

    with patch("jarvis.memory.knowledge._get_embeddings", return_value=mock_embeddings), \
         patch("jarvis.memory.knowledge._get_client", return_value=mock_client):
        from jarvis.memory.knowledge import init_collection, store_knowledge, retrieve_knowledge
        init_collection()
        store_knowledge("Paris is the capital of France.", "https://example.com", "user1")
        result = retrieve_knowledge("What is the capital of France?", "user1")

    assert "Paris" in result
    mock_client.upsert.assert_called_once()
    mock_client.search.assert_called_once()
```

- [ ] **Step 3: Run integration test**

```bash
pytest tests/integration/test_rag_pipeline.py -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add jarvis/memory/knowledge.py tests/integration/
git commit -m "ADD: knowledge memory with Qdrant (store/retrieve with embeddings)"
```

---

## Task 6: Agent State + Nodes

**Files:**
- Create: `jarvis/agent/__init__.py`
- Create: `jarvis/agent/state.py`
- Create: `jarvis/agent/nodes/__init__.py`
- Create: `jarvis/agent/nodes/memory_load.py`
- Create: `jarvis/agent/nodes/rag_retrieve.py`
- Create: `jarvis/agent/nodes/plan_and_call.py`
- Create: `jarvis/agent/nodes/reflect.py`
- Create: `jarvis/agent/nodes/memory_write.py`
- Create: `tests/unit/test_reflect_node.py`

- [ ] **Step 1: Write failing tests for reflect node**

```python
# tests/unit/test_reflect_node.py
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage
from jarvis.agent.state import AgentState


def _base_state(**overrides) -> AgentState:
    state: AgentState = {
        "messages": [HumanMessage(content="What is 2+2?"), AIMessage(content="2+2 equals 4.")],
        "history": [],
        "user_id": "test_user",
        "query": "What is 2+2?",
        "rag_context": "",
        "reflection_score": 0.0,
        "retry_count": 0,
        "final_answer": "",
        "low_confidence": False,
        "llm_override": None,
        "reflect_llm_override": None,
    }
    state.update(overrides)
    return state


def test_reflect_high_score_no_retry():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="0.9")

    with patch("jarvis.agent.nodes.reflect.get_model", return_value=mock_llm):
        from jarvis.agent.nodes.reflect import reflect
        result = reflect(_base_state())

    assert result["reflection_score"] == pytest.approx(0.9)
    assert result["final_answer"] == "2+2 equals 4."
    assert result["retry_count"] == 1
    assert result["low_confidence"] is False


def test_reflect_low_score_sets_low_confidence_after_max_retries():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="0.3")

    with patch("jarvis.agent.nodes.reflect.get_model", return_value=mock_llm):
        from jarvis.agent.nodes.reflect import reflect
        result = reflect(_base_state(retry_count=2))

    assert result["low_confidence"] is True
    assert result["retry_count"] == 3


def test_reflect_low_score_below_max_retries_not_low_confidence():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="0.3")

    with patch("jarvis.agent.nodes.reflect.get_model", return_value=mock_llm):
        from jarvis.agent.nodes.reflect import reflect
        result = reflect(_base_state(retry_count=0))

    assert result["low_confidence"] is False
    assert result["retry_count"] == 1


def test_reflect_malformed_score_defaults_to_half():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="I cannot score this.")

    with patch("jarvis.agent.nodes.reflect.get_model", return_value=mock_llm):
        from jarvis.agent.nodes.reflect import reflect
        result = reflect(_base_state())

    assert result["reflection_score"] == pytest.approx(0.5)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_reflect_node.py -v
```

Expected: `ModuleNotFoundError: No module named 'jarvis.agent'`

- [ ] **Step 3: Create `jarvis/agent/__init__.py`** (empty) and `jarvis/agent/nodes/__init__.py`** (empty)

- [ ] **Step 4: Create `jarvis/agent/state.py`**

```python
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
```

- [ ] **Step 5: Create `jarvis/agent/nodes/memory_load.py`**

```python
import logging
from jarvis.agent.state import AgentState
from jarvis.memory import conversation as conv_mem

logger = logging.getLogger(__name__)


def memory_load(state: AgentState) -> dict:
    try:
        history = conv_mem.load_history(state["user_id"])
        return {"history": history}
    except Exception as e:
        logger.warning("PostgreSQL unavailable, skipping history load: %s", e)
        return {"history": []}
```

- [ ] **Step 6: Create `jarvis/agent/nodes/rag_retrieve.py`**

```python
import logging
from jarvis.agent.state import AgentState
from jarvis.memory import knowledge as know_mem

logger = logging.getLogger(__name__)


def rag_retrieve(state: AgentState) -> dict:
    try:
        context = know_mem.retrieve_knowledge(state["query"], state["user_id"])
        return {"rag_context": context}
    except Exception as e:
        logger.warning("Qdrant unavailable, skipping RAG retrieval: %s", e)
        return {"rag_context": ""}
```

- [ ] **Step 7: Create `jarvis/agent/nodes/plan_and_call.py`**

```python
from langchain_core.messages import SystemMessage
from jarvis.agent.state import AgentState
from jarvis.config import ANSWER_LLM
from jarvis.llm.router import get_model
from jarvis.tools.registry import get_tools


def plan_and_call(state: AgentState) -> dict:
    model_spec = state.get("llm_override") or ANSWER_LLM
    llm = get_model(model_spec).bind_tools(get_tools())

    system_content = "You are Jarvis, a helpful AI assistant. Answer questions accurately and completely."
    if state.get("rag_context"):
        system_content += f"\n\nRelevant knowledge from memory:\n{state['rag_context']}"

    all_messages = [SystemMessage(content=system_content)] + state["history"] + state["messages"]
    response = llm.invoke(all_messages)
    return {"messages": [response]}
```

- [ ] **Step 8: Create `jarvis/agent/nodes/reflect.py`**

```python
import re
import logging
from langchain_core.messages import HumanMessage, AIMessage
from jarvis.agent.state import AgentState
from jarvis.config import REFLECT_LLM, REFLECTION_SCORE_THRESHOLD, REFLECTION_MAX_RETRIES
from jarvis.llm.router import get_model

logger = logging.getLogger(__name__)


def _extract_last_ai_answer(state: AgentState) -> str:
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            return msg.content
    return ""


def reflect(state: AgentState) -> dict:
    answer = _extract_last_ai_answer(state)
    model_spec = state.get("reflect_llm_override") or REFLECT_LLM
    llm = get_model(model_spec)

    prompt = (
        f"Rate this answer from 0.0 to 1.0 based on accuracy, completeness, "
        f"and whether it directly answers the question.\n\n"
        f"Question: {state['query']}\n"
        f"Answer: {answer}\n\n"
        f"Respond with ONLY a decimal number between 0.0 and 1.0."
    )
    response = llm.invoke([HumanMessage(content=prompt)])

    try:
        match = re.search(r"\d+\.?\d*", response.content)
        score = float(match.group()) if match else 0.5
        score = max(0.0, min(1.0, score))
    except (AttributeError, ValueError):
        score = 0.5
        logger.warning("Could not parse reflection score from: %s", response.content)

    retry_count = state["retry_count"] + 1
    low_confidence = retry_count >= REFLECTION_MAX_RETRIES and score < REFLECTION_SCORE_THRESHOLD

    return {
        "reflection_score": score,
        "retry_count": retry_count,
        "final_answer": answer,
        "low_confidence": low_confidence,
    }
```

- [ ] **Step 9: Create `jarvis/agent/nodes/memory_write.py`**

```python
import logging
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from jarvis.agent.state import AgentState
from jarvis.config import KNOWLEDGE_MIN_LENGTH
from jarvis.memory import conversation as conv_mem
from jarvis.memory import knowledge as know_mem

logger = logging.getLogger(__name__)


def memory_write(state: AgentState) -> dict:
    user_id = state["user_id"]

    try:
        for msg in state["messages"]:
            if isinstance(msg, HumanMessage):
                conv_mem.save_message(user_id, "human", msg.content)
            elif isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                conv_mem.save_message(user_id, "ai", msg.content)
    except Exception as e:
        logger.warning("Failed to save conversation history: %s", e)

    try:
        for msg in state["messages"]:
            if isinstance(msg, ToolMessage):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if len(content) > KNOWLEDGE_MIN_LENGTH:
                    know_mem.store_knowledge(content, f"tool:{msg.name}", user_id)
    except Exception as e:
        logger.warning("Failed to store tool results as knowledge: %s", e)

    return {}
```

- [ ] **Step 10: Run reflect tests**

```bash
pytest tests/unit/test_reflect_node.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 11: Commit**

```bash
git add jarvis/agent/ tests/unit/test_reflect_node.py
git commit -m "ADD: agent state and all 5 LangGraph nodes"
```

---

## Task 7: LangGraph Graph

**Files:**
- Create: `jarvis/agent/graph.py`
- Create: `tests/integration/test_graph_flow.py`

- [ ] **Step 1: Write failing integration test**

```python
# tests/integration/test_graph_flow.py
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage
from jarvis.agent.state import AgentState


def _make_graph_with_mocks():
    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm
    mock_llm.invoke.return_value = AIMessage(content="The answer is 42.")

    mock_reflect_llm = MagicMock()
    mock_reflect_llm.invoke.return_value = MagicMock(content="0.9")

    patches = [
        patch("jarvis.agent.nodes.memory_load.conv_mem.load_history", return_value=[]),
        patch("jarvis.agent.nodes.rag_retrieve.know_mem.retrieve_knowledge", return_value=""),
        patch("jarvis.agent.nodes.plan_and_call.get_model", return_value=mock_llm),
        patch("jarvis.agent.nodes.reflect.get_model", return_value=mock_reflect_llm),
        patch("jarvis.agent.nodes.memory_write.conv_mem.save_message"),
        patch("jarvis.agent.nodes.memory_write.know_mem.store_knowledge"),
    ]
    return patches


def test_graph_completes_single_turn():
    patches = _make_graph_with_mocks()
    for p in patches:
        p.start()

    try:
        from jarvis.agent.graph import graph
        initial_state: AgentState = {
            "messages": [HumanMessage(content="What is 6 times 7?")],
            "history": [],
            "user_id": "test_user",
            "query": "What is 6 times 7?",
            "rag_context": "",
            "reflection_score": 0.0,
            "retry_count": 0,
            "final_answer": "",
            "low_confidence": False,
            "llm_override": None,
            "reflect_llm_override": None,
        }
        result = graph.invoke(initial_state)
        assert result["final_answer"] == "The answer is 42."
        assert result["reflection_score"] == pytest.approx(0.9)
    finally:
        for p in patches:
            p.stop()


def test_graph_retries_on_low_score():
    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm
    # First call returns bad answer, second returns better
    mock_llm.invoke.side_effect = [
        AIMessage(content="I don't know."),
        AIMessage(content="6 times 7 is 42."),
    ]

    mock_reflect_llm = MagicMock()
    mock_reflect_llm.invoke.side_effect = [
        MagicMock(content="0.2"),  # first: low score → retry
        MagicMock(content="0.95"), # second: high score → done
    ]

    patches = [
        patch("jarvis.agent.nodes.memory_load.conv_mem.load_history", return_value=[]),
        patch("jarvis.agent.nodes.rag_retrieve.know_mem.retrieve_knowledge", return_value=""),
        patch("jarvis.agent.nodes.plan_and_call.get_model", return_value=mock_llm),
        patch("jarvis.agent.nodes.reflect.get_model", return_value=mock_reflect_llm),
        patch("jarvis.agent.nodes.memory_write.conv_mem.save_message"),
        patch("jarvis.agent.nodes.memory_write.know_mem.store_knowledge"),
    ]
    for p in patches:
        p.start()

    try:
        from jarvis.agent.graph import graph
        initial_state: AgentState = {
            "messages": [HumanMessage(content="What is 6 times 7?")],
            "history": [],
            "user_id": "test_user",
            "query": "What is 6 times 7?",
            "rag_context": "",
            "reflection_score": 0.0,
            "retry_count": 0,
            "final_answer": "",
            "low_confidence": False,
            "llm_override": None,
            "reflect_llm_override": None,
        }
        result = graph.invoke(initial_state)
        assert result["final_answer"] == "6 times 7 is 42."
        assert result["retry_count"] == 2
    finally:
        for p in patches:
            p.stop()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/integration/test_graph_flow.py -v
```

Expected: `ModuleNotFoundError: No module named 'jarvis.agent.graph'`

- [ ] **Step 3: Create `jarvis/agent/graph.py`**

```python
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from jarvis.agent.state import AgentState
from jarvis.agent.nodes.memory_load import memory_load
from jarvis.agent.nodes.rag_retrieve import rag_retrieve
from jarvis.agent.nodes.plan_and_call import plan_and_call
from jarvis.agent.nodes.reflect import reflect
from jarvis.agent.nodes.memory_write import memory_write
from jarvis.config import REFLECTION_SCORE_THRESHOLD, REFLECTION_MAX_RETRIES
from langchain_core.messages import AIMessage

import jarvis.tools.search  # noqa: F401 — registers web_search
import jarvis.tools.scraper  # noqa: F401 — registers web_scrape

from jarvis.tools.registry import get_tools


def _route_after_plan(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tool_node"
    return "reflect"


def _route_after_reflect(state: AgentState) -> str:
    if (
        state["reflection_score"] < REFLECTION_SCORE_THRESHOLD
        and state["retry_count"] < REFLECTION_MAX_RETRIES
    ):
        return "plan_and_call"
    return "memory_write"


builder = StateGraph(AgentState)

builder.add_node("memory_load", memory_load)
builder.add_node("rag_retrieve", rag_retrieve)
builder.add_node("plan_and_call", plan_and_call)
builder.add_node("tool_node", ToolNode(get_tools()))
builder.add_node("reflect", reflect)
builder.add_node("memory_write", memory_write)

builder.set_entry_point("memory_load")
builder.add_edge("memory_load", "rag_retrieve")
builder.add_edge("rag_retrieve", "plan_and_call")
builder.add_conditional_edges("plan_and_call", _route_after_plan, {
    "tool_node": "tool_node",
    "reflect": "reflect",
})
builder.add_edge("tool_node", "plan_and_call")
builder.add_conditional_edges("reflect", _route_after_reflect, {
    "plan_and_call": "plan_and_call",
    "memory_write": "memory_write",
})
builder.add_edge("memory_write", END)

graph = builder.compile()
```

- [ ] **Step 4: Run integration tests**

```bash
pytest tests/integration/test_graph_flow.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add jarvis/agent/graph.py tests/integration/test_graph_flow.py
git commit -m "ADD: LangGraph graph with conditional routing and retry loop"
```

---

## Task 8: FastAPI HTTP Service

**Files:**
- Create: `jarvis/api/__init__.py`
- Create: `jarvis/api/http/__init__.py`
- Create: `jarvis/api/http/routes.py`
- Create: `tests/e2e/__init__.py`
- Create: `tests/e2e/test_api.py`

- [ ] **Step 1: Write failing e2e tests**

```python
# tests/e2e/test_api.py
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch("jarvis.agent.nodes.memory_load.conv_mem.load_history", return_value=[]), \
         patch("jarvis.agent.nodes.rag_retrieve.know_mem.retrieve_knowledge", return_value=""), \
         patch("jarvis.agent.nodes.memory_write.conv_mem.save_message"), \
         patch("jarvis.agent.nodes.memory_write.know_mem.store_knowledge"):
        from jarvis.api.http.routes import app
        yield TestClient(app)


def test_chat_returns_answer(client):
    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm
    mock_llm.invoke.return_value = AIMessage(content="Paris is the capital of France.")

    mock_reflect = MagicMock()
    mock_reflect.invoke.return_value = MagicMock(content="0.95")

    with patch("jarvis.agent.nodes.plan_and_call.get_model", return_value=mock_llm), \
         patch("jarvis.agent.nodes.reflect.get_model", return_value=mock_reflect):
        resp = client.post("/chat", json={"message": "Capital of France?", "user_id": "u1"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "Paris is the capital of France."
    assert data["low_confidence"] is False


def test_chat_missing_user_id_returns_422(client):
    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 422


def test_ingest_stores_knowledge(client):
    with patch("jarvis.memory.knowledge.store_knowledge") as mock_store:
        resp = client.post("/ingest", json={
            "content": "LangGraph is a graph-based framework for LLM agents.",
            "source_url": "https://docs.langchain.com/langgraph",
            "user_id": "u1",
        })
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_get_memory_returns_history(client):
    with patch("jarvis.memory.conversation.get_history_records") as mock_hist:
        mock_hist.return_value = [
            {"role": "human", "content": "hi", "created_at": "2026-01-01T00:00:00"},
        ]
        resp = client.get("/memory/u1")
    assert resp.status_code == 200
    assert resp.json()[0]["role"] == "human"


def test_delete_memory(client):
    with patch("jarvis.memory.conversation.delete_history") as mock_del:
        resp = client.delete("/memory/u1")
    assert resp.status_code == 200
    mock_del.assert_called_once_with("u1")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/e2e/test_api.py -v
```

Expected: `ModuleNotFoundError: No module named 'jarvis.api'`

- [ ] **Step 3: Create `jarvis/api/__init__.py`** and `jarvis/api/http/__init__.py`** (both empty)

- [ ] **Step 4: Create `jarvis/api/http/routes.py`**

```python
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
```

- [ ] **Step 5: Run e2e tests**

```bash
pytest tests/e2e/test_api.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add jarvis/api/ tests/e2e/
git commit -m "ADD: FastAPI HTTP service with /chat, /ingest, /memory endpoints"
```

---

## Task 9: gRPC Service

**Files:**
- Create: `jarvis/api/grpc/__init__.py`
- Create: `jarvis/api/grpc/jarvis.proto`
- Generate: `jarvis/api/grpc/jarvis_pb2.py` and `jarvis/api/grpc/jarvis_pb2_grpc.py`
- Create: `jarvis/api/grpc/servicer.py`
- Create: `jarvis/api/grpc/server.py`

- [ ] **Step 1: Create `jarvis/api/grpc/__init__.py`** (empty)

- [ ] **Step 2: Create `jarvis/api/grpc/jarvis.proto`**

```protobuf
syntax = "proto3";

package jarvis;

service JarvisService {
  rpc Chat(ChatRequest) returns (ChatResponse);
  rpc Ingest(IngestRequest) returns (IngestResponse);
  rpc GetMemory(MemoryRequest) returns (MemoryResponse);
  rpc DeleteMemory(MemoryRequest) returns (DeleteResponse);
}

message ChatRequest {
  string message = 1;
  string user_id = 2;
  string llm = 3;
  string reflect_llm = 4;
}

message ChatResponse {
  string answer = 1;
  bool low_confidence = 2;
}

message IngestRequest {
  string content = 1;
  string source_url = 2;
  string user_id = 3;
}

message IngestResponse {
  bool success = 1;
}

message MemoryRequest {
  string user_id = 1;
}

message MemoryResponse {
  repeated ConversationEntry entries = 1;
}

message ConversationEntry {
  string role = 1;
  string content = 2;
  string created_at = 3;
}

message DeleteResponse {
  bool success = 1;
}
```

- [ ] **Step 3: Generate Python stubs**

```bash
python -m grpc_tools.protoc \
  -I jarvis/api/grpc \
  --python_out=jarvis/api/grpc \
  --grpc_python_out=jarvis/api/grpc \
  jarvis/api/grpc/jarvis.proto
```

Expected: `jarvis_pb2.py` and `jarvis_pb2_grpc.py` created in `jarvis/api/grpc/`.

- [ ] **Step 4: Fix generated import in `jarvis_pb2_grpc.py`**

Open `jarvis/api/grpc/jarvis_pb2_grpc.py` and change:
```python
import jarvis_pb2 as jarvis__pb2
```
to:
```python
from jarvis.api.grpc import jarvis_pb2 as jarvis__pb2
```

- [ ] **Step 5: Create `jarvis/api/grpc/servicer.py`**

```python
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
        know_mem.store_knowledge(request.content, request.source_url, request.user_id)
        return jarvis_pb2.IngestResponse(success=True)

    def GetMemory(self, request, context):
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

    def DeleteMemory(self, request, context):
        conv_mem.delete_history(request.user_id)
        return jarvis_pb2.DeleteResponse(success=True)
```

- [ ] **Step 6: Create `jarvis/api/grpc/server.py`**

```python
import grpc
from jarvis.api.grpc import jarvis_pb2_grpc
from jarvis.api.grpc.servicer import JarvisServicer
from jarvis.config import GRPC_PORT


async def create_grpc_server() -> grpc.aio.Server:
    server = grpc.aio.server()
    jarvis_pb2_grpc.add_JarvisServiceServicer_to_server(JarvisServicer(), server)
    server.add_insecure_port(f"[::]:{GRPC_PORT}")
    return server
```

- [ ] **Step 7: Verify gRPC imports work**

```bash
python -c "from jarvis.api.grpc.server import create_grpc_server; print('OK')"
```

Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add jarvis/api/grpc/
git commit -m "ADD: gRPC service with Chat, Ingest, GetMemory, DeleteMemory rpcs"
```

---

## Task 10: Main Entry Point

**Files:**
- Create: `jarvis/main.py`

- [ ] **Step 1: Create `jarvis/main.py`**

```python
import asyncio
import logging
import uvicorn
from jarvis.config import HTTP_PORT, GRPC_PORT
from jarvis.api.http.routes import app
from jarvis.api.grpc.server import create_grpc_server
from jarvis.memory.conversation import init_db
from jarvis.memory.knowledge import init_collection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def serve():
    logger.info("Initializing storage...")
    init_db()
    init_collection()

    grpc_server = await create_grpc_server()
    await grpc_server.start()
    logger.info("gRPC server listening on :%d", GRPC_PORT)

    config = uvicorn.Config(app, host="0.0.0.0", port=HTTP_PORT, log_level="info")
    http_server = uvicorn.Server(config)
    logger.info("HTTP server starting on :%d", HTTP_PORT)

    await asyncio.gather(
        http_server.serve(),
        grpc_server.wait_for_termination(),
    )


if __name__ == "__main__":
    asyncio.run(serve())
```

- [ ] **Step 2: Verify import**

```bash
python -c "from jarvis.main import serve; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v --ignore=tests/integration/test_rag_pipeline.py
```

Expected: all unit and e2e tests PASS.

- [ ] **Step 4: Commit**

```bash
git add jarvis/main.py
git commit -m "ADD: main entry point starting HTTP and gRPC servers concurrently"
```

---

## Task 11: Final Integration + Docker Compose

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
version: "3.9"
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: jarvis
    ports:
      - "5432:5432"

  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"
```

- [ ] **Step 2: Start dependencies**

```bash
docker compose up -d
```

Expected: postgres and qdrant containers running.

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS (integration tests skip if SILICONFLOW_API_KEY not set).

- [ ] **Step 4: Smoke-test the running server (requires API keys in .env)**

```bash
python jarvis/main.py &
sleep 3
curl -s -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, who are you?", "user_id": "test"}' | python -m json.tool
```

Expected: JSON response with `"answer"` field.

- [ ] **Step 5: Final commit**

```bash
git add docker-compose.yml
git commit -m "ADD: docker-compose for local Postgres and Qdrant dev dependencies"
```

---

## Self-Review Checklist

- [x] LLM Provider layer: SiliconFlow, OpenAI, Claude, router — Task 2
- [x] `provider not exist` error handling — Task 2, router.py
- [x] `provider not working:{reason}` error handling — Task 2, router.py
- [x] Tool registry with @register_tool decorator — Task 3
- [x] web_search tool (Tavily) — Task 3
- [x] web_scrape tool (BeautifulSoup) — Task 3
- [x] Conversation memory (PostgreSQL) — Task 4
- [x] Knowledge memory (Qdrant) — Task 5
- [x] Embedding model (Qwen3-Embedding-8B via SiliconFlow) — Task 5
- [x] AgentState with all required fields — Task 6
- [x] All 5 agent nodes — Task 6
- [x] Reflection: score < 0.7 → retry, max 3 retries, low_confidence flag — Task 6
- [x] Knowledge auto-ingest from tool results > 200 chars — Task 6, memory_write
- [x] LangGraph graph with conditional routing — Task 7
- [x] Retry loop: reflect → plan_and_call — Task 7
- [x] PostgreSQL degradation (skip history, warn) — Task 6, memory_load
- [x] Qdrant degradation (skip RAG, warn) — Task 6, rag_retrieve
- [x] FastAPI HTTP :8080 — Task 8
- [x] HTTP_PORT env var — Task 1, config.py
- [x] /chat, /ingest, /memory GET/DELETE endpoints — Task 8
- [x] Request-level LLM override — Task 8, routes.py
- [x] gRPC :9090 — Task 9
- [x] GRPC_PORT env var — Task 1, config.py
- [x] All 4 gRPC RPCs — Task 9
- [x] HTTP and gRPC share same graph — Tasks 8/9
- [x] Concurrent startup — Task 10
- [x] Unit tests: router, reflect, tool_registry — Tasks 2/3/6
- [x] Integration tests: graph_flow, rag_pipeline — Tasks 5/7
- [x] E2E tests: all HTTP endpoints — Task 8
