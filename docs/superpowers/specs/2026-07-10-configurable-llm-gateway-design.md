# Configurable LLM Gateway Design Spec

**Date:** 2026-07-10
**Status:** Implemented, tested, and approved by automated code review
**Scope:** Chat providers only. SiliconFlow embeddings remain unchanged.

## 1. Goal

Move every default Jarvis chat capability to the direct DeepSeek API while
keeping OpenAI, Claude, and SiliconFlow Chat available as optional request
overrides. Provider selection must be configuration-driven and business nodes
must not depend on provider SDK objects or message protocols.

Default profiles:

| Profile | Default model | Thinking | Tools |
|---|---|---|---|
| `answer` | `deepseek/deepseek-v4-pro` | enabled, high effort | enabled |
| `reflection` | `deepseek/deepseek-v4-flash` | disabled | disabled |
| `agent_dispatch` | `deepseek/deepseek-v4-flash` | disabled | disabled |

SiliconFlow continues to provide embeddings through the existing
`EMBED_MODEL`, `SILICONFLOW_API_KEY`, and `SILICONFLOW_BASE_URL` settings.

## 2. Confirmed Boundaries

1. Providers that use a known protocol family are added by configuration only.
   The supported adapter names are a fixed safe registry:
   `deepseek`, `openai_compatible`, and `anthropic`.
2. A provider with a genuinely new protocol requires one new adapter. Business
   callers and graph nodes must remain unchanged.
3. Profiles are added or changed in configuration without changing callers.
4. Existing HTTP and gRPC override fields remain supported. An override changes
   only the target model; the selected profile still controls thinking, tools,
   capability fallback, message limits, retry policy, and output expectations.
5. Docker image construction, image push, Docker Compose, Kubernetes, SSH, and
   remote deployment remain outside this change and require explicit user
   approval before execution.

## 3. Public Interface

Production code calls one synchronous gateway method:

```python
message = llm.chat(
    profile="answer",
    messages=messages,
    tools=get_tools(),
    override=state.get("llm_override"),
)
```

The return type is a normalized LangChain `AIMessage`. The gateway is the only
production module allowed to:

- resolve profiles and providers;
- instantiate provider chat clients;
- bind tools;
- map profile thinking policy to provider parameters;
- validate adapter capabilities;
- trim provider-limited message histories;
- retry transient provider failures;
- invoke provider SDKs;
- translate provider exceptions into Jarvis exceptions.

Graph nodes do not receive raw `ChatOpenAI`, `ChatAnthropic`, or `ChatDeepSeek`
objects. `jarvis.llm.router.get_model()` may remain temporarily as a deprecated
compatibility shim, but no production graph node may import or call it.
The public `jarvis.llm.llm` facade initializes its underlying `LLMGateway`
lazily on the first `chat()` call, so importing legacy modules does not require
the YAML file or a provider key.

## 4. Module Structure

```text
jarvis/llm/
├── __init__.py
├── gateway.py
├── config.py
├── errors.py
├── router.py
└── adapters/
    ├── __init__.py
    ├── base.py
    ├── deepseek.py
    ├── openai_compatible.py
    └── anthropic.py
```

Responsibilities:

| Module | Responsibility |
|---|---|
| `config.py` | Load and validate provider/profile YAML into typed records |
| `gateway.py` | Resolve policy, validate capabilities, trim, invoke, retry, normalize |
| `errors.py` | Define the normalized exception hierarchy and safe public messages |
| `adapters/base.py` | Define the adapter contract and capability metadata |
| `adapters/deepseek.py` | Construct `JarvisChatDeepSeek`, map thinking policy, and replay reasoning metadata |
| `adapters/openai_compatible.py` | Handle OpenAI, SiliconFlow Chat, and compatible providers |
| `adapters/anthropic.py` | Construct and invoke `ChatAnthropic` |
| `router.py` | Deprecated compatibility entry point only |

The gateway is a deep module: provider protocol details stay behind one small
interface instead of spreading through LangGraph nodes.

## 5. Configuration

The default file is repository-root `llm.yaml`. `LLM_CONFIG_PATH` can select a
different path. API keys are referenced by environment variable name and are
never stored in YAML.

```yaml
providers:
  deepseek:
    adapter: deepseek
    base_url: https://api.deepseek.com
    base_url_env: DEEPSEEK_BASE_URL
    api_key_env: DEEPSEEK_API_KEY
    capabilities:
      tools: true
      thinking: true

  openai:
    adapter: openai_compatible
    base_url: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
    capabilities:
      tools: true
      thinking: false

  siliconflow:
    adapter: openai_compatible
    base_url: https://api.siliconflow.cn/v1
    base_url_env: SILICONFLOW_BASE_URL
    api_key_env: SILICONFLOW_API_KEY
    capabilities:
      tools: true
      thinking: false
    limits:
      max_messages: 10

  claude:
    adapter: anthropic
    api_key_env: ANTHROPIC_API_KEY
    capabilities:
      tools: true
      thinking: false

profiles:
  answer:
    model: deepseek/deepseek-v4-pro
    tools: enabled
    thinking:
      mode: enabled
      effort: high
      on_unsupported: disable
    retry:
      max_attempts: 2
      base_delay_seconds: 0.25

  reflection:
    model: deepseek/deepseek-v4-flash
    tools: disabled
    thinking:
      mode: disabled
    retry:
      max_attempts: 2
      base_delay_seconds: 0.25

  agent_dispatch:
    model: deepseek/deepseek-v4-flash
    tools: disabled
    thinking:
      mode: disabled
    retry:
      max_attempts: 1
      base_delay_seconds: 0.0
```

Model specs split on the first `/` only. For example,
`siliconflow/deepseek-ai/DeepSeek-V4-Pro` resolves provider `siliconflow` and
model ID `deepseek-ai/DeepSeek-V4-Pro`.

Structural YAML validation occurs when configuration is loaded. API keys are
validated only when a selected provider is resolved, so unused optional
providers do not prevent startup. A missing key for a selected default profile
is a configuration precondition failure, not a provider availability failure.
When both `base_url` and `base_url_env` are present, a non-empty environment
value wins and the literal URL is the fallback.

Arbitrary Python import paths are forbidden in YAML. `adapter` must match the
fixed registry.

## 6. Adapter Contract And Capabilities

Each adapter exposes construction and invocation behind a common contract and
declares capabilities such as tool calling and thinking policy support. The
gateway validates the resolved profile before invoking the provider.

DeepSeek policy maps to the current OpenAI-format API exactly:

- thinking mode uses `extra_body={"thinking": {"type": "enabled"}}` or
  `extra_body={"thinking": {"type": "disabled"}}`;
- effort uses the top-level `reasoning_effort="high"` or `"max"` argument;
- thinking requests do not set `temperature`, `top_p`, `presence_penalty`, or
  `frequency_penalty` because DeepSeek documents them as unsupported.

Rules:

1. An `answer` override must support tools when tools are supplied.
2. The default `answer` model must support and enable its requested thinking
   policy. For request overrides, `thinking.on_unsupported` is authoritative.
   The `answer` profile explicitly sets it to `disable`, so a configured
   OpenAI, Claude, or SiliconFlow Chat model that does not support thinking can
   still answer with tools. This downgrade is logged with safe provider/model
   identifiers and is covered by tests; it is never an implicit adapter choice.
   A profile without `on_unsupported: disable` rejects unsupported thinking as
   invalid input.
3. `reflection` and `agent_dispatch` overrides retain their own disabled-tools
   and disabled-thinking policies. They cannot accidentally inherit the
   `answer` policy.
4. Provider-specific model exceptions can be represented in configuration,
   but callers still use the profile interface.
5. Provider SDK and LangChain retries are disabled with `max_retries=0` in all
   adapters. The gateway is the sole retry owner and uses the resolved
   profile's `retry` block. `max_attempts` includes the initial attempt.

## 7. DeepSeek Reasoning And Message Lifetime

DeepSeek thinking mode requires `reasoning_content` from a tool-call assistant
message to be sent back with the next request in that tool loop. The
`ChatDeepSeek` 1.1.0 exposes the response value as
`AIMessage.additional_kwargs["reasoning_content"]`. The adapter must preserve
that field unchanged, and the gateway must pass that same message through the LangGraph
`AIMessage -> ToolNode -> next llm.chat(...)` sequence.

The 1.1.0 package captures the response field but its inherited OpenAI message
serializer does not replay arbitrary `additional_kwargs` into the next request.
`adapters/deepseek.py` therefore defines a narrow `JarvisChatDeepSeek`
subclass that overrides `_get_request_payload()`: after the parent builds the
payload, it copies `reasoning_content` from each source `AIMessage` into the
corresponding outbound assistant message. No other provider payload fields are
rewritten. This workaround is isolated in the adapter and can be removed only
after an upgraded package passes the same transport contract test.

The DeepSeek contract test must mock the SDK transport beneath
`ChatDeepSeek`, not the gateway return value. It verifies both sides of the
conversion: the first response becomes
`AIMessage.additional_kwargs["reasoning_content"]`, and the next outbound
assistant message contains the exact `reasoning_content` value in the provider
request payload alongside its `tool_calls`.

Jarvis adopts this explicit persistence invariant:

- typed provider transcripts containing reasoning metadata, assistant
  tool-call messages, and matching `ToolMessage`s live only inside one
  `graph.invoke()` execution;
- persistent conversation memory stores only user text and final assistant
  text;
- later HTTP/gRPC requests never reconstruct or replay intermediate tool-call
  transcripts;
- Qdrant may continue storing long tool-result content as untyped knowledge
  text for RAG, but retrieval must never reconstruct that text as an
  `AIMessage(tool_calls=...)` or `ToolMessage(tool_call_id=...)`;
- therefore no incomplete DeepSeek reasoning/tool sequence is replayed across
  requests.

If persistent tool transcripts are introduced later, the conversation schema
must first be migrated to store complete typed messages, including tool call
IDs, tool results, and `reasoning_content`. Persisting only part of such a
sequence is forbidden.

DeepSeek has a context-token limit but its current chat schema does not publish
a fixed message-count maximum. Jarvis therefore does not impose a DeepSeek
message-count trim beyond the provider/context error behavior.

## 8. Provider Message Limits

Providers may configure `limits.max_messages`. SiliconFlow Chat is configured
with its documented maximum of 10 messages. Trimming works on legal message
groups, never on a flat list:

1. Preserve the system message and current user turn.
2. Treat an assistant message with tool calls and all matching `ToolMessage`s
   as one atomic group.
3. Drop the oldest complete history groups first.
4. Preserve chronological order and assistant/tool adjacency.
5. If the mandatory current group alone exceeds the provider limit, raise a
   normalized context-limit error instead of sending an invalid sequence.
6. Validate tool sequences before trimming. An orphan `ToolMessage`, duplicate
   `tool_call_id`, missing tool result, or mismatched tool result is an
   `LLMInvalidRequestError`; the gateway never attempts to repair and send it.
7. A DeepSeek thinking response that contains tool calls but omits
   `reasoning_content` is an `LLMInvalidResponseError` before another provider
   request is attempted.

## 9. Production Migration

All current chat callers move to the gateway:

| Caller | Profile | Override |
|---|---|---|
| `jarvis/agent/nodes/plan_and_call.py` | `answer` | `llm_override` |
| `jarvis/agent/nodes/reflect.py` | `reflection` | `reflect_llm_override` |
| `jarvis/agent/nodes/agent_dispatch.py` and `jarvis/agents/dispatcher.py` | `agent_dispatch` | `reflect_llm_override` |

Tests migrate from patching `get_model()` or provider SDK classes to patching
`llm.chat()`. HTTP and gRPC handlers migrate to the normalized gateway error
hierarchy. A regression test must assert that production graph nodes do not
import `jarvis.llm.router.get_model`.

## 10. Error Model

Provider exceptions are normalized at actual invocation time, not only during
client construction.

```text
LLMError
├── LLMInvalidRequestError
├── LLMConfigurationError
├── LLMContextLimitError
├── LLMRateLimitError
├── LLMTimeoutError
├── LLMUnavailableError
└── LLMInvalidResponseError
```

| Jarvis error | HTTP | gRPC |
|---|---:|---|
| invalid provider/model/override/capability | 400 | `INVALID_ARGUMENT` |
| context or legal message group too large | 400 | `INVALID_ARGUMENT` |
| selected provider configuration missing | 500 | `FAILED_PRECONDITION` |
| provider rate limited | 429 | `RESOURCE_EXHAUSTED` |
| provider timed out | 504 | `DEADLINE_EXCEEDED` |
| provider unavailable | 503 | `UNAVAILABLE` |
| invalid provider response or reasoning replay | 502 | `INTERNAL` |

Only transient rate-limit, timeout, and unavailable failures are eligible for
the gateway's bounded profile retry. Adapters always set their own
`max_retries=0`, preventing nested retries. Invalid input, configuration,
context, and response failures are not retried. Agent dispatch preserves its
current graceful fallback after a normalized LLM failure.

Public error text is stable and redacted. Logs may retain the exception class
and safe provider/model identifiers, but must not contain API keys,
authorization headers, full request bodies, or raw provider payloads. HTTP and
gRPC responses must not return `str(provider_exception)`.

## 11. Dependencies And Runtime Configuration

Add the direct dependency `langchain-deepseek>=1.1.0,<2.0.0` and build the
DeepSeek adapter on its `ChatDeepSeek` integration. Add:

- `DEEPSEEK_API_KEY`;
- optional `DEEPSEEK_BASE_URL` or the YAML `base_url` default;
- `LLM_CONFIG_PATH`, defaulting to `llm.yaml`.

Remove `ANSWER_LLM` and `REFLECT_LLM` as runtime defaults after profiles are in
place. Keep request-level `llm` and `reflect_llm` fields for compatibility.
SiliconFlow embedding settings remain unchanged.

Update `README.md`, `.env.example`, `jarvis.yaml`, and `.codex` memory to match
the new defaults. Checked-in Kubernetes configuration can be edited, but no
image build or deployment command is part of implementation.

## 12. Test Strategy

Unit tests:

- YAML parsing, fixed adapter registry, first-slash model parsing, and lazy key
  validation;
- profile and override resolution, including unsupported thinking/tools;
- explicit `answer` override fallback from enabled thinking to disabled
  thinking while retaining required tool support;
- provider construction for DeepSeek, OpenAI-compatible, and Anthropic
  adapters;
- legal message grouping and SiliconFlow 10-message trimming;
- normalized construction and invocation errors, retry eligibility, and error
  redaction;
- malformed reflection and agent-dispatch responses retain existing fallback
  behavior.

Graph and adapter contract tests:

- answer, reflection, and agent dispatch call the correct profiles;
- provider objects never escape the gateway;
- a DeepSeek tool loop preserves `reasoning_content` from the assistant tool
  call in `AIMessage.additional_kwargs` through `ToolNode` into the exact next
  provider request payload;
- `JarvisChatDeepSeek._get_request_payload()` adds only
  `reasoning_content` to matching assistant payloads and retains the parent's
  message ordering and tool-call encoding;
- orphan, duplicate, missing, and mismatched tool-call sequences are rejected
  before provider invocation;
- persisted history contains only final user/assistant text and never an
  incomplete tool/reasoning sequence;
- no production node imports deprecated `get_model()`.

API tests:

- one HTTP and one gRPC assertion for each normalized error mapping;
- request `llm` and `reflect_llm` overrides remain backward compatible;
- safe public messages never expose provider exception details.

All tests mock provider network calls. No real API key, Docker build, or remote
deployment is required.

## 13. Source Constraints

The design is based on the current official provider documentation:

- DeepSeek chat completion:
  <https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/>
- DeepSeek thinking mode and reasoning replay:
  <https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/>
- DeepSeek multi-round chat:
  <https://api-docs.deepseek.com/zh-cn/guides/multi_round_chat/>
- DeepSeek current models and context limits:
  <https://api-docs.deepseek.com/zh-cn/quick_start/pricing/>
- LangChain DeepSeek integration:
  <https://docs.langchain.com/oss/python/integrations/chat/deepseek>

These are implementation constraints, not deployment approval.
