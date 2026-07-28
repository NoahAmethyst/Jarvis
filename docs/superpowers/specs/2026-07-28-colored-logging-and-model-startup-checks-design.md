# Colored Logging and Model Startup Checks Design

## Goal

Make Jarvis startup and runtime logs easy to scan by rendering `INFO`, `WARN`,
and `ERROR` level labels in green, yellow, and red. During startup, verify the
connectivity and API credentials of every chat provider referenced by the
configured profiles and the provider referenced by `EMBED_MODEL`.

Provider validation is diagnostic. A failed check must emit an `ERROR` without
preventing PostgreSQL, Qdrant, gRPC, or HTTP startup.

## Colored Logging

Add a small logging module built on Python's standard `logging` package. It
will configure the root logger with the existing timestamp, logger name, level,
and message fields.

The formatter will:

- display `INFO`, `WARN`, and `ERROR` as the visible level labels;
- wrap only those labels in ANSI green, yellow, and red sequences;
- enable colors by default, including when output is captured by Kubernetes;
- disable all ANSI sequences when the `NO_COLOR` environment variable is
  present; and
- avoid mutating shared `LogRecord` instances while formatting.

Jarvis and Uvicorn will use the same root logging configuration so startup
output does not switch between unrelated formats.

## Active Provider Discovery

Chat checks will load the validated LLM configuration and walk the configured
profiles in declaration order. Providers will be deduplicated, and the first
referenced model for each provider will be used for one lightweight check.
Unused providers in the `providers` section will not be checked.

The embedding check will parse `EMBED_MODEL` independently because embedding
configuration is not part of the chat profile gateway. The current default is
`siliconflow/Qwen/Qwen3-Embedding-8B`.

Embedding provider names are fail-closed. Only the explicitly supported
`siliconflow` and `openai` providers may produce a request; an unknown or
malformed provider is logged as a configuration failure without constructing a
client or transmitting a credential.

## Connectivity Checks

Each active chat provider will receive one minimal real chat request using the
selected model with optional features such as tools and thinking disabled for
the check. The active embedding model will receive one short `embed_query`
request. Real inference is used because configuration inspection or a model
listing endpoint cannot prove that the configured credential may invoke the
specific model.

Every diagnostic request will use a 10-second provider-client timeout with SDK
retries disabled. This bounds the startup delay when a provider is unreachable.

A successful check will log an `INFO` containing only the provider and model.
A failure will log an `ERROR` containing the provider, model, and a safe failure
category. Logs must never contain an API key, response body, request payload,
or raw exception message.

Failures will be isolated per check. Missing credentials, authentication
failures, timeouts, connection failures, and other provider errors will not
stop subsequent checks or application startup.

## Startup Sequence

`serve()` will run these steps in order:

1. Configure colored logging before application startup messages.
2. Run active chat-provider connectivity checks.
3. Run the active embedding-model connectivity check.
4. Continue with the existing storage, gRPC, and HTTP initialization regardless
   of connectivity-check results.

The checks are intentionally synchronous because the existing LangChain model
and embedding APIs are synchronous and startup already performs synchronous
storage initialization.

## Testing

Implementation will follow red-green-refactor:

- formatter tests for the three labels and ANSI colors;
- a formatter test proving `NO_COLOR` produces clean text;
- discovery tests proving profile providers are deduplicated and unused
  providers are skipped;
- chat and embedding check tests for success and redacted failure logging;
- a startup orchestration test proving a failed check does not prevent storage
  and server initialization; and
- the repository's relevant unit suite plus the configured lint/test checks
  before commit and push.

Automated tests will replace all external provider calls with fakes, so they do
not need network access or consume model quota.

## Out of Scope

- Checking providers that are configured but unused.
- Rechecking providers periodically after startup.
- Adding a health endpoint or Kubernetes readiness gate.
- Failing startup because a model check failed.
- Adding a third-party logging dependency.
