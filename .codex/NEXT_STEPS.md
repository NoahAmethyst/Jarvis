# Next Steps

## Immediate Startup Plan For Future Sessions

1. Read `.codex/README.md`.
2. Read `.codex/WORKING_RULES.md`.
3. Read `.codex/PROJECT_CONTEXT.md`.
4. Read this file.
5. Run `git status --short --branch`.
6. For any requested change, inspect the exact files involved before editing.

## Current Repository State At Handoff

Observed before creating `.codex`:

```text
## master...origin/master [ahead 6]
 M jarvis.yaml
?? .agents/
?? docs/study/
```

Treat these as pre-existing changes. The `.codex` commit should stage only
`.codex` files unless the user explicitly asks for more.

The snapshot above is historical. Always trust the current
`git status --short --branch` output over this block.

## Active LLM Gateway Work

Status on 2026-07-10: implementation Tasks 1-6 are complete locally. Focused
configuration, Adapter, Gateway, caller, API, memory, and embedding tests pass.
The full suite and final automated code review remain before completion.

- Design spec:
  `docs/superpowers/specs/2026-07-10-configurable-llm-gateway-design.md`.
- Implementation plan:
  `docs/superpowers/plans/2026-07-10-configurable-llm-gateway.md`.
- All default chat Profiles use the direct DeepSeek API.
- `answer` uses `deepseek-v4-pro` with high-effort thinking and tools.
- `reflection` and `agent_dispatch` use `deepseek-v4-flash` with thinking and
  tools disabled.
- SiliconFlow remains the default embedding provider.
- OpenAI, Claude, and SiliconFlow Chat remain optional model overrides behind
  protocol adapters.
- The `answer` profile explicitly disables thinking when an override does not
  support it, while tool capability remains required. This preserves old
  provider override compatibility without changing DeepSeek defaults.
- Provider additions within a known protocol family are configuration-only.
- DeepSeek reasoning/tool messages are preserved only inside one graph
  execution. Persistent history continues to store final user/assistant text,
  so incomplete tool reasoning is never replayed across requests.
- Next action: run the full verification matrix, resolve automated code-review
  findings, record exact totals, and create the final local commit.
- Do not build an image or perform deployment actions without explicit user
  approval.

## Recommended Technical Plan

1. Stabilize project memory and docs. Status: ongoing.
   - Keep `.codex/PROJECT_CONTEXT.md` aligned with code.
   - Keep `README.md` aligned with runtime behavior.
   - Treat `./docs` as the confirmed handoff/documentation directory. The
     earlier `./docx` mention was a path-name confusion corrected by the user's
     screenshot showing `ls | grep docs`.
   - Current feature execution plan is
     `docs/superpowers/plans/2026-07-10-configurable-llm-gateway.md`.
   - The broader operational plan remains
     `docs/superpowers/plans/2026-07-09-jarvis-current-state-next-steps.md`.
   - The original bootstrap plan
     `docs/superpowers/plans/2026-05-22-jarvis-implementation.md` is preserved
     as historical and should not be executed directly.
2. Verify the full test suite in the local environment. Status: completed on
   2026-07-09 with a local `.venv`.
   - `.venv/bin/python -m pytest tests/unit -v`: 31 passed.
   - `.venv/bin/python -m pytest tests/e2e -v`: 5 passed, 1
     Starlette/FastAPI TestClient deprecation warning.
   - `.venv/bin/python -m pytest tests/integration -v`: 3 passed.
   - `.venv/bin/python -m pytest tests/ -v`: 40 passed, 1
     Starlette/FastAPI TestClient deprecation warning.
3. Audit Agent dispatch behavior. Status: completed on 2026-07-09.
   - `agents/openai.yaml` is parsed as Claude-style metadata fallback for
     missing `SKILL.md` name/description.
   - Added unit coverage for `openai.yaml` metadata fallback.
   - Confirmed `.agents/skills` is included in Docker builds because there is
     no `.dockerignore` and `Dockerfile` uses `COPY . .`.
4. Audit deployment config. Status: partially completed on 2026-07-09.
   - Added `AGENTS_DIR` and `AGENT_DISPATCH_THRESHOLD` to `jarvis.yaml`
     ConfigMap.
   - Check readiness/liveness endpoints if `/docs` is disabled in production.
   - Because Jarvis will deploy to a remote server, ask the user before any
     Docker image build, image push, Docker Compose action, `kubectl` command,
     SSH command, or remote server change.
5. Improve observability. Status: pending.
   - Consider structured logs for selected agent, score, retries, tool calls,
     and degraded memory/RAG paths.
6. Clarify Memory/RAG persistence behavior. Status: pending.
   - Current automatic knowledge writing stores any long `ToolMessage`, not
     only web search/scrape results.
   - If source-specific behavior is required, tests should cover it.

## Likely Useful Test Commands

```bash
pytest tests/unit -v
pytest tests/e2e -v
pytest tests/integration -v
pytest tests/ -v
```

There is no lint configuration in `pyproject.toml` at handoff time.

## Commit Message Examples

```text
FEATURE
1. add Codex handoff memory
2. add project working rules
```

```text
FIX
1. parse Claude-style agent metadata consistently
2. cover openai yaml agent metadata loading
```

```text
OPTIMIZE
1. simplify reflection score parsing
2. reduce duplicated API state initialization
```
