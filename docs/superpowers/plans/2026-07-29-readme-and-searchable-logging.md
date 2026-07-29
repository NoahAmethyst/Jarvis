# README and Searchable Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add stable `【类别:值】` tags to Jarvis critical logs and update README so operators can understand and search model, node, storage, service, and health events.

**Architecture:** A small pure formatter in `jarvis/logging_config.py` owns tag syntax and sanitization. Existing business modules opt into the helper only at critical events, preserving log levels, color rendering, health-access filtering, application behavior, and ordinary Uvicorn access logs. README documents the behavior verified by focused unit tests and the full test suite.

**Tech Stack:** Python 3.11+, standard-library `logging`, pytest, FastAPI/Uvicorn, LangGraph, Markdown

---

## File Map

- Modify `jarvis/logging_config.py`: provide the reusable tag formatter without changing color or access filtering.
- Modify `jarvis/startup_checks.py`: label Chat and Embedding connectivity results.
- Modify `jarvis/main.py`: label startup, storage, HTTP, and gRPC lifecycle events.
- Modify `jarvis/llm/gateway.py`: label selected provider/model decisions and request failures.
- Modify `jarvis/llm/router.py`: label legacy provider configuration failures without logging exception bodies.
- Modify `jarvis/agents/loader.py`: label Agent definition parse failures.
- Modify `jarvis/agents/dispatcher.py`: label Agent scoring, selection, threshold, and fallback decisions.
- Modify `jarvis/agent/nodes/*.py`: label critical node degradation and reflection events.
- Modify `jarvis/memory/conversation.py`: label PostgreSQL initialization.
- Modify `jarvis/memory/knowledge.py`: label Qdrant collection readiness.
- Modify focused tests under `tests/unit/`: verify formatting, redaction, and representative event tags.
- Modify `README.md`: document core capabilities, startup checks, searchable colored logs, health endpoints, and deployment behavior.

### Task 1: Add the canonical log-tag formatter

**Files:**
- Modify: `tests/unit/test_logging_config.py`
- Modify: `jarvis/logging_config.py`

- [ ] **Step 1: Write failing formatter tests**

Add the import and tests:

```python
from jarvis.logging_config import format_log_tags


def test_format_log_tags_preserves_field_order():
    assert format_log_tags(
        ("供应商", "deepseek"),
        ("模型", "deepseek-v4-pro"),
        ("结果", "成功"),
    ) == "【供应商:deepseek】【模型:deepseek-v4-pro】【结果:成功】"


def test_format_log_tags_keeps_each_tag_on_one_safe_line():
    assert format_log_tags(
        ("节点", "rag_retrieve\nforged"),
        ("组件", "Qdrant】extra【"),
    ) == "【节点:rag_retrieve forged】【组件:Qdrant)extra(】"
```

- [ ] **Step 2: Run the tests and verify the missing helper fails**

Run:

```bash
.venv/bin/pytest tests/unit/test_logging_config.py -q
```

Expected: collection fails because `format_log_tags` does not exist.

- [ ] **Step 3: Implement the minimal pure formatter**

Add to `jarvis/logging_config.py`:

```python
def _safe_tag_part(value: object) -> str:
    return (
        str(value)
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("【", "(")
        .replace("】", ")")
    )


def format_log_tags(*fields: tuple[str, object]) -> str:
    return "".join(
        f"【{_safe_tag_part(name)}:{_safe_tag_part(value)}】"
        for name, value in fields
    )
```

- [ ] **Step 4: Run the focused tests**

Run:

```bash
.venv/bin/pytest tests/unit/test_logging_config.py -q
```

Expected: all logging configuration tests pass.

### Task 2: Label provider checks and service lifecycle logs

**Files:**
- Modify: `tests/unit/test_startup_checks.py`
- Modify: `tests/unit/test_main.py`
- Modify: `tests/unit/test_llm_gateway.py`
- Modify: `jarvis/startup_checks.py`
- Modify: `jarvis/main.py`
- Modify: `jarvis/llm/gateway.py`
- Modify: `jarvis/llm/router.py`

- [ ] **Step 1: Change startup-check assertions to the approved labels**

Assert representative success and failure messages exactly:

```python
assert (
    "【供应商:deepseek】【模型:model-a】【类型:Chat】【结果:成功】 "
    "Startup connectivity check completed"
) in caplog.text

assert (
    "【供应商:deepseek】【模型:model-a】【类型:Chat】【结果:失败】"
    "【类别:credential】 Startup connectivity check failed"
) in caplog.text

assert (
    "【供应商:siliconflow】【模型:Qwen/Qwen3-Embedding-8B】"
    "【类型:Embedding】【结果:成功】 Startup connectivity check completed"
) in caplog.text
```

Retain all assertions that prove secret response bodies are absent.

- [ ] **Step 2: Add lifecycle and gateway log assertions**

In `tests/unit/test_main.py`, update the internal model-check failure assertion:

```python
assert (
    "【组件:模型启动检查】【结果:失败】【类别:internal】 "
    "Unexpected startup check failure"
) in caplog.text
```

In `tests/unit/test_llm_gateway.py`, capture a failed request and assert:

```python
assert "【供应商:deepseek】【模型:model-a】【结果:失败】" in caplog.text
assert "【错误:" in caplog.text
```

- [ ] **Step 3: Run the focused tests and verify they fail on old text**

Run:

```bash
.venv/bin/pytest tests/unit/test_startup_checks.py tests/unit/test_main.py tests/unit/test_llm_gateway.py -q
```

Expected: assertions fail because current logs use `provider=...` prose.

- [ ] **Step 4: Migrate startup checks**

Import `format_log_tags` and emit:

```python
logger.info(
    "%s Startup connectivity check completed",
    format_log_tags(
        ("供应商", target.provider_name),
        ("模型", target.model_id),
        ("类型", "Chat"),
        ("结果", "成功"),
    ),
)
```

Failures use the same order followed by `("类别", failure_category(error))`.
Embedding uses `("类型", "Embedding")`. Configuration failures that cannot be parsed
use `unknown` for supplier and model.

- [ ] **Step 5: Migrate service lifecycle logs**

Use these stable events in `jarvis/main.py`:

```python
logger.error(
    "%s Unexpected startup check failure",
    format_log_tags(("组件", "模型启动检查"), ("结果", "失败"), ("类别", "internal")),
)
logger.info(
    "%s Initializing storage",
    format_log_tags(("组件", "存储"), ("状态", "初始化")),
)
logger.info(
    "%s Server listening",
    format_log_tags(("服务", "gRPC"), ("端口", GRPC_PORT), ("状态", "就绪")),
)
logger.info(
    "%s Server starting",
    format_log_tags(("服务", "HTTP"), ("端口", HTTP_PORT), ("状态", "启动")),
)
```

- [ ] **Step 6: Migrate gateway and legacy router logs**

Gateway thinking fallback labels supplier/model and `状态:降级`. Gateway request
failures label supplier/model, `结果:失败`, and exception type as `错误`, while
retaining the current retry behavior.

Legacy router failures label `组件:LLM路由`; known providers additionally label
`供应商`. Log only `type(error).__name__`, never `str(error)`.

- [ ] **Step 7: Run the focused tests**

Run:

```bash
.venv/bin/pytest tests/unit/test_startup_checks.py tests/unit/test_main.py tests/unit/test_llm_gateway.py tests/unit/test_llm_router.py -q
```

Expected: all selected tests pass.

### Task 3: Label Agent, node, storage, and configuration events

**Files:**
- Modify: `tests/unit/test_agent_dispatch.py`
- Modify: `tests/unit/test_reflect_node.py`
- Modify: `tests/unit/test_memory_persistence.py`
- Modify: `jarvis/agents/loader.py`
- Modify: `jarvis/agents/dispatcher.py`
- Modify: `jarvis/agent/nodes/agent_dispatch.py`
- Modify: `jarvis/agent/nodes/memory_load.py`
- Modify: `jarvis/agent/nodes/rag_retrieve.py`
- Modify: `jarvis/agent/nodes/reflect.py`
- Modify: `jarvis/agent/nodes/memory_write.py`
- Modify: `jarvis/memory/conversation.py`
- Modify: `jarvis/memory/knowledge.py`

- [ ] **Step 1: Add representative failing assertions**

Use `caplog` to assert:

```python
assert (
    "【节点:agent_dispatch】【Agent:TestAgent】【评分:0.90】 Agent selected"
) in caplog.text
assert (
    "【节点:agent_dispatch】【Agent:TestAgent】【评分:0.30】"
    "【阈值:0.60】【状态:跳过】 Best Agent is below threshold"
) in caplog.text
assert (
    "【节点:reflect】【状态:解析失败】【默认评分:0.50】 "
    "Could not parse reflection score"
) in caplog.text
assert "I cannot score this." not in caplog.text
```

Add a low-reflection-score assertion:

```python
assert (
    "【节点:reflect】【评分:0.30】【重试:1/3】【状态:重试】 "
    "Reflection requested another answer"
) in caplog.text
```

Add degradation assertions for `memory_load`, `rag_retrieve`, and `memory_write`
that include node/component/status/error-type labels and exclude injected secret
exception messages.

- [ ] **Step 2: Run focused tests and verify old logs fail**

Run:

```bash
.venv/bin/pytest tests/unit/test_agent_dispatch.py tests/unit/test_reflect_node.py tests/unit/test_memory_persistence.py -q
```

Expected: new label assertions fail.

- [ ] **Step 3: Migrate Agent loader and dispatcher events**

Agent parse failures use:

```python
logger.warning(
    "%s Failed to parse Agent definition file=%s",
    format_log_tags(
        ("组件", "Agent加载器"),
        ("结果", "失败"),
        ("错误", type(error).__name__),
    ),
    path,
)
```

Dispatcher selection, threshold skip, per-Agent score failure, and outer fallback
use `节点:agent_dispatch`, safe Agent name, score/threshold where available, stable
status, and exception type only. Threshold skip moves from DEBUG to INFO so the
key decision is visible at the configured production log level.

- [ ] **Step 4: Migrate node degradation and reflection events**

Use:

```python
format_log_tags(
    ("节点", "memory_load"),
    ("组件", "PostgreSQL"),
    ("状态", "降级"),
    ("错误", type(error).__name__),
)
```

and the equivalent `rag_retrieve/Qdrant`, `agent_dispatch`, and
`memory_write/PostgreSQL|Qdrant` combinations.

Reflection parsing no longer logs `response.content`. When a score is below the
threshold, log `评分`, `重试`, and either `状态:重试` or `状态:低置信度`.

- [ ] **Step 5: Label storage readiness**

PostgreSQL initialization emits:

```text
【组件:PostgreSQL】【状态:就绪】 Conversation storage initialized
```

Qdrant initialization emits:

```text
【组件:Qdrant】【集合:jarvis_knowledge】【状态:就绪】 Knowledge collection initialized
```

- [ ] **Step 6: Run the node and storage tests**

Run:

```bash
.venv/bin/pytest tests/unit/test_agent_dispatch.py tests/unit/test_reflect_node.py tests/unit/test_memory_persistence.py tests/integration/test_graph_flow.py tests/integration/test_rag_pipeline.py -q
```

Expected: all selected tests pass with no secret test strings in captured logs.

### Task 4: Update README for operators

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a concise core-capabilities list**

Immediately after the introduction, summarize:

- LangGraph workflow with Agent dispatch and reflection;
- Profile-based multi-provider LLM gateway;
- PostgreSQL conversation memory and Qdrant RAG;
- HTTP/gRPC interfaces;
- startup provider/Embedding checks;
- colored searchable logs and dedicated health probes.

- [ ] **Step 2: Clarify quick-start behavior**

Keep the existing four-step local startup flow, ensure `docker-compose.yml`,
`.env.example`, `llm.yaml`, ports, required default keys, storage hard
dependencies, and network exposure statements match the repository.

- [ ] **Step 3: Add “启动连通性检查”**

Document that startup performs one bounded real request for every distinct Chat
provider actually referenced by `profiles`, plus the current `EMBED_MODEL`.
Explain that failures are redacted and non-blocking, while PostgreSQL/Qdrant
initialization remains blocking.

- [ ] **Step 4: Add “日志与可观测性”**

Document:

```text
INFO=绿色  WARN=黄色  ERROR=红色
NO_COLOR=1 python jarvis/main.py
【供应商:deepseek】【模型:deepseek-v4-pro】【类型:Chat】【结果:成功】 ...
【节点:rag_retrieve】【组件:Qdrant】【状态:降级】 ...
```

Provide exact-match search examples using `grep -F`, and state that labels never
contain API keys, full prompts, or full model responses.

- [ ] **Step 5: Add “健康检查”**

Add a table:

| Endpoint | Success | Failure | Purpose |
|---|---|---|---|
| `/health/live` | `200 {"status":"ok"}` | process unavailable | liveness |
| `/health/ready` | `200 {"status":"ready"}` | `503 {"detail":"not ready"}` | readiness |

Explain that Docker and Kubernetes use these endpoints, external provider calls
are not executed by probes, and their Uvicorn access records are filtered while
ordinary `/docs`, `/chat`, and other access logs remain visible.

- [ ] **Step 6: Correct cross-references and directory comments**

Verify all linked local files exist and the directory tree includes
`startup_checks.py`, `logging_config.py`, `agents/`, and the HTTP/gRPC modules.
Keep detailed API contracts in `API.md`.

### Task 5: Full verification and publication preparation

**Files:**
- Verify all modified task files only.

- [ ] **Step 1: Run focused logging and behavior tests**

Run:

```bash
.venv/bin/pytest tests/unit/test_logging_config.py tests/unit/test_startup_checks.py tests/unit/test_main.py tests/unit/test_llm_gateway.py tests/unit/test_llm_router.py tests/unit/test_agent_dispatch.py tests/unit/test_reflect_node.py tests/unit/test_memory_persistence.py -q
```

Expected: all pass.

- [ ] **Step 2: Run the complete suite**

Run:

```bash
.venv/bin/pytest -q
```

Expected: all tests pass; the existing Starlette/httpx deprecation warning may
remain.

- [ ] **Step 3: Compile Python sources**

Run:

```bash
.venv/bin/python -m compileall -q jarvis tests
```

Expected: exit code 0.

- [ ] **Step 4: Verify README references**

Run a read-only script that extracts relative Markdown targets from `README.md`,
removes anchors, and asserts each referenced repository path exists. Also verify
the documented health paths and environment variable names occur in the source
configuration.

Expected: no missing targets or mismatched documented identifiers.

- [ ] **Step 5: Review diff and secrets**

Run `git diff --check`, inspect the exact task-file diff, and scan added lines for
credential-like assignments. Confirm unrelated study files and
`.github/workflows/Dockerfile` remain outside the task commit.

- [ ] **Step 6: Commit only task files**

Commit the implementation and README with:

```bash
git commit --only <exact-task-file-list> -m "FEATURE add searchable critical logs and refresh README"
```

Do not include any unrelated staged, unstaged, or untracked files.

