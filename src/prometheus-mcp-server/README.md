<p align="center">
  <img src="https://raw.githubusercontent.com/cncf/artwork/main/projects/prometheus/stacked/color/prometheus-stacked-color.svg" alt="Prometheus MCP Server" width="140" onError="this.style.display='none'"/>
</p>

<h1 align="center">Prometheus MCP Server</h1>

<p align="center">
  An MCP server that gives AI assistants the power to query, instrument, and manage Prometheus monitoring — from backend discovery to exporter deployment, PromQL execution, TSDB optimization, and governance.
</p>

<p align="center">
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://prometheus.io/"><img src="https://img.shields.io/badge/Prometheus-Compatible-E6522C.svg?style=flat-square&logo=prometheus&logoColor=white" alt="Prometheus"/></a>
  <a href="https://discord.gg/tSN2Qn9uM8"><img src="https://img.shields.io/badge/Discord-Join%20Us-5865F2.svg?style=flat-square&logo=discord&logoColor=white" alt="Discord"/></a>
</p>

<p align="center">
  <a href="#getting-started">Quick Start</a> · <a href="https://github.com/talkops-ai/talkops-mcp">Docs</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=bug_report.md">Report Bug</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=feature_request.md">Request Feature</a>
</p>

---

## Why Prometheus MCP Server?

**The problem:** Prometheus is the backbone of cloud-native observability, but using it effectively requires deep expertise. Writing correct PromQL (especially counter semantics), deploying the right exporter for each third-party system, wiring up ServiceMonitors, managing TSDB cardinality, and configuring remote-write — each of these is a mini-specialization. If you want an AI assistant to help, it typically hallucinates metric names, ignores counter rules, or generates unsafe unbounded queries.

**The solution:** The Prometheus MCP Server gives AI assistants (like Claude, Cline, or Cursor) structured, safe tools to operate Prometheus natively. Instead of guessing at PromQL or writing YAML from memory, your AI can now confidently manage the entire Prometheus lifecycle:

1. **Zero-to-One Application Onboarding:** The AI recommends the right instrumentation strategy (direct library, exporter, or builtin metrics), generates ready-to-paste code snippets for Go/Java/Python/Node.js, validates the `/metrics` endpoint, and wires up a ServiceMonitor — all in one guided workflow.
2. **Safe PromQL Execution:** Counter enforcement (counters must use `rate()`/`increase()`), automatic range-query downsampling to ~200 points per series (protecting LLM context windows), and query validation before execution.
3. **Exporter Lifecycle Management:** A built-in catalog of 19 exporters with one-command Kubernetes deployment — including RBAC, ConfigMaps, DaemonSets, and multi-manifest orchestration.
4. **TSDB FinOps & Cardinality Control:** Analyze top cardinality metrics, generate relabel configs to drop/keep labels, create recording rules, and configure remote-write to Thanos/Mimir/Cortex — all as ready-to-paste YAML.
5. **Multi-Backend Support:** Manage multiple Prometheus-compatible backends (Prometheus, Thanos, Mimir, Cortex, VictoriaMetrics) with explicit `backend_id` on every call — no hidden defaults.

---

## Key Features

**Backend Discovery & Multi-Backend**
- Discover and inspect multiple Prometheus-compatible backends
- Health checks, build info, feature flags, and runtime configuration
- Supports Prometheus, Thanos, Mimir, Cortex, and VictoriaMetrics

**PromQL Query Engine**
- Validate PromQL syntax before execution
- Instant and range queries with counter enforcement
- Automatic downsampling for range queries (100–200 points/series)
- Label topology exploration for understanding metric dimensionality

**Application Onboarding**
- Recommend instrumentation strategy (direct, exporter, or builtin)
- Generate code snippets for Go, Java, Python, Node.js
- Validate `/metrics` endpoints for Prometheus/OpenMetrics format
- Guided workflows for Kubernetes and VM/legacy environments

**Exporter Lifecycle**
- 19-exporter catalog with deploy-ready configurations
- One-command Kubernetes install (Deployment/DaemonSet + Service + RBAC)
- End-to-end verification with polling (endpoint + `up{}` series check)

**Scrape Configuration**
- Apply ServiceMonitor CRDs with auto-detected operator selector labels
- Manage file_sd_configs for VM/legacy targets
- Trigger Prometheus reload after config changes

**TSDB FinOps & Optimization**
- Cardinality analysis with top-N hotspot detection
- Generate metric_relabel_configs for label dropping/keeping
- Create recording rules for pre-computing expensive queries
- Configure remote-write to long-term storage backends

**Governance & Security**
- Scoped access policies per backend (whitelist/blacklist/read-only)
- In-memory audit log with filtering by backend, action, and time

**Production-Ready Middleware**
- Response limiting (100KB max), rate limiting (10 req/s, burst 20)
- Response caching, structured logging, error handling, timing

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
      ┌────────────┬───────────┼───────────┬────────────┐
      │            │           │           │            │
 ┌────▼────┐ ┌────▼────┐ ┌────▼────┐ ┌────▼────┐ ┌────▼────┐
 │  Tools  │ │Resources│ │ Prompts │ │  Utils  │ │ Models  │
 │ (9)     │ │ (12)    │ │ (5)     │ │         │ │         │
 └────┬────┘ └────┬────┘ └─────────┘ └─────────┘ └─────────┘
      │            │
      └──────┬─────┘
             │
  ┌──────────▼──────────┐
  │    Service Layer     │
  │                      │
  │ prometheus_service   │
  │ kubernetes_service   │
  └──────────┬──────────┘
             │
  ┌──────────▼──────────┐
  │ Prometheus HTTP API  │
  │ + Python K8s Client  │
  └─────────────────────┘
```

**How it works:**

1. An AI assistant connects via HTTP, SSE, or stdio.
2. The AI loads `prom://system/backends` resource to discover available backends.
3. Every subsequent tool call requires an explicit `backend_id` — no hidden state.
4. Service layers interact with Prometheus HTTP API and Kubernetes API.
5. Middleware enforces rate limiting, response size caps, and caching.

---

## Table of Contents

- [Why Prometheus MCP Server?](#why-prometheus-mcp-server)
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
| **Prometheus** | HTTP API v1 · PromQL · ServiceMonitor CRDs |
| **Kubernetes** | Python K8s Client · RBAC · CRDs |
| **Transport** | HTTP · SSE · Streamable-HTTP · stdio |
| **Infrastructure** | Docker · [uv](https://github.com/astral-sh/uv) |

---

## Getting Started

### Prerequisites

- **Docker** (recommended) or **Python 3.12+** (for local dev)
- **Access to a Prometheus-compatible backend** (Prometheus, Thanos, Mimir, Cortex, or VictoriaMetrics)
- **Kubernetes cluster** (optional — required for exporter deployment and ServiceMonitor features)

### Quick Start with Docker (recommended)

```bash
docker run --rm -it \
  -p 8767:8767 \
  -e PROMETHEUS_BASE_URL=http://host.docker.internal:9090 \
  -e MCP_TRANSPORT=http \
  talkopsai/prometheus-mcp-server:latest
```

The server is now listening on `http://localhost:8767/mcp`.

Point your MCP client at it:

```json
{
  "mcpServers": {
    "prometheus": {
      "url": "http://localhost:8767/mcp",
      "description": "MCP Server for Prometheus observability and monitoring management"
    }
  }
}
```

### From Source (Python)

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) for dependency management.

2. Clone and set up:

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/prometheus-mcp-server
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

3. Configure your `.env`:

```bash
PROMETHEUS_BASE_URL=http://localhost:9090
MCP_TRANSPORT=http
MCP_LOG_LEVEL=INFO
```

4. Run the server:

```bash
uv run prometheus-mcp-server
```

Or, with the venv activated: `prometheus-mcp-server`.

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
| `MCP_SERVER_NAME` | `prometheus-mcp-server` | Server name identifier |
| `MCP_SERVER_VERSION` | `0.1.0` | Server version string |
| `MCP_TRANSPORT` | `stdio` | Transport mode: `http`, `sse`, `streamable-http`, or `stdio` |
| `MCP_HOST` | `0.0.0.0` | Host address for HTTP server |
| `MCP_PORT` | `8767` | Port for HTTP server |
| `MCP_PATH` | `/mcp` | MCP endpoint path |
| `MCP_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `MCP_LOG_FORMAT` | `json` | Log format: `json` or `text` |
| `MCP_HTTP_TIMEOUT` | `300` | HTTP server timeout (seconds) |
| `MCP_HTTP_KEEPALIVE_TIMEOUT` | `5` | HTTP keepalive timeout (seconds) |
| `MCP_HTTP_CONNECT_TIMEOUT` | `60` | HTTP connect timeout (seconds) |

### Prometheus Backend (Single)

| Variable | Default | Description |
|----------|---------|-------------|
| `PROMETHEUS_BASE_URL` | `http://localhost:9090` | Prometheus HTTP API base URL |
| `PROMETHEUS_BACKEND_ID` | `default` | Backend identifier used in all tool calls |
| `PROMETHEUS_TYPE` | `prometheus` | Backend type: `prometheus`, `thanos`, `mimir`, `cortex`, `victoriametrics`, `other` |
| `PROMETHEUS_DISPLAY_NAME` | *(empty)* | Human-readable backend name |
| `PROMETHEUS_AUTH_HEADER` | *(empty)* | Authorization header value (e.g. `Bearer <token>`) |
| `PROMETHEUS_VERIFY_SSL` | `true` | Verify SSL certificates |
| `PROMETHEUS_TIMEOUT` | `30` | HTTP timeout for Prometheus API calls (seconds) |

### Prometheus Backends (Multi)

For multiple backends, set `PROMETHEUS_BACKENDS` as a JSON array:

```bash
PROMETHEUS_BACKENDS='[
  {"id": "prod", "base_url": "https://prom-prod.example.com", "type": "prometheus", "labels": {"env": "prod"}},
  {"id": "staging", "base_url": "https://thanos-staging.example.com", "type": "thanos", "labels": {"env": "staging"}}
]'
```

### Kubernetes

| Variable | Default | Description |
|----------|---------|-------------|
| `K8S_CONTEXT` | *(empty)* | Specific K8s context to use |
| `K8S_IN_CLUSTER` | `false` | Set `true` when running inside a pod |
| `K8S_ENABLED` | `true` | Enable Kubernetes integration |

---

## Available Tools

### PromQL Query Engine
| Tool | Description |
|------|-------------|
| `prom_validate_promql` | Check PromQL syntax before executing. |
| `prom_query_instant` | Execute a point-in-time PromQL query with counter enforcement. |
| `prom_query_range` | Execute a time-range PromQL query with automatic downsampling. |
| `prom_query_a2ui_chart` | Execute a time-range PromQL query and return data formatted for A2UI dynamic components. |
| `prom_explore_labels` | Discover label names and top values for a given metric. |
| `prom_suggest_promql` | Generate a PromQL expression from natural language intent. |

### Application Onboarding
| Tool | Description |
|------|-------------|
| `prom_recommend_instrumentation` | Recommend direct instrumentation vs exporter vs builtin_metrics. |
| `prom_test_endpoint` | Validate that an endpoint exposes valid Prometheus/OpenMetrics metrics. |
| `prom_apply_servicemonitor` | Generate and apply a ServiceMonitor CRD for Prometheus Operator. |
| `prom_apply_probe` | Generate and apply a Probe CRD for Prometheus Operator. |
| `prom_manage_file_sd` | Add or remove static targets in a file_sd_configs JSON file. |

### Exporter Lifecycle
| Tool | Description |
|------|-------------|
| `prom_recommend_exporter` | Get exporter recommendations for a specific service type. |
| `prom_install_exporter` | Deploy an exporter to Kubernetes (creates Deployment/DaemonSet + Service). |
| `prom_uninstall_exporter` | Remove an exporter from Kubernetes. |
| `prom_verify_exporter` | End-to-end health check: scrape endpoint and check Prometheus up{} series. |

### TSDB FinOps & Optimization
| Tool | Description |
|------|-------------|
| `prom_optimize_cardinality` | Analyze top-N cardinality metrics and recommend optimization strategies. |
| `prom_plan_relabel` | Generate metric_relabel_configs YAML to drop/keep labels. |
| `prom_create_recording_rule` | Generate recording rule group YAML. |
| `prom_configure_remote_write` | Generate remote_write config YAML for long-term storage. |

### Rule Management & Authoring
| Tool | Description |
|------|-------------|
| `prom_get_rule_group` | Get a single rule group by name with full rule details. |
| `prom_upsert_rule_group` | Create or update a rule group (YAML, CRD, or HTTP Ruler). |
| `prom_delete_rule_group` | Delete a rule group. |
| `prom_describe_alert_rule` | Provide a human-readable explanation of an alerting rule. |
| `prom_draft_alert_rule` | Generate an alert rule from natural language intent. |
| `prom_tune_alert_rule` | Suggest rule adjustments based on firing history. |

### Rule Simulation & Testing
| Tool | Description |
|------|-------------|
| `prom_check_rule_group` | Validate rule group syntax via promtool check rules. |
| `prom_run_rule_tests` | Run promtool test rules with synthetic test scenarios. |
| `prom_simulate_firing_synthetic` | Run synthetic alert firing test via promtool. |
| `prom_simulate_firing_historical` | Evaluate alert expression against real historical data. |
| `prom_analyze_firing_history` | Analyze alert firing frequency and duration for tuning. |

---

## Available Resources

| Resource URI | Description |
|--------------|-------------|
| `prom://system/backends` | All known backends with health status — use this as the **first step** in any workflow |
| `prom://system/backends/{backend_id}` | Detailed capabilities, runtime info, and health for one backend |
| `prom://config/runtime` | Sanitized runtime configuration: global settings, remote-write targets, TSDB stats |
| `prom://topology/services` | Logical service catalog derived from scrape targets with health status |
| `prom://topology/failed_targets` | Aggregated view of failed/down scrape targets for quick triage |
| `prom://topology/services/{job}/metrics` | All metrics emitted by a specific service/job, with type and HELP text |
| `prom://metadata/catalog` | Metric names with type and HELP text — prevents metric name hallucination |
| `prom://schema/label_values` | Per-metric label values snapshot for understanding metric dimensionality |
| `prom://tsdb/cardinality` | TSDB cardinality overview and top-N high-cardinality metrics |
| `prom://rules/groups` | Alerting and recording rule group inventory across all backends |
| `prom://kubernetes/prometheusrules` | All PrometheusRule CRDs with Kubernetes metadata (name, namespace, labels) required for safe `prom_upsert_rule_group` operations |
| `prom://exporters/catalog` | Built-in exporter catalog with types, ports, images, and supported environments |
| `prom://best-practices` | Prometheus best practices for monitoring, querying, and FinOps |
| `prom://onboarding-guide` | Step-by-step guide for onboarding applications to Prometheus |

---

## Available Prompts

Guided workflow prompts that orchestrate multiple tools into step-by-step journeys:

| Prompt Name | Description | Parameters |
|-------------|-------------|------------|
| `prom-k8s-app-onboarding-guided` | Guided workflow for instrumenting and onboarding a K8s application | `backend_id`, `language`, `namespace`, `service_name` |
| `prom-k8s-exporter-onboarding-guided` | Guided workflow for onboarding third-party systems via exporters | `backend_id`, `workload_type`, `namespace` |
| `prom-vm-legacy-onboarding-guided` | Guided workflow for VM/legacy (non-Kubernetes) environments | `backend_id`, `workload_type`, `language`, `target_host`, `target_port` |
| `prom-query-guided` | Guided workflow for safely querying Prometheus metrics | `backend_id`, `metric_name` |
| `prom-troubleshoot-guided` | Guided workflow for diagnosing failed scrape targets | `backend_id`, `job`, `namespace` |

---

## Usage

Supported workflows with prompt examples and links to detailed guides:

| Workflow | Prompt Example | Documentation |
|----------|----------------|---------------|
| **K8s App Onboarding** | `"Onboard my Python app 'api-server' in the 'production' namespace to Prometheus."` | [PROM_ONBOARDING_TEST_GUIDE.md](docs/PROM_ONBOARDING_TEST_GUIDE.md) |
| **Exporter Onboarding** | `"Deploy a postgres_exporter in the 'monitoring' namespace for our PostgreSQL database."` | [PROM_EXPORTER_TEST_GUIDE.md](docs/PROM_EXPORTER_TEST_GUIDE.md) |
| **VM/Legacy Onboarding** | `"Add my VM host 10.0.1.5:9100 to Prometheus file_sd targets."` | [PROM_ONBOARDING_TEST_GUIDE.md](docs/PROM_ONBOARDING_TEST_GUIDE.md) |
| **PromQL Querying** | `"Show me the request rate for http_requests_total over the last hour."` | [PROM_QUERY_TEST_GUIDE.md](docs/PROM_QUERY_TEST_GUIDE.md) |
| **TSDB FinOps** | `"Analyze cardinality hotspots and recommend optimization strategies."` | [PROM_FINOPS_TEST_GUIDE.md](docs/PROM_FINOPS_TEST_GUIDE.md) |
| **Rule Management** | `"Draft an alert for high error rates and simulate if it would have fired."` | [PROM_RULE_TEST_GUIDE.md](docs/PROM_RULE_TEST_GUIDE.md) |
| **K8s CRD Rule Upsert** | `"Find the exact CRD name for my alertmanager rules and safely patch them."` | [PROM_K8S_RULE_CRD_TEST_GUIDE.md](docs/PROM_K8S_RULE_CRD_TEST_GUIDE.md) |
| **Troubleshooting** | `"Why is my 'api-server' job showing as down in Prometheus?"` | [PROM_TROUBLESHOOTING_TEST_GUIDE.md](docs/PROM_TROUBLESHOOTING_TEST_GUIDE.md) |

See [WORKFLOW_JOURNEYS.md](docs/WORKFLOW_JOURNEYS.md) for the full workflow reference and [PROMPT_REFERENCE.md](docs/PROMPT_REFERENCE.md) for natural-language prompts.

---

## Project Structure

```text
prometheus-mcp-server/
├── prometheus_mcp_server/         # Main package
│   ├── tools/                     # MCP Tools (9 tool groups, 28 tools)
│   │   ├── discovery/             # Backend discovery
│   │   ├── query/                 # PromQL query engine
│   │   ├── onboarding/            # App instrumentation
│   │   ├── exporter/              # Exporter lifecycle
│   │   ├── scrape_config/         # ServiceMonitor & file_sd
│   │   ├── diagnostics/           # TSDB diagnostics
│   │   ├── tsdb_finops/           # FinOps optimization
│   │   ├── rules/                 # Rules management
│   │   ├── rule_testing/          # Promtool testing
│   │   └── simulators/            # Synthetic firing simulators
│   ├── resources/                 # MCP Resources (12 URIs)
│   │   ├── backend_resources.py   # Backend health & capabilities
│   │   ├── config_resources.py    # Runtime configuration
│   │   ├── topology_resources.py  # Services & failed targets
│   │   ├── metadata_resources.py  # Metric catalog
│   │   ├── tsdb_resources.py      # Cardinality overview
│   │   ├── rules_resources.py     # Rule group inventory
│   │   ├── kubernetes_resources.py # PrometheusRule CRD discovery
│   │   ├── exporter_resources.py  # Exporter catalog
│   │   └── static_resources.py    # Best practices & guides
│   ├── prompts/                   # MCP Prompts (5 guided workflows)
│   │   ├── onboarding_prompts.py  # K8s app, exporter, VM flows
│   │   ├── query_prompts.py       # Safe query workflow
│   │   └── troubleshooting_prompts.py
│   ├── services/                  # Business logic
│   │   ├── prometheus_service.py  # Prometheus HTTP API wrapper
│   │   └── kubernetes_service.py  # K8s API wrapper
│   ├── server/                    # FastMCP server setup
│   │   ├── core.py                # Server creation
│   │   ├── bootstrap.py           # Component initialization
│   │   └── middleware.py          # 7-layer middleware stack
│   ├── models/                    # Pydantic data models
│   ├── utils/                     # Helpers
│   │   ├── exporter_catalog.py    # 19-exporter registry logic
│   │   ├── snippet_generator.py   # Code snippet generation
│   │   ├── promql_helpers.py      # Counter detection & step calc
│   │   ├── endpoint_tester.py     # /metrics endpoint validator
│   │   └── json_coerce.py         # LLM input coercion
│   ├── static/                    # Static documentation
│   ├── exceptions/                # Custom exception hierarchy
│   ├── config.py                  # Environment parsing & exporter registry
│   └── main.py                    # Entry point
├── tests/                         # Test suites
├── docs/                          # Documentation
├── pyproject.toml                 # Package definitions (Python 3.12)
└── README.md                      # This documentation
```

---

## Roadmap

**Shipped:**

- [x] Multi-backend discovery with health checks and capabilities
- [x] PromQL query engine with counter enforcement and auto-downsampling
- [x] Application onboarding with code generation (Go, Java, Python, Node.js)
- [x] 19-exporter catalog with Kubernetes deployment automation
- [x] ServiceMonitor CRD management with auto-detected operator labels
- [x] file_sd_configs management for VM/legacy environments
- [x] TSDB cardinality analysis and FinOps optimization configs
- [x] Governance access policies and audit logging
- [x] 5 guided workflow prompts for onboarding, querying, and troubleshooting
- [x] 7-layer middleware stack (rate limiting, response limiting, caching)

**Coming next:**

- [ ] AlertManager integration for alert rule management
- [ ] Grafana dashboard generation from queries
- [ ] Recording rule lifecycle management (apply, not just generate)
- [x] PrometheusRule CRD discovery (`prom://kubernetes/prometheusrules`) for autonomous rule upsert workflows

See [open issues](https://github.com/talkops-ai/talkops-mcp/issues) for the full list of proposed features.

---

## Contributing

Contributions are welcome. The process is straightforward:

1. Fork the repo
2. Create a branch (`git checkout -b feature/CardinalityAlerts`)
3. Make your changes and commit
4. Push and open a PR

If you're considering something bigger, open an issue first so we can align on the approach.

---

## FAQ

<details>
<summary><b>Which MCP clients work with this?</b></summary>
Any MCP-compatible client including Claude Desktop, Cline, Cursor, and custom clients. Connect via <code>http://localhost:8767/mcp</code> for HTTP transport, or configure stdio for direct process communication.
</details>

<details>
<summary><b>Which Prometheus-compatible backends are supported?</b></summary>
Prometheus, Thanos, Mimir, Cortex, and VictoriaMetrics. Set the backend <code>type</code> in your configuration to enable backend-specific feature detection.
</details>

<details>
<summary><b>Does this modify my Prometheus configuration?</b></summary>
Most tools are read-only. The exceptions are: <code>prom_install_exporter</code>/<code>prom_uninstall_exporter</code> (create/delete K8s resources), <code>prom_apply_servicemonitor</code>/<code>prom_manage_file_sd</code> (creates ServiceMonitor CRDs or writes file_sd JSON), and <code>prom_upsert_rule_group</code>/<code>prom_delete_rule_group</code> (modifies alert rules). TSDB FinOps tools generate YAML only — they do NOT apply changes.
</details>

<details>
<summary><b>Why does the server enforce counter rules?</b></summary>
Raw counter values are almost always meaningless — the absolute number has no operational significance. The server blocks raw counter queries by default and requires <code>rate()</code> or <code>increase()</code> wrappers. Set <code>allow_raw_counters=true</code> to override when needed.
</details>

---

## Troubleshooting

### Backend Connection Issues

1. Verify `PROMETHEUS_BASE_URL` points to a reachable Prometheus instance.
2. Load the `prom://system/backends` resource to check health status.
3. If using auth, verify `PROMETHEUS_AUTH_HEADER` is set correctly.
4. For SSL issues, try `PROMETHEUS_VERIFY_SSL=false` (development only).

### Kubernetes Integration Issues

1. Ensure `K8S_ENABLED=true` and your kubeconfig is accessible.
2. For in-cluster deployment, set `K8S_IN_CLUSTER=true`.
3. ServiceMonitor creation requires Prometheus Operator installed in the cluster.

### Query Timeout or Large Results

1. The server auto-downsamples range queries to ~200 points per series.
2. Increase `MCP_HTTP_TIMEOUT` for slow backends.
3. Response limiting middleware caps payloads at 100KB — use more specific queries.

---

## Security Considerations

- **Never expose the MCP server to the public internet** without proper authentication.
- **Exporter deployments create real Kubernetes resources** — review manifests before using `prom_install_exporter`.
- **file_sd operations write to the local filesystem** — ensure proper file permissions.

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
- [Prometheus](https://prometheus.io/) for the foundational monitoring ecosystem.
- [Kubernetes](https://kubernetes.io/) for container orchestration APIs.
