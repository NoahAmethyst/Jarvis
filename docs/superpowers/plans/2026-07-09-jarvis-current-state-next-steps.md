# Jarvis Current State Next Steps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the current Jarvis repository from "implemented and locally tested" to "remote-server deployable with safer API coverage, startup behavior, health checks, deployment documentation, and explicit user approval gates."

**Architecture:** Keep the existing LangGraph backend intact. Add missing tests and small operational surfaces around the current code: gRPC behavior coverage, HTTP health endpoints, storage-startup retry policy, deployment manifests/runbook, and documentation alignment. Deployment and image construction remain gated by user confirmation.

**Tech Stack:** Python 3.11+, LangGraph, LangChain, FastAPI, gRPC/protobuf, Qdrant, PostgreSQL, Docker, Kubernetes YAML, pytest.

## Global Constraints

- Do not build Docker images, push images, run `docker compose`, run `kubectl`, SSH to a remote server, or deploy to any remote host without first asking the user and receiving explicit confirmation.
- Jarvis is intended to deploy on a remote server; every deployment task must separate local file edits from build/push/deploy commands.
- Use `.venv/bin/python -m pytest ...` for local verification in this workspace.
- Keep `.codex/PROJECT_CONTEXT.md`, `.codex/NEXT_STEPS.md`, and `README.md` synchronized with behavior changes.
- Use commit messages in the repository rule format: `FIX`, `FEATURE`, or `OPTIMIZE` followed by numbered English change descriptions.
- Do not revert unrelated user changes. Current user-owned study-material changes may exist under `docs/study/interaction`.
- Keep `.agents/skills` intact; it is runtime configuration and project learning context.
- Treat `docs/superpowers/plans/2026-05-22-jarvis-implementation.md` as historical only.

---

## Current Baseline

- Latest known full local test command: `.venv/bin/python -m pytest tests/ -v`.
- Latest known result after Agent dispatch fallback work: `40 passed, 1 warning`.
- Existing runtime graph includes `memory_load -> agent_dispatch -> rag_retrieve -> plan_and_call -> tool_node -> reflect -> memory_write`.
- Existing deployment manifest is `jarvis.yaml`, with `AGENTS_DIR` and `AGENT_DISPATCH_THRESHOLD` in the ConfigMap.
- Existing Dockerfile copies the full repository into the image with `COPY . .`; there is no `.dockerignore`, so `.agents/skills` is included if present in the build context.

## File Map

```text
jarvis/
├── api/
│   ├── http/routes.py              # add health/readiness endpoints
│   └── grpc/servicer.py            # test behavior through direct servicer calls
├── main.py                         # add storage init retry helper
├── config.py                       # add startup retry config
└── ...
tests/
├── unit/test_grpc_servicer.py      # new gRPC behavior tests
├── unit/test_main_startup.py       # new startup retry tests
└── e2e/test_api.py                 # extend HTTP health endpoint tests
docs/
├── deployment/remote-server.md     # new remote deployment runbook
└── superpowers/plans/
    └── 2026-07-09-jarvis-current-state-next-steps.md
README.md                          # update tests/deployment notes
jarvis.yaml                         # update probes and deployment defaults
.codex/
├── PROJECT_CONTEXT.md
└── NEXT_STEPS.md
```

---

### Task 1: Add gRPC Servicer Behavior Tests

**Files:**
- Create: `tests/unit/test_grpc_servicer.py`
- Modify only if tests reveal a bug: `jarvis/api/grpc/servicer.py`

**Interfaces:**
- Consumes: `JarvisServicer.Chat/Ingest/GetMemory/DeleteMemory`.
- Produces: regression coverage for successful responses and gRPC error-code mapping.

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_grpc_servicer.py`:

```python
from unittest.mock import MagicMock, patch

import grpc

from jarvis.api.grpc import jarvis_pb2
from jarvis.api.grpc.servicer import JarvisServicer
from jarvis.llm.router import ProviderNotFoundError, ProviderUnavailableError


class FakeContext:
    def __init__(self):
        self.code = None
        self.details = None

    def set_code(self, code):
        self.code = code

    def set_details(self, details):
        self.details = details


def test_grpc_chat_returns_answer():
    servicer = JarvisServicer()
    request = jarvis_pb2.ChatRequest(message="hello", user_id="u1")
    context = FakeContext()

    with patch("jarvis.api.grpc.servicer.graph.invoke") as mock_graph:
        mock_graph.return_value = {"final_answer": "hi", "low_confidence": False}
        response = servicer.Chat(request, context)

    assert response.answer == "hi"
    assert response.low_confidence is False
    assert context.code is None
    initial_state = mock_graph.call_args.args[0]
    assert initial_state["query"] == "hello"
    assert initial_state["active_agent"] is None
    assert initial_state["agent_dispatch_score"] == 0.0


def test_grpc_chat_unknown_provider_maps_invalid_argument():
    servicer = JarvisServicer()
    request = jarvis_pb2.ChatRequest(message="hello", user_id="u1")
    context = FakeContext()

    with patch("jarvis.api.grpc.servicer.graph.invoke", side_effect=ProviderNotFoundError("provider not exist")):
        response = servicer.Chat(request, context)

    assert response.answer == ""
    assert context.code == grpc.StatusCode.INVALID_ARGUMENT
    assert context.details == "provider not exist"


def test_grpc_chat_provider_unavailable_maps_unavailable():
    servicer = JarvisServicer()
    request = jarvis_pb2.ChatRequest(message="hello", user_id="u1")
    context = FakeContext()

    with patch("jarvis.api.grpc.servicer.graph.invoke", side_effect=ProviderUnavailableError("provider not working:boom")):
        response = servicer.Chat(request, context)

    assert response.answer == ""
    assert context.code == grpc.StatusCode.UNAVAILABLE
    assert context.details == "provider not working:boom"


def test_grpc_ingest_internal_error_sets_internal():
    servicer = JarvisServicer()
    request = jarvis_pb2.IngestRequest(content="x", source_url="s", user_id="u1")
    context = FakeContext()

    with patch("jarvis.api.grpc.servicer.know_mem.store_knowledge", side_effect=RuntimeError("qdrant down")):
        response = servicer.Ingest(request, context)

    assert response.success is False
    assert context.code == grpc.StatusCode.INTERNAL
    assert context.details == "qdrant down"


def test_grpc_memory_methods_return_entries_and_delete():
    servicer = JarvisServicer()
    context = FakeContext()

    with patch("jarvis.api.grpc.servicer.conv_mem.get_history_records") as mock_history:
        mock_history.return_value = [{"role": "human", "content": "hi", "created_at": "2026-07-09T00:00:00"}]
        memory_response = servicer.GetMemory(jarvis_pb2.MemoryRequest(user_id="u1"), context)

    assert memory_response.entries[0].role == "human"
    assert memory_response.entries[0].content == "hi"

    with patch("jarvis.api.grpc.servicer.conv_mem.delete_history") as mock_delete:
        delete_response = servicer.DeleteMemory(jarvis_pb2.MemoryRequest(user_id="u1"), FakeContext())

    assert delete_response.success is True
    mock_delete.assert_called_once_with("u1")
```

- [ ] **Step 2: Run red test**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_grpc_servicer.py -v
```

Expected: FAIL only if current behavior is missing or imports are wrong. If it passes immediately, record that gRPC behavior was already covered by implementation and keep the test.

- [ ] **Step 3: Fix only proven defects**

If tests fail because `jarvis/api/grpc/servicer.py` behavior is wrong, adjust only the failing branch. Preserve current public response shapes.

- [ ] **Step 4: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_grpc_servicer.py -v
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_grpc_servicer.py jarvis/api/grpc/servicer.py
git commit -m "FEATURE
1. add grpc servicer behavior coverage
2. verify grpc error code mapping"
```

---

### Task 2: Add HTTP Health And Readiness Endpoints

**Files:**
- Modify: `jarvis/api/http/routes.py`
- Modify: `tests/e2e/test_api.py`
- Modify: `jarvis.yaml`
- Modify: `README.md`

**Interfaces:**
- Produces: `GET /healthz` for liveness and `GET /readyz` for Kubernetes readiness.
- Consumes: FastAPI `app`.

- [ ] **Step 1: Add failing API tests**

Append to `tests/e2e/test_api.py`:

```python
def test_healthz_returns_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_returns_ready(client):
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}
```

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/e2e/test_api.py::test_healthz_returns_ok tests/e2e/test_api.py::test_readyz_returns_ready -v
```

Expected: both tests fail with HTTP 404.

- [ ] **Step 3: Implement endpoints**

Add to `jarvis/api/http/routes.py` after the request models:

```python
@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    return {"status": "ready"}
```

- [ ] **Step 4: Update Kubernetes probes**

In `jarvis.yaml`, change Jarvis container probes:

```yaml
          readinessProbe:
            httpGet:
              path: /readyz
              port: 8080
            initialDelaySeconds: 15
            periodSeconds: 10
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 30
            periodSeconds: 30
            failureThreshold: 3
```

- [ ] **Step 5: Update README**

Add under HTTP API:

```markdown
### GET /healthz

Liveness probe endpoint.

### GET /readyz

Readiness probe endpoint.
```

- [ ] **Step 6: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/e2e/test_api.py -v
.venv/bin/python -c "import yaml; list(yaml.safe_load_all(open('jarvis.yaml'))); print('jarvis.yaml ok')"
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass and `jarvis.yaml ok`.

- [ ] **Step 7: Commit**

```bash
git add jarvis/api/http/routes.py tests/e2e/test_api.py jarvis.yaml README.md
git commit -m "FEATURE
1. add health and readiness endpoints
2. use health probes in kubernetes manifest"
```

---

### Task 3: Add Storage Startup Retry Policy

**Files:**
- Modify: `jarvis/config.py`
- Modify: `jarvis/main.py`
- Create: `tests/unit/test_main_startup.py`
- Modify: `README.md`
- Modify: `jarvis.yaml`

**Interfaces:**
- Produces: `initialize_storage(init_db_fn=..., init_collection_fn=..., sleep_fn=...)`.
- Consumes: `STORAGE_INIT_RETRIES` and `STORAGE_INIT_RETRY_SECONDS`.

- [ ] **Step 1: Add failing unit tests**

Create `tests/unit/test_main_startup.py`:

```python
import pytest

from jarvis.main import initialize_storage


def test_initialize_storage_succeeds_first_try():
    calls = []

    def init_db():
        calls.append("db")

    def init_collection():
        calls.append("qdrant")

    initialize_storage(init_db_fn=init_db, init_collection_fn=init_collection, retries=1, retry_seconds=0, sleep_fn=lambda _: None)

    assert calls == ["db", "qdrant"]


def test_initialize_storage_retries_then_succeeds():
    attempts = {"count": 0}
    sleeps = []

    def init_db():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("postgres starting")

    def init_collection():
        return None

    initialize_storage(init_db_fn=init_db, init_collection_fn=init_collection, retries=2, retry_seconds=3, sleep_fn=sleeps.append)

    assert attempts["count"] == 2
    assert sleeps == [3]


def test_initialize_storage_raises_after_retries_exhausted():
    def init_db():
        raise RuntimeError("postgres down")

    with pytest.raises(RuntimeError, match="postgres down"):
        initialize_storage(init_db_fn=init_db, init_collection_fn=lambda: None, retries=2, retry_seconds=0, sleep_fn=lambda _: None)
```

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_main_startup.py -v
```

Expected: FAIL with `ImportError` or missing `initialize_storage`.

- [ ] **Step 3: Add config**

In `jarvis/config.py`:

```python
STORAGE_INIT_RETRIES = int(os.getenv("STORAGE_INIT_RETRIES", "5"))
STORAGE_INIT_RETRY_SECONDS = float(os.getenv("STORAGE_INIT_RETRY_SECONDS", "2"))
```

- [ ] **Step 4: Implement startup retry helper**

In `jarvis/main.py`, import `time` and config values, then add:

```python
import time
from jarvis.config import HTTP_PORT, GRPC_PORT, STORAGE_INIT_RETRIES, STORAGE_INIT_RETRY_SECONDS


def initialize_storage(
    init_db_fn=init_db,
    init_collection_fn=init_collection,
    retries: int = STORAGE_INIT_RETRIES,
    retry_seconds: float = STORAGE_INIT_RETRY_SECONDS,
    sleep_fn=time.sleep,
):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            init_db_fn()
            init_collection_fn()
            return
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                raise
            logger.warning("Storage initialization failed on attempt %d/%d: %s", attempt, retries, exc)
            sleep_fn(retry_seconds)
    raise last_error
```

Change `serve()` from:

```python
    init_db()
    init_collection()
```

to:

```python
    initialize_storage()
```

- [ ] **Step 5: Update deployment config**

Add to `jarvis.yaml` ConfigMap:

```yaml
  STORAGE_INIT_RETRIES: "12"
  STORAGE_INIT_RETRY_SECONDS: "5"
```

- [ ] **Step 6: Update README env table**

Add:

```markdown
| `STORAGE_INIT_RETRIES` | `5` | 服务启动时初始化 PostgreSQL/Qdrant 的最大重试次数 |
| `STORAGE_INIT_RETRY_SECONDS` | `2` | 存储初始化失败后的重试间隔秒数 |
```

- [ ] **Step 7: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_main_startup.py -v
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add jarvis/config.py jarvis/main.py tests/unit/test_main_startup.py README.md jarvis.yaml
git commit -m "FEATURE
1. add storage startup retry policy
2. document startup retry configuration"
```

---

### Task 4: Write Remote Server Deployment Runbook With Approval Gate

**Files:**
- Create: `docs/deployment/remote-server.md`
- Modify: `README.md`
- Modify: `.codex/NEXT_STEPS.md`

**Interfaces:**
- Produces: human-approved deployment checklist.
- Does not run: `docker build`, `docker push`, `docker compose`, `kubectl`, `ssh`, or remote commands.

- [ ] **Step 1: Create runbook**

Create `docs/deployment/remote-server.md`:

```markdown
# Jarvis Remote Server Deployment Runbook

## Approval Gate

Before any deployment action, Codex must ask the user for explicit confirmation.
This includes:

- building a Docker image
- tagging a Docker image
- pushing an image to a registry
- running `docker compose`
- running `kubectl`
- connecting to a remote server over SSH
- changing remote secrets, ports, DNS, or firewall rules

## Required User Decisions

Collect these values before deployment:

| Decision | Required Value |
|----------|----------------|
| Deployment mode | Kubernetes or Docker Compose |
| Remote host | hostname or IP |
| Container registry | registry URL and image name |
| Image tag | immutable tag, e.g. git SHA |
| Public HTTP port | default `30080` if Kubernetes NodePort |
| Public gRPC port | default `30094` if Kubernetes NodePort |
| Secrets source | manual Kubernetes Secret, External Secrets, Vault, or `.env` |
| Required API keys | `SILICONFLOW_API_KEY`, optional `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `TAVILY_API_KEY` |
| Data persistence | remote PostgreSQL/Qdrant PVCs or external managed services |

## Preflight Checks

Run locally before requesting deployment approval:

```bash
.venv/bin/python -m pytest tests/ -v
.venv/bin/python -c "import yaml; list(yaml.safe_load_all(open('jarvis.yaml'))); print('jarvis.yaml ok')"
git status --short --branch
```

Expected:

- all tests pass
- `jarvis.yaml ok`
- no unintended uncommitted changes

## Kubernetes Deployment Outline

Do not run these commands until the user approves the target server and registry:

```bash
docker build -t <registry>/<image>:<tag> .
docker push <registry>/<image>:<tag>
kubectl apply -f jarvis.yaml
kubectl rollout status deployment/jarvis -n default
```

Before applying, update `jarvis.yaml` image from `jarvis:latest` to the approved immutable image tag.

## Docker Compose Deployment Outline

Do not run these commands until the user approves Docker Compose deployment:

```bash
docker compose up -d
.venv/bin/python jarvis/main.py
```

For production Compose, create a separate production compose file instead of reusing local dev defaults blindly.

## Post-deployment Checks

After user-approved deployment:

```bash
curl http://<host>:<http-port>/healthz
curl http://<host>:<http-port>/readyz
curl -X POST http://<host>:<http-port>/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"hello","user_id":"deployment-smoke"}'
```

Expected:

- `/healthz` returns `{"status":"ok"}`
- `/readyz` returns `{"status":"ready"}`
- `/chat` returns an `answer` field
```

- [ ] **Step 2: Link runbook from README**

Add to README after Quick Start:

```markdown
## 远端部署

远端服务器部署前必须先确认部署方式、镜像仓库、端口、密钥来源和数据持久化方案。部署流程见
`docs/deployment/remote-server.md`。在用户确认前，不应构建镜像、推送镜像或执行远端部署命令。
```

- [ ] **Step 3: Update `.codex/NEXT_STEPS.md`**

Mark deployment runbook status as completed and keep actual deployment pending user approval.

- [ ] **Step 4: Verify**

Run:

```bash
test -f docs/deployment/remote-server.md
git diff --check docs/deployment/remote-server.md README.md .codex/NEXT_STEPS.md
```

Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add docs/deployment/remote-server.md README.md .codex/NEXT_STEPS.md
git commit -m "FEATURE
1. add remote deployment approval runbook
2. document deployment confirmation gate"
```

---

### Task 5: Clarify Mocked Versus Real Integration Tests

**Files:**
- Modify: `README.md`
- Modify: `.codex/PROJECT_CONTEXT.md`
- Optionally create: `tests/integration/README.md`

**Interfaces:**
- Produces: accurate documentation for current test behavior.
- Consumes: existing tests under `tests/unit`, `tests/e2e`, `tests/integration`.

- [ ] **Step 1: Update README testing section**

Replace the current sentence:

```markdown
测试分三层：`tests/unit/`（mock LLM）、`tests/integration/`（真实 Qdrant/PostgreSQL）、`tests/e2e/`（FastAPI TestClient）。
```

with:

```markdown
测试分三层：

- `tests/unit/`：mock LLM、Agent dispatcher、工具注册等纯逻辑。
- `tests/integration/`：当前以 mock Qdrant/PostgreSQL/LLM 为主，验证 graph 和 RAG 调用链；不等同于真实外部服务验收。
- `tests/e2e/`：使用 FastAPI TestClient 验证 HTTP endpoint 行为。

真实 PostgreSQL/Qdrant/LLM/API key 联调应作为远端或本地部署 smoke test 单独执行。
```

- [ ] **Step 2: Add optional integration README**

Create `tests/integration/README.md`:

```markdown
# Integration Tests

Current integration tests are process-level integration tests with mocked external clients.
They verify Jarvis graph and RAG call wiring without requiring live PostgreSQL, Qdrant, or LLM APIs.

Live-service validation belongs in deployment smoke tests after the user approves the target environment.
```

- [ ] **Step 3: Update `.codex/PROJECT_CONTEXT.md`**

Remove the current inconsistency note saying README is inaccurate once README is fixed.

- [ ] **Step 4: Verify**

Run:

```bash
git diff --check README.md tests/integration/README.md .codex/PROJECT_CONTEXT.md
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/integration/README.md .codex/PROJECT_CONTEXT.md
git commit -m "FIX
1. clarify integration test scope
2. document live service validation boundary"
```

---

### Task 6: Add Minimal Operational Logging

**Files:**
- Modify: `jarvis/agent/nodes/agent_dispatch.py`
- Modify: `jarvis/agent/nodes/reflect.py`
- Modify: `jarvis/agent/graph.py` only if routing logs are needed.
- Modify: `tests/unit/test_agent_dispatch.py` only if behavior changes.

**Interfaces:**
- Produces: logs for selected agent, dispatch score, reflection score, retry count, and low-confidence outcome.
- Does not change response schema.

- [ ] **Step 1: Add behavior-neutral logs**

In `jarvis/agent/nodes/agent_dispatch.py`, after dispatch returns:

```python
if selected is not None:
    logger.info("Active agent selected: %s score=%.3f", selected.name, score)
else:
    logger.info("No active agent selected; best_score=%.3f", score)
```

In `jarvis/agent/nodes/reflect.py`, before return:

```python
logger.info(
    "Reflection score=%.3f retry_count=%d low_confidence=%s",
    score,
    retry_count,
    low_confidence,
)
```

- [ ] **Step 2: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_agent_dispatch.py tests/unit/test_reflect_node.py -v
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add jarvis/agent/nodes/agent_dispatch.py jarvis/agent/nodes/reflect.py
git commit -m "OPTIMIZE
1. add agent dispatch operational logs
2. add reflection retry diagnostic logs"
```

---

### Task 7: Final Pre-deployment Review Gate

**Files:**
- Modify: `.codex/NEXT_STEPS.md`
- Modify: `.codex/PROJECT_CONTEXT.md`
- No remote commands.

**Interfaces:**
- Produces: final checklist for user confirmation before any build/deploy step.

- [ ] **Step 1: Run final local verification**

Run:

```bash
.venv/bin/python -m pytest tests/ -v
.venv/bin/python -c "import yaml; list(yaml.safe_load_all(open('jarvis.yaml'))); print('jarvis.yaml ok')"
git status --short --branch
```

Expected:

- all tests pass
- `jarvis.yaml ok`
- only intended documentation updates are uncommitted

- [ ] **Step 2: Update `.codex/NEXT_STEPS.md`**

Set next step to:

```markdown
Next execution gate: ask the user for remote deployment decisions before building images or touching a remote server.
```

- [ ] **Step 3: Commit**

```bash
git add .codex/NEXT_STEPS.md .codex/PROJECT_CONTEXT.md
git commit -m "OPTIMIZE
1. record predeployment confirmation gate
2. update project context after deployment planning"
```

- [ ] **Step 4: Ask user for deployment confirmation**

Ask for:

```text
1. Deployment mode: Kubernetes or Docker Compose?
2. Remote server host/IP and OS?
3. Container registry and image name?
4. Should I build and push an image now?
5. Should I run remote deployment commands now?
```

Do not proceed until the user answers.

---

## Self-Review

**Spec coverage:** This plan covers current known gaps: gRPC tests, health probes, startup retry behavior, remote deployment documentation, mocked-vs-real test clarity, observability, and explicit deployment approval.

**Placeholder scan:** No `TBD`, `TODO`, `implement later`, or "write tests" placeholders remain. Every task includes concrete files, commands, and expected outcomes.

**Type consistency:** New functions and endpoints are consistently named: `initialize_storage`, `/healthz`, `/readyz`, `STORAGE_INIT_RETRIES`, and `STORAGE_INIT_RETRY_SECONDS`.

## Execution Options After User Confirmation

Plan complete and saved to `docs/superpowers/plans/2026-07-09-jarvis-current-state-next-steps.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

Before any image build, image push, Docker Compose deployment, Kubernetes apply, SSH command, or remote server change, Codex must ask the user for explicit confirmation.
