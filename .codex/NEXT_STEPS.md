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

## Recommended Technical Plan

1. Stabilize project memory and docs.
   - Keep `.codex/PROJECT_CONTEXT.md` aligned with code.
   - Keep `README.md` aligned with runtime behavior.
2. Verify the full test suite in the local environment.
   - Start with `pytest tests/unit -v`.
   - Then run `pytest tests/e2e -v`.
   - Run integration tests only after deciding whether real PostgreSQL/Qdrant
     should be started with Docker.
3. Audit Agent dispatch behavior.
   - Decide whether `agents/openai.yaml` should be parsed as the spec says.
   - If yes, add loader tests before implementation.
   - Confirm whether `.agents/skills` should be packaged, mounted, or
     configured in deployment.
4. Audit deployment config.
   - Add `AGENTS_DIR` and `AGENT_DISPATCH_THRESHOLD` to `jarvis.yaml` if the
     Kubernetes manifest is meant to support custom Agent dispatch.
   - Check readiness/liveness endpoints if `/docs` is disabled in production.
5. Improve observability.
   - Consider structured logs for selected agent, score, retries, tool calls,
     and degraded memory/RAG paths.
6. Clarify Memory/RAG persistence behavior.
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
