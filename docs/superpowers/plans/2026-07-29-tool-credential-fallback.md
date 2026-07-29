# Tool Credential Checks and Graceful Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent missing or temporarily unavailable external tools from aborting Chat requests while providing redacted startup credential diagnostics.

**Architecture:** Tool registrations declare required environment variables and the registry exposes only currently available tools. Startup checks audit active model, embedding, and tool credentials without reading values into logs. A dedicated graph node converts supported `ToolUnavailableError` failures into ToolMessages, disables the failed tool for the current request, and lets the model answer directly.

**Tech Stack:** Python 3.11, LangChain `StructuredTool`, LangGraph, Requests, Pytest

---

## File Map

- Create `jarvis/tools/errors.py`: safe operational tool exception and HTTP classification.
- Create `jarvis/agent/nodes/tool_execute.py`: per-request safe tool execution.
- Modify `jarvis/tools/registry.py`: registration metadata and availability filtering.
- Modify `jarvis/tools/search.py`: Tavily credential declaration and failure normalization.
- Modify `jarvis/tools/scraper.py`: HTTP failure normalization.
- Modify `jarvis/startup_checks.py`: credential discovery, redacted audit, and probe skipping.
- Modify `jarvis/agent/state.py`: per-request unavailable-tool state.
- Modify `jarvis/agent/nodes/plan_and_call.py`: bind only available request tools.
- Modify `jarvis/agent/graph.py`: replace generic ToolNode with safe execution node.
- Modify `jarvis/api/http/routes.py`: initialize unavailable-tool state.
- Modify `jarvis/api/grpc/servicer.py`: initialize unavailable-tool state.
- Modify `jarvis/main.py`: retain the unified startup-check entry point.
- Modify `tests/unit/test_tool_registry.py`: registry metadata and filtering tests.
- Create `tests/unit/test_external_tools.py`: tool failure classification tests.
- Create `tests/unit/test_tool_execute.py`: safe execution and logging tests.
- Modify `tests/unit/test_startup_checks.py`: credential audit tests.
- Modify `tests/integration/test_graph_flow.py`: direct-answer fallback regression.
- Modify `README.md`: startup audit and tool degradation behavior.

### Task 1: Declarative tool requirements

**Files:**
- Modify: `jarvis/tools/registry.py`
- Modify: `tests/unit/test_tool_registry.py`

- [ ] **Step 1: Write failing registry tests**

```python
def test_tool_with_missing_requirement_is_filtered(monkeypatch):
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)

    @register_tool(
        name="search",
        description="Search",
        required_env_vars=("SEARCH_API_KEY",),
    )
    def search(query: str) -> str:
        return query

    assert get_tools() == []
    assert get_tool_registration("search").missing_env_vars() == (
        "SEARCH_API_KEY",
    )


def test_excluded_tool_is_filtered(monkeypatch):
    monkeypatch.setenv("SEARCH_API_KEY", "configured")

    @register_tool(
        name="search",
        description="Search",
        required_env_vars=("SEARCH_API_KEY",),
    )
    def search(query: str) -> str:
        return query

    assert [tool.name for tool in get_tools()] == ["search"]
    assert get_tools(excluded_names={"search"}) == []
```

- [ ] **Step 2: Verify RED**

Run: `pytest tests/unit/test_tool_registry.py -q`

Expected: FAIL because `required_env_vars`, `get_tool_registration`, and
`excluded_names` do not exist.

- [ ] **Step 3: Implement registry metadata**

```python
import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from langchain_core.tools import StructuredTool


@dataclass(frozen=True)
class ToolRegistration:
    tool: StructuredTool
    required_env_vars: tuple[str, ...] = ()

    def missing_env_vars(
        self,
        environ: Mapping[str, str] | None = None,
    ) -> tuple[str, ...]:
        source = os.environ if environ is None else environ
        return tuple(name for name in self.required_env_vars if not source.get(name))


_REGISTRY: dict[str, ToolRegistration] = {}


def register_tool(
    name: str,
    description: str,
    required_env_vars: tuple[str, ...] = (),
):
    def decorator(func: Callable) -> Callable:
        tool = StructuredTool.from_function(
            func=func,
            name=name,
            description=description,
        )
        _REGISTRY[name] = ToolRegistration(tool, tuple(required_env_vars))
        return func

    return decorator


def get_tool_registrations() -> list[ToolRegistration]:
    return list(_REGISTRY.values())


def get_tool_registration(name: str) -> ToolRegistration | None:
    return _REGISTRY.get(name)


def get_tools(excluded_names: Iterable[str] = ()) -> list[StructuredTool]:
    excluded = set(excluded_names)
    return [
        registration.tool
        for name, registration in _REGISTRY.items()
        if name not in excluded and not registration.missing_env_vars()
    ]
```

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/unit/test_tool_registry.py -q`

Expected: all registry tests pass.

- [ ] **Step 5: Commit**

```bash
git add jarvis/tools/registry.py tests/unit/test_tool_registry.py
git commit -m "FEATURE declare tool credential requirements"
```

### Task 2: Startup credential audit

**Files:**
- Modify: `jarvis/startup_checks.py`
- Modify: `tests/unit/test_startup_checks.py`

- [ ] **Step 1: Write failing credential-audit tests**

```python
def test_credential_audit_logs_status_without_values(
    monkeypatch,
    caplog,
):
    monkeypatch.setenv("ALPHA_API_KEY", "secret-alpha")
    monkeypatch.delenv("BETA_API_KEY", raising=False)
    monkeypatch.setenv("SILICONFLOW_API_KEY", "secret-embedding")

    with caplog.at_level(logging.INFO, logger="jarvis.startup_checks"):
        missing = check_required_credentials(
            _settings(),
            "siliconflow/embedding-model",
            tool_registrations=[],
        )

    assert missing == {"BETA_API_KEY"}
    assert "【组件:alpha】【类型:Chat】【配置:ALPHA_API_KEY】【状态:已配置】" in caplog.text
    assert "【组件:beta】【类型:Chat】【配置:BETA_API_KEY】【状态:未配置】" in caplog.text
    assert "secret-alpha" not in caplog.text
    assert "secret-embedding" not in caplog.text


def test_missing_chat_credential_skips_connectivity_probe(caplog):
    adapter = FakeAdapter(FakeModel(AIMessage(content="OK")))

    check_chat_providers(
        _settings(),
        adapters={"deepseek": adapter, "openai_compatible": adapter},
        missing_env_vars={"ALPHA_API_KEY", "BETA_API_KEY"},
    )

    assert adapter.calls == []
```

- [ ] **Step 2: Verify RED**

Run: `pytest tests/unit/test_startup_checks.py -q`

Expected: FAIL because the credential-audit API and probe filter are absent.

- [ ] **Step 3: Implement safe discovery and logging**

Add a frozen `CredentialTarget(component, component_type, env_var)` dataclass,
derive active Chat targets from `ProviderSettings.api_key_env`, map
`siliconflow` and `openai` embedding providers to their API-key environment
variables, and derive Tool targets from `ToolRegistration.required_env_vars`.

Implement:

```python
def check_required_credentials(
    settings: LLMSettings | None,
    embedding_model_spec: str,
    tool_registrations: Iterable[ToolRegistration] | None = None,
    environ: Mapping[str, str] | None = None,
) -> set[str]:
    source = os.environ if environ is None else environ
    missing: set[str] = set()
    for target in discover_credential_targets(
        settings,
        embedding_model_spec,
        tool_registrations=tool_registrations,
    ):
        configured = bool(source.get(target.env_var))
        if not configured:
            missing.add(target.env_var)
        log = logger.info if configured else logger.warning
        log(
            "%s Required credential %s",
            format_log_tags(
                ("组件", target.component),
                ("类型", target.component_type),
                ("配置", target.env_var),
                ("状态", "已配置" if configured else "未配置"),
            ),
            "is configured" if configured else "is not configured",
        )
    return missing
```

Pass the missing set to Chat and Embedding probes and skip only those probes.
Continue probing configured credentials so invalid credentials and provider
outages retain ERROR logs. Always run the tool audit even if LLM configuration
loading fails.

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/unit/test_startup_checks.py -q`

Expected: all startup-check tests pass, with no credential values in captured
logs.

- [ ] **Step 5: Commit**

```bash
git add jarvis/startup_checks.py tests/unit/test_startup_checks.py
git commit -m "FEATURE audit startup credential configuration"
```

### Task 3: Normalize external tool outages

**Files:**
- Create: `jarvis/tools/errors.py`
- Modify: `jarvis/tools/search.py`
- Modify: `jarvis/tools/scraper.py`
- Create: `tests/unit/test_external_tools.py`

- [ ] **Step 1: Write failing external-tool tests**

```python
@pytest.mark.parametrize(
    ("status_code", "category"),
    [(401, "credential"), (403, "credential"), (500, "provider"), (503, "provider")],
)
def test_web_search_normalizes_supported_http_failures(
    monkeypatch,
    status_code,
    category,
):
    monkeypatch.setattr(search, "TAVILY_API_KEY", "configured")
    response = MagicMock(status_code=status_code)
    monkeypatch.setattr(search.requests, "post", MagicMock(return_value=response))

    with pytest.raises(ToolUnavailableError) as raised:
        search.web_search("query")

    assert raised.value.tool_name == "web_search"
    assert raised.value.category == category


def test_web_scrape_normalizes_timeout(monkeypatch):
    monkeypatch.setattr(
        scraper.requests,
        "get",
        MagicMock(side_effect=requests.Timeout("secret-response")),
    )

    with pytest.raises(ToolUnavailableError) as raised:
        scraper.web_scrape("https://example.com")

    assert raised.value.category == "timeout"


def test_web_search_preserves_unsupported_400(monkeypatch):
    monkeypatch.setattr(search, "TAVILY_API_KEY", "configured")
    response = MagicMock(status_code=400)
    response.raise_for_status.side_effect = requests.HTTPError("bad request")
    monkeypatch.setattr(search.requests, "post", MagicMock(return_value=response))

    with pytest.raises(requests.HTTPError):
        search.web_search("query")
```

- [ ] **Step 2: Verify RED**

Run: `pytest tests/unit/test_external_tools.py -q`

Expected: FAIL because `ToolUnavailableError` and normalization are absent.

- [ ] **Step 3: Implement safe failure normalization**

```python
class ToolUnavailableError(RuntimeError):
    def __init__(self, tool_name: str, category: str):
        self.tool_name = tool_name
        self.category = category
        super().__init__("tool is unavailable")


def raise_for_tool_status(response, tool_name: str) -> None:
    if response.status_code in {401, 403}:
        raise ToolUnavailableError(tool_name, "credential")
    if 500 <= response.status_code <= 599:
        raise ToolUnavailableError(tool_name, "provider")
    response.raise_for_status()
```

Catch `requests.Timeout` before `requests.ConnectionError` in each external
tool, convert them to `timeout` and `connectivity`, and use
`raise_for_tool_status`. Add defense-in-depth configuration handling to
`web_search` and declare:

```python
@register_tool(
    name="web_search",
    description="Search the web for up-to-date information. Input: search query string.",
    required_env_vars=("TAVILY_API_KEY",),
)
```

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/unit/test_external_tools.py -q`

Expected: all external-tool tests pass.

- [ ] **Step 5: Commit**

```bash
git add jarvis/tools/errors.py jarvis/tools/search.py jarvis/tools/scraper.py tests/unit/test_external_tools.py
git commit -m "FIX normalize external tool outages"
```

### Task 4: Per-request safe tool execution

**Files:**
- Create: `jarvis/agent/nodes/tool_execute.py`
- Modify: `jarvis/agent/state.py`
- Modify: `jarvis/agent/nodes/plan_and_call.py`
- Modify: `jarvis/agent/graph.py`
- Modify: `jarvis/api/http/routes.py`
- Modify: `jarvis/api/grpc/servicer.py`
- Create: `tests/unit/test_tool_execute.py`
- Modify: `tests/integration/test_graph_flow.py`

- [ ] **Step 1: Write failing node tests**

```python
def test_tool_outage_returns_message_and_disables_tool(monkeypatch, caplog):
    @register_tool(name="search", description="Search")
    def search(query: str) -> str:
        raise ToolUnavailableError("search", "timeout")

    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "search", "args": {"query": "x"}, "id": "call-1"}
                ],
            )
        ],
        "unavailable_tools": [],
    }

    with caplog.at_level(logging.WARNING, logger="jarvis.agent.nodes.tool_execute"):
        result = execute_tools(state)

    assert result["unavailable_tools"] == ["search"]
    assert result["messages"][0].tool_call_id == "call-1"
    assert "Do not retry" in result["messages"][0].content
    assert "【工具:search】【状态:降级】【类别:timeout】" in caplog.text


def test_unexpected_tool_bug_propagates():
    @register_tool(name="broken", description="Broken")
    def broken(value: str) -> str:
        raise ValueError("programming bug")

    with pytest.raises(ValueError, match="programming bug"):
        execute_tools(tool_call_state("broken", {"value": "x"}))


def test_graph_falls_back_after_tool_credential_failure(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "configured")
    answer_tool_names = []

    def fake_chat(profile, messages, tools, override=None):
        if profile == "reflection":
            return AIMessage(content="0.9")
        answer_tool_names.append([tool.name for tool in tools])
        if len(answer_tool_names) == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "web_search",
                        "args": {"query": "current information"},
                        "id": "call-1",
                    }
                ],
            )
        return AIMessage(
            content="I cannot search right now, but here is what I know."
        )

    with patch(
        "jarvis.agent.nodes.plan_and_call.llm.chat",
        side_effect=fake_chat,
    ), patch.object(
        get_tool_registration("web_search").tool,
        "invoke",
        side_effect=ToolUnavailableError("web_search", "credential"),
    ):
        result = graph.invoke(initial_state())

    assert "web_search" in answer_tool_names[0]
    assert "web_search" not in answer_tool_names[1]
    assert result["final_answer"] == (
        "I cannot search right now, but here is what I know."
    )
```

- [ ] **Step 2: Verify RED**

Run:
`pytest tests/unit/test_tool_execute.py tests/integration/test_graph_flow.py::test_graph_falls_back_after_tool_credential_failure -q`

Expected: FAIL because the safe node does not exist and the original graph
propagates `ToolUnavailableError`.

- [ ] **Step 3: Implement safe node and request state**

Implement `execute_tools(state)` to resolve each tool call from the registry,
invoke it, catch only `ToolUnavailableError`, log stable tags without exception
text, emit a ToolMessage, and return a sorted union of unavailable tool names.
Unknown tools and all other exceptions propagate.

Add to `AgentState`:

```python
unavailable_tools: list[str]
```

Initialize it to `[]` in HTTP and gRPC Chat states. Change `plan_and_call` to:

```python
tools = get_tools(excluded_names=state.get("unavailable_tools", []))
response = llm.chat(
    profile="answer",
    messages=all_messages,
    tools=tools,
    override=state.get("llm_override"),
)
```

Replace `ToolNode(get_tools())` with `execute_tools` in `graph.py`.

- [ ] **Step 4: Verify GREEN**

Run:
`pytest tests/unit/test_tool_execute.py tests/integration/test_graph_flow.py::test_graph_falls_back_after_tool_credential_failure tests/unit/test_llm_callers.py tests/e2e/test_api.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add jarvis/agent/nodes/tool_execute.py jarvis/agent/state.py jarvis/agent/nodes/plan_and_call.py jarvis/agent/graph.py jarvis/api/http/routes.py jarvis/api/grpc/servicer.py tests/unit/test_tool_execute.py tests/integration/test_graph_flow.py
git commit -m "FIX degrade unavailable tools per chat request"
```

### Task 5: Documentation and complete verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document startup and fallback behavior**

Update the startup-check section to state that active model, Embedding, and
tool credential presence is logged without values; missing credentials produce
WARNING logs; missing optional tool credentials remove only the tool; and
supported runtime tool outages fall back to a direct answer.

- [ ] **Step 2: Run focused tests**

Run:

```bash
pytest tests/unit/test_tool_registry.py tests/unit/test_startup_checks.py tests/unit/test_external_tools.py tests/unit/test_tool_execute.py tests/integration/test_graph_flow.py tests/e2e/test_api.py -q
```

Expected: all focused tests pass.

- [ ] **Step 3: Run complete tests**

Run: `pytest -q`

Expected: all tests pass with zero failures.

- [ ] **Step 4: Run repository checks**

Run:

```bash
git diff --check
python -m compileall -q jarvis tests
```

Expected: both commands exit 0.

- [ ] **Step 5: Scan task commits for credentials**

Run a non-printing scan over the task-owned diff and commits for private-key
headers and live credential prefixes. The command must report only pass/fail,
never matching content.

Expected: no credential material detected.

- [ ] **Step 6: Commit documentation**

```bash
git add README.md
git commit -m "DOCS explain tool credential fallback"
```

### Task 6: Publish and deploy

**Files:**
- No tracked manifest change expected.

- [ ] **Step 1: Push task commits**

Push completed task commits to GitHub `master` without staging or committing
unrelated workspace changes.

- [ ] **Step 2: Monitor GitHub Actions**

Wait for the triggered image workflow to reach success or terminal failure. On
failure, report the failing job and step before any deployment mutation.

- [ ] **Step 3: Update the Kubernetes Secret securely**

Read `TAVILY_API_KEY` only from an ignored `*.secret.yaml`, a protected local
environment variable, or another secure credential mechanism. Do not place it
in a command argument or output. Update only `jarvis-secrets`.

- [ ] **Step 4: Restart only with explicit authorization**

The user has authorized adding the Secret, but Kubernetes rollout/restart is a
separate mutation under repository rules. Request authorization immediately
before restarting or deleting a Pod.

- [ ] **Step 5: Verify production**

After an authorized rollout, verify:

- the Deployment is ready;
- startup logs report `TAVILY_API_KEY` configured without its value;
- one search request succeeds;
- no credential or raw provider response appears in logs.
