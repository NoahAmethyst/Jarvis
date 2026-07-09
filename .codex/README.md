# Codex Project Memory

This directory is the handoff memory for Codex sessions working on Jarvis.
At the start of every new conversation, read this file first, then read the
linked files in order.

## Read Order

1. `.codex/WORKING_RULES.md` - mandatory operating rules.
2. `.codex/PROJECT_CONTEXT.md` - current architecture and code understanding.
3. `.codex/NEXT_STEPS.md` - recommended execution plan and known gaps.
4. `README.md` - public project description that must stay consistent.
5. Relevant source files for the requested task.

## Current Snapshot

- Date captured: 2026-07-09.
- Project root: `/Users/amethyst/Jarvis`.
- Project type: Python 3.11+ LangGraph LLM assistant backend.
- Interfaces: FastAPI HTTP on `:8080`, gRPC on `:9090`.
- Core runtime flow:

```text
HTTP/gRPC request
  -> AgentState
  -> memory_load
  -> agent_dispatch
  -> rag_retrieve
  -> plan_and_call
  -> tool_node when model emits tool calls
  -> reflect
  -> memory_write
  -> response
```

## Important Handoff Notes

- The project was originally created/executed by Claude Code. Codex is now
  taking over by maintaining durable memory in this directory.
- User screenshot correction on 2026-07-09: the visible directory is `./docs`,
  not `./docx`. `./docs` exists and contains prior design, plan, and study
  handoff materials, including `docs/superpowers/*` and `docs/study/*`.
  No `./docx` directory has been confirmed in this worktree.
- Existing uncommitted work before this handoff included `jarvis.yaml`,
  `.agents/`, and `docs/study/`. Treat those as user or prior-agent changes;
  do not revert them without explicit instruction.
- `.agents/skills/ai-agent-mentor` exists and is used by Jarvis' runtime
  custom Agent dispatch mechanism as well as by Codex skill context.
