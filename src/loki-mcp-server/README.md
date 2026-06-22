<p align="center">
  <img src="https://grafana.com/media/docs/loki/logo-grafana-loki.png" alt="Loki MCP Server" width="200" onError="this.style.display='none'"/>
</p>

<h1 align="center">Loki MCP Server</h1>

<p align="center">
  An MCP server that gives AI assistants the power to explore, query, and analyze logs from Grafana Loki — with LogQL query construction, log structure discovery, cardinality-aware schema exploration, and production-safe query guardrails.
</p>

<p align="center">
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://grafana.com/oss/loki/"><img src="https://img.shields.io/badge/Grafana%20Loki-Compatible-F46800.svg?style=flat-square&logo=grafana&logoColor=white" alt="Grafana Loki"/></a>
  <a href="https://discord.gg/tSN2Qn9uM8"><img src="https://img.shields.io/badge/Discord-Join%20Us-5865F2.svg?style=flat-square&logo=discord&logoColor=white" alt="Discord"/></a>
</p>

<p align="center">
  <a href="#getting-started">Quick Start</a> · <a href="https://github.com/talkops-ai/talkops-mcp">Docs</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=bug_report.md">Report Bug</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=feature_request.md">Request Feature</a>
</p>

---

## Why Loki MCP Server?

**The problem:** Grafana Loki is the industry-standard log aggregation system, but effective log analysis is complex. Writing LogQL queries requires knowledge of stream selectors, line filters, parser stages, and metric functions. Understanding the label taxonomy, avoiding high-cardinality pitfalls, and building efficient parser pipelines each require specialized knowledge. When AI assistants try to help, they hallucinate label names, guess at field structures, construct unbounded queries that overwhelm backends, or miss the discovery-first workflow that experienced SREs follow.

**The solution:** The Loki MCP Server gives AI assistants (like Claude, Cline, or Cursor) structured, safe tools to interact with Grafana Loki natively:

1. **Schema Discovery:** Say *"What labels exist in my Loki cluster?"* and the AI discovers all label names, their values, and active series counts — so it never hallucates labels that don't exist.
2. **Log Structure Analysis:** Say *"What fields can I query in checkout-service logs?"* and the AI discovers JSON/logfmt keys, their types, estimated cardinality, and the parser needed to extract them — all before writing a single LogQL pipeline.
3. **Production-Safe Execution:** The AI pre-checks query cost (streams, chunks, bytes) against configurable guardrails, validates time windows, detects high-cardinality labels in selectors, and clamps result limits — protecting both the AI's context window and the Loki backend.
4. **Unified Query Execution:** Both log range queries and metric queries (`rate()`, `count_over_time()`, `avg_over_time()`) are handled by a single tool with automatic result formatting.
5. **Guided Workflows:** Five built-in prompt workflows guide the AI through multi-step journeys — error investigation, health checks, log structure analysis, LogQL query building, and schema exploration.

---

## Key Features

**Label & Schema Discovery**
- Global label taxonomy discovery (`get_cluster_labels`)
- Label value enumeration with optional scope queries (`get_label_values`)
- Active series validation with per-label cardinality and high-cardinality warnings (`get_active_series`)

**Log Structure Analysis**
- Structural pattern detection via Loki's pattern ingester (`get_log_patterns`)
- Detected field discovery — JSON/logfmt keys, types, cardinality, and parser hints (`get_detected_fields`)
- Auto-suggested parser pipelines (`| pattern "<pattern>"`)

**Production-Safe Query Execution**
- Preflight cost estimation: streams, chunks, entries, bytes with human-readable output (`get_query_stats`)
- Configurable guardrails: max query bytes (5 GB default), max time window (14 days), max log limit (5000), high-cardinality threshold (10,000)
- Automatic cost-based query rejection when byte threshold is exceeded
- High-cardinality label detection in stream selectors with inline warnings

**Unified LogQL Execution**
- Instant queries for point-in-time scalar answers (`execute_logql_instant`)
- Range queries for log streams and metric time-series (`execute_logql_query`)
- Interactive dynamic UI rendering for A2UI log tables (`loki_query_a2ui`)
- Support for `rate()`, `count_over_time()`, `avg_over_time()`, `sum_over_time()`, `quantile_over_time()`, `histogram_over_time()`
- Configurable step size for metric queries

**Multi-Tenancy**
- Bearer token and Basic Auth support
- `X-Scope-OrgID` header injection for multi-tenant Loki deployments
- Configurable via environment variables

**Production-Ready Infrastructure**
- Structured JSON logging with configurable log levels
- Frozen dataclass configuration (immutable at runtime)
- Middleware stack: error handling, response limiting, rate limiting, structured logging, timing

---

## Architecture

```
                    ┌─────────────────────────┐
                    │     MCP Client          │
                    │ (Claude, Cline, Cursor) │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │   FastMCP Server Core   │
                    │  (HTTP / SSE / stdio)   │
                    │  + Middleware Stack      │
                    └──────────┬──────────────┘
                               │
       ┌────────────┬──────────┼──────────┬────────────┐
       │            │          │          │            │
  ┌────▼────┐ ┌────▼────┐ ┌───▼───┐ ┌────▼────┐ ┌────▼────┐
  │  Tools  │ │Resources│ │Prompts│ │  Utils  │ │ Models  │
  │   (8)   │ │   (8)   │ │  (5)  │ │         │ │         │
  └────┬────┘ └────┬────┘ └───────┘ └─────────┘ └─────────┘
       │            │
       └──────┬─────┘
              │
   ┌──────────▼──────────┐
   │    Service Layer     │
   │                      │
   │    loki_service      │
   └──────────┬──────────┘
              │
   ┌──────────▼──────────┐
   │   Loki HTTP API     │
   │   /loki/api/v1/*    │
   └─────────────────────┘
```

**How it works:**

1. An AI assistant connects via HTTP, SSE, or stdio.
2. The AI loads `loki://system/health` to verify Loki is reachable.
3. Tools follow a **discovery-first workflow**: labels → values → series → fields → stats → execute.
4. The service layer (`loki_service`) handles HTTP calls with connection pooling, auth injection, and response validation.
5. Middleware enforces rate limiting, response size caps, and structured logging.

---

## Table of Contents

- [Why Loki MCP Server?](#why-loki-mcp-server)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Available Tools](#available-tools)
- [Available Resources](#available-resources)
- [Available Prompts](#available-prompts)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [FAQ](#faq)
- [Troubleshooting](#troubleshooting)
- [Security Considerations](#security-considerations)
- [License](#license)
- [Contact](#contact)
- [Acknowledgments](#acknowledgments)

---

## Tech Stack

| Category | Technologies |
|----------|-------------|
| **Language** | Python 3.12+ |
| **MCP Framework** | [FastMCP](https://github.com/jlowin/fastmcp) ≥2.13.3 |
| **Protocol** | [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) |
| **Log Backend** | [Grafana Loki](https://grafana.com/oss/loki/) HTTP API |
| **HTTP Client** | [httpx](https://www.python-httpx.org/) — async, connection pooling |
| **Transport** | HTTP · SSE · Streamable-HTTP · stdio |
| **Infrastructure** | Docker · [uv](https://github.com/astral-sh/uv) |

---

## Getting Started

### Prerequisites

- **Docker** (recommended) or **Python 3.12+** (for local dev)
- **Grafana Loki** backend accessible via HTTP (default port: `3100`)

### Quick Start with Docker (recommended)

```bash
docker run --rm -it \
  -p 8770:8770 \
  -e MCP_TRANSPORT=http \
  -e LOKI_URL=http://host.docker.internal:3100 \
  talkopsai/loki-mcp-server:latest
```

The server is now listening on `http://localhost:8770/mcp`.

Point your MCP client at it:

```json
{
  "mcpServers": {
    "loki": {
      "url": "http://localhost:8770/mcp",
      "description": "MCP Server for Grafana Loki log observability"
    }
  }
}
```

### From Source (Python)

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) for dependency management.

2. Clone and set up:

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/loki-mcp-server
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

3. Configure your `.env`:

```bash
LOKI_URL=http://localhost:3100
MCP_TRANSPORT=http
MCP_LOG_LEVEL=INFO
```

4. Run the server:

```bash
uv run loki-mcp-server
```

Or, with the venv activated: `loki-mcp-server`.

5. Run tests:

```bash
source .venv/bin/activate
pytest tests/
```

---

## Configuration

All configuration is via environment variables (loaded from `.env` via python-dotenv).

### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_NAME` | `loki-mcp-server` | Server name identifier |
| `MCP_SERVER_VERSION` | `0.1.0` | Server version string |
| `MCP_TRANSPORT` | `stdio` | Transport mode: `http`, `sse`, `streamable-http`, or `stdio` |
| `MCP_HOST` | `0.0.0.0` | Host address for HTTP server |
| `MCP_PORT` | `8770` | Port for HTTP server |
| `MCP_PATH` | `/mcp` | MCP endpoint path |
| `MCP_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `MCP_LOG_FORMAT` | `json` | Log format: `json` or `text` |
| `MCP_HTTP_TIMEOUT` | `300` | HTTP server timeout (seconds) |
| `MCP_HTTP_KEEPALIVE_TIMEOUT` | `5` | HTTP keepalive timeout (seconds) |
| `MCP_HTTP_CONNECT_TIMEOUT` | `60` | HTTP connect timeout (seconds) |

### Loki Backend

| Variable | Default | Description |
|----------|---------|-------------|
| `LOKI_URL` | `http://loki:3100` | Loki HTTP API base URL |
| `LOKI_TIMEOUT` | `30` | HTTP timeout per request (seconds) |
| `LOKI_VERIFY_SSL` | `true` | Verify SSL certificates |

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `LOKI_AUTH_TOKEN` | *(empty)* | Bearer token for Loki authentication |
| `LOKI_BASIC_AUTH_USER` | *(empty)* | Basic auth username |
| `LOKI_BASIC_AUTH_PASSWORD` | *(empty)* | Basic auth password |
| `LOKI_ORG_ID` | *(empty)* | Multi-tenant org ID (`X-Scope-OrgID` header) |

### Query Guardrails

| Variable | Default | Description |
|----------|---------|-------------|
| `LOKI_MAX_QUERY_BYTES` | `5000000000` (5 GB) | Maximum bytes a query may scan before rejection |
| `LOKI_MAX_TIME_WINDOW_HOURS` | `336` (14 days) | Maximum query time range in hours |
| `LOKI_MAX_LOG_LIMIT` | `5000` | Maximum log lines per query |
| `LOKI_HIGH_CARDINALITY_THRESHOLD` | `10000` | Warn when a label exceeds this many unique values |

---

## Available Tools

### Discovery
| Tool | Description |
|------|-------------|
| `get_cluster_labels` | Discover global label taxonomy in Loki. **Always call first** before writing any LogQL queries. Returns all label names so the AI never halluccinates labels that don't exist. |
| `get_label_values` | Discover concrete values for a label. Use after `get_cluster_labels` to learn valid label values (namespaces, apps, clusters) before writing LogQL queries. Supports optional scope queries. |
| `get_active_series` | Validate that selectors correspond to active streams. Returns per-label cardinality to identify high-cardinality labels that should NOT be placed in `{}` stream selectors. |

### Structure
| Tool | Description |
|------|-------------|
| `get_log_patterns` | Understand structural patterns of logs without raw text. Returns recurring log shapes and auto-suggested parser pipelines. Requires Loki's pattern ingester. |
| `get_detected_fields` | Discover structured keys available in logs. Returns JSON/logfmt field names, their inferred types, estimated cardinality, and the parser needed to extract them. Requires Loki 3.0+. |

### Safety
| Tool | Description |
|------|-------------|
| `get_query_stats` | Preflight a selector to estimate query cost. Returns streams, chunks, entries, and bytes a query would touch. **Always check before heavy queries.** |

### Execution
| Tool | Description |
|------|-------------|
| `execute_logql_instant` | Execute a point-in-time LogQL query for scalar answers. Best for `count`, `rate`, `avg` aggregations that answer "what is the current value?". |
| `execute_logql_query` | **Primary query tool.** Execute a LogQL range query for log lines or metric time-series. Handles both log queries (returns streams) and metric queries with `rate()`, `count_over_time()`, etc. (returns matrix). Includes guardrails: time window validation, cardinality checks, and cost-based rejection. |
| `loki_query_a2ui` | **Dynamic UI tool.** Execute a LogQL range query and return data formatted for A2UI interactive log tables in the frontend. Automatically parses logs into a deterministic layout schema. |

---

## Available Resources

### Dynamic Resources

| Resource URI | Description |
|--------------|-------------|
| `loki://system/health` | Loki reachability, readiness status, and label count |
| `loki://schema/labels` | All available label names in Loki |

### Configuration Resources

| Resource URI | Description |
|--------------|-------------|
| `loki://config/guardrails` | Current safety thresholds: max query bytes, time windows, log limits, cardinality threshold |
| `loki://config/backends` | Configured Loki backend connection details: URL, timeout, SSL, auth type, org ID |

### Reference Resources (Static)

| Resource URI | Description |
|--------------|-------------|
| `loki://reference/logql` | LogQL syntax guide: stream selectors, line filters, parsers, metric queries, examples |
| `loki://reference/best-practices` | Cardinality rules, pattern parser vs regex, structured metadata, pipeline order |
| `loki://reference/query-templates` | Common incident, debug, audit, and performance LogQL query patterns |
| `loki://reference/label-governance` | Label naming conventions, cardinality rules, structured metadata guidance |

---

## Available Prompts

Guided workflow prompts that orchestrate multiple tools into step-by-step journeys:

| Prompt Name | Description | Parameters |
|-------------|-------------|------------|
| `investigate_errors` | Step-by-step error investigation: discover labels → find service → validate selector → detect fields → check cost → fetch error logs → quantify error rate | `service_name`, `time_range` |
| `check_health` | Quick health check: verify Loki reachability → check label taxonomy → validate service streams → check volume → fetch latest logs | `service_name` |
| `analyze_log_structure` | Log structure discovery: validate service → discover structured fields → discover patterns → sample raw logs → recommend parsers | `service_name` |
| `build_logql_query` | Guided query builder: understand environment → explore labels → validate selector → discover fields → read references → preflight → execute | `intent` |
| `explore_schema` | Full schema exploration: global labels → drill into key labels → cardinality analysis → log structure → governance review | *(none)* |

---

## Usage

Supported workflows with prompt examples and links to detailed guides:

| Workflow | Prompt Example | Documentation |
|----------|----------------|---------------|
| **Error Investigation** | `"Investigate errors for the 'checkout-service' over the last hour."` | [LOKI_ERROR_INVESTIGATION_TEST_GUIDE.md](docs/LOKI_ERROR_INVESTIGATION_TEST_GUIDE.md) |
| **Service Health Check** | `"Run a health check for the 'payment-service'."` | [LOKI_HEALTH_CHECK_TEST_GUIDE.md](docs/LOKI_HEALTH_CHECK_TEST_GUIDE.md) |
| **Log Structure Analysis** | `"Analyze the log structure for 'api-gateway'."` | [LOKI_LOG_STRUCTURE_TEST_GUIDE.md](docs/LOKI_LOG_STRUCTURE_TEST_GUIDE.md) |
| **LogQL Query Builder** | `"Build a LogQL query to find slow HTTP requests with status 500."` | [LOKI_LOGQL_BUILDER_TEST_GUIDE.md](docs/LOKI_LOGQL_BUILDER_TEST_GUIDE.md) |
| **Schema Exploration** | `"Explore the full label schema of this Loki cluster."` | [LOKI_SCHEMA_EXPLORATION_TEST_GUIDE.md](docs/LOKI_SCHEMA_EXPLORATION_TEST_GUIDE.md) |
| **Incident Response** | `"There's an outage in production — show me error logs across all services in the last 15 minutes."` | [LOKI_INCIDENT_RESPONSE_TEST_GUIDE.md](docs/LOKI_INCIDENT_RESPONSE_TEST_GUIDE.md) |
| **Performance Analysis** | `"What's the current request rate and error rate for 'order-service'?"` | [LOKI_PERFORMANCE_ANALYSIS_TEST_GUIDE.md](docs/LOKI_PERFORMANCE_ANALYSIS_TEST_GUIDE.md) |

---

## Project Structure

```text
loki-mcp-server/
├── loki_mcp_server/               # Main package
│   ├── tools/                     # MCP Tools (4 groups, 8 tools)
│   │   ├── discovery/             # Label & series discovery
│   │   │   └── discovery_tools.py # 3 tools: get_cluster_labels, get_label_values, get_active_series
│   │   ├── structure/             # Log structure analysis
│   │   │   └── structure_tools.py # 2 tools: get_log_patterns, get_detected_fields
│   │   ├── safety/                # Query cost estimation
│   │   │   └── safety_tools.py    # 1 tool: get_query_stats
│   │   ├── execution/             # LogQL query execution
│   │   │   └── execution_tools.py # 3 tools: execute_logql_instant, execute_logql_query, loki_query_a2ui
│   │   ├── base.py                # Base tool class with service_locator DI
│   │   ├── registry.py            # Tool registry for lifecycle management
│   │   └── __init__.py            # initialize_tools factory
│   ├── resources/                 # MCP Resources (8 URIs)
│   │   ├── loki_resources.py      # System, config, and reference resources
│   │   └── base.py                # Base resource class
│   ├── prompts/                   # MCP Prompts (5 guided workflows)
│   │   ├── loki_prompts.py        # All prompt definitions
│   │   └── base.py                # Base prompt class
│   ├── services/                  # Business logic
│   │   └── loki_service.py        # Async HTTP client: all Loki API calls, auth injection,
│   │                              # connection pooling, response validation
│   ├── server/                    # FastMCP server setup
│   │   ├── core.py                # Server creation & instructions loading
│   │   ├── bootstrap.py           # Component initialization & DI (service_locator pattern)
│   │   └── middleware.py          # Middleware stack (error handling, logging, timing)
│   ├── models/                    # Pydantic data models
│   │   ├── common.py              # Shared model utilities
│   │   ├── schema.py              # Label schema models
│   │   ├── query.py               # Query response models
│   │   ├── patterns.py            # Pattern models
│   │   ├── stats.py               # Index stats models
│   │   └── detected_fields.py     # Detected fields models
│   ├── utils/                     # Helpers
│   │   ├── logql_helpers.py       # Stream selector validation, high-cardinality detection,
│   │   │                          # log entry formatting, parser suggestion
│   │   ├── time_utils.py          # Relative time parsing (now-1h → epoch), time window validation
│   │   └── pagination.py          # Cursor-based pagination utilities
│   ├── exceptions/                # Custom exception hierarchy
│   │   └── __init__.py            # LokiConnectionError, LokiQueryError, LokiQueryTooExpensiveError, etc.
│   ├── static/                    # Static reference files
│   │   ├── LOKI_MCP_INSTRUCTIONS.md  # MCP system instructions for AI agents
│   │   ├── logql_reference.md     # LogQL syntax guide
│   │   ├── best_practices.md      # Loki best practices
│   │   ├── query_templates.md     # Common LogQL query patterns
│   │   └── label_governance.md    # Label naming and cardinality governance
│   ├── config.py                  # Environment parsing & config dataclasses
│   └── main.py                    # Entry point & CLI
├── tests/                         # Test suites
│   ├── unit/                      # Unit tests (deterministic, mocked)
│   ├── integration/               # In-memory MCP integration tests
│   ├── fixtures/                  # Test fixtures (JSON responses)
│   └── conftest.py                # Shared test configuration
├── docs/                          # Documentation & test guides
├── pyproject.toml                 # Package definition (Python 3.12)
├── Dockerfile                     # Docker build
└── README.md                      # This documentation
```

---

## Roadmap

**Shipped in this release:**

- [x] Label taxonomy discovery with time-window scoping
- [x] Label value enumeration with scope queries
- [x] Active series validation with per-label cardinality and high-cardinality warnings
- [x] Log pattern detection via Loki pattern ingester
- [x] Detected field discovery (JSON/logfmt keys, types, cardinality, parsers)
- [x] Preflight query cost estimation with configurable byte thresholds
- [x] Unified LogQL execution for log streams and metric time-series
- [x] Instant query execution for point-in-time scalar answers
- [x] 5 guided workflow prompts (error investigation, health check, log structure, LogQL builder, schema exploration)
- [x] 8 MCP resources (dynamic health/schema, config guardrails/backends, static references)
- [x] Multi-tenancy with Bearer token, Basic Auth, and X-Scope-OrgID
- [x] Middleware stack (error handling, response limiting, rate limiting, logging, timing)
- [x] Configurable guardrails (max bytes, max time window, max log limit, cardinality threshold)
- [x] High-cardinality label detection in stream selectors

**Coming next:**

- [ ] Log-to-trace correlation (extract trace IDs from log lines → pivot to Tempo MCP server)
- [ ] Multi-backend support (staging, production, multi-cluster)
- [ ] Loki ruler integration (alerting rule management)
- [ ] Log volume analysis (per-label byte usage trends)

See [open issues](https://github.com/talkops-ai/talkops-mcp/issues) for the full list of proposed features.

---

## Contributing

Contributions are welcome. The process is straightforward:

1. Fork the repo
2. Create a branch (`git checkout -b feature/LogStructureAnalysis`)
3. Make your changes and commit
4. Push and open a PR

If you're considering something bigger, open an issue first so we can align on the approach.

---

## FAQ

<details>
<summary><b>Which MCP clients work with this?</b></summary>
Any MCP-compatible client including Claude Desktop, Cline, Cursor, and custom clients. Connect via <code>http://localhost:8770/mcp</code> for HTTP transport, or configure stdio for direct process communication.
</details>

<details>
<summary><b>Does this require Grafana Loki?</b></summary>
Yes. The server communicates with Loki's HTTP API (<code>/loki/api/v1/labels</code>, <code>/loki/api/v1/query_range</code>, <code>/loki/api/v1/index/stats</code>, <code>/loki/api/v1/detected_fields</code>, etc.). Any Grafana Loki deployment (single-binary, simple-scalable, or microservices mode) will work. The detected fields endpoint requires Loki 3.0+. The pattern ingester requires Loki's <code>pattern_ingester.enabled: true</code>.
</details>

<details>
<summary><b>Does this modify my Loki backend?</b></summary>
No. All 8 tools are <b>read-only</b>. The server only performs HTTP GET requests against Loki's query APIs. No logs, labels, or configurations are created, modified, or deleted.
</details>

<details>
<summary><b>How does multi-tenancy work?</b></summary>
For multi-tenant Loki deployments, set <code>LOKI_ORG_ID</code> to your tenant ID. The server injects the <code>X-Scope-OrgID</code> header on every request. For Bearer token auth, set <code>LOKI_AUTH_TOKEN</code>. For Basic Auth, set <code>LOKI_BASIC_AUTH_USER</code> and <code>LOKI_BASIC_AUTH_PASSWORD</code>.
</details>

<details>
<summary><b>What are query guardrails?</b></summary>
The server enforces configurable safety limits to prevent unbounded queries: maximum query bytes (<code>LOKI_MAX_QUERY_BYTES=5000000000</code>), maximum time window (<code>LOKI_MAX_TIME_WINDOW_HOURS=336</code>), maximum log lines (<code>LOKI_MAX_LOG_LIMIT=5000</code>), and high-cardinality threshold (<code>LOKI_HIGH_CARDINALITY_THRESHOLD=10000</code>). These protect both the AI agent's context window and the Loki backend.
</details>

<details>
<summary><b>What is the discovery-first workflow?</b></summary>
The recommended tool call order: <code>get_cluster_labels</code> → <code>get_label_values</code> → <code>get_active_series</code> → <code>get_detected_fields</code> → <code>get_query_stats</code> → <code>execute_logql_query</code>. This ensures the AI discovers the actual label taxonomy and log structure before constructing queries, preventing hallucinated labels, wrong parsers, and unbounded queries.
</details>

<details>
<summary><b>What Loki features are required?</b></summary>
Core tools (<code>get_cluster_labels</code>, <code>get_label_values</code>, <code>execute_logql_query</code>) work with any Loki version. <code>get_detected_fields</code> requires Loki 3.0+ (the <code>/loki/api/v1/detected_fields</code> endpoint). <code>get_log_patterns</code> requires Loki's pattern ingester to be enabled (<code>pattern_ingester.enabled: true</code>).
</details>

---

## Troubleshooting

### Loki Connection Issues

1. Verify `LOKI_URL` points to an accessible Loki HTTP endpoint (default port: `3100`).
2. Load the `loki://system/health` resource to check Loki reachability.
3. For Loki behind a load balancer or gateway, verify the base URL routes to the query-frontend.
4. For authenticated backends, set `LOKI_AUTH_TOKEN` (Bearer) or `LOKI_BASIC_AUTH_USER`/`LOKI_BASIC_AUTH_PASSWORD` (Basic).

### No Logs Found

1. Run `get_cluster_labels()` to verify data exists — if labels are returned, Loki has data.
2. Run `get_label_values(label="app")` to see available service names.
3. Broaden the time range: try `start="now-24h"` or `start="now-7d"`.
4. Start with the broadest possible query: `execute_logql_query(query='{app=~".+"}', start="now-1h", limit=5)`.
5. For multi-tenant deployments, verify the correct `LOKI_ORG_ID` is configured.

### Detected Fields Endpoint Not Working

1. `get_detected_fields` requires **Loki 3.0+** with the `/loki/api/v1/detected_fields` endpoint.
2. If you get a 404, your Loki version may not support this endpoint — upgrade Loki.
3. If fields are empty, logs may be unstructured (plain text without JSON/logfmt keys).

### Pattern Ingester Not Working

1. `get_log_patterns` requires Loki's **pattern ingester** to be enabled.
2. In your Loki config: `pattern_ingester: { enabled: true }`.
3. Pattern data is ephemeral — typically covers the last 3 hours only.
4. If you get a 404, the pattern ingester is not enabled.

### Query Too Expensive Errors

1. The `execute_logql_query` tool pre-checks query cost against `LOKI_MAX_QUERY_BYTES`.
2. Use `get_query_stats` first to estimate cost before executing.
3. Narrow the time range, add more specific selectors, or increase `LOKI_MAX_QUERY_BYTES`.

---

## Security Considerations

- **Never expose the MCP server to the public internet** without proper authentication.
- **All tools are read-only** — the server only performs HTTP GET requests against Loki's query APIs. No data is created, modified, or deleted.
- **Tenant isolation** — in multi-tenant deployments, the server injects the `X-Scope-OrgID` header on every request. Verify that the org ID is correctly scoped to prevent cross-tenant data leakage.
- **Auth credentials** — if `LOKI_AUTH_TOKEN` or `LOKI_BASIC_AUTH_PASSWORD` is set, it is included in every request to the backend. Protect these values as secrets.
- **Query guardrails** — the server enforces byte, time window, limit, and cardinality thresholds to prevent unbounded queries. Review and adjust the guardrail settings for your environment.

---

## License

Apache 2.0 — see [LICENSE](../../LICENSE).

---

## Contact

**TalkOps AI** — [github.com/talkops-ai](https://github.com/talkops-ai)

**Project:** [github.com/talkops-ai/talkops-mcp](https://github.com/talkops-ai/talkops-mcp)

**Discord:** [Join the community](https://discord.gg/tSN2Qn9uM8)

---

## Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io/) for enabling AI-native tool interfaces.
- [FastMCP](https://github.com/jlowin/fastmcp) for the Python MCP server framework.
- [Grafana Loki](https://grafana.com/oss/loki/) for the scalable log aggregation system.
- [OpenTelemetry](https://opentelemetry.io/) for the industry-standard observability framework.
