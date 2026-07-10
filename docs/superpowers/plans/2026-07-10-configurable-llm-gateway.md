# Configurable LLM Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route every default Jarvis chat capability through direct DeepSeek
profiles while retaining configuration-driven OpenAI, Claude, and SiliconFlow
Chat overrides and unchanged SiliconFlow embeddings.

**Architecture:** Introduce a synchronous profile-based gateway as the only
production LLM invocation boundary. Typed YAML configuration resolves a profile
to a fixed protocol adapter; adapters construct LangChain clients while the
gateway owns capability fallback, legal message trimming, retry, invocation,
and normalized errors. Current LangGraph nodes keep their business logic but
stop receiving raw provider models.

**Tech Stack:** Python 3.11+, Pydantic 2, PyYAML, LangChain 1.x,
`langchain-deepseek>=1.1.0,<2.0.0`, LangGraph, FastAPI, gRPC, pytest.

## Global Constraints

- Default `answer`: `deepseek/deepseek-v4-pro`, thinking enabled,
  `reasoning_effort=high`, tools enabled.
- Default `reflection` and `agent_dispatch`:
  `deepseek/deepseek-v4-flash`, thinking disabled, tools disabled.
- SiliconFlow embeddings and `EMBED_MODEL` remain unchanged.
- `llm` and `reflect_llm` request fields remain backward compatible model
  overrides.
- An `answer` override that lacks thinking support explicitly falls back to
  thinking disabled; it must still support tools.
- Adapter names are fixed to `deepseek`, `openai_compatible`, and `anthropic`.
  YAML never imports arbitrary Python paths.
- `JarvisChatDeepSeek` must replay
  `AIMessage.additional_kwargs["reasoning_content"]` in later tool-loop
  request payloads.
- Typed tool transcripts never cross `graph.invoke()` boundaries. Existing
  Qdrant storage of tool-result text remains untyped RAG knowledge.
- Provider SDK retries are disabled with `max_retries=0`; the gateway is the
  only retry owner.
- Public errors are redacted and stable. Never expose API keys, authorization
  headers, request bodies, or raw provider exceptions.
- Do not build or push images, run Docker Compose, run `kubectl`, use SSH, or
  change a remote server without explicit user approval.
- Do not stage or modify unrelated user-owned files under `.agents/skills` or
  `docs/study/interaction`.
- Before the first implementation edit, run `git status --short` and record the
  exact pre-existing dirty paths. The known study-material paths at plan time
  are user-owned and must remain unstaged.
- If a file in this plan is already dirty before its task begins, inspect
  `git diff -- <file>` and establish hunk ownership. Stage only task-owned hunks
  with `git add -p <file>`. If ownership cannot be established, do not edit or
  stage that file until the conflict is resolved.
- Before every commit, inspect both `git diff --cached --name-only` and
  `git diff --cached`. Unstage any hunk that is not owned by the current task.
- Use `.venv/bin/python -m pytest ...` for verification.

## File Map

```text
llm.yaml                              # providers and behavior profiles
pyproject.toml                        # direct langchain-deepseek dependency
jarvis/config.py                      # LLM_CONFIG_PATH; embedding config stays
jarvis/llm/
├── __init__.py                       # public singleton `llm`
├── config.py                         # typed YAML models and model-spec parser
├── errors.py                         # normalized safe LLM exception tree
├── gateway.py                        # profile resolution and invocation seam
├── router.py                         # deprecated legacy compatibility only
└── adapters/
    ├── __init__.py                   # fixed adapter registry
    ├── base.py                       # adapter creation contract
    ├── deepseek.py                   # ChatDeepSeek policy and replay fix
    ├── openai_compatible.py          # OpenAI/SiliconFlow Chat
    └── anthropic.py                  # Claude protocol
jarvis/agent/nodes/plan_and_call.py   # answer profile caller
jarvis/agent/nodes/reflect.py         # reflection profile caller
jarvis/agent/nodes/agent_dispatch.py  # dispatch override forwarding
jarvis/agents/dispatcher.py           # agent_dispatch profile caller
jarvis/api/http/routes.py             # normalized HTTP mapping
jarvis/api/grpc/servicer.py           # normalized gRPC mapping
tests/unit/test_llm_config.py
tests/unit/test_llm_adapters.py
tests/unit/test_llm_gateway.py
tests/unit/test_llm_callers.py
tests/unit/test_grpc_servicer.py
tests/unit/test_memory_persistence.py
tests/unit/test_embedding_config.py
tests/integration/test_graph_flow.py
tests/e2e/test_api.py
.env.example
README.md
jarvis.yaml
.codex/PROJECT_CONTEXT.md
.codex/NEXT_STEPS.md
```

---

### Task 1: Add Typed LLM Configuration And Defaults

**Files:**
- Create: `llm.yaml`
- Create: `jarvis/llm/config.py`
- Create: `jarvis/llm/errors.py`
- Create: `tests/unit/test_llm_config.py`
- Modify: `jarvis/config.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `load_llm_config(path: str | Path | None = None) -> LLMSettings`.
- Produces: `parse_model_spec(model_spec: str) -> tuple[str, str]`.
- Produces typed `ProviderSettings`, `ProfileSettings`, `ThinkingSettings`,
  `RetrySettings`, `Capabilities`, and `ProviderLimits` records.
- Produces: the complete normalized `LLMError` hierarchy used by later tasks.
- Consumes: `LLM_CONFIG_PATH`, default `llm.yaml`.

- [x] **Step 1: Write failing configuration tests**

Cover these exact cases in `tests/unit/test_llm_config.py`:

```python
ROOT = Path(__file__).resolve().parents[2]

def write_yaml(tmp_path, adapter):
    path = tmp_path / "llm.yaml"
    path.write_text(
        yaml.safe_dump({
            "providers": {
                "test": {
                    "adapter": adapter,
                    "api_key_env": "TEST_API_KEY",
                    "capabilities": {"tools": True, "thinking": False},
                },
            },
            "profiles": {
                "answer": {
                    "model": "test/model",
                    "tools": "enabled",
                    "thinking": {"mode": "disabled"},
                },
            },
        })
    )
    return path

def test_default_profiles_use_direct_deepseek():
    settings = load_llm_config(ROOT / "llm.yaml")
    assert settings.profiles["answer"].model == "deepseek/deepseek-v4-pro"
    assert settings.profiles["answer"].thinking.mode == "enabled"
    assert settings.profiles["answer"].thinking.effort == "high"
    assert settings.profiles["reflection"].model == "deepseek/deepseek-v4-flash"
    assert settings.profiles["agent_dispatch"].thinking.mode == "disabled"


def test_model_spec_splits_only_first_slash():
    assert parse_model_spec("siliconflow/deepseek-ai/DeepSeek-V4-Pro") == (
        "siliconflow",
        "deepseek-ai/DeepSeek-V4-Pro",
    )


@pytest.mark.parametrize("spec", ["", "deepseek", "/model", "deepseek/"])
def test_invalid_model_spec_is_rejected(spec):
    with pytest.raises(LLMInvalidRequestError):
        parse_model_spec(spec)


def test_unknown_adapter_name_is_rejected(tmp_path):
    path = write_yaml(tmp_path, adapter="some.module.Adapter")
    with pytest.raises(ValueError):
        load_llm_config(path)


def test_unused_provider_key_is_not_required(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings = load_llm_config(ROOT / "llm.yaml")
    assert "claude" in settings.providers
```

- [x] **Step 2: Run the tests and verify red**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_llm_config.py -v
```

Expected: collection fails because `jarvis.llm.config` does not exist.

- [x] **Step 3: Add the normalized exception hierarchy**

Create `jarvis/llm/errors.py` before configuration parsing uses it:

```python
class LLMError(Exception):
    pass

class LLMInvalidRequestError(LLMError):
    pass

class LLMConfigurationError(LLMError):
    pass

class LLMContextLimitError(LLMInvalidRequestError):
    pass

class LLMRateLimitError(LLMError):
    pass

class LLMTimeoutError(LLMError):
    pass

class LLMUnavailableError(LLMError):
    pass

class LLMInvalidResponseError(LLMError):
    pass
```

Every later raise site uses stable public text and preserves internal causes
with exception chaining.

- [x] **Step 4: Add dependencies and configuration models**

Add to `pyproject.toml`:

```toml
"langchain-deepseek>=1.1.0,<2.0.0",
"pyyaml>=6.0",
```

Add only this chat setting to `jarvis/config.py`; leave embedding settings
unchanged:

```python
LLM_CONFIG_PATH = os.getenv("LLM_CONFIG_PATH", "llm.yaml")
```

Implement strict Pydantic models in `jarvis/llm/config.py` with
`ConfigDict(extra="forbid")`. Use these constrained fields:

```python
AdapterName = Literal["deepseek", "openai_compatible", "anthropic"]
ThinkingMode = Literal["enabled", "disabled"]
ThinkingFallback = Literal["error", "disable"]

class ThinkingSettings(BaseModel):
    mode: ThinkingMode
    effort: Literal["high", "max"] | None = None
    on_unsupported: ThinkingFallback = "error"

class RetrySettings(BaseModel):
    max_attempts: int = Field(default=1, ge=1, le=5)
    base_delay_seconds: float = Field(default=0.0, ge=0.0, le=10.0)
```

Validate that every profile model references a configured provider and that
enabled thinking has an effort. Do not read provider API keys during YAML load.

- [x] **Step 5: Add `llm.yaml` exactly from the approved spec**

Include DeepSeek, OpenAI, SiliconFlow Chat, and Claude providers. Give DeepSeek
and SiliconFlow both a literal default `base_url` and a `base_url_env` override.
Configure SiliconFlow Chat `limits.max_messages: 10`. Configure the three
approved profiles and their retry blocks. The `answer` profile must set
`thinking.on_unsupported: disable`.

- [x] **Step 6: Synchronize the local virtual environment**

```bash
.venv/bin/python -m pip install -e ".[dev]"
```

Expected: `langchain-deepseek>=1.1.0,<2.0.0` is installed and Jarvis remains an
editable install. This is a local dependency action, not an image build or
deployment.

- [x] **Step 7: Run focused tests**

```bash
.venv/bin/python -m pytest tests/unit/test_llm_config.py -v
```

Expected: all configuration tests pass.

- [x] **Step 8: Commit**

```bash
git status --short
git add pyproject.toml llm.yaml jarvis/config.py jarvis/llm/config.py jarvis/llm/errors.py tests/unit/test_llm_config.py
git commit -m "FEATURE
1. add typed llm provider configuration
2. define direct deepseek chat profiles"
```

---

### Task 2: Add Normalized Errors And Protocol Adapters

**Files:**
- Create: `jarvis/llm/adapters/__init__.py`
- Create: `jarvis/llm/adapters/base.py`
- Create: `jarvis/llm/adapters/deepseek.py`
- Create: `jarvis/llm/adapters/openai_compatible.py`
- Create: `jarvis/llm/adapters/anthropic.py`
- Create: `tests/unit/test_llm_adapters.py`

**Interfaces:**
- Produces: `BaseAdapter.create_model(provider, model_id, thinking) -> BaseChatModel`.
- Produces: `ADAPTERS: dict[AdapterName, BaseAdapter]`.
- Produces: `JarvisChatDeepSeek(ChatDeepSeek)` with reasoning replay.
- Consumes: normalized `LLMError` subclasses from Task 1.

- [x] **Step 1: Write failing adapter and error tests**

Tests must assert:

```python
@tool
def fake_web_search(query: str) -> str:
    """Return a deterministic search result."""
    return "result"

def make_deepseek_model(monkeypatch, http_client=None):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    return JarvisChatDeepSeek(
        model="deepseek-v4-pro",
        api_key="test-key",
        base_url="https://api.deepseek.com",
        max_retries=0,
        http_client=http_client,
        reasoning_effort="high",
        extra_body={"thinking": {"type": "enabled"}},
    )

def deepseek_tool_call_response(reasoning_content, tool_call_id):
    return {
        "id": "chatcmpl-tool",
        "object": "chat.completion",
        "created": 1,
        "model": "deepseek-v4-pro",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "reasoning_content": reasoning_content,
                "tool_calls": [{
                    "id": tool_call_id,
                    "type": "function",
                    "function": {"name": "fake_web_search", "arguments": "{}"},
                }],
            },
            "finish_reason": "tool_calls",
        }],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }

def deepseek_final_response(content):
    return {
        "id": "chatcmpl-final",
        "object": "chat.completion",
        "created": 2,
        "model": "deepseek-v4-pro",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }

def test_deepseek_adapter_maps_thinking_policy(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    model = DeepSeekAdapter().create_model(
        provider=deepseek_provider(),
        model_id="deepseek-v4-pro",
        thinking=ThinkingSettings(mode="enabled", effort="high"),
    )
    assert model.max_retries == 0
    assert model.reasoning_effort == "high"
    assert model.extra_body == {"thinking": {"type": "enabled"}}


def test_deepseek_payload_replays_reasoning_content(monkeypatch):
    model = make_deepseek_model(monkeypatch)
    assistant = AIMessage(
        content="",
        tool_calls=[{"name": "web_search", "args": {}, "id": "call-1"}],
        additional_kwargs={"reasoning_content": "must replay"},
    )
    payload = model._get_request_payload([
        HumanMessage(content="search"),
        assistant,
        ToolMessage(content="result", tool_call_id="call-1"),
    ])
    assert payload["messages"][1]["reasoning_content"] == "must replay"


def test_deepseek_transport_parses_and_replays_reasoning_content(monkeypatch):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(200, json=deepseek_tool_call_response(
                reasoning_content="must replay",
                tool_call_id="call-1",
            ))
        return httpx.Response(200, json=deepseek_final_response("done"))

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    model = make_deepseek_model(monkeypatch, http_client=http_client)
    bound = model.bind_tools([fake_web_search])
    first = bound.invoke([HumanMessage(content="search")])
    assert first.additional_kwargs["reasoning_content"] == "must replay"

    bound.invoke([
        HumanMessage(content="search"),
        first,
        ToolMessage(content="result", tool_call_id="call-1"),
    ])
    assert requests[1]["messages"][1]["reasoning_content"] == "must replay"


def test_optional_provider_key_is_checked_when_selected(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = ProviderSettings(
        adapter="anthropic",
        api_key_env="ANTHROPIC_API_KEY",
        capabilities=Capabilities(tools=True, thinking=False),
    )
    with pytest.raises(LLMConfigurationError) as exc_info:
        AnthropicAdapter().create_model(
            provider=provider,
            model_id="claude-opus-4-1",
            thinking=ThinkingSettings(mode="disabled"),
        )
    assert str(exc_info.value) == "selected LLM provider is not configured"
```

Also test OpenAI-compatible and Anthropic constructor arguments, fixed adapter
registry membership, `max_retries=0`, safe exception text, a non-empty
`base_url_env` overriding the literal URL, and an empty environment value
falling back to the literal URL.

- [x] **Step 2: Run adapter tests and verify red**

```bash
.venv/bin/python -m pytest tests/unit/test_llm_adapters.py -v
```

Expected: imports fail because adapters and errors do not exist.

- [x] **Step 3: Implement adapter construction**

`BaseAdapter` resolves `api_key_env`, optional `base_url`, and optional
`base_url_env`. A non-empty environment value overrides the literal URL; the
literal URL is the fallback. A missing selected key raises
`LLMConfigurationError("selected LLM provider is not configured")`.

Construct clients with:

```python
ChatOpenAI(model=model_id, api_key=key, base_url=base_url, max_retries=0)
ChatAnthropic(model_name=model_id, api_key=key, base_url=base_url, max_retries=0)
JarvisChatDeepSeek(
    model=model_id,
    api_key=key,
    base_url=base_url,
    max_retries=0,
    reasoning_effort=effort,
    extra_body={"thinking": {"type": mode}},
)
```

Do not send DeepSeek sampling parameters in thinking mode.

- [x] **Step 4: Implement `JarvisChatDeepSeek` replay**

Override `_get_request_payload()` narrowly:

```python
def _get_request_payload(self, input_, *, stop=None, **kwargs):
    source_messages = self._convert_input(input_).to_messages()
    payload = super()._get_request_payload(input_, stop=stop, **kwargs)
    for source, target in zip(source_messages, payload["messages"], strict=True):
        if isinstance(source, AIMessage):
            reasoning = source.additional_kwargs.get("reasoning_content")
            if reasoning is not None:
                target["reasoning_content"] = reasoning
    return payload
```

Do not modify content, tool-call encoding, order, or any non-DeepSeek adapter.

- [x] **Step 5: Run adapter tests**

```bash
.venv/bin/python -m pytest tests/unit/test_llm_adapters.py -v
```

Expected: all tests pass without network access.

- [x] **Step 6: Commit**

```bash
git status --short
git add jarvis/llm/adapters/__init__.py jarvis/llm/adapters/base.py jarvis/llm/adapters/deepseek.py jarvis/llm/adapters/openai_compatible.py jarvis/llm/adapters/anthropic.py tests/unit/test_llm_adapters.py
git commit -m "FEATURE
1. add protocol-specific llm adapters
2. preserve deepseek tool reasoning payloads"
```

---

### Task 3: Implement The Profile Gateway

**Files:**
- Create: `jarvis/llm/gateway.py`
- Create: `tests/unit/test_llm_gateway.py`
- Modify: `jarvis/llm/__init__.py`

**Interfaces:**
- Produces: `LLMGateway.chat(profile, messages, tools=None, override=None) -> AIMessage`.
- Produces: lazy module facade `jarvis.llm.llm` and cached `get_llm()`.
- Consumes: `LLMSettings`, fixed `ADAPTERS`, LangChain messages and tools.

- [x] **Step 1: Write failing gateway tests**

Cover profile selection, first-slash overrides, explicit thinking fallback,
required tools, legal message groups, retries, and error normalization:

```python
def test_answer_profile_uses_deepseek_v4_pro(fake_adapter, settings, fake_tool):
    gateway = LLMGateway(settings, adapters={"deepseek": fake_adapter})
    gateway.chat("answer", [HumanMessage(content="hello")], tools=[fake_tool])
    assert fake_adapter.calls[0].model_id == "deepseek-v4-pro"
    assert fake_adapter.calls[0].thinking.mode == "enabled"


def test_non_thinking_answer_override_falls_back_explicitly(
    settings, fake_adapters, fake_tool
):
    gateway = LLMGateway(settings, adapters=fake_adapters.registry)
    gateway.chat(
        "answer",
        [HumanMessage(content="hello")],
        tools=[fake_tool],
        override="openai/gpt-4o",
    )
    assert fake_adapters.openai.calls[0].thinking.mode == "disabled"


def test_answer_override_without_tools_is_rejected(
    settings, fake_adapters, fake_tool
):
    settings.providers["openai"].capabilities.tools = False
    gateway = LLMGateway(settings, adapters=fake_adapters.registry)
    with pytest.raises(LLMInvalidRequestError):
        gateway.chat(
            "answer",
            [HumanMessage(content="hello")],
            tools=[fake_tool],
            override="openai/gpt-4o",
        )


@pytest.mark.parametrize("messages", [
    orphan_tool_messages(),
    duplicate_tool_ids(),
    missing_tool_result(),
    mismatched_tool_result(),
])
def test_invalid_tool_sequences_are_rejected_before_invoke(
    messages, settings, fake_adapters, fake_tool
):
    gateway = LLMGateway(settings, adapters=fake_adapters.registry)
    with pytest.raises(LLMInvalidRequestError):
        gateway.chat("answer", messages, tools=[fake_tool])
    assert fake_adapters.deepseek.model.invoke.call_count == 0
```

Add a SiliconFlow 10-message test proving oldest complete history groups are
dropped while system, current user, assistant tool call, and matching tool
results remain. Add a mandatory-group-too-large context error test.

Add transient retry tests proving exactly `max_attempts` calls and no retry for
invalid request/config/response errors. Patch `time.sleep`.

- [x] **Step 2: Run gateway tests and verify red**

```bash
.venv/bin/python -m pytest tests/unit/test_llm_gateway.py -v
```

Expected: import fails because `LLMGateway` does not exist.

- [x] **Step 3: Implement profile and capability resolution**

`chat()` must:

1. resolve the profile;
2. apply the override model only;
3. resolve provider and fixed adapter;
4. clone profile thinking policy;
5. explicitly disable thinking for an unsupported override only when
   `on_unsupported == "disable"`;
6. reject missing tool capability when tools are requested;
7. validate and trim messages;
8. construct the provider model;
9. bind tools only when profile tools are enabled and tools are present;
10. invoke inside normalized retry/error handling;
11. require an `AIMessage` response;
12. require DeepSeek `reasoning_content` when enabled thinking returns tool
    calls.

- [x] **Step 4: Implement legal message grouping**

Use a private `_group_messages()` state machine. An `AIMessage` with tool calls
starts an atomic group; consume following `ToolMessage`s until every unique
tool-call ID is satisfied. Reject orphan, duplicate, missing, or mismatched IDs.

For `max_messages`, mark all system groups and the group containing the last
`HumanMessage` plus every later group as mandatory. Drop oldest optional groups
until within the limit. If mandatory groups alone exceed the limit, raise
`LLMContextLimitError`.

- [x] **Step 5: Implement normalized invocation and retry**

Map known OpenAI/Anthropic timeout, rate-limit, connection, invalid-request,
and 5xx exceptions to the approved hierarchy. Unknown provider exceptions map
to `LLMUnavailableError`. Log only exception class plus safe provider/model
identifiers. Retry only `LLMRateLimitError`, `LLMTimeoutError`, and
`LLMUnavailableError` according to the profile.

- [x] **Step 6: Export a lazy facade**

In `jarvis/llm/__init__.py`, avoid loading YAML during package import:

```python
from functools import lru_cache

from jarvis.llm.config import load_llm_config
from jarvis.llm.gateway import LLMGateway

@lru_cache(maxsize=1)
def get_llm() -> LLMGateway:
    return LLMGateway(load_llm_config())

class _LazyLLM:
    def chat(self, *args, **kwargs):
        return get_llm().chat(*args, **kwargs)

llm = _LazyLLM()
```

Add a test that changes the working directory to an empty temporary directory
and imports `jarvis.llm.router`; import must succeed without loading YAML. The
first `llm.chat()` call loads and validates YAML, while provider keys remain
lazy until adapter construction.

- [x] **Step 7: Run gateway and adapter tests**

```bash
.venv/bin/python -m pytest tests/unit/test_llm_config.py tests/unit/test_llm_adapters.py tests/unit/test_llm_gateway.py -v
```

Expected: all tests pass.

- [x] **Step 8: Commit**

```bash
git status --short
git add jarvis/llm/__init__.py jarvis/llm/gateway.py tests/unit/test_llm_gateway.py
git commit -m "FEATURE
1. add profile-based llm gateway
2. normalize limits retries and provider errors"
```

---

### Task 4: Migrate Every Production Chat Caller

**Files:**
- Modify: `jarvis/agent/nodes/plan_and_call.py`
- Modify: `jarvis/agent/nodes/reflect.py`
- Modify: `jarvis/agent/nodes/agent_dispatch.py`
- Modify: `jarvis/agents/dispatcher.py`
- Create: `tests/unit/test_llm_callers.py`
- Modify: `tests/unit/test_reflect_node.py`
- Modify: `tests/unit/test_agent_dispatch.py`
- Modify: `tests/integration/test_graph_flow.py`

**Interfaces:**
- Consumes: `jarvis.llm.llm.chat(...)` only.
- Produces: unchanged graph node return dictionaries and dispatch fallback.

- [x] **Step 1: Write caller seam tests**

Patch `llm.chat` and assert exact calls:

```python
mock_chat.assert_called_once_with(
    profile="answer",
    messages=expected_messages,
    tools=get_tools(),
    override=state["llm_override"],
)
```

Reflection must use `profile="reflection"`, one `HumanMessage`, no tools, and
`reflect_llm_override`. Agent scoring must use `profile="agent_dispatch"`, no
tools, and the same override forwarded by the node.

Add a static regression assertion over production caller source files:

```python
assert "jarvis.llm.router" not in source
assert "get_model" not in source
```

- [x] **Step 2: Run caller tests and verify red**

```bash
.venv/bin/python -m pytest tests/unit/test_llm_callers.py -v
```

Expected: current nodes still import `get_model`.

- [x] **Step 3: Migrate answer and reflection**

Keep prompt construction and score parsing unchanged. Replace model creation,
binding, and invocation with gateway calls. The `answer` caller supplies
`get_tools()`; reflection supplies no tools.

- [x] **Step 4: Migrate agent dispatch**

Change `dispatch_agent` to accept `model_override: str | None` rather than a
required default `model_spec`. `_score_agent` calls the `agent_dispatch`
profile. Preserve per-agent failure isolation and the outer graceful fallback.

- [x] **Step 5: Update existing mocks and run node tests**

```bash
.venv/bin/python -m pytest tests/unit/test_llm_callers.py tests/unit/test_reflect_node.py tests/unit/test_agent_dispatch.py tests/integration/test_graph_flow.py -v
```

Expected: all tests pass and graph behavior is unchanged.

- [x] **Step 6: Commit**

```bash
git status --short
git add jarvis/agent/nodes/plan_and_call.py jarvis/agent/nodes/reflect.py jarvis/agent/nodes/agent_dispatch.py jarvis/agents/dispatcher.py tests/unit/test_llm_callers.py tests/unit/test_reflect_node.py tests/unit/test_agent_dispatch.py tests/integration/test_graph_flow.py
git commit -m "OPTIMIZE
1. route graph chat calls through llm profiles
2. remove provider objects from business nodes"
```

---

### Task 5: Map Normalized Errors At HTTP And gRPC Boundaries

**Files:**
- Modify: `jarvis/api/http/routes.py`
- Modify: `jarvis/api/grpc/servicer.py`
- Modify: `tests/e2e/test_api.py`
- Create: `tests/unit/test_grpc_servicer.py`

**Interfaces:**
- Consumes: every concrete `LLMError`.
- Produces: approved HTTP status and gRPC status mappings with safe details.

- [x] **Step 1: Write parameterized HTTP mapping tests**

Patch `graph.invoke` to raise each safe error and assert:

```python
HTTP_CASES = [
    (LLMInvalidRequestError("invalid LLM request"), 400),
    (LLMContextLimitError("LLM context limit exceeded"), 400),
    (LLMConfigurationError("selected LLM provider is not configured"), 500),
    (LLMRateLimitError("LLM rate limit exceeded"), 429),
    (LLMTimeoutError("LLM request timed out"), 504),
    (LLMUnavailableError("LLM provider unavailable"), 503),
    (LLMInvalidResponseError("LLM provider returned an invalid response"), 502),
]
```

Assert response details equal only the safe message and do not contain a fake
key or raw cause.

- [x] **Step 2: Write equivalent direct gRPC servicer tests**

Use a `FakeContext` recording `set_code` and `set_details`. Assert mappings to
`INVALID_ARGUMENT`, `FAILED_PRECONDITION`, `RESOURCE_EXHAUSTED`,
`DEADLINE_EXCEEDED`, `UNAVAILABLE`, and `INTERNAL`.

- [x] **Step 3: Run mapping tests and verify red**

```bash
.venv/bin/python -m pytest tests/e2e/test_api.py tests/unit/test_grpc_servicer.py -v
```

Expected: new cases fail because routes catch only legacy router errors.

- [x] **Step 4: Replace legacy exception handling**

Both API boundaries must catch every concrete `LLMError` exactly once and use
the approved mapping. Do not return `str()` from arbitrary exceptions in the
chat endpoint. Leave ingest and memory behavior outside this task.

- [x] **Step 5: Run API tests**

```bash
.venv/bin/python -m pytest tests/e2e/test_api.py tests/unit/test_grpc_servicer.py -v
```

Expected: all tests pass.

- [x] **Step 6: Commit**

```bash
git status --short
git add jarvis/api/http/routes.py jarvis/api/grpc/servicer.py tests/e2e/test_api.py tests/unit/test_grpc_servicer.py
git commit -m "FIX
1. map normalized llm errors at api boundaries
2. redact provider failures from public responses"
```

---

### Task 6: Align Runtime Examples, Documentation, And Project Memory

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `jarvis.yaml`
- Modify: `.codex/PROJECT_CONTEXT.md`
- Modify: `.codex/NEXT_STEPS.md`
- Modify or retain with deprecation note: `jarvis/llm/router.py`
- Create: `tests/unit/test_memory_persistence.py`
- Create: `tests/unit/test_embedding_config.py`
- Test: `tests/unit/test_llm_callers.py`

**Interfaces:**
- Produces: documentation and checked-in configuration matching runtime.
- Preserves: request `llm`/`reflect_llm` fields and legacy router import for
  non-production callers.

- [x] **Step 1: Update environment examples**

Remove `ANSWER_LLM` and `REFLECT_LLM`. Add:

```dotenv
DEEPSEEK_API_KEY=your_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
LLM_CONFIG_PATH=llm.yaml
```

Keep SiliconFlow key/base URL and embedding settings.

- [x] **Step 2: Update Kubernetes examples without deploying**

In `jarvis.yaml`, replace chat model env entries with
`LLM_CONFIG_PATH: "llm.yaml"`, add `DEEPSEEK_BASE_URL`, and add a
`DEEPSEEK_API_KEY: "REPLACE_ME"` Secret entry. Keep SiliconFlow embedding
configuration unchanged. Do not run `kubectl` or build an image.

- [x] **Step 3: Update README**

Document profiles, provider YAML, direct DeepSeek defaults, override fallback,
API key variables, the unchanged SiliconFlow embedding path, and the rule that
known-protocol providers are configuration-only. Replace statements that Agent
dispatch directly uses `REFLECT_LLM` with the `agent_dispatch` profile.

- [x] **Step 4: Preserve and mark the legacy router**

Keep `router.get_model()` import-compatible for external callers, add a
deprecation docstring, and ensure production source tests prove it is unused.
Do not extend its hardcoded registry; all new production behavior belongs to
the gateway.

- [x] **Step 5: Update `.codex` memory**

Rewrite the LLM Layer section of `.codex/PROJECT_CONTEXT.md` to describe the
gateway, profiles, adapters, DeepSeek reasoning replay, and unchanged
SiliconFlow embeddings. Mark this plan complete in `.codex/NEXT_STEPS.md` and
record verification results after Task 7.

- [x] **Step 6: Add persistence and embedding protection tests**

`tests/unit/test_memory_persistence.py` must prove that `memory_write()` sends
only human and final non-tool assistant text to PostgreSQL, sends long tool
result content to Qdrant as plain text, and never passes `reasoning_content`,
`tool_calls`, or `tool_call_id` into conversation persistence.

`tests/unit/test_embedding_config.py` must patch
`jarvis.memory.knowledge.OpenAIEmbeddings`, call `_get_embeddings()`, and assert
that a `siliconflow/...` `EMBED_MODEL` uses `SILICONFLOW_API_KEY`,
`SILICONFLOW_BASE_URL`, and the model ID after the first slash.

- [x] **Step 7: Verify configuration and references**

```bash
.venv/bin/python -c "import yaml; yaml.safe_load(open('llm.yaml')); list(yaml.safe_load_all(open('jarvis.yaml'))); print('yaml ok')"
rg -n "ANSWER_LLM|REFLECT_LLM|get_model" jarvis README.md .env.example jarvis.yaml
.venv/bin/python -m pytest tests/unit/test_llm_callers.py -v
.venv/bin/python -m pytest tests/unit/test_memory_persistence.py tests/unit/test_embedding_config.py -v
git diff --check
```

Expected: `yaml ok`; obsolete chat defaults absent; `get_model` appears only in
the deprecated router, legacy router tests, or an explicit no-production-import
test; tests pass; no whitespace errors.

- [x] **Step 8: Commit**

```bash
git status --short
git add .env.example README.md jarvis.yaml jarvis/llm/router.py tests/unit/test_memory_persistence.py tests/unit/test_embedding_config.py .codex/PROJECT_CONTEXT.md .codex/NEXT_STEPS.md
git commit -m "FEATURE
1. document configurable deepseek chat profiles
2. align deployment examples and project memory"
```

---

### Task 7: Full Verification And Automated Code Review

**Files:**
- Modify only if verification proves a defect: files from Tasks 1-6.

**Interfaces:**
- Produces: green test evidence and independent review approval.

- [ ] **Step 1: Run focused LLM tests**

```bash
.venv/bin/python -m pytest tests/unit/test_llm_config.py tests/unit/test_llm_adapters.py tests/unit/test_llm_gateway.py tests/unit/test_llm_callers.py -v
```

Expected: all pass.

- [ ] **Step 2: Run the full suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass; the known FastAPI/Starlette deprecation warning may remain.

- [ ] **Step 3: Run static safety checks**

```bash
.venv/bin/python -m compileall -q jarvis tests
git diff --check
rg -n "ANSWER_LLM|REFLECT_LLM" jarvis README.md .env.example jarvis.yaml llm.yaml
rg -n "jarvis\.llm\.router|get_model" jarvis/agent jarvis/agents
```

Expected: compile and diff checks succeed; obsolete defaults and production
router imports return no matches.

- [ ] **Step 4: Invoke an independent code-review Agent**

Ask it to review the complete diff against
`docs/superpowers/specs/2026-07-10-configurable-llm-gateway-design.md`, with
special attention to API protocol correctness, reasoning replay, capability
fallback, retries, legal tool groups, error redaction, docs, and tests. Resolve
all Critical findings and all applicable Important findings, then re-run the
affected tests.

- [ ] **Step 5: Record verification and commit review fixes**

Update `.codex/NEXT_STEPS.md` with exact test totals and reviewer outcome, then:

```bash
git status --short
git add llm.yaml pyproject.toml jarvis/config.py jarvis/llm/__init__.py jarvis/llm/config.py jarvis/llm/errors.py jarvis/llm/gateway.py jarvis/llm/router.py jarvis/llm/adapters/__init__.py jarvis/llm/adapters/base.py jarvis/llm/adapters/deepseek.py jarvis/llm/adapters/openai_compatible.py jarvis/llm/adapters/anthropic.py jarvis/agent/nodes/plan_and_call.py jarvis/agent/nodes/reflect.py jarvis/agent/nodes/agent_dispatch.py jarvis/agents/dispatcher.py jarvis/api/http/routes.py jarvis/api/grpc/servicer.py tests/unit/test_llm_config.py tests/unit/test_llm_adapters.py tests/unit/test_llm_gateway.py tests/unit/test_llm_callers.py tests/unit/test_grpc_servicer.py tests/unit/test_memory_persistence.py tests/unit/test_embedding_config.py tests/unit/test_reflect_node.py tests/unit/test_agent_dispatch.py tests/integration/test_graph_flow.py tests/e2e/test_api.py .env.example README.md jarvis.yaml .codex/PROJECT_CONTEXT.md .codex/NEXT_STEPS.md
git commit -m "FIX
1. resolve llm gateway review findings
2. record final verification evidence"
```

Skip an empty commit when the reviewer finds no issues and the verification
record was already committed. Do not push.
