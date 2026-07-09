# Jarvis Study Map

Use this reference to locate the project learning materials for AI Agent mentoring.

## User Profile

Source: `docs/study/interaction/learning-profile.md`

- Backend engineer with Golang as main language; familiar with Java and Python.
- Has microservices, Kubernetes, and backend service experience.
- Goal: transition toward AI Agent engineering or AI model deployment/platform engineering.
- Current gap: LLM application abstraction and mechanism-level interview expression.
- Teaching should connect AI concepts to backend boundaries, state, services, deployment, observability, and cost.

## Teaching Protocol

Source: `docs/study/interaction/teacher-protocol.md`

Teach concepts through:

```text
Problem -> What breaks without it -> Mechanism -> System layer -> Interview expression -> Jarvis files
```

Answer quality levels:

1. Term level.
2. Phenomenon level.
3. Mechanism level.
4. Engineering level.

## Staged Plan

Source: `docs/study/interaction/staged-learning-plan.md`

- 初阶: LLM application foundations: LLM, context, hallucination, RAG basics, Tool Calling basics, Memory basics.
- 中阶: Agent system design: AgentState, Agent Graph, Tool Registry, RAG pipeline, Memory, Planner/Executor, Reflection.
- 高阶: Engineering and platformization: API boundary, configuration, observability, reliability, cost control, security, Docker/Kubernetes, interview project depth.

Use stage completion criteria instead of calendar time.

## Concept Knowledge Map

Source: `docs/study/interaction/knowledge-map.md`

Key expressions:

- LLM is `P(next_token | context)`.
- Hallucination happens because language probability is not the same as factual verification.
- RAG changes context, not model parameters.
- Chunking balances semantic completeness and retrieval precision.
- top-k balances recall and noise.
- rerank addresses "semantically similar but not task-relevant" retrieval.
- Memory maintains cross-step and cross-turn state.
- RAG is query-driven external retrieval; Memory is process-driven state accumulation.
- Tool Calling lets the model choose intent and arguments while the system validates and executes.

## Interview Project

Source: `docs/study/interaction/interview-agent-project.md`

Main project theme:

```text
Multi-tool Agent + AI inference/platform deployment
```

Core story:

- API receives natural-language tasks.
- AgentState carries request and execution context.
- Planner decomposes tasks.
- Executor invokes tools.
- RAG provides external knowledge constraints.
- Memory maintains multi-step state.
- Reflection/Validation checks results and triggers finite retries.
- Docker/Kubernetes deployment supports scaling and operational reliability.

## Jarvis Study Chapters

Source: `docs/study/index.md`

Recommended order:

1. `docs/study/00-agent-learning-map.md`
2. `docs/study/01-project-architecture.md`
3. `docs/study/02-agent-state-and-message-flow.md`
4. `docs/study/03-langgraph-execution-graph.md`
5. `docs/study/04-llm-router-and-model-abstraction.md`
6. `docs/study/05-tool-calling-and-registry.md`
7. `docs/study/06-memory-and-rag.md`
8. `docs/study/07-reflection-and-self-correction.md`
9. `docs/study/08-api-boundary-and-service-design.md`
10. `docs/study/09-engineering-thinking.md`

## Jarvis Code Map

Use this order for code walkthroughs:

1. `jarvis/api/http/routes.py`: HTTP entry and AgentState construction.
2. `jarvis/api/grpc/servicer.py`: gRPC entry using the same core Agent capability.
3. `jarvis/agent/state.py`: runtime state shape.
4. `jarvis/agent/graph.py`: nodes, routing, and loop structure.
5. `jarvis/agent/nodes/plan_and_call.py`: model planning, context, history, tools.
6. `jarvis/agent/nodes/rag_retrieve.py`: RAG retrieval node.
7. `jarvis/agent/nodes/memory_load.py` and `memory_write.py`: memory lifecycle.
8. `jarvis/agent/nodes/reflect.py`: answer scoring and retry.
9. `jarvis/tools/registry.py`: tool registration.
10. `jarvis/memory/conversation.py` and `knowledge.py`: conversation and knowledge storage.
11. `jarvis/llm/router.py`: provider/model abstraction.
12. `jarvis/config.py`, `docker-compose.yml`, `Dockerfile`: configuration and deployment.

## Test Map

- `tests/unit/test_llm_router.py`: model routing.
- `tests/unit/test_tool_registry.py`: tool registration.
- `tests/unit/test_reflect_node.py`: reflection logic.
- `tests/integration/test_graph_flow.py`: graph flow.
- `tests/integration/test_rag_pipeline.py`: RAG pipeline.
- `tests/e2e/test_api.py`: API behavior.
