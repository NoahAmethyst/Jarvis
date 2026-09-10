# Runtime Model Administration

## Scope

Replace outdated DeepSeek defaults with the official V4.1 Flash API identifier
`deepseek-flash`. Add a small same-origin configuration page at `/admin/models`
to choose model IDs for existing profiles without modifying application code.
Embedding continues to use SiliconFlow. Provider registration stays in YAML.

## Decisions

- Use existing PostgreSQL for persistence instead of modifying ConfigMap files
  or ephemeral container files. SQLite/file-only persistence would not meet
  the remote multi-replica service requirement.
- Enable runtime reads explicitly through `LLM_RUNTIME_CONFIG_ENABLED=true`.
  Management additionally requires `JARVIS_ADMIN_TOKEN` from a secure source.
- Store model mappings in a singleton row with a revision. Atomic conditional
  updates reject stale writes. The UI submits the base configuration hash too.
- Pin an independent configuration snapshot across each complete HTTP Chat,
  gRPC Chat, or gRPC Generate request, including tools and reflection.
- Preserve request-level overrides. Provider capabilities and secrets cannot
  be edited through the browser. An incompatible profile/provider is rejected.
- Allow manual model IDs; discovery is an optional OpenAI-compatible catalog
  lookup with bounded response size/concurrency and redacted errors. Saving
  does not certify that a model exists or supports every provider capability.
- DB errors do not fall back silently. All replicas must use identical base
  configurations and a shared primary database. Heterogeneous rolling config
  migrations require operator coordination and are outside this change.
- Existing startup probes check YAML defaults. Runtime model changes do not
  automatically run paid connectivity probes.

## Review And Verification

Independent design review identified tool-loop compatibility as a blocker;
request-scoped ContextVar snapshots resolve it. Capability/credential checks,
CAS, strict CSP, text-only rendering and opt-in management address the other
applicable findings. Provider-level declarations cannot certify a future model;
this limitation is explicitly documented, with manual entry preserved.

Implementation sequence: persistence and runtime snapshots; authenticated API;
packaged UI; focused tests and browser checks; documentation; scoped commit.
Deployment, image building, and remote mutations remain separate approval steps.

Verification on 2026-09-10: full suite 226 passed; after strengthening timeout
and response-size assertions, all 26 management tests passed again. Browser
checks exercised desktop/mobile layouts, login/logout, custom model save and
reload, default restore, catalog success/failure, revision conflicts, and no
horizontal overflow or JavaScript errors. Independent implementation review
closed both discovered issues (interruptible catalog deadline and effective
credential checks on restore). No live PostgreSQL concurrency test or paid
provider call was performed; database behavior is covered with transaction mocks.
