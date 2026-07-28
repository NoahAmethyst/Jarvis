# Colored Logging and Model Startup Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add colored `INFO`/`WARN`/`ERROR` logs and non-blocking startup checks for the chat and embedding providers Jarvis actually uses.

**Architecture:** A focused `logging_config` module owns root logging and ANSI formatting. A focused `startup_checks` module discovers active chat providers, performs one real request per provider plus one embedding request, and converts failures into redacted log categories. `serve()` configures logging, runs the diagnostic checks defensively, and then continues its existing startup sequence.

**Tech Stack:** Python 3.11+, standard `logging`, Pydantic settings, LangChain chat/embedding interfaces, pytest.

---

### Task 1: Colored logging formatter

**Files:**
- Create: `jarvis/logging_config.py`
- Create: `tests/unit/test_logging_config.py`

- [ ] **Step 1: Write failing formatter tests**

```python
import logging

import pytest

from jarvis.logging_config import ColorLevelFormatter


@pytest.mark.parametrize(
    ("level", "label", "color"),
    [
        (logging.INFO, "INFO", "\x1b[32m"),
        (logging.WARNING, "WARN", "\x1b[33m"),
        (logging.ERROR, "ERROR", "\x1b[31m"),
    ],
)
def test_formatter_colors_supported_level_labels(level, label, color):
    formatter = ColorLevelFormatter("%(levelname)s %(message)s", use_color=True)
    record = logging.LogRecord("jarvis.test", level, __file__, 1, "message", (), None)

    rendered = formatter.format(record)

    assert rendered == f"{color}{label}\x1b[0m message"
    assert record.levelname == logging.getLevelName(level)


def test_formatter_honors_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    formatter = ColorLevelFormatter("%(levelname)s %(message)s")
    record = logging.LogRecord(
        "jarvis.test", logging.WARNING, __file__, 1, "message", (), None
    )

    assert formatter.format(record) == "WARN message"
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `pytest tests/unit/test_logging_config.py -v`

Expected: collection fails because `jarvis.logging_config` does not exist.

- [ ] **Step 3: Implement the formatter and root configuration**

Create `jarvis/logging_config.py` with:

```python
import copy
import logging
import os


LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
RESET = "\x1b[0m"
LEVEL_LABELS = {
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
}
LEVEL_COLORS = {
    logging.INFO: "\x1b[32m",
    logging.WARNING: "\x1b[33m",
    logging.ERROR: "\x1b[31m",
}


class ColorLevelFormatter(logging.Formatter):
    def __init__(self, *args, use_color: bool | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_color = "NO_COLOR" not in os.environ if use_color is None else use_color

    def format(self, record: logging.LogRecord) -> str:
        formatted_record = copy.copy(record)
        label = LEVEL_LABELS.get(record.levelno, record.levelname)
        if self.use_color and record.levelno in LEVEL_COLORS:
            label = f"{LEVEL_COLORS[record.levelno]}{label}{RESET}"
        formatted_record.levelname = label
        return super().format(formatted_record)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(ColorLevelFormatter(LOG_FORMAT))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
```

- [ ] **Step 4: Run the formatter tests and verify GREEN**

Run: `pytest tests/unit/test_logging_config.py -v`

Expected: 4 tests pass.

### Task 2: Active model startup checks

**Files:**
- Create: `jarvis/startup_checks.py`
- Modify: `jarvis/llm/errors.py`
- Modify: `jarvis/llm/adapters/base.py`
- Modify: `jarvis/llm/adapters/deepseek.py`
- Modify: `jarvis/llm/adapters/openai_compatible.py`
- Modify: `jarvis/llm/adapters/anthropic.py`
- Modify: `jarvis/memory/knowledge.py`
- Create: `tests/unit/test_startup_checks.py`
- Modify: `tests/unit/test_llm_adapters.py`
- Modify: `tests/unit/test_embedding_config.py`

- [ ] **Step 1: Write failing target-discovery tests**

Build an `LLMSettings` fixture with two profiles for provider `alpha`, one
profile for provider `beta`, and an unused provider `unused`. Assert that
`discover_active_chat_targets(settings)` returns only:

```python
[
    ChatTarget(provider_name="alpha", model_id="model-a"),
    ChatTarget(provider_name="beta", model_id="model-c"),
]
```

- [ ] **Step 2: Run the discovery test and verify RED**

Run: `pytest tests/unit/test_startup_checks.py::test_discovers_one_model_per_active_provider -v`

Expected: collection fails because `jarvis.startup_checks` does not exist.

- [ ] **Step 3: Implement chat target discovery**

Create `jarvis/startup_checks.py` with a frozen `ChatTarget` dataclass and:

```python
def discover_active_chat_targets(settings: LLMSettings) -> list[ChatTarget]:
    targets = []
    seen = set()
    for profile in settings.profiles.values():
        provider_name, model_id = parse_model_spec(profile.model)
        if provider_name in seen:
            continue
        seen.add(provider_name)
        targets.append(ChatTarget(provider_name, model_id))
    return targets
```

- [ ] **Step 4: Run the discovery test and verify GREEN**

Run: `pytest tests/unit/test_startup_checks.py::test_discovers_one_model_per_active_provider -v`

Expected: the test passes.

- [ ] **Step 5: Write failing chat-check tests**

Add fakes whose adapter returns a model with `invoke()`. Assert:

- one successful `invoke([HumanMessage(...)])` call per discovered provider;
- success logs contain provider/model and `succeeded`;
- a fake exception with `status_code = 401` logs `category=credential`;
- raw exception text such as `secret-response-body` never appears in logs; and
- one provider failure does not prevent the next provider from being checked.

- [ ] **Step 6: Run chat-check tests and verify RED**

Run: `pytest tests/unit/test_startup_checks.py -k "chat_check" -v`

Expected: tests fail because `check_chat_providers` and safe categorization are absent.

- [ ] **Step 7: Implement redacted chat checks**

Implement:

```python
def failure_category(error: Exception) -> str:
    if getattr(error, "status_code", None) in {401, 403}:
        return "credential"
    if isinstance(error, LLMConfigurationError):
        return "credential"
    if isinstance(error, (LLMTimeoutError, openai.APITimeoutError, anthropic.APITimeoutError)):
        return "timeout"
    if isinstance(
        error,
        (LLMUnavailableError, openai.APIConnectionError, anthropic.APIConnectionError),
    ):
        return "connectivity"
    return "provider"
```

Then implement `check_chat_providers(settings, adapters=None)` to create each
model with `ThinkingSettings(mode="disabled")`, invoke a minimal human message,
require an `AIMessage` response, and log only provider/model/category fields.
Catch failures inside the per-provider loop. Pass a 10-second request timeout
through each adapter so an unreachable provider cannot indefinitely block
startup.

- [ ] **Step 8: Run chat-check tests and verify GREEN**

Run: `pytest tests/unit/test_startup_checks.py -k "chat_check" -v`

Expected: all selected tests pass.

- [ ] **Step 9: Write failing embedding-check tests**

Add tests that inject an embeddings factory and assert:

- `embed_query("Jarvis startup connectivity check")` is called;
- the success log names the provider/model parsed from `EMBED_MODEL`; and
- a failed embedding request logs a safe category without raw exception text.

- [ ] **Step 10: Run embedding-check tests and verify RED**

Run: `pytest tests/unit/test_startup_checks.py -k "embedding_check" -v`

Expected: tests fail because `check_embedding_model` is absent.

- [ ] **Step 11: Implement the embedding and orchestration checks**

Implement `check_embedding_model(model_spec, embeddings_factory=None)` using
`jarvis.memory.knowledge._parse_embed_model` and `_get_embeddings`. Add
`run_model_startup_checks()` that loads LLM settings, logs a redacted error if
configuration loading fails, still runs the embedding check, and never sends
raw provider exceptions to a log call.

Make embedding parsing fail closed for malformed model specifications and
providers other than `siliconflow` or `openai`. Add a credential-specific error
subclass so missing keys are reported as `credential`, while invalid YAML or
schema remains `configuration`. Apply the same 10-second timeout to the
embedding client.

- [ ] **Step 12: Run all startup-check tests and verify GREEN**

Run: `pytest tests/unit/test_startup_checks.py -v`

Expected: all tests pass.

### Task 3: Startup wiring and Uvicorn logging

**Files:**
- Modify: `jarvis/main.py`
- Create: `tests/unit/test_main.py`

- [ ] **Step 1: Write a failing non-blocking startup test**

Patch `run_model_startup_checks` to raise `RuntimeError("secret-response-body")`,
patch `configure_logging`, and make `init_db` raise a sentinel exception. Await
`serve()` and assert the sentinel is raised, proving startup advanced past the
failed model check. Assert captured logs contain `category=internal` and exclude
the raw exception text.

- [ ] **Step 2: Run the startup test and verify RED**

Run: `pytest tests/unit/test_main.py -v`

Expected: the test fails because `serve()` does not run or isolate startup checks.

- [ ] **Step 3: Wire checks into `serve()`**

Replace `logging.basicConfig` with imports of `configure_logging` and
`run_model_startup_checks`. At the beginning of `serve()`:

```python
configure_logging()
try:
    run_model_startup_checks()
except Exception:
    logger.error("Model startup checks failed category=internal")
```

Pass `log_config=None` to `uvicorn.Config` so Uvicorn propagates through the
same root formatter.

- [ ] **Step 4: Run the startup test and verify GREEN**

Run: `pytest tests/unit/test_main.py -v`

Expected: the test passes.

### Task 4: Regression verification and publication

**Files:**
- Verify all task files plus the approved spec and this plan.

- [ ] **Step 1: Run focused tests**

Run:

```bash
pytest tests/unit/test_logging_config.py tests/unit/test_startup_checks.py tests/unit/test_main.py -v
```

Expected: all focused tests pass.

- [ ] **Step 2: Run the complete test suite**

Run: `pytest`

Expected: the complete suite passes with zero failures.

- [ ] **Step 3: Run syntax and diff validation**

Run:

```bash
python -m compileall -q jarvis tests
git diff --check
```

Expected: both commands exit zero.

- [ ] **Step 4: Review task-only diff and protect unrelated work**

Inspect `git status --short`, task-file diffs, and the staged diff. Stage only:

```text
jarvis/logging_config.py
jarvis/startup_checks.py
jarvis/main.py
jarvis/llm/errors.py
jarvis/llm/adapters/base.py
jarvis/llm/adapters/deepseek.py
jarvis/llm/adapters/openai_compatible.py
jarvis/llm/adapters/anthropic.py
jarvis/memory/knowledge.py
tests/unit/test_logging_config.py
tests/unit/test_startup_checks.py
tests/unit/test_main.py
tests/unit/test_llm_adapters.py
tests/unit/test_embedding_config.py
docs/superpowers/plans/2026-07-28-colored-logging-and-model-startup-checks.md
```

Do not stage or alter any pre-existing unrelated file.

- [ ] **Step 5: Scan the exact commits being pushed for secrets**

Review `origin/master..HEAD` and the staged diff for secret-shaped values
without printing values. Abort publication if a real credential is detected.

- [ ] **Step 6: Commit and push**

Commit with:

```bash
git commit -m "FEATURE add colored logs and model startup checks"
git push origin master
```

- [ ] **Step 7: Monitor GitHub Actions**

Find the workflow run triggered by the pushed commit and monitor it until
success or terminal failure. If it fails, report the failing job and step before
making any further deployment change.
