# Health Probes and Access Log Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add dedicated live/ready endpoints, point deployment probes at them, and suppress only their repetitive Uvicorn access records.

**Architecture:** FastAPI owns lightweight health semantics through `app.state.ready`. The logging module owns a narrow `uvicorn.access` filter. Docker and Kubernetes configuration consume the new endpoints without coupling health to Swagger or external dependencies.

**Tech Stack:** Python 3.11, FastAPI, standard logging, pytest, Docker, Kubernetes.

---

### Task 1: Health endpoints

**Files:**
- Modify: `jarvis/api/http/routes.py`
- Modify: `tests/e2e/test_api.py`

- [ ] **Step 1: Write failing endpoint tests**

```python
def test_liveness_is_available(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_is_unavailable_before_startup(client):
    client.app.state.ready = False
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "not ready"}


def test_readiness_is_available_after_startup(client):
    client.app.state.ready = True
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
```

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/e2e/test_api.py -k "liveness or readiness" -v`

Expected: all three requests return 404.

- [ ] **Step 3: Implement the endpoints**

Initialize `app.state.ready = False`, add `/health/live`, and add
`/health/ready` as asynchronous handlers with `include_in_schema=False`. Raise
`HTTPException(status_code=503, detail="not ready")` while the flag is false.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/pytest tests/e2e/test_api.py -k "liveness or readiness" -v`

Expected: 3 tests pass.

### Task 2: Startup readiness transition

**Files:**
- Modify: `jarvis/main.py`
- Modify: `tests/unit/test_main.py`

- [ ] **Step 1: Write a failing startup test**

Use existing async server fakes, set `main.app.state.ready = False`, call
`serve()`, and assert it becomes true only after `init_db`,
`init_collection`, and `grpc_server.start()` have run.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/unit/test_main.py::test_startup_marks_application_ready -v`

Expected: readiness remains false.

- [ ] **Step 3: Implement the transition**

Set `app.state.ready = False` at the start of `serve()` and set it to true
after the gRPC server starts and before Uvicorn is constructed.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/pytest tests/unit/test_main.py -v`

Expected: all main tests pass.

### Task 3: Focused Uvicorn access filter

**Files:**
- Modify: `jarvis/logging_config.py`
- Modify: `tests/unit/test_logging_config.py`

- [ ] **Step 1: Write failing filter tests**

Create representative `uvicorn.access` records with Uvicorn's argument layout
`(client, method, path, http_version, status_code)`. Assert the filter returns
false for `/health/live` and `/health/ready`, true for `/docs` and `/chat`, and
true for non-Uvicorn records.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/unit/test_logging_config.py -k health -v`

Expected: import or behavior failure because the filter is absent.

- [ ] **Step 3: Implement and attach the filter**

Add `HealthCheckAccessFilter(logging.Filter)` that reads `record.args[2]` only
for `uvicorn.access` records and suppresses the two exact health paths. Attach
one instance to the root `StreamHandler` in `configure_logging()`.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/pytest tests/unit/test_logging_config.py -v`

Expected: all logging tests pass.

### Task 4: Deployment configuration and documentation

**Files:**
- Modify: `jarvis.yaml`
- Modify: `Dockerfile`
- Modify: `API.md`
- Create: `tests/unit/test_health_deployment_config.py`

- [ ] **Step 1: Write failing manifest tests**

Load `jarvis.yaml` with `yaml.safe_load_all`, locate the Jarvis container, and
assert readiness uses `/health/ready` and liveness uses `/health/live`. Read
`Dockerfile` and assert its health command contains `/health/live` and not
`/docs`.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/unit/test_health_deployment_config.py -v`

Expected: assertions fail because all checks still use `/docs`.

- [ ] **Step 3: Update deployment files**

Replace the three `/docs` health targets with the dedicated paths. Update
`API.md` to document the two endpoints, their semantics, and the rule that
probes must not call external dependencies.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/pytest tests/unit/test_health_deployment_config.py -v`

Expected: manifest tests pass.

### Task 5: Verification, publication, and deployment

**Files:**
- Verify and stage only files listed in Tasks 1-4 plus this plan and its design.

- [ ] **Step 1: Run focused and complete tests**

```bash
.venv/bin/pytest tests/e2e/test_api.py tests/unit/test_main.py tests/unit/test_logging_config.py tests/unit/test_health_deployment_config.py -v
.venv/bin/pytest
.venv/bin/python -m compileall -q jarvis tests
```

Expected: all commands exit zero.

- [ ] **Step 2: Inspect and scan the exact task diff**

Run `git diff --check`, review the task-only staged diff, and scan
`origin/master..HEAD` plus staged task files for high-risk credential patterns
without printing values.

- [ ] **Step 3: Commit and push**

Commit only task paths with message:

```text
FIX add dedicated health probes and filter access logs
```

Push `master`, then monitor the triggered Docker Image CI and Update App runs
to terminal status.

- [ ] **Step 4: Synchronize and apply the manifest**

Copy only sanitized `jarvis.yaml` to `/root/jarvis/jarvis.yaml`, inspect the
remote diff without exposing secrets, apply it with Kubernetes, and wait for
the Deployment rollout.

- [ ] **Step 5: Verify production**

Confirm the live/ready endpoints return 200, inspect the active probe paths, and
sample recent logs long enough to cover at least two readiness periods and one
liveness period. Periodic health access entries must be absent while ordinary
application access logging remains enabled.
