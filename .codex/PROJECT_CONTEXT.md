# Jarvis Project Context

## What Jarvis Is

Jarvis is a Python backend service for an LLM assistant built around LangGraph.
It combines:

- HTTP API via FastAPI.
- gRPC API via protobuf stubs.
- A configuration-driven LLM Profile Gateway with direct DeepSeek defaults and
  optional OpenAI, Claude, and SiliconFlow Chat overrides.
- Tool calling through a decorator-based registry.
- Conversation memory in PostgreSQL.
- Knowledge/RAG memory in Qdrant.
- Reflection scoring with retry.
- Custom Agent dispatch from `.agents/skills`.

## Runtime Entry Points

- `jarvis/main.py`
  - Calls `init_db()` and `init_collection()`.
  - Starts gRPC and HTTP concurrently with `asyncio.gather`.
- `jarvis/api/http/routes.py`
  - Defines `/chat`, `/ingest`, `/memory/{uid}`, and `DELETE /memory/{uid}`.
  - Builds `AgentState` and invokes `graph.invoke`.
  - Maps normalized LLM errors to HTTP 400/429/500/502/503/504 with redacted
    public messages.
- `jarvis/api/grpc/servicer.py`
  - Mirrors the HTTP behavior through `JarvisService`.
  - Maps normalized LLM errors to the corresponding gRPC argument,
    precondition, resource, deadline, availability, and internal statuses.

## Agent State

`jarvis/agent/state.py` defines the shared `AgentState` TypedDict. Important
fields:

- `messages`: LangChain messages accumulated by LangGraph `add_messages`.
- `history`: prior conversation loaded from PostgreSQL.
- `query`: the current user query.
- `rag_context`: retrieved Qdrant context.
- `reflection_score`, `retry_count`, `final_answer`, `low_confidence`.
- `llm_override`, `reflect_llm_override`.
- `active_agent`, `agent_dispatch_score`.

## LangGraph Flow

`jarvis/agent/graph.py` compiles this graph:

```text
memory_load
  -> agent_dispatch
  -> rag_retrieve
  -> plan_and_call
  -> tool_node if the last AIMessage has tool_calls
  -> plan_and_call after tool execution
  -> reflect when no tool call is needed
  -> plan_and_call again if score is below threshold and retry remains
  -> memory_write
  -> END
```

Thresholds come from:

- `REFLECTION_SCORE_THRESHOLD`, default `0.7`.
- `REFLECTION_MAX_RETRIES`, default `3`.

## Node Responsibilities

- `memory_load`
  - Loads up to 20 prior conversation messages from PostgreSQL.
  - Degrades to empty history if PostgreSQL is unavailable.
- `agent_dispatch`
  - Loads custom agents from `AGENTS_DIR`, default `.agents/skills`.
  - Scores each agent with the `agent_dispatch` LLM Profile or request
    `reflect_llm_override`.
  - Activates the highest-scoring agent if score is at least
    `AGENT_DISPATCH_THRESHOLD`, default `0.6`.
  - Degrades to no active agent on errors.
- `rag_retrieve`
  - Embeds current query and retrieves user-scoped knowledge from Qdrant.
  - Degrades to empty context on errors.
- `plan_and_call`
  - Builds a system prompt from the Jarvis base prompt, RAG context, and active
    agent instructions.
  - Calls `llm.chat(profile="answer", ...)` with request `llm_override`.
  - The Gateway binds all registered tools and invokes the model.
- `reflect`
  - Extracts the last non-tool AI answer.
  - Asks the reflection model for a numeric score.
  - Parses the first decimal-like number, clamps it to `[0.0, 1.0]`, and
    defaults to `0.5` if parsing fails.
  - Increments `retry_count`.
  - Sets `low_confidence` only when max retries are reached and score is below
    threshold.
  - Calls `llm.chat(profile="reflection", ...)` with request
    `reflect_llm_override`.
- `memory_write`
  - Saves human messages and final non-tool AI answers to PostgreSQL.
  - Stores long `ToolMessage` content in Qdrant when length exceeds
    `KNOWLEDGE_MIN_LENGTH`, default `200`.
  - Logs and continues on storage failures.

## LLM Layer

- Root `llm.yaml`
  - Defines providers, fixed adapter names, capabilities, message limits, and
    behavior Profiles.
  - `answer`: `deepseek/deepseek-v4-pro`, thinking high, tools enabled.
  - `reflection` and `agent_dispatch`: `deepseek/deepseek-v4-flash`, thinking
    and tools disabled.
- `jarvis/llm/config.py`
  - Strictly validates YAML with Pydantic and splits model specs on the first
    slash.
  - Loads structure without requiring keys for unused optional providers.
- `jarvis/llm/gateway.py`
  - Is the only production boundary for Profile resolution, capability
    fallback, legal message-group trimming, tool binding, retries, invocation,
    and safe error normalization.
  - Explicitly disables thinking when the `answer` request override lacks that
    capability; required tool support remains a hard constraint.
  - SiliconFlow Chat is limited to 10 messages and is trimmed by complete
    assistant/tool groups.
- `jarvis/llm/adapters`
  - Fixed registry: `deepseek`, `openai_compatible`, and `anthropic`.
  - `JarvisChatDeepSeek` preserves
    `AIMessage.additional_kwargs["reasoning_content"]` in later tool-loop
    request payloads.
  - Provider SDK retries are disabled; the Gateway owns bounded retries.
- `jarvis/llm/errors.py`
  - Defines stable, redacted errors for invalid input/config/context, rate
    limits, timeouts, unavailability, and invalid responses.
- `jarvis/llm/router.py`
  - Retains the old raw-model API only for external compatibility.
  - Production graph and agent callers do not import it.

## Memory And RAG

- `jarvis/memory/conversation.py`
  - Uses psycopg2 directly.
  - Table: `conversations(id, user_id, role, content, created_at)`.
  - Loads latest messages by descending timestamp, then reverses them into
    chronological order.
  - Stores only user text and final assistant text, never typed tool/reasoning
    transcripts.
- `jarvis/memory/knowledge.py`
  - Collection name: `jarvis_knowledge`.
  - Uses `OpenAIEmbeddings`; SiliconFlow embeddings are supported by OpenAI
    compatible base URL.
  - Point IDs are deterministic SHA-256 hashes of `user_id`, source, and text.
  - Retrieval filters by `user_id` and joins payload texts with `---`.
  - Long tool-result text may remain untyped RAG knowledge; it is never
    reconstructed as provider tool messages.

## Tools

- `jarvis/tools/registry.py`
  - `@register_tool(name, description)` wraps functions as LangChain
    `StructuredTool`.
  - `get_tools()` returns registered tools.
- `jarvis/tools/search.py`
  - Registers `web_search`.
  - Calls Tavily search API.
- `jarvis/tools/scraper.py`
  - Registers `web_scrape`.
  - Fetches a URL with `requests`, strips common page chrome with BeautifulSoup,
    and returns the first 5000 chars.
- Important: `jarvis/agent/graph.py` imports `jarvis.tools.search` and
  `jarvis.tools.scraper` only for registration side effects.

## Custom Agent Dispatch

- Agent representation: `jarvis/agents/__init__.py::AgentDefinition`.
- Loader: `jarvis/agents/loader.py`.
- Dispatcher: `jarvis/agents/dispatcher.py`.
- Supported directory: `.agents/skills/<agent-name>/`.
- Parse priority:
  1. `agent.json`
  2. `agent.yaml`
  3. Claude-style `SKILL.md`
- Implementation detail: Claude-style parser reads `SKILL.md` frontmatter and
  body. If `name` or `description` are missing, it falls back to
  `agents/openai.yaml` `interface.display_name` and
  `interface.short_description`.
- Current local agent:
  - `.agents/skills/ai-agent-mentor/SKILL.md`
  - Used for Jarvis AI Agent learning, code walkthroughs, exercises,
    interviews, and staged learning plans.

## Documentation And Learning Materials

- `README.md`
  - Public architecture, setup, API, config, tool extension, custom Agent
    docs, degradation behavior, and test command.
- `docs/superpowers/specs/2026-05-22-jarvis-design.md`
  - Original Jarvis design.
- `docs/superpowers/specs/2026-06-18-agent-dispatch-design.md`
  - Custom Agent dispatch design.
- `docs/superpowers/specs/2026-07-10-configurable-llm-gateway-design.md`
  - Approved configurable chat provider and direct DeepSeek design.
- `docs/superpowers/plans/2026-07-10-configurable-llm-gateway.md`
  - Reviewed implementation and verification plan.
- `docs/superpowers/plans/2026-05-22-jarvis-implementation.md`
  - Original implementation plan.
- `docs/study`
  - Learning path for AI Agent concepts mapped to Jarvis code.
  - `docs/study/interaction` stores learning profile, staged plan, interview
    framing, and teaching protocol.
- User screenshot correction on 2026-07-09 confirmed the relevant handoff
  directory is `./docs`, not `./docx`. Current `docs` contents include
  `docs/superpowers/plans/2026-05-22-jarvis-implementation.md`,
  `docs/superpowers/specs/2026-05-22-jarvis-design.md`,
  `docs/superpowers/specs/2026-06-18-agent-dispatch-design.md`, and the
  `docs/study` learning materials.

## Tests

- Unit:
  - `tests/unit/test_llm_config.py`
  - `tests/unit/test_llm_adapters.py`
  - `tests/unit/test_llm_gateway.py`
  - `tests/unit/test_llm_callers.py`
  - `tests/unit/test_grpc_servicer.py`
  - `tests/unit/test_memory_persistence.py`
  - `tests/unit/test_embedding_config.py`
  - `tests/unit/test_llm_router.py`
  - `tests/unit/test_tool_registry.py`
  - `tests/unit/test_reflect_node.py`
  - `tests/unit/test_agent_dispatch.py`
- Integration:
  - `tests/integration/test_graph_flow.py`
  - `tests/integration/test_rag_pipeline.py`
- E2E:
  - `tests/e2e/test_api.py`
- Existing tests heavily mock LLMs, storage, and graph dependencies. Real
  PostgreSQL/Qdrant integration is minimal and should be treated carefully.

## Deployment

- `docker-compose.yml`
  - Runs PostgreSQL and Qdrant locally.
- `Dockerfile`
  - Multi-stage Python 3.11 slim build.
  - Regenerates gRPC stubs and patches package-relative imports.
  - `jarvis.yaml`
  - Kubernetes manifests for namespace, ConfigMap, Secret, PostgreSQL,
    Qdrant, Jarvis deployment, and service.
  - ConfigMap includes Agent dispatch defaults: `AGENTS_DIR` and
    `AGENT_DISPATCH_THRESHOLD`.
  - ConfigMap points to `llm.yaml` and the direct DeepSeek base URL; Secret has
    a `DEEPSEEK_API_KEY` placeholder.

## Current Known Inconsistencies

- Earlier `.codex` notes confused `docx` with `docs`. The screenshot provided
  by the user shows `ls | grep docs` returning `docs`. Treat `./docs` as the
  confirmed documentation/handoff directory; do not assume a separate `./docx`
  directory exists unless it appears in the filesystem.
- The current integration tests mock substantial external storage behavior;
  they are not proof of a live PostgreSQL/Qdrant deployment.
