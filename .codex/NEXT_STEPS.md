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

1. Stabilize project memory and docs. Status: ongoing.
   - Keep `.codex/PROJECT_CONTEXT.md` aligned with code.
   - Keep `README.md` aligned with runtime behavior.
   - Treat `./docs` as the confirmed handoff/documentation directory. The
     earlier `./docx` mention was a path-name confusion corrected by the user's
     screenshot showing `ls | grep docs`.
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
