# Working Rules

These rules are mandatory for future Codex sessions in this repository.

## Session Startup

1. At the start of a new conversation, read `.codex/README.md`.
2. Then read `.codex/WORKING_RULES.md`, `.codex/PROJECT_CONTEXT.md`, and
   `.codex/NEXT_STEPS.md`.
3. Use those files to rebuild project context before editing code.
4. After reading `.codex`, inspect current `git status --short --branch` so
   existing user or prior-agent changes are not accidentally overwritten.

## Keep Memory And Docs Consistent

1. If a code change makes `.codex/PROJECT_CONTEXT.md` inaccurate, update it in
   the same change set.
2. If a behavior change makes `README.md` inaccurate, update `README.md` in the
   same change set.
3. If plans, priorities, known gaps, or operational assumptions change, update
   `.codex/NEXT_STEPS.md`.
4. Do not let README, `.codex` memory, tests, and implementation drift apart.

## Git Discipline

1. Do not revert unrelated changes you did not make.
2. Stage only files that belong to the current task.
3. After modifications, create a git commit.
4. Commit message format must be:

```text
FEATURE
1. english description of change
2. english description of change
```

Use `FIX` for bug fixes, `FEATURE` for new capabilities or documentation
artifacts, and `OPTIMIZE` for refactors or performance/readability improvements.

## Verification

1. Prefer targeted tests for the changed surface area.
2. For code changes, run at least the relevant `pytest` target before commit.
3. For documentation-only changes, verify the changed files exist and are
   readable, and inspect `git diff --check`.
4. Record any skipped verification in the final response.

## Project-Specific Guardrails

1. Jarvis is a backend Agent service, not a frontend app.
2. Runtime behavior is centered on `AgentState` and the LangGraph graph in
   `jarvis/agent/graph.py`.
3. External dependencies include LLM APIs, Tavily, PostgreSQL, and Qdrant.
   Tests should mock these unless intentionally running integration services.
4. The `.agents/skills` directory is both project data and local agent
   configuration. Do not delete or rewrite it casually.
5. New tools should be added through `@register_tool` and imported from
   `jarvis/agent/graph.py` so registration happens at graph import time.
