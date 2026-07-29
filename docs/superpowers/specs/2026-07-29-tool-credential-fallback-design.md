# Tool Credential Checks and Graceful Fallback Design

## Context

Jarvis currently registers `web_search` even when `TAVILY_API_KEY` is not
configured. The tool sends an empty credential to Tavily, Tavily returns HTTP
401, and the unhandled `requests.HTTPError` escapes through LangGraph and the
gRPC `Chat` method.

The existing startup checks probe active Chat providers and the Embedding
provider, but they do not provide a unified, presence-only audit of credentials
required by services and tools. Existing PostgreSQL, Qdrant, and Agent dispatch
nodes already degrade safely when their optional work fails.

## Goals

- Audit credentials required by active model providers, the active Embedding
  provider, and registered tools during startup.
- Log configured credentials at INFO and missing credentials at WARNING without
  logging credential values or exception response bodies.
- Prevent tools with missing credentials from being advertised to the model.
- Convert supported external tool failures into a controlled, per-request
  fallback to a direct model answer.
- Prevent a failed tool from being called again during the same Chat request.
- Preserve explicit failures for programming errors and invalid tool input.

## Non-goals

- Do not store credentials in Git, tracked YAML, command arguments, or logs.
- Do not make optional credential absence fail application startup or
  readiness.
- Do not invent a fallback when the primary answer model itself has no usable
  credential. A direct model answer is impossible without that dependency.
- Do not implement a process-wide circuit breaker or persistent tool health
  state. Transient failures affect only the current Chat request.
- Do not change existing PostgreSQL, Qdrant, or Agent dispatch fallback
  behavior.

## Credential Classification

Credentials fall into two operational groups:

1. **Mandatory model credentials**
   - Credentials referenced by active LLM profiles in `llm.yaml`.
   - The credential selected by `EMBED_MODEL`.
   - Their absence is logged at WARNING during the presence audit.
   - Missing Embedding credentials continue to use the existing RAG fallback.
   - Missing primary answer-model credentials still produce the existing clear
     LLM configuration error at request time because no direct-answer fallback
     exists.

2. **Optional tool credentials**
   - Environment variables declared by registered tools, initially
     `TAVILY_API_KEY` for `web_search`.
   - Their absence disables only the affected tool.
   - The model receives the remaining available tools and can answer directly.

## Architecture

### Declarative tool requirements

Extend the tool registry so each registration can declare
`required_env_vars`. The registry retains both the `StructuredTool` and its
requirements.

The registry exposes:

- all registrations for startup auditing;
- available tools for model binding;
- filtering by tool names already marked unavailable in the current request.

Environment-variable values are read only for a boolean non-empty check. They
are never returned by registry APIs or written to logs.

`web_search` declares `TAVILY_API_KEY`. `web_scrape` has no credential
requirement and remains available unless it fails while executing.

### Startup credential audit

The startup-check module performs a presence audit before real connectivity
probes:

- load the active LLM settings;
- discover one active target per provider;
- inspect each active provider's `api_key_env`;
- derive the Embedding credential environment variable from `EMBED_MODEL`;
- inspect every registered tool requirement.

Each unique component/credential pair emits one structured log:

- configured: INFO with `状态=已配置`;
- missing: WARNING with `状态=未配置`.

Logs include the component, component type, environment-variable name, and
status. They never include values, raw exceptions, request URLs, response
bodies, queries, or user content.

Real provider connectivity probes run only when the corresponding credential is
present. A configured but rejected credential remains a connectivity-check
failure and retains ERROR severity. A missing credential is not probed and is
reported only as the explicit WARNING.

Tool credential checks are presence-only and do not consume an external search
request during startup.

### Per-request tool availability

Add `unavailable_tools` to `AgentState`. It starts empty for each gRPC/HTTP Chat
request.

`plan_and_call` asks the registry for tools excluding:

- tools whose required environment variables are missing; and
- names in the request's `unavailable_tools`.

Consequently, a missing `TAVILY_API_KEY` prevents `web_search` from being
advertised on the first model call. The model answers directly without
generating an invalid search request.

### Safe tool execution

External tools normalize only supported operational failures into a
`ToolUnavailableError` containing:

- tool name;
- stable error category;
- a safe model-facing fallback message.

Supported fallback categories are:

| Failure | Category |
|---|---|
| HTTP 401 or 403 | `credential` |
| request timeout | `timeout` |
| connection failure | `connectivity` |
| HTTP 5xx | `provider` |

Other HTTP 4xx responses, invalid arguments, parsing bugs, and unexpected
programming errors are not converted. They continue to surface for diagnosis.

A dedicated safe tool-execution graph node:

1. executes the requested registered tools;
2. on success, returns normal `ToolMessage` results;
3. on `ToolUnavailableError`, logs a redacted WARNING;
4. returns a safe `ToolMessage` instructing the model to answer without that
   tool;
5. adds the failed tool name to `unavailable_tools`.

The graph then returns to `plan_and_call`. That call no longer binds the failed
tool, so the same request cannot retry it. The failure does not disable the tool
for later Chat requests, allowing recovery from transient outages.

Multiple tool calls in one assistant message are processed independently.
Successful tool results remain available even if another tool becomes
unavailable.

## Logging

Startup warning example:

```text
【组件:web_search】【类型:Tool】【配置:TAVILY_API_KEY】【状态:未配置】 Required credential is not configured
```

Runtime fallback example:

```text
【节点:tool_node】【工具:web_search】【状态:降级】【类别:credential】 Tool unavailable
```

No raw exception message is logged because provider messages can contain
request data or credential-related response bodies.

## Data Flow

### Missing tool credential

1. Startup audit logs a WARNING.
2. Chat request starts with `unavailable_tools=[]`.
3. Registry filters out `web_search` because its requirement is missing.
4. The model receives no `web_search` definition.
5. The model answers directly.

### Runtime tool outage

1. The model requests an available tool.
2. The safe tool node executes it.
3. The tool converts a supported operational failure into
   `ToolUnavailableError`.
4. The node logs a redacted WARNING and emits a safe `ToolMessage`.
5. The node records the tool in `unavailable_tools`.
6. `plan_and_call` invokes the model again without the failed tool.
7. The model answers using its existing knowledge and any successful tool
   results.

## Testing

Use test-driven development with focused tests for:

- registry metadata and environment-based filtering;
- missing tool credentials never being advertised;
- configured tool credentials preserving availability;
- startup INFO/WARNING logs and value redaction;
- active but missing Chat provider credentials being skipped by connectivity
  probes;
- missing Embedding credentials being reported without a request;
- supported `web_search` and `web_scrape` request failures being normalized;
- unsupported 4xx and programming errors still propagating;
- runtime failure producing a safe ToolMessage;
- runtime failure updating `unavailable_tools`;
- the subsequent model call excluding the failed tool;
- successful and failed parallel tool calls producing independent results;
- the original Tavily 401 path completing with a direct model response rather
  than escaping through gRPC.

Run the relevant unit and integration tests first, followed by the complete
Pytest suite.

## Deployment and Secret Handling

The existing Deployment imports all keys from `jarvis-secrets` through
`envFrom`, so no tracked manifest change is required to add
`TAVILY_API_KEY`.

The credential must be supplied from an ignored `*.secret.yaml` file, a secure
environment variable, or another local credential mechanism. It must not appear
in a tracked file, shell command argument, generated log, test fixture, commit,
or assistant response.

After the application-code change:

1. run tests and inspect the exact task diff;
2. scan the commits to be pushed for credential material without printing it;
3. commit and push only task-owned files to `master`;
4. monitor the GitHub Actions image build to terminal success;
5. update `jarvis-secrets` through the secure input;
6. only with explicit authorization, restart or roll out the Deployment;
7. verify startup credential logs and one successful search request.

Because a credential was shared in chat, rotation is recommended before using
it as a long-lived production credential.
