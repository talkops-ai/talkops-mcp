<p align="center">
  <img src="https://raw.githubusercontent.com/grafana/tempo/main/docs/sources/tempo/logo_and_name.png" alt="Tempo MCP Server" width="200" onError="this.style.display='none'"/>
</p>

<h1 align="center">Tempo MCP Server</h1>

<p align="center">
  An MCP server that gives AI assistants the power to search, analyze, summarize, and correlate distributed traces from Grafana Tempo — with TraceQL query construction, RED metrics analysis, cross-pillar pivots, service topology mapping, and operational diagnostics.
</p>

<p align="center">
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://grafana.com/oss/tempo/"><img src="https://img.shields.io/badge/Grafana%20Tempo-Compatible-F46800.svg?style=flat-square&logo=grafana&logoColor=white" alt="Grafana Tempo"/></a>
  <a href="https://discord.gg/tSN2Qn9uM8"><img src="https://img.shields.io/badge/Discord-Join%20Us-5865F2.svg?style=flat-square&logo=discord&logoColor=white" alt="Discord"/></a>
</p>

<p align="center">
  <a href="#getting-started">Quick Start</a> · <a href="https://github.com/talkops-ai/talkops-mcp">Docs</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=bug_report.md">Report Bug</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=feature_request.md">Request Feature</a>
</p>

---

## Why Tempo MCP Server?

**The problem:** Grafana Tempo is a powerful distributed tracing backend, but effective trace analysis is complex. Constructing TraceQL queries requires knowledge of attribute scopes, intrinsic fields, and structural operators. Correlating traces with metrics (RED analysis) and logs requires multi-step pivots across different APIs. Diagnosing latency spikes means navigating critical paths, identifying root causes, and finding related incidents — each a specialized skill. When AI assistants try to help, they hallucinate TraceQL syntax, miss multi-tenant requirements, or generate unbounded queries that overwhelm backends.

**The solution:** The Tempo MCP Server gives AI assistants (like Claude, Cline, or Cursor) structured, safe tools to interact with Grafana Tempo natively:

1. **Smart Trace Search:** Say *"Find error traces from the API service in production"* and the AI auto-translates K8s-friendly filters (namespace, service, deployment) into valid TraceQL, enforces query guardrails (time ranges, limits), and returns compact summaries.
2. **Intelligent Trace Analysis:** The AI fetches a trace, extracts the critical path, identifies error spans, detects the suspected root cause, and recommends follow-up queries — all in a single `tempo_summarize_trace` call.
3. **Metrics-First Triage:** Execute RED metrics queries (rate, errors, duration) using TraceQL metrics functions like `rate()`, `quantile_over_time()`, and `count_over_time()` — then pivot from aggregated metrics to concrete traces via exemplars.
4. **Cross-Pillar Correlation:** Extract trace IDs from log lines and retrieve the full trace. Pivot from metrics spikes to exemplar traces. Correlate related traces using strategies like same-service errors, same-endpoint, or temporal neighbors.
5. **Backend Diagnostics:** Aggregate health checks, build info, component service status, and ring member health into a single curated diagnostics report with severity-ranked findings and remediation steps.
6. **Service Topology:** Map service dependencies from Tempo's metrics-generator service graph data, with request rates and error rates per edge.

---

## Key Features

**TraceQL Search with K8s-Friendly Filters**
- Raw TraceQL queries or structured K8s filters (namespace, service, deployment, cluster)
- Auto-translation of K8s concepts to OTel attributes via canonical mapping
- Query guardrails: time range enforcement, limit clamping, empty-query rejection
- Basic TraceQL validation before sending to backend
- Non-determinism awareness in result metadata

**Trace Retrieval & Analysis**
- Single-trace fetch with LLM-optimized format support (Tempo 2.9+ `application/vnd.grafana.llm`)
- Automatic fallback to standard OTLP JSON when LLM format is unavailable
- Server-side trace summarization: critical path extraction, error detection, root cause analysis, and recommended next queries
- **Time gap detection**: disambiguates wall-clock duration from critical path duration when async/disjointed spans inflate the trace window
- Related trace correlation with three strategies: same-service errors, same-endpoint, temporal neighbors

**Schema Discovery**
- Attribute name discovery across scopes (resource, span, intrinsic, event, link, instrumentation)
- Attribute value enumeration with time-window scoping and TraceQL filtering
- Canonical K8s-to-Tempo attribute mapping with optional live validation against a backend

**TraceQL Metrics**
- Range queries returning Prometheus-compatible time series (matrix format)
- Instant queries returning point-in-time metrics (vector format)
- Support for `rate()`, `count_over_time()`, `avg_over_time()`, `max_over_time()`, `min_over_time()`, `sum_over_time()`, `quantile_over_time()`, `histogram_over_time()`

**Cross-Pillar Pivots**
- Metrics-to-traces: extract exemplar trace IDs from TraceQL metrics queries
- Logs-to-traces: parse trace IDs from log lines (supports `trace_id=`, `traceId:`, `TraceID=`, standalone 32-char hex) and retrieve full traces

**Backend Discovery & Diagnostics**
- Multi-backend support with per-backend health probing
- Kubernetes service discovery (label-based + Tempo Operator CRDs: TempoStack, TempoMonolithic)
- Comprehensive diagnostics: readiness, build info, component services, ring status
- Severity-ranked findings with actionable remediation steps

**Service Topology**
- Service dependency mapping from `traces_service_graph_request_total` metrics
- Request rate and error rate per service edge
- Service-focused filtering for targeted topology views

**Multi-Tenancy**
- Per-backend tenant header injection (`X-Scope-OrgID`)
- Cross-tenant queries via pipe-separated tenant IDs
- Tenant ID validation (max 150 bytes, restricted charset)
- Graceful handling of single-tenant and multi-tenant backends

**Production-Ready Middleware**
- Response limiting (100KB max), rate limiting (10 req/s, burst 20)
- Response caching (10s for tools, 30s for resources, 5min for listings)
- Structured logging, error handling, timing

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
  │  (16)   │ │  (11)   │ │  (5)  │ │         │ │         │
  └────┬────┘ └────┬────┘ └───────┘ └─────────┘ └─────────┘
       │            │
       └──────┬─────┘
              │
   ┌──────────▼──────────┐
   │    Service Layer     │
   │                      │
   │   tempo_service      │
   │   kubernetes_service │
   └──────────┬──────────┘
              │
   ┌──────────▼──────────┐
   │  Tempo HTTP API      │
   │  + K8s Discovery     │
   └─────────────────────┘
```

**How it works:**

1. An AI assistant connects via HTTP, SSE, or stdio.
2. The AI loads `tempo://system/backends` resource to discover available Tempo backends and their health.
3. Tools interact with Tempo's HTTP API to search traces, compute metrics, and run diagnostics.
4. The service layer (`tempo_service`) handles HTTP calls with connection pooling, tenant injection, and LLM format negotiation.
5. Optional Kubernetes discovery (`kubernetes_service`) finds Tempo services via labels and Tempo Operator CRDs.
6. Middleware enforces rate limiting, response size caps, caching, and structured logging.

---

## Table of Contents

- [Why Tempo MCP Server?](#why-tempo-mcp-server)
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
| **Tracing Backend** | [Grafana Tempo](https://grafana.com/oss/tempo/) HTTP API |
| **HTTP Client** | [httpx](https://www.python-httpx.org/) — async, connection pooling |
| **Kubernetes** | Python K8s Client · Tempo Operator CRDs |
| **Transport** | HTTP · SSE · Streamable-HTTP · stdio |
| **Infrastructure** | Docker · [uv](https://github.com/astral-sh/uv) |

---

## Getting Started

### Prerequisites

- **Docker** (recommended) or **Python 3.12+** (for local dev)
- **Grafana Tempo** backend accessible via HTTP (monolithic or microservices mode)
- Optionally: **Kubernetes** with the [Tempo Operator](https://github.com/grafana/tempo-operator) for auto-discovery

### Quick Start with Docker (recommended)

```bash
docker run --rm -it \
  -p 8768:8768 \
  -e MCP_TRANSPORT=http \
  -e TEMPO_BASE_URL=http://host.docker.internal:3200 \
  talkopsai/tempo-mcp-server:latest
```

The server is now listening on `http://localhost:8768/mcp`.

Point your MCP client at it:

```json
{
  "mcpServers": {
    "tempo": {
      "url": "http://localhost:8768/mcp",
      "description": "MCP Server for Grafana Tempo distributed tracing"
    }
  }
}
```

### From Source (Python)

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) for dependency management.

2. Clone and set up:

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/tempo-mcp-server
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

3. Configure your `.env`:

```bash
TEMPO_BASE_URL=http://localhost:3200
MCP_TRANSPORT=http
MCP_LOG_LEVEL=INFO
```

4. Run the server:

```bash
uv run tempo-mcp-server
```

Or, with the venv activated: `tempo-mcp-server`.

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
| `MCP_SERVER_NAME` | `tempo-mcp-server` | Server name identifier |
| `MCP_SERVER_VERSION` | `0.1.0` | Server version string |
| `MCP_TRANSPORT` | `stdio` | Transport mode: `http`, `sse`, `streamable-http`, or `stdio` |
| `MCP_HOST` | `0.0.0.0` | Host address for HTTP server |
| `MCP_PORT` | `8768` | Port for HTTP server |
| `MCP_PATH` | `/mcp` | MCP endpoint path |
| `MCP_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `MCP_LOG_FORMAT` | `json` | Log format: `json` or `text` |
| `MCP_HTTP_TIMEOUT` | `300` | HTTP server timeout (seconds) |
| `MCP_HTTP_KEEPALIVE_TIMEOUT` | `5` | HTTP keepalive timeout (seconds) |
| `MCP_HTTP_CONNECT_TIMEOUT` | `60` | HTTP connect timeout (seconds) |

### Tempo Backend (Single Backend Mode)

| Variable | Default | Description |
|----------|---------|-------------|
| `TEMPO_BASE_URL` | `http://localhost:3200` | Tempo HTTP API base URL |
| `TEMPO_BACKEND_ID` | `default` | Backend identifier |
| `TEMPO_DISPLAY_NAME` | *(empty)* | Human-readable backend name |
| `TEMPO_TYPE` | `tempo` | Backend type: `tempo`, `tempo-gateway`, `unknown` |
| `TEMPO_DEPLOYMENT_MODE` | `unknown` | Deployment mode: `monolithic`, `microservices`, `unknown` |
| `TEMPO_AUTH_HEADER` | *(empty)* | Authorization header value (e.g., `Bearer <token>`) |
| `TEMPO_VERIFY_SSL` | `true` | Verify SSL certificates |
| `TEMPO_TIMEOUT` | `30` | HTTP timeout per request (seconds) |

### Tempo Backend (Multi-Backend Mode)

| Variable | Default | Description |
|----------|---------|-------------|
| `TEMPO_BACKENDS` | *(empty)* | JSON array of backend configs (overrides single backend). See `.env.example`. |

### Multi-Tenancy

| Variable | Default | Description |
|----------|---------|-------------|
| `TEMPO_MULTI_TENANT` | `false` | Enable multi-tenant mode for the backend |
| `TEMPO_DEFAULT_TENANT` | *(empty)* | Default tenant ID (required if `TEMPO_MULTI_TENANT=true`) |
| `TEMPO_TENANT_HEADER` | `X-Scope-OrgID` | HTTP header name for tenant ID injection |

### Query Policies / Guardrails

| Variable | Default | Description |
|----------|---------|-------------|
| `TEMPO_MAX_LOOKBACK` | `168h` | Maximum query lookback (7 days) |
| `TEMPO_DEFAULT_SEARCH_LIMIT` | `20` | Default max traces per search |
| `TEMPO_MAX_SEARCH_LIMIT` | `100` | Absolute max traces per search |
| `TEMPO_DEFAULT_SPSS` | `3` | Default spans per span-set |
| `TEMPO_MAX_SPSS` | `10` | Maximum spans per span-set |
| `TEMPO_REQUIRE_TIME_RANGE` | `true` | Require time range on searches |
| `TEMPO_REQUIRE_FILTER_OR_QUERY` | `true` | Require at least one filter or TraceQL query |
| `TEMPO_DEFAULT_METRICS_SAMPLING` | *(empty)* | Default metrics sampling rate (e.g., `fixed-span:0.1`) |
| `TEMPO_MAX_METRICS_DURATION` | `3h` | Maximum allowed metrics query time range. Should match Tempo's `query_frontend.metrics.max_duration`. |

### LLM Format

| Variable | Default | Description |
|----------|---------|-------------|
| `TEMPO_LLM_FORMAT` | `true` | Enable LLM-optimized trace format (Tempo 2.9+ `application/vnd.grafana.llm`) |

### Kubernetes Discovery

| Variable | Default | Description |
|----------|---------|-------------|
| `K8S_ENABLED` | `false` | Enable Kubernetes-based Tempo backend discovery |
| `K8S_CONTEXT` | *(empty)* | Specific kubeconfig context to use |
| `K8S_IN_CLUSTER` | `false` | Set `true` when running inside a Kubernetes pod |

### Tempo Operator CRD

| Variable | Default | Description |
|----------|---------|-------------|
| `TEMPO_CRD_GROUP` | `tempo.grafana.com` | Tempo Operator CRD API group |
| `TEMPO_CRD_API_VERSION` | `v1alpha1` | CRD API version (change when Operator graduates to v1) |

---

## Available Tools

### Discovery
| Tool | Description |
|------|-------------|
| `tempo_list_backends` | List all configured Tempo backends with health status (ready/not_ready). Use this first to discover available backends. |
| `tempo_get_backend` | Get detailed profile for a specific backend: health, version, build info, capabilities, deployment mode, tenant requirements, and component service statuses. |
| `tempo_get_query_policies` | Get query guardrails and default search parameters: max lookback, search limits, SPSS limits, and time range requirements. |

### Schema Discovery
| Tool | Description |
|------|-------------|
| `tempo_get_attribute_names` | Discover available trace attribute names from a Tempo backend, grouped by scope (resource, span, intrinsic, event, link, instrumentation). Supports time-window scoping. |
| `tempo_get_attribute_values` | Get distinct values for a specific trace attribute. Useful for understanding data distribution and building dynamic filters. Supports TraceQL scoping. |
| `tempo_get_k8s_attribute_map` | Get the canonical mapping between Kubernetes concepts (namespace, pod, deployment) and their OTel/Tempo attribute names. Optionally validates against a live backend's tag list. |

### Search & Retrieval
| Tool | Description |
|------|-------------|
| `tempo_traceql_search` | **HIGH-INTENT:** Search for traces using raw TraceQL or K8s-friendly filters (namespace, service, deployment, cluster, status, duration). Auto-translates filters to TraceQL, enforces query guardrails, and returns compact summaries. |
| `tempo_get_trace` | Retrieve a single trace by ID with LLM-optimized format. Attempts `application/vnd.grafana.llm` first, falls back to standard OTLP JSON. |
| `tempo_query_a2ui` | Retrieve a trace heavily optimized and structured for A2UI rendering. DAG-aware pruning enforces payload limits while preserving critical paths and parent-child linkages. |
| `tempo_summarize_trace` | **HIGH-INTENT:** Generate an intelligent summary of a trace — critical path extraction, error detection, suspected root cause, K8s context, time gap detection (wall-clock vs. critical path disambiguation), and recommended next queries. Primary analysis primitive. |
| `tempo_find_related_traces` | **HIGH-INTENT:** Find traces related to a seed trace using correlation strategies: `same_service_errors`, `same_endpoint`, or `temporal_neighbors`. One call replaces manual multi-step correlation. |

### Metrics
| Tool | Description |
|------|-------------|
| `tempo_traceql_metrics_range` | Execute a TraceQL metrics range query. Returns Prometheus-compatible time series (matrix). Use for RED metrics, trend analysis, and SLO calculations. Supports `rate()`, `count_over_time()`, `quantile_over_time()`, etc. |
| `tempo_traceql_metrics_instant` | Execute a TraceQL metrics instant query. Returns point-in-time metrics (vector). |

### Cross-Pillar Pivots
| Tool | Description |
|------|-------------|
| `tempo_get_exemplar_traces` | Pivot from aggregated metrics to concrete traces. Extracts exemplar trace IDs from a TraceQL metrics query result. |
| `tempo_get_trace_from_log` | Extract a trace ID from a log line (supports multiple formats) and retrieve + summarize the associated trace. One call replaces parse → fetch → analyze. |

### Diagnostics
| Tool | Description |
|------|-------------|
| `tempo_get_diagnostics` | **HIGH-INTENT:** Comprehensive backend diagnostics. Aggregates health check, build info, component service status, and ring member health into a curated report with severity-ranked findings and suggested actions. |

### Topology
| Tool | Description |
|------|-------------|
| `tempo_get_service_dependencies` | Map service dependencies from Tempo's metrics-generator service graph data. Returns nodes and edges with request rates. Supports service-focused filtering. |

### Operator CRD Management
| Tool | Description |
|------|-------------|
| `tempo_list_operator_crs` | List Tempo Operator custom resources (TempoStack, TempoMonolithic) across namespaces with status. Read-only. |
| `tempo_get_operator_cr` | Get a Tempo Operator CR with full spec, status, conditions, and storage configuration. Read-only. |
| `tempo_create_operator_cr` | Create a TempoStack or TempoMonolithic CR. Generates complete CRD manifest with storage, retention, resources. **dry_run=True by default.** |
| `tempo_patch_operator_cr` | Patch specific fields of an existing Tempo Operator CR (retention, resources, search). **dry_run=True by default.** |

### Trace Comparison
| Tool | Description |
|------|-------------|
| `tempo_compare_traces` | **HIGH-INTENT:** Compare two traces and report structural + timing + error + attribute differences. 5-dimensional diff: services, span counts, durations, errors, attributes. |

### Alerting Expression Generator
| Tool | Description |
|------|-------------|
| `tempo_generate_alerting_expression` | Generate PromQL alerting expressions from trace patterns using spanmetrics. Returns ready-to-paste PrometheusRule YAML. **Cross-MCP workflow: pass output to prom_upsert_rule_group.** |

## Available Resources

### Dynamic Resources

| Resource URI | Description |
|--------------|-------------|
| `tempo://system/backends` | All configured Tempo backends with health status |
| `tempo://system/backends/{backend_id}` | Detailed profile for a specific Tempo backend |
| `tempo://deployment/overview` | Deployment topology: backends, modes, tenants, K8s integration status |

### Reference Resources (Static)

| Resource URI | Description |
|--------------|-------------|
| `tempo://reference/traceql` | TraceQL syntax reference: selectors, operators, intrinsics, scoped attributes, structural queries, examples |
| `tempo://reference/traceql-metrics` | TraceQL metrics functions: rate, count_over_time, quantile, histogram, grouping, aggregations, sampling |
| `tempo://reference/k8s-attributes` | Canonical K8s-to-Tempo attribute mapping for Kubernetes observability |
| `tempo://reference/query-policies` | Query guardrails, limits, continuation strategy, and safety guidelines (dynamically populated from config) |

### Runbook Resources

| Resource URI | Description |
|--------------|-------------|
| `tempo://runbooks/latency-spike` | Step-by-step runbook for investigating latency spikes: detect → locate → analyze → correlate → root cause |
| `tempo://runbooks/error-burst` | Step-by-step runbook for investigating error bursts: quantify → search → triage → correlate |
| `tempo://runbooks/no-traces-found` | Diagnostic runbook for "no traces found" scenarios: backend health → data existence → scope checks → ingestion |
| `tempo://runbooks/cross-tenant-access` | Runbook for cross-tenant query configuration, usage, and constraints |

### Example Resources

| Resource URI | Description |
|--------------|-------------|
| `tempo://examples/common-queries` | Common TraceQL and metrics query examples for quick reference: service exploration, error investigation, performance analysis, structural queries, metrics queries |

---

## Available Prompts

Guided workflow prompts that orchestrate multiple tools into step-by-step journeys:

| Prompt Name | Description | Parameters |
|-------------|-------------|------------|
| `tempo-error-triage` | Guided 4-phase error triage: quantify impact (error rate vs. baseline), find error traces, analyze root cause via summarization + correlation, contextualize with diagnostics | `backend_id`, `service`, `namespace` |
| `tempo-latency-investigation` | Guided 4-phase latency investigation: confirm spike (P99 trend), find slow traces above threshold, critical path analysis via summarization, compare with normal traces | `backend_id`, `service`, `threshold_ms` |
| `tempo-missing-traces` | Guided 4-phase diagnostic for "no traces found": verify backend health, verify data exists (attribute names, broadest search), check scope (tenant, namespace, service), consult runbook | `backend_id`, `service` |
| `tempo-traceql-builder` | Interactive TraceQL query construction: parse user intent, discover available attributes, construct query using reference, execute, and refine | `backend_id`, `intent` |
| `tempo-metrics-first-triage` | RED metrics-first triage for a service: rate, error rate, P99 duration, investigate anomalies, deep dive into individual traces | `backend_id`, `service` |

---

## Usage

Supported workflows with prompt examples and links to detailed guides:

| Workflow | Prompt Example | Documentation |
|----------|----------------|---------------|
| **Error Triage** | `"Triage errors for the 'checkout-service' in the 'production' namespace using backend 'prod'."` | [TEMPO_ERROR_TRIAGE_TEST_GUIDE.md](docs/TEMPO_ERROR_TRIAGE_TEST_GUIDE.md) |
| **Latency Investigation** | `"Investigate latency spikes above 500ms for 'api-gateway' using backend 'prod'."` | [TEMPO_LATENCY_INVESTIGATION_TEST_GUIDE.md](docs/TEMPO_LATENCY_INVESTIGATION_TEST_GUIDE.md) |
| **Missing Traces** | `"No traces found for 'payment-service' — diagnose the issue on backend 'prod'."` | [TEMPO_MISSING_TRACES_TEST_GUIDE.md](docs/TEMPO_MISSING_TRACES_TEST_GUIDE.md) |
| **TraceQL Builder** | `"Build a TraceQL query to find slow database calls over 100ms in the frontend."` | [TEMPO_TRACEQL_BUILDER_TEST_GUIDE.md](docs/TEMPO_TRACEQL_BUILDER_TEST_GUIDE.md) |
| **Metrics-First Triage** | `"Run a RED analysis for 'order-service' over the last 6 hours."` | [TEMPO_METRICS_FIRST_TRIAGE_TEST_GUIDE.md](docs/TEMPO_METRICS_FIRST_TRIAGE_TEST_GUIDE.md) |

---

## Project Structure

```text
tempo-mcp-server/
├── tempo_mcp_server/              # Main package
│   ├── tools/                     # MCP Tools (10 tool groups, 23 tools)
│   │   ├── discovery/             # Backend listing, inspection, query policies
│   │   │   └── discovery_tools.py # 3 tools: list_backends, get_backend, get_query_policies
│   │   ├── schema/                # Attribute/tag discovery
│   │   │   └── schema_tools.py    # 3 tools: get_attribute_names, get_attribute_values, get_k8s_attribute_map
│   │   ├── search/                # Trace search & retrieval
│   │   │   └── search_tools.py    # 5 tools: traceql_search, get_trace, query_a2ui, summarize_trace, find_related_traces
│   │   ├── metrics/               # TraceQL metrics queries
│   │   │   └── metrics_tools.py   # 2 tools: metrics_range, metrics_instant
│   │   ├── pivot/                 # Cross-pillar correlation
│   │   │   └── pivot_tools.py     # 2 tools: get_exemplar_traces, get_trace_from_log
│   │   ├── diagnostics/           # Backend health & diagnostics
│   │   │   └── diagnostics_tools.py # 1 tool: get_diagnostics
│   │   ├── topology/              # Service dependency mapping
│   │   │   └── topology_tools.py  # 1 tool: get_service_dependencies
│   │   ├── operator/              # Tempo Operator CRD lifecycle
│   │   │   └── operator_tools.py  # 4 tools: list_operator_crs, get_operator_cr, create_operator_cr, patch_operator_cr
│   │   ├── comparison/            # Trace comparison
│   │   │   └── comparison_tools.py # 1 tool: compare_traces
│   │   └── alerting/              # Alerting expression generation
│   │       └── alerting_tools.py  # 1 tool: generate_alerting_expression
│   ├── resources/                 # MCP Resources (11 URIs)
│   │   ├── backend_resources.py   # Dynamic: backends listing, backend detail
│   │   ├── deployment_resources.py # Dynamic: deployment overview
│   │   ├── reference_resources.py # Static: TraceQL, metrics, K8s attributes, query policies
│   │   ├── runbook_resources.py   # Static: latency spike, error burst, no traces, cross-tenant
│   │   └── examples_resources.py  # Static: common TraceQL query examples
│   ├── prompts/                   # MCP Prompts (5 guided workflows)
│   │   ├── query_prompts.py       # TraceQL builder, metrics-first triage
│   │   └── troubleshooting_prompts.py # Error triage, latency investigation, missing traces
│   ├── services/                  # Business logic
│   │   ├── tempo_service.py       # Async HTTP client: all Tempo API calls, tenant injection,
│   │   │                          # LLM format negotiation, connection pooling
│   │   └── kubernetes_service.py  # K8s discovery & CRD management: service labels, Tempo Operator CRDs,
│   │                              # create/patch TempoStack/TempoMonolithic
│   ├── server/                    # FastMCP server setup
│   │   ├── core.py                # Server creation & instructions loading
│   │   ├── bootstrap.py           # Component initialization & DI
│   │   └── middleware.py          # 7-layer middleware stack
│   ├── models/                    # Pydantic data models
│   │   ├── search.py              # SearchFilters, trace response models
│   │   ├── schema.py              # Attribute scope definitions
│   │   ├── backend.py             # Backend config models
│   │   ├── trace.py               # Trace summary models
│   │   ├── metrics.py             # Metrics response models
│   │   ├── pivot.py               # Pivot response models
│   │   ├── topology.py            # Topology models
│   │   ├── diagnostics.py         # Diagnostics models
│   │   ├── operator.py            # Tempo Operator CRD models
│   │   └── comparison.py          # Trace comparison models
│   ├── utils/                     # Helpers
│   │   ├── traceql_helpers.py     # TraceQL construction, validation, K8s attribute mapping
│   │   ├── trace_summarizer.py    # Critical path extraction, error detection, headline generation
│   │   ├── trace_differ.py        # 5-dimensional trace diff engine
│   │   ├── trace_id_extractor.py  # Regex-based trace ID parsing from log lines
│   │   └── time_helpers.py        # Relative time parsing (1h, 24h, 7d → Unix epoch)
│   ├── static/                    # Static data files
│   │   └── TEMPO_MCP_INSTRUCTIONS.md  # MCP system instructions for AI agents
│   ├── exceptions/                # Custom exception hierarchy
│   │   └── custom.py              # TempoOperationError, TempoQueryError, TempoTenantError, etc.
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

- [x] TraceQL search with K8s-friendly filters and query guardrails
- [x] Intelligent trace summarization (critical path, error detection, root cause)
- [x] Related trace discovery via correlation strategies
- [x] Attribute name/value discovery with scope filtering and time-window scoping
- [x] K8s-to-Tempo canonical attribute mapping with live validation
- [x] TraceQL metrics: range and instant queries with Prometheus-compatible output
- [x] Metrics-to-traces exemplar pivot
- [x] Logs-to-traces pivot (multi-format trace ID extraction)
- [x] Comprehensive backend diagnostics (readiness, build info, services, rings)
- [x] Service topology mapping from metrics-generator data
- [x] Multi-tenancy with tenant validation and cross-tenant support
- [x] 5 guided workflow prompts (error triage, latency, missing traces, TraceQL builder, RED triage)
- [x] 11 MCP resources (dynamic backends, static references, runbooks, examples)
- [x] 7-layer middleware stack (error handling, response limiting, rate limiting, caching, logging, timing)
- [x] Tempo Operator CRD management (list/get/create/patch TempoStack & TempoMonolithic)
- [x] Trace comparison (diff two traces by ID — 5-dimensional structural analysis)
- [x] Alerting expression generator (PromQL from trace patterns → cross-MCP workflow with Prometheus server)

**Coming next:**

- [ ] Multi-cluster support
- [ ] Trace diff visualization (HTML/Mermaid output for trace comparison)
- [ ] Batch trace analysis (compare N traces, detect outliers)
- [ ] Custom TraceQL metrics function library

See [open issues](https://github.com/talkops-ai/talkops-mcp/issues) for the full list of proposed features.

---

## Contributing

Contributions are welcome. The process is straightforward:

1. Fork the repo
2. Create a branch (`git checkout -b feature/TraceComparison`)
3. Make your changes and commit
4. Push and open a PR

If you're considering something bigger, open an issue first so we can align on the approach.

---

## FAQ

<details>
<summary><b>Which MCP clients work with this?</b></summary>
Any MCP-compatible client including Claude Desktop, Cline, Cursor, and custom clients. Connect via <code>http://localhost:8768/mcp</code> for HTTP transport, or configure stdio for direct process communication.
</details>

<details>
<summary><b>Does this require Grafana Tempo?</b></summary>
Yes. The server communicates with Tempo's HTTP API (<code>/api/search</code>, <code>/api/v2/traces/{traceID}</code>, <code>/api/v2/search/tags</code>, <code>/api/metrics/query_range</code>, etc.). Any Grafana Tempo deployment (monolithic, microservices, or via the Tempo Operator) will work. The LLM-optimized trace format requires Tempo 2.9+.
</details>

<details>
<summary><b>Does this modify my cluster or Tempo backend?</b></summary>
No. All 16 tools are <b>read-only</b>. The server only performs HTTP GET requests against Tempo's query APIs. No traces, metrics, or configurations are created, modified, or deleted.
</details>

<details>
<summary><b>Can I use multiple Tempo backends?</b></summary>
Yes. Set the <code>TEMPO_BACKENDS</code> environment variable to a JSON array of backend configurations. Each backend gets its own ID, base URL, tenant settings, and auth header. All tools accept a <code>backend_id</code> parameter to target a specific backend. See <code>.env.example</code> for the format.
</details>

<details>
<summary><b>How does multi-tenancy work?</b></summary>
For multi-tenant Tempo deployments, set <code>TEMPO_MULTI_TENANT=true</code> and <code>TEMPO_DEFAULT_TENANT</code>. The server injects the <code>X-Scope-OrgID</code> header (configurable via <code>TEMPO_TENANT_HEADER</code>) on every request. Tools accept an optional <code>tenant</code> parameter to override the default. For cross-tenant queries, use pipe-separated values (e.g., <code>tenant="team-a|team-b"</code>). Tenant IDs are validated: max 150 bytes, alphanumeric + <code>!-_.*'()</code>.
</details>

<details>
<summary><b>What is the LLM trace format?</b></summary>
Tempo 2.9+ supports an experimental <code>application/vnd.grafana.llm</code> Accept header that returns traces in a compact, LLM-friendly format — optimized for token efficiency when used with AI assistants. The server attempts this format first and automatically falls back to standard OTLP JSON if the backend doesn't support it. Disable with <code>TEMPO_LLM_FORMAT=false</code>.
</details>

<details>
<summary><b>Can I use this without Kubernetes?</b></summary>
Yes. Set <code>K8S_ENABLED=false</code> (the default). All tools work against Tempo's HTTP API directly — Kubernetes is only needed for auto-discovery of Tempo backends via service labels or Tempo Operator CRDs. Configure your backend URL(s) via <code>TEMPO_BASE_URL</code> or <code>TEMPO_BACKENDS</code>.
</details>

<details>
<summary><b>What are query guardrails?</b></summary>
The server enforces configurable safety limits to prevent unbounded queries: time range is required by default (<code>TEMPO_REQUIRE_TIME_RANGE=true</code>), search results are capped (<code>TEMPO_MAX_SEARCH_LIMIT=100</code>), SPSS is bounded (<code>TEMPO_MAX_SPSS=10</code>), and at least one filter or query is required (<code>TEMPO_REQUIRE_FILTER_OR_QUERY=true</code>). These protect both the AI agent's context window and the Tempo backend.
</details>

---

## Troubleshooting

### Tempo Connection Issues

1. Verify `TEMPO_BASE_URL` points to an accessible Tempo HTTP endpoint (default port: `3200`).
2. Load the `tempo://system/backends` resource to check backend health.
3. Run `tempo_get_diagnostics(backend_id="default")` for detailed health analysis.
4. For Tempo behind a load balancer or gateway, verify the base URL routes to the query-frontend.
5. For authenticated backends, set `TEMPO_AUTH_HEADER` (e.g., `Bearer <token>`).

### No Traces Found

1. Run `tempo_get_attribute_names(backend_id="default", since="1h")` to verify data exists.
2. Broaden the time range: try `since="24h"` or `since="7d"`.
3. Start with the broadest possible query: `tempo_traceql_search(backend_id="default", since="24h", limit=5)`.
4. For multi-tenant backends, verify the correct `tenant` parameter is being passed.
5. Load the `tempo://runbooks/no-traces-found` resource for a full diagnostic walkthrough.
6. Check that data is flowing through your ingestion pipeline (OTel Collector → Tempo).

### TraceQL Metrics Not Working

1. TraceQL metrics require Tempo's **metrics-generator** with the `local-blocks` processor enabled.
2. Run `tempo_get_diagnostics(backend_id="default")` to check backend capabilities.
3. Verify the metrics-generator is configured in your Tempo deployment.

### Kubernetes Discovery Not Finding Backends

1. Ensure `K8S_ENABLED=true` in your `.env`.
2. Verify your kubeconfig is accessible and the correct context is set.
3. Tempo services must have the label `app.kubernetes.io/name=tempo` for label-based discovery.
4. For Tempo Operator discovery, ensure TempoStack or TempoMonolithic CRDs exist in the cluster.
5. For in-cluster deployment, set `K8S_IN_CLUSTER=true`.

### Diagnostics Reporting False-Positive Ring Errors (404)

1. If `tempo_get_diagnostics` reports `404 Not Found` for ring endpoints (e.g., `/distributor/ring`, `/ingester/ring`), your `TEMPO_BASE_URL` likely points to a Tempo Gateway or Query-Frontend in a distributed/microservices deployment.
2. **Gateways generally do not proxy internal diagnostic ring endpoints**, which only exist on the specific backend pods.
3. **Fix**: Ensure `TEMPO_DEPLOYMENT_MODE=unknown` (the default) is set in your `.env`. This explicitly instructs the MCP server to gracefully skip ring checks and rely only on `/status/services`, preventing false-positive degraded health states while still validating core component availability.

---

## Security Considerations

- **Never expose the MCP server to the public internet** without proper authentication.
- **All tools are read-only** — the server only performs HTTP GET requests against Tempo's query APIs. No data is created, modified, or deleted.
- **Tenant isolation** — in multi-tenant deployments, the server injects tenant headers on every request. Verify that tenant IDs are correctly scoped to prevent cross-tenant data leakage.
- **Auth headers** — if `TEMPO_AUTH_HEADER` is set, it is included in every request to the backend. Protect this value as a secret.
- **Query guardrails** — the server enforces time range, limit, and filter requirements to prevent unbounded queries. Review and adjust the policy settings for your environment.
- **Kubernetes credentials** — when `K8S_ENABLED=true`, the server reads Kubernetes service/CRD metadata (read-only). Ensure the service account has minimal RBAC (only `get`, `list` on Services and Tempo CRDs).

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
- [Grafana Tempo](https://grafana.com/oss/tempo/) for the scalable distributed tracing backend.
- [Tempo Operator](https://github.com/grafana/tempo-operator) for Kubernetes-native Tempo lifecycle management.
- [OpenTelemetry](https://opentelemetry.io/) for the industry-standard observability framework.
