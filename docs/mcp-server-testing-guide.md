# TalkOps MCP Server Testing Guide

> **Version**: 1.0.0 · **Last Updated**: 2025-05-22
> **Audience**: All TalkOps MCP server contributors
> **Applies to**: `prometheus-mcp-server`, `tempo-mcp-server`, `otel-mcp-server`, and all future MCP servers.

---

## Table of Contents

1. [Why This Guide Exists](#1-why-this-guide-exists)
2. [Testing Philosophy](#2-testing-philosophy)
3. [Test Architecture — The Three Layers](#3-test-architecture--the-three-layers)
4. [Directory Structure Standard](#4-directory-structure-standard)
5. [Layer 1: Unit Tests](#5-layer-1-unit-tests)
6. [Layer 2: MCP Integration Tests (In-Memory)](#6-layer-2-mcp-integration-tests-in-memory)
7. [Layer 3: E2E Workflow Tests](#7-layer-3-e2e-workflow-tests)
8. [Fixture Architecture](#8-fixture-architecture)
9. [FastMCP Client API — The Gotchas](#9-fastmcp-client-api--the-gotchas)
10. [What To Test Per MCP Primitive](#10-what-to-test-per-mcp-primitive)
11. [HTTP Mocking with respx](#11-http-mocking-with-respx)
12. [Common Patterns & Recipes](#12-common-patterns--recipes)
13. [Migration Guide: Flat → Structured](#13-migration-guide-flat--structured)
14. [CI/CD Integration](#14-cicd-integration)
15. [Checklist Before PR](#15-checklist-before-pr)

---

## 1. Why This Guide Exists

Our initial test suites were "flat" — a handful of `test_*.py` files in a single `tests/` directory, with inline mock data, no separation between unit and integration tests, and no use of the FastMCP in-memory client. This approach has three problems:

1. **No protocol-level validation**: Tests called Python functions directly, bypassing the entire MCP JSON-RPC layer (tool registration, parameter schema validation, serialization).
2. **Coupled fixtures**: Mock data was hardcoded in `conftest.py` as Python dicts, making it hard to share realistic API response shapes across tests.
3. **Not scalable**: When the number of tools/resources grows, a flat layout becomes unnavigable.

This guide standardizes how we test **all** TalkOps MCP servers.

---

## 2. Testing Philosophy

### The Test Pyramid for MCP Servers

```
         ┌──────────────────┐
         │  E2E Workflow     │  ← Few: multi-tool chains
         │  (FastMCP Client) │
         ├──────────────────┤
         │  MCP Integration  │  ← Medium: every tool & resource through MCP
         │  (FastMCP Client) │
         ├──────────────────┤
         │  Unit Tests       │  ← Many: pure logic, mocked deps
         │  (Direct Python)  │
         └──────────────────┘
```

### Core Principles

| Principle | What It Means |
|---|---|
| **No LLMs in tests** | Tests are deterministic. Never rely on an LLM to select or invoke tools. |
| **Mock at the HTTP layer** | Use `respx` to intercept `httpx` calls. Don't mock internal methods — that hides bugs. |
| **Test the protocol, not just Python** | Integration tests must go through `Client(mcp)` to validate JSON-RPC serialization, tool registration, and schema. |
| **Fixtures are JSON files** | External `.json` files that match the real API response shape. Not inline Python dicts. |
| **Dependency Injection** | Services are injected via `service_locator`. This makes mocking trivial. |

---

## 3. Test Architecture — The Three Layers

### Layer 1: Unit Tests (`tests/unit/`)

- **What**: Pure logic tests — parsing, validation, formatting, summarization.
- **How**: Direct Python function/class calls. External services are mocked via `unittest.mock`.
- **Speed**: <1s for 100+ tests.
- **No MCP involved**: These tests never import `FastMCP` or `Client`.

### Layer 2: MCP Integration Tests (`tests/integration/`)

- **What**: Every tool and resource called through the MCP protocol using FastMCP's in-memory `Client`.
- **How**: `async with Client(mcp_server) as client: client.call_tool(...)`. HTTP backends are stubbed with `respx`.
- **Speed**: 2-3s for 30+ tests.
- **This is the critical layer**: It catches schema-implementation drift, serialization bugs, and registration errors that unit tests miss.

### Layer 3: E2E Workflow Tests (`tests/integration/test_*_flow.py`)

- **What**: Multi-tool chains that simulate real user workflows (e.g., "metrics → search → summarize").
- **How**: Same `Client(mcp)` pattern, but calls multiple tools in sequence within a single test.
- **Speed**: 3-5s for 5-10 tests.
- **Purpose**: Validates that the tools compose correctly — the output of one tool can be used as input to the next.

---

## 4. Directory Structure Standard

Every TalkOps MCP server **MUST** use this directory structure:

```text
tests/
  __init__.py
  conftest.py                              # Root fixtures (shared across all tests)
  fixtures/
    <backend_name>/                        # e.g., tempo/, prometheus/, otel/
      <endpoint_response>.json             # One file per API endpoint shape
  unit/
    __init__.py
    test_<domain>.py                       # One file per logical domain
  integration/
    __init__.py
    test_inmemory_mcp_tools.py             # All tools via FastMCP Client
    test_inmemory_mcp_resources.py         # All resources via FastMCP Client
    test_<workflow_name>_flow.py           # E2E workflow tests
```

### Naming Conventions

| File | Purpose |
|---|---|
| `test_request_builders.py` | URL construction, header building, query param assembly |
| `test_guardrails.py` | Query validation, limit clamping, policy enforcement |
| `test_<data>_parsing.py` | Response normalization and data extraction |
| `test_<feature>_summarizer.py` | Summarization / aggregation logic |
| `test_diagnostics.py` | Health check, status combining |
| `test_resources.py` | Static resource content rendering |
| `test_inmemory_mcp_tools.py` | ALL tools through MCP Client |
| `test_inmemory_mcp_resources.py` | ALL resources through MCP Client |
| `test_<workflow>_flow.py` | Multi-tool E2E workflows |

---

## 5. Layer 1: Unit Tests

### What To Test

| Category | Examples |
|---|---|
| **Config parsing** | `Config.from_env()`, backend normalization, defaults |
| **Request building** | URL construction, header injection (tenant, auth, accept) |
| **Validation** | Query syntax, tenant format, time range parsing |
| **Data transformation** | Response parsing, attribute mapping, summarization |
| **Policy enforcement** | Limit clamping, required fields, guardrails |
| **Resource rendering** | Static markdown content, dynamic JSON content |

### Pattern

```python
# tests/unit/test_request_builders.py

import pytest
from your_mcp_server.services.your_service import YourService
from your_mcp_server.config import BackendConfig, ServerConfig

@pytest.fixture
def svc():
    config = ServerConfig(backends=[BackendConfig(id="test", base_url="http://test:9090")])
    return YourService(config)

class TestHeaderBuilding:
    def test_no_auth_header_by_default(self, svc):
        headers = svc._build_headers(svc._get_backend("test"))
        assert "Authorization" not in headers

    def test_auth_header_when_configured(self, svc):
        backend = BackendConfig(id="auth", base_url="http://x:9090", auth_header="Bearer token")
        headers = svc._build_headers(backend)
        assert headers["Authorization"] == "Bearer token"
```

### Key Rules

1. **Never call `ServerBootstrap.initialize()`** — that's for integration tests.
2. **Use `respx` for HTTP assertions** — when you need to verify what URL/headers/params were sent.
3. **One test class per logical concern** — `TestHeaderBuilding`, `TestTenantValidation`, etc.

---

## 6. Layer 2: MCP Integration Tests (In-Memory)

This is the most important layer. It validates that your tools and resources work **through the actual MCP protocol**.

### The Pattern

```python
# tests/integration/test_inmemory_mcp_tools.py

import os
import pytest
from unittest.mock import patch
import respx
import httpx

@pytest.fixture
def mock_endpoints():
    """Stub all backend HTTP endpoints."""
    with respx.mock(assert_all_called=False) as mock:
        base = "http://test-backend:9090"
        mock.get(f"{base}/api/v1/query").mock(
            return_value=httpx.Response(200, json={"status": "success", "data": {"result": []}})
        )
        yield mock

@pytest.fixture
def bootstrapped_mcp(mock_endpoints):
    """Bootstrapped FastMCP with all endpoints stubbed."""
    env = {"YOUR_BASE_URL": "http://test-backend:9090", "K8S_ENABLED": "false"}
    with patch.dict(os.environ, env, clear=False):
        from your_mcp_server.server.bootstrap import ServerBootstrap
        mcp, _ = ServerBootstrap.initialize()
        return mcp

class TestTools:
    @pytest.mark.asyncio
    async def test_my_tool(self, bootstrapped_mcp, mock_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.call_tool("my_tool_name", {"param": "value"})
            # ⚠️ IMPORTANT: call_tool returns CallToolResult, not a list!
            text = result.content[0].text if result.content else str(result)
            assert "expected_substring" in text
```

### What This Catches That Unit Tests Don't

| Issue | Unit Test | MCP Integration Test |
|---|---|---|
| Tool not registered with `@mcp.tool` | ❌ | ✅ Tool not found error |
| Parameter schema mismatch | ❌ | ✅ Validation error |
| Response serialization bug | ❌ | ✅ Serialization error |
| Tool name typo | ❌ | ✅ Tool not found |
| Resource URI not registered | ❌ | ✅ Resource not found |
| Return type doesn't match MCP content model | ❌ | ✅ Content type error |

---

## 7. Layer 3: E2E Workflow Tests

### The Pattern

```python
# tests/integration/test_metrics_triage_flow.py

class TestMetricsTriageFlow:
    @pytest.mark.asyncio
    async def test_metrics_to_search_to_summarize(self, bootstrapped_mcp, mock_full):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            # Step 1: Query metrics
            metrics = await client.call_tool("metrics_range", {"query": "rate(...)", "since": "1h"})
            assert metrics.content

            # Step 2: Search for traces based on metrics insight
            search = await client.call_tool("trace_search", {"service": "api", "since": "1h"})
            assert search.content

            # Step 3: Summarize the trace
            summary = await client.call_tool("summarize_trace", {"trace_id": "abc123"})
            assert "headline" in summary.content[0].text
```

### When To Write Workflow Tests

- When the architect defines a "user journey" or "runbook"
- When 2+ tools are meant to be chained (output of one → input of next)
- NOT for every permutation — just the key workflows

---

## 8. Fixture Architecture

### Rules

1. **One JSON file per API endpoint response shape**
2. **Placed in `tests/fixtures/<backend>/`**
3. **Loaded via helper function, never hardcoded in `conftest.py`**
4. **Must match the real API response structure** (copy from actual Tempo/Prometheus responses)

### Fixture Loader

```python
# tests/conftest.py

import json
from pathlib import Path
from typing import Any, Dict

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "your_backend"

def _load_fixture(name: str) -> Dict[str, Any]:
    """Load a JSON fixture file."""
    with open(FIXTURES_DIR / name, encoding="utf-8") as f:
        return json.load(f)
```

### Example Fixture Files

```text
tests/fixtures/prometheus/
  instant_query_response.json      # /api/v1/query
  range_query_response.json        # /api/v1/query_range
  labels_response.json             # /api/v1/labels
  targets_response.json            # /api/v1/targets
  metadata_response.json           # /api/v1/metadata
  buildinfo_response.json          # /api/v1/status/buildinfo
```

### Why JSON Files, Not Python Dicts?

| Inline Python Dict | External JSON File |
|---|---|
| Coupled to test file | Reusable across tests |
| Hard to validate shape | Can be validated against OpenAPI schema |
| Diverges from real API | Can be captured from real API responses |
| Clutters `conftest.py` | Clean `conftest.py` with just fixtures |

---

## 9. FastMCP Client API — The Gotchas

> ⚠️ **This is the #1 source of confusion when writing MCP tests.**

### `call_tool()` Return Type

```python
# FastMCP 2.10+ (2025)
result = await client.call_tool("tool_name", {"arg": "value"})

# result is a CallToolResult object, NOT a list!
# ❌ WRONG: result[0].text  → TypeError: 'CallToolResult' object is not subscriptable
# ✅ RIGHT: result.content[0].text
# ✅ RIGHT: result.data  (auto-hydrated Python object)
```

| Property | Type | Description |
|---|---|---|
| `result.content` | `list[TextContent \| ImageContent]` | Standard MCP content blocks |
| `result.content[0].text` | `str` | Text content of the first block |
| `result.data` | `Any` | FastMCP-exclusive: hydrated Python object |
| `result.is_error` | `bool` | Whether the tool execution failed |
| `result.structured_content` | `dict` | Raw JSON before hydration |

### `read_resource()` Return Type

```python
# FastMCP 2.10+ (2025)
result = await client.read_resource("your://resource/uri")

# result IS a list of ReadResourceContents!
# ✅ RIGHT: result[0].text
# ❌ WRONG: result.content[0].text  → AttributeError: 'list' has no attribute 'content'
```

| Return | Type | Access Pattern |
|---|---|---|
| `call_tool()` | `CallToolResult` | `result.content[0].text` |
| `read_resource()` | `list[ReadResourceContents]` | `result[0].text` |

### Safe Accessor Helper

To avoid this confusion, use a helper:

```python
def get_text(result) -> str:
    """Extract text from either call_tool or read_resource result."""
    if isinstance(result, list):
        # read_resource returns a list
        return result[0].text if result else ""
    # call_tool returns CallToolResult
    return result.content[0].text if result.content else str(result)
```

---

## 10. What To Test Per MCP Primitive

### Tools

| What | How | Priority |
|---|---|---|
| **Registration** | `client.call_tool("name", {})` doesn't throw "tool not found" | P0 |
| **Parameter schema** | Required params → error when missing | P0 |
| **Happy path** | Valid args → expected response shape | P0 |
| **Error responses** | Backend 5xx → structured error with `is_error=True` | P1 |
| **Edge cases** | Empty strings, boundary values, invalid IDs | P1 |
| **Timeouts** | Slow backend → timeout error (not hang) | P2 |

### Resources

| What | How | Priority |
|---|---|---|
| **URI registered** | `client.read_resource("uri")` doesn't throw | P0 |
| **Content is non-empty** | `len(result[0].text) > 0` | P0 |
| **Content contains key info** | `"expected_keyword" in text` | P0 |
| **Dynamic resources** | Content changes based on config | P1 |
| **MIME type** | Text resources return text, JSON returns valid JSON | P2 |

### Prompts

| What | How | Priority |
|---|---|---|
| **Registered** | `client.get_prompt("name")` doesn't throw | P0 |
| **Contains tool references** | Prompt text mentions correct tool names | P1 |
| **Argument substitution** | Dynamic prompts inject args correctly | P1 |

---

## 11. HTTP Mocking with respx

### Why respx?

- Intercepts `httpx.AsyncClient` at the transport layer (same library all our MCP servers use)
- No monkey-patching — works with `async with` patterns
- Supports URL regex matching for dynamic path segments
- `assert_all_called=False` prevents flaky tests from unused routes

### Pattern: Stub All Endpoints in `conftest.py`

```python
@pytest.fixture
def mock_backend_http():
    with respx.mock(assert_all_called=False) as mock:
        base = "http://test-backend:9090"

        # Static endpoints
        mock.get(f"{base}/ready").mock(return_value=httpx.Response(200, text="ready"))
        mock.get(f"{base}/api/v1/labels").mock(
            return_value=httpx.Response(200, json=_load_fixture("labels_response.json"))
        )

        # Dynamic path segments (regex)
        mock.get(url__regex=rf"{base}/api/v1/label/.+/values").mock(
            return_value=httpx.Response(200, json=_load_fixture("label_values.json"))
        )

        yield mock
```

### Pattern: Assert Request Details (Unit Tests)

```python
@respx.mock
@pytest.mark.asyncio
async def test_search_params(self, svc):
    route = respx.get("http://test:3200/api/search").mock(
        return_value=httpx.Response(200, json={"traces": []})
    )
    await svc.search(q="{ status = error }", limit=10)

    # Assert what was actually sent
    request = route.calls[0].request
    params = dict(request.url.params)
    assert params["q"] == "{ status = error }"
    assert params["limit"] == "10"
```

### Pattern: Test Error Responses

```python
@respx.mock
@pytest.mark.asyncio
async def test_backend_500_handled(self, svc):
    respx.get("http://test:3200/api/search").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )
    with pytest.raises(YourBackendError, match="500"):
        await svc.search(q="{ }")
```

---

## 12. Common Patterns & Recipes

### Pattern: Mocking Kubernetes Imports

The `kubernetes` Python package uses lazy local imports. You can't use `patch("module.attribute")` — you need to mock `sys.modules`:

```python
import sys
from unittest.mock import MagicMock

def test_k8s_discovery():
    mock_k8s_client = MagicMock()
    mock_k8s_client.CustomObjectsApi.return_value = your_mock_api

    mock_k8s_package = MagicMock()
    mock_k8s_package.client = mock_k8s_client

    # Remove any cached imports
    saved = {k: sys.modules.pop(k) for k in list(sys.modules) if k.startswith("kubernetes")}
    sys.modules["kubernetes"] = mock_k8s_package
    sys.modules["kubernetes.client"] = mock_k8s_client

    try:
        result = your_discovery_function()
        assert len(result) >= 1
    finally:
        # Restore
        for k in list(sys.modules) if k.startswith("kubernetes"):
            del sys.modules[k]
        sys.modules.update(saved)
```

### Pattern: Testing Multi-Tenant Headers

```python
class TestTenantInjection:
    def test_default_tenant(self, svc):
        backend = svc._get_backend("multi-tenant-backend")
        headers = svc._build_headers(backend)
        assert headers["X-Scope-OrgID"] == "default-tenant"

    def test_explicit_tenant(self, svc):
        backend = svc._get_backend("multi-tenant-backend")
        headers = svc._build_headers(backend, tenant="team-b")
        assert headers["X-Scope-OrgID"] == "team-b"

    def test_missing_tenant_raises(self, svc):
        backend = BackendConfig(multi_tenant=True)  # no default_tenant
        with pytest.raises(TenantError):
            svc._build_headers(backend)
```

### Pattern: Testing Resource Content

```python
class TestResources:
    def setup_method(self):
        # Register resources into a mock MCP to capture the handler functions
        resource_class = YourResourceClass(service_locator)
        mcp = MagicMock()
        self.registered = {}
        def capture(uri, **kwargs):
            def decorator(fn):
                self.registered[uri] = fn
                return fn
            return decorator
        mcp.resource = capture
        resource_class.register(mcp)

    @pytest.mark.asyncio
    async def test_reference_content(self):
        content = await self.registered["your://reference/doc"]()
        assert "Expected Keyword" in content
        assert len(content) > 100  # Not empty
```

---

## 13. Migration Guide: Flat → Structured

### Step-by-Step

```
Step 1: Create directory structure
  mkdir -p tests/{unit,integration,fixtures/<backend>}
  touch tests/unit/__init__.py tests/integration/__init__.py

Step 2: Extract fixture data → JSON files
  Take all MOCK_*_RESPONSE dicts from conftest.py
  Save each as tests/fixtures/<backend>/<endpoint>.json

Step 3: Rewrite conftest.py
  Add _load_fixture() helper
  Create composable fixtures (service, config, mock_http, mcp_server, mcp_client)
  Remove all inline MOCK_* dicts

Step 4: Split tests by domain
  test_services.py → unit/test_request_builders.py + unit/test_<feature>.py
  test_config.py   → unit/test_backend_discovery.py
  test_models.py   → unit/test_guardrails.py or test_<data>_parsing.py
  test_utils.py    → unit/test_<specific_util>.py

Step 5: Create integration tests
  test_inmemory_mcp_tools.py     → one test per tool via Client(mcp)
  test_inmemory_mcp_resources.py → one test per resource via Client(mcp)
  test_<workflow>_flow.py        → one per key user workflow

Step 6: Delete old flat files
  rm tests/test_config.py tests/test_models.py tests/test_services.py ...

Step 7: Verify
  uv run pytest tests/unit/ -v
  uv run pytest tests/integration/ -v
  uv run pytest tests/ -v --tb=short
```

### Before (Flat — Don't Do This)

```text
tests/
  conftest.py          # 170 lines of inline dicts
  test_config.py       # 20 tests
  test_models.py       # 15 tests
  test_services.py     # 30 tests
  test_utils.py        # 13 tests
```

### After (Structured — Do This)

```text
tests/
  conftest.py                          # 100 lines — composable fixtures
  fixtures/prometheus/                 # 8 JSON files
  unit/                                # 100+ tests
    test_backend_discovery.py
    test_request_builders.py
    test_guardrails.py
    test_<domain>.py
    test_resources.py
  integration/                         # 28+ tests
    test_inmemory_mcp_tools.py
    test_inmemory_mcp_resources.py
    test_<workflow>_flow.py
```

---

## 14. CI/CD Integration

### `pyproject.toml` Configuration

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### Pipeline Commands

```bash
# Fast gate (unit only — run on every push)
uv run pytest tests/unit/ -v --tb=short

# Full gate (unit + integration — run on PR)
uv run pytest tests/ -v --tb=short

# With coverage
uv run pytest tests/ --cov=your_mcp_server --cov-report=term-missing
```

### Coverage Targets

| Category | Target |
|---|---|
| Request builders, guardrails, parsing | 90%+ |
| Summarization, diagnostics | 80%+ |
| Tool/resource schema validation | 100% (via integration tests) |

---

## 15. Checklist Before PR

Use this checklist when submitting test changes:

- [ ] **Directory structure** matches §4
- [ ] **No inline mock dicts** in `conftest.py` — all JSON files in `fixtures/`
- [ ] **Every tool** has at least one integration test via `Client(mcp)`
- [ ] **Every resource** has at least one integration test via `Client(mcp)`
- [ ] **`call_tool` accessor** uses `result.content[0].text` (NOT `result[0].text`)
- [ ] **`read_resource` accessor** uses `result[0].text` (NOT `result.content[0].text`)
- [ ] **Error scenarios** tested (backend 5xx, missing params, invalid input)
- [ ] **No network calls** in tests — all HTTP is mocked via `respx`
- [ ] **All tests pass**: `uv run pytest tests/ -v --tb=short`
- [ ] **Test names** are descriptive: `test_<what>_<condition>_<expected>` pattern

---

## Appendix A: Quick Reference Card

```
╔══════════════════════════════════════════════════════════════════╗
║  FASTMCP CLIENT API — QUICK REFERENCE (v2.10+, 2025)           ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  TOOL CALL:                                                      ║
║    result = await client.call_tool("name", {"arg": "val"})       ║
║    text   = result.content[0].text    # ← CallToolResult         ║
║    data   = result.data               # ← auto-hydrated object   ║
║    error  = result.is_error           # ← bool                   ║
║                                                                  ║
║  RESOURCE READ:                                                  ║
║    result = await client.read_resource("scheme://path")           ║
║    text   = result[0].text            # ← list[Contents]         ║
║                                                                  ║
║  BOOTSTRAP:                                                      ║
║    mcp, config = ServerBootstrap.initialize()                    ║
║    async with Client(mcp) as client:                             ║
║        ...                                                       ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

## Appendix B: Recommended Dependencies

```toml
[project.optional-dependencies]
dev = [
    "pytest>=9.0",
    "pytest-asyncio>=1.0",
    "respx>=0.22",
    "httpx>=0.27",
]
```

---

## Appendix C: Real Example — Tempo MCP Server Test Stats

After migrating from flat to structured:

| Metric | Before | After |
|---|---|---|
| Total tests | 78 | 130 |
| Test files | 5 (flat) | 16 (structured) |
| JSON fixtures | 0 | 8 |
| MCP integration tests | 0 | 28 |
| Workflow E2E tests | 0 | 5 |
| Run time | ~3s | ~2.5s |
| Protocol-level bugs caught | 0 | 3 (accessor, schema, registration) |

The migration took 1 session and caught 3 real issues that the flat tests missed (wrong `call_tool` return type, a tool not being registered, and a resource URI typo).
