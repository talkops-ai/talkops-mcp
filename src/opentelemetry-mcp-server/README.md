<p align="center">
  <img src="https://raw.githubusercontent.com/cncf/artwork/main/projects/opentelemetry/stacked/color/opentelemetry-stacked-color.svg" alt="OpenTelemetry MCP Server" width="140" onError="this.style.display='none'"/>
</p>

<h1 align="center">OpenTelemetry MCP Server</h1>

<p align="center">
  An MCP server that gives AI assistants the power to discover, provision, instrument, validate, and govern OpenTelemetry pipelines on Kubernetes — from intent-driven collector provisioning to cardinality control, sampling optimization, and security auditing.
</p>

<p align="center">
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://opentelemetry.io/"><img src="https://img.shields.io/badge/OpenTelemetry-Compatible-4B5EFF.svg?style=flat-square&logo=opentelemetry&logoColor=white" alt="OpenTelemetry"/></a>
  <a href="https://discord.gg/tSN2Qn9uM8"><img src="https://img.shields.io/badge/Discord-Join%20Us-5865F2.svg?style=flat-square&logo=discord&logoColor=white" alt="Discord"/></a>
</p>

<p align="center">
  <a href="#getting-started">Quick Start</a> · <a href="https://github.com/talkops-ai/talkops-mcp">Docs</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=bug_report.md">Report Bug</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=feature_request.md">Request Feature</a>
</p>

---

## Why OpenTelemetry MCP Server?

**The problem:** OpenTelemetry is the industry standard for observability, but operating it on Kubernetes is complex. Setting up auto-instrumentation across languages, configuring collector pipelines with the correct processor ordering, tuning sampling strategies, and managing cardinality from SpanMetrics connectors — each is a specialized task. When AI assistants try to help, they hallucinate CRD schemas, mis-order processors, or generate unsafe configs that cause data loss.

**The solution:** The OpenTelemetry MCP Server gives AI assistants (like Claude, Cline, or Cursor) structured, safe tools to manage the entire OTel lifecycle natively:

1. **Intent-Driven Collector Provisioning:** Say *"I want traces and metrics in my namespace"* and the AI auto-discovers backends (Jaeger, Tempo, Prometheus, Loki, OpenSearch), generates best-practice configs with correct processor ordering, selects the right deployment mode, sizes resources for your cluster — and deploys with dry-run-first safety.
2. **Zero-to-Instrumented Onboarding:** The AI looks up language support, creates an Instrumentation CRD, annotates Deployments for auto-instrumentation injection, and verifies the rollout — all with dry-run-first safety.
2. **Pipeline Investigation & Validation:** Deep-inspect any OTel Collector's config, validate processor ordering against best practices, audit filelog receiver safety, and check k8sattributes enrichment profiles.
3. **Metric Cardinality Governance:** Detect high-cardinality dimensions from SpanMetrics connectors, generate transform processor YAML to drop attributes, and estimate series counts before they explode.
4. **Sampling Strategy Optimization:** Cross-reference head sampling (Instrumentation CRDs) with tail sampling (collector config), detect conflicts, and generate config patches to switch strategies.
5. **Security Posture Auditing:** Scan eBPF instrumentation pods for privileged mode, SYS_ADMIN capabilities, and hostPID access. Risk-assess the entire observability footprint.

---

## Key Features

**Intent-Driven Collector Provisioning**
- Express what you want (signals, namespace) — the tool auto-discovers everything else
- Three-strategy backend discovery: existing collector configs → K8s service name matching → graceful debug fallback
- 10 built-in backend patterns: Jaeger, Tempo, Zipkin, Prometheus, Thanos, Mimir, VictoriaMetrics, OpenSearch, Elasticsearch, Loki
- Best-practice processor chain always enforced: `memory_limiter → k8sattributes → resourcedetection → resource → batch`
- Smart mode selection: DaemonSet for filelog, StatefulSet for Prometheus scraping, Deployment for OTLP
- Auto-sizing from cluster scale (node count → small/medium/large resource tiers)
- Filelog safety built-in: self-exclusion patterns, namespace scoping, checkpoint storage, `start_at=end`
- SpanMetrics connector wiring with correct traces→connector→metrics pipeline topology
- Proactive recommendations ("Consider spanmetrics for RED metrics", "Filelog needs DaemonSet")

**Collector Discovery & Inspection**
- List and inspect OpenTelemetryCollector CRDs across namespaces with pagination
- Full pipeline topology: receivers, processors, exporters, and connectors
- Summary and full (raw YAML) detail levels

**Service Instrumentation**
- Language support matrix with framework-specific guidance (Java, Python, Node.js, .NET, Go, Rust)
- Create or patch Instrumentation CRDs with sampler, propagators, and per-language images
- Annotate Deployments for auto-instrumentation with dry-run-first safety
- List instrumented services with annotation status, init container injection, signal detection, and **4-tier language detection** (annotations → image patterns → container/deployment names → runtime env vars)

**Pipeline Validation**
- Processor ordering validation (memory_limiter → k8sattributes → batch)
- Filelog receiver safety checks (checkpoint storage, self-collection loops, resource detection)
- Target Allocator state inspection (allocation strategy, selectors, prometheusCR)
- Collector topology recommendations based on signals, workload count, and cluster size

**Metric Cardinality Governance**
- SpanMetrics dimension analysis with series count estimation
- Histogram bucket count auditing
- Transform processor YAML generation for dropping attributes
- Existing remediation detection (transform processors already in config)

**Sampling Management**
- Holistic sampling view: head (Instrumentation CRD) + tail (collector config)
- Conflict detection (head + tail simultaneously)
- Config patch generation for switching between head, tail, or none
- Tail sampling policy templates (error-sampling, slow-traces, probabilistic-fallback)

**SpanMetrics Connector**
- Inspect existing SpanMetrics configuration (dimensions, histograms, pipeline wiring)
- Generate SpanMetrics enablement YAML with custom dimensions and bucket boundaries
- Cardinality warnings for high-dimension configurations

**Security Auditing**
- eBPF agent discovery (OpenTelemetry eBPF, Grafana Beyla)
- Security context analysis: privileged mode, hostPID, capabilities, host volume mounts
- Risk assessment with prioritized remediation recommendations

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
 │ (19)    │ │ (9)     │ │ (5)     │ │         │ │         │
 └────┬────┘ └────┬────┘ └─────────┘ └─────────┘ └─────────┘
      │            │
      └──────┬─────┘
             │
  ┌──────────▼──────────┐
  │    Service Layer     │
  │                      │
  │ kubernetes_service   │
  │ collector_config_svc │
  │ config_builder       │
  └──────────┬──────────┘
             │
  ┌──────────▼──────────┐
  │ Python K8s Client   │
  │ + OTel Operator CRDs│
  └─────────────────────┘
```

**How it works:**

1. An AI assistant connects via HTTP, SSE, or stdio.
2. The AI loads `otel://system/health` resource to check Kubernetes connectivity and CRD availability.
3. Tools interact with the Kubernetes API to read/write OpenTelemetryCollector and Instrumentation CRDs.
4. Service layers (`kubernetes_service`, `collector_config_service`) handle API calls and config parsing.
5. Middleware enforces rate limiting, response size caps, caching, and structured logging.

---

## Table of Contents

- [Why OpenTelemetry MCP Server?](#why-opentelemetry-mcp-server)
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
| **OpenTelemetry** | Operator CRDs · Instrumentation CRDs · Collector config |
| **Kubernetes** | Python K8s Client · Custom Resources · RBAC |
| **Transport** | HTTP · SSE · Streamable-HTTP · stdio |
| **Infrastructure** | Docker · [uv](https://github.com/astral-sh/uv) |

---

## Getting Started

### Prerequisites

- **Docker** (recommended) or **Python 3.12+** (for local dev)
- **Kubernetes cluster** with the [OpenTelemetry Operator](https://github.com/open-telemetry/opentelemetry-operator) installed
- **kubectl** configured with access to the target cluster

> **RBAC Note for Collector Provisioning (`otel_provision_collector`)**
>
> When provisioning collectors with `dry_run=False`, the tool automatically creates `ClusterRole` and `ClusterRoleBinding` resources for the `k8sattributes` processor. This is necessary because:
>
> - The `k8sattributes` processor enriches telemetry with Kubernetes metadata (pod name, namespace, node, etc.)
> - It needs `get`, `list`, `watch` permissions on Pods, ReplicaSets, Namespaces, Nodes, and Jobs
> - **The OTel Operator does NOT auto-create these RBAC resources** — without them, the collector will log `pods is forbidden` errors
>
> **Prerequisites for the MCP server's own ServiceAccount:**
> - The ServiceAccount running the MCP server needs permissions to `create`, `patch`, `get` on `ClusterRole` and `ClusterRoleBinding` resources
> - For local development (kubeconfig), your kubectl user typically already has cluster-admin
> - For in-cluster deployment, add these rules to the MCP server's ServiceAccount:
>
> ```yaml
> apiVersion: rbac.authorization.k8s.io/v1
> kind: ClusterRole
> metadata:
>   name: otel-mcp-server-rbac-manager
> rules:
>   - apiGroups: ["rbac.authorization.k8s.io"]
>     resources: ["clusterroles", "clusterrolebindings"]
>     verbs: ["get", "create", "patch"]
> ```
>
> See [SUPPORTED_BACKENDS.md](docs/SUPPORTED_BACKENDS.md) for the full list of auto-discoverable backends and default ports.

### Quick Start with Docker (recommended)

```bash
docker run --rm -it \
  -p 8771:8771 \
  -e MCP_TRANSPORT=http \
  -e K8S_IN_CLUSTER=true \
  talkopsai/opentelemetry-mcp-server:latest
```

The server is now listening on `http://localhost:8771/mcp`.

Point your MCP client at it:

```json
{
  "mcpServers": {
    "opentelemetry": {
      "url": "http://localhost:8771/mcp",
      "description": "MCP Server for OpenTelemetry Kubernetes observability"
    }
  }
}
```

### From Source (Python)

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) for dependency management.

2. Clone and set up:

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/opentelemetry-mcp-server
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

3. Configure your `.env`:

```bash
MCP_TRANSPORT=http
K8S_ENABLED=true
MCP_LOG_LEVEL=INFO
```

4. Run the server:

```bash
uv run opentelemetry-mcp-server
```

Or, with the venv activated: `opentelemetry-mcp-server`.

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
| `MCP_SERVER_NAME` | `opentelemetry-mcp-server` | Server name identifier |
| `MCP_SERVER_VERSION` | `0.1.0` | Server version string |
| `MCP_TRANSPORT` | `stdio` | Transport mode: `http`, `sse`, `streamable-http`, or `stdio` |
| `MCP_HOST` | `0.0.0.0` | Host address for HTTP server |
| `MCP_PORT` | `8771` | Port for HTTP server |
| `MCP_PATH` | `/mcp` | MCP endpoint path |
| `MCP_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `MCP_LOG_FORMAT` | `json` | Log format: `json` or `text` |
| `MCP_HTTP_TIMEOUT` | `300` | HTTP server timeout (seconds) |
| `MCP_HTTP_KEEPALIVE_TIMEOUT` | `5` | HTTP keepalive timeout (seconds) |
| `MCP_HTTP_CONNECT_TIMEOUT` | `60` | HTTP connect timeout (seconds) |

### Kubernetes

| Variable | Default | Description |
|----------|---------|-------------|
| `K8S_IN_CLUSTER` | `false` | Set `true` if running inside a pod |
| `K8S_ENABLED` | `true` | Enable/disable K8s features entirely |

### OTel Operator CRD

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_CRD_GROUP` | `opentelemetry.io` | API group for OTel CRDs |
| `OTEL_CRD_API_VERSION` | `v1beta1` | API version for **Collector** CRDs (`OpenTelemetryCollector`) |
| `OTEL_INSTRUMENTATION_API_VERSION` | `v1alpha1` | API version for **Instrumentation** CRDs (separate because Instrumentation CRDs are promoted at a different rate than Collector CRDs) |
| `OTEL_COLLECTOR_PLURAL` | `opentelemetrycollectors` | Plural name for Collector CRD |
| `OTEL_INSTRUMENTATION_PLURAL` | `instrumentations` | Plural name for Instrumentation CRD |

### Target Allocator

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_TA_SERVICE_DISCOVERY` | `true` | Enable Target Allocator service discovery |
| `OTEL_TA_DEFAULT_PORT` | `8080` | Default Target Allocator port |

### Prometheus Integration

| Variable | Default | Description |
|----------|---------|-------------|
| `PROMETHEUS_BASE_URL` | *(empty)* | Prometheus HTTP API base URL (for cardinality queries) |
| `PROMETHEUS_TIMEOUT` | `30` | HTTP timeout for Prometheus API calls (seconds) |
| `PROMETHEUS_VERIFY_SSL` | `true` | Verify SSL certificates |

### Language Registry

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_LANG_REGISTRY_PATH` | *(builtin)* | Override path to custom language registry JSON |

---

## Available Tools

### Discovery
| Tool | Description |
|------|-------------|
| `otel_list_collectors` | List OpenTelemetryCollector CRDs with namespace filtering, label selectors, and pagination. |
| `otel_query_a2ui` | Retrieve the status of all OpenTelemetry Collectors and their pipelines, formatted precisely for A2UI Status Datatables. Includes deep pipeline metrics health checking via internal `:8888/metrics` endpoints. |
| `otel_get_collector` | Get detailed information about a specific collector (pipelines, status, raw YAML config). |
| `otel_list_instrumented_services` | List workloads in a namespace with their auto-instrumentation status, annotations, init containers, OTEL_* env vars, and detected language (4-tier: annotations → image patterns → container names → runtime env vars like `JAVA_HOME`, `PYTHONPATH`). |

### Collector Management
| Tool | Description |
|------|-------------|
| `otel_provision_collector` | **Smart, intent-driven** collector provisioning. Accepts `namespace` + `signals` (e.g., `["traces", "metrics"]`), auto-discovers backend endpoints from existing collectors and K8s services, generates best-practice configs with correct processor ordering, selects deployment mode, and sizes resources from cluster scale. **Automatically creates RBAC (ClusterRole + ClusterRoleBinding) for the k8sattributes processor.** Supports `enable_spanmetrics`, `enable_filelog`, `prometheus_scrape`, and `dry_run` modes. See [Supported Backends](docs/SUPPORTED_BACKENDS.md) for auto-discoverable backends. |
| `otel_patch_collector` | **Expert-level** CRD management. Create or replace an OpenTelemetryCollector CRD with full config YAML, dynamic labels, annotations, and spec. Supports `overwrite` (full replace with resourceVersion) and `dry_run` modes. |

### Instrumentation
| Tool | Description |
|------|-------------|
| `otel_lookup_instrumentation` | Map a language and optional framework to OTel instrumentation support (auto-instrumentation availability, annotation key, SDK package). |
| `otel_patch_instrumentation` | Create or patch an Instrumentation CRD with exporter endpoint, propagators, sampler, and per-language images. Supports `dry_run`. |
| `otel_annotate_deployment` | Apply auto-instrumentation annotation to a Deployment's pod template. **Detects conflicting hardcoded `OTEL_*` env vars** (e.g., `OTEL_EXPORTER_OTLP_ENDPOINT`) that would silently override Operator-injected endpoints, and warns with remediation steps. Supports `dry_run`. Triggers rolling restart when applied. |

### Validation
| Tool | Description |
|------|-------------|
| `otel_validate_k8sattributes_order` | Validate processor ordering in collector pipelines against recommended order (memory_limiter → k8sattributes → resourcedetection → transform → filter → tail_sampling → batch). |
| `otel_check_filelog_safety` | Check filelog receiver for safety issues: missing checkpoint storage, self-collection feedback loops, and missing resource detection. |
| `otel_inspect_target_allocator_state` | Inspect Target Allocator configuration: allocation strategy, ServiceMonitor/PodMonitor selectors, prometheusCR enablement, replicas. |
| `otel_recommend_collector_topology` | Recommend collector deployment mode (DaemonSet/Deployment/Gateway), pipeline topology, and resource sizing based on signals, workload count, and cluster size. |

### Governance
| Tool | Description |
|------|-------------|
| `otel_detect_cardinality` | Detect metric cardinality issues from SpanMetrics dimensions and histogram buckets. Returns estimated series counts and severity ratings. |
| `otel_gen_drop_attribute_rules` | Generate transform processor YAML snippet to drop high-cardinality attributes for metrics, traces, or logs signals. |
| `otel_analyze_ebpf_footprint` | Scan eBPF instrumentation pods for security posture: privileged mode, hostPID, Linux capabilities, and host volume mounts. |

### Sampling
| Tool | Description |
|------|-------------|
| `otel_inspect_sampling_configuration` | Inspect complete sampling config: cross-references head sampling (Instrumentation CRD) with tail sampling (collector config). Detects conflicts. |
| `otel_toggle_sampling_strategy` | Generate config patches to switch between head, tail, or no sampling. Includes tail sampling policy templates. Supports `dry_run`. |

### SpanMetrics
| Tool | Description |
|------|-------------|
| `otel_inspect_spanmetrics_config` | Inspect SpanMetrics connector configuration: dimensions, histogram config, pipeline wiring, and cardinality estimates. |
| `otel_enable_spanmetrics_for_service` | Generate SpanMetrics connector YAML with custom dimensions, histogram buckets, and pipeline wiring instructions. Supports `dry_run`. |

---

## Available Resources

| Resource URI | Description |
|--------------|-------------|
| `otel://system/health` | Server health status: Kubernetes connectivity, OTel CRD availability, and server version |
| `otel://collector/{namespace}/{name}` | Full collector config: pipeline topology, receivers, processors, exporters, deployment mode, and status |
| `otel://k8s-enrichment/{namespace}/{collector}` | k8sattributes processor profile: extracted metadata, labels, annotations, pod association, and pipeline positions |
| `otel://logs-profile/{namespace}/{collector}` | Filelog receiver config: include/exclude paths, operators, safety analysis, and pipeline wiring |
| `otel://spanmetrics/{namespace}/{collector}` | SpanMetrics connector profile: dimensions, histogram config, pipeline wiring, and cardinality estimates |
| `otel://instrumentation/{namespace}/{name}` | Instrumentation CRD details: exporter endpoint, propagators, sampler, per-language specs, and resource attributes |
| `otel://target-allocator/{namespace}/{name}` | Target Allocator state: allocation strategy, ServiceMonitor/PodMonitor selectors, replicas, and prometheusCR status |
| `otel://lang/{language}` | Per-language instrumentation capabilities: signal support, auto-instrumentation availability, framework support, SDK package |
| `otel://registry/languages` | Full catalog of all supported languages with signal stability, auto-instrumentation, and framework support matrices |

---

## Available Prompts

Guided workflow prompts that orchestrate multiple tools into step-by-step journeys:

| Prompt Name | Description | Parameters |
|-------------|-------------|------------|
| `otel_onboard_service` | Guided workflow for onboarding a new service to OpenTelemetry: language detection, Instrumentation CR setup, annotation application, and verification | `service_name`, `namespace`, `language` |
| `otel_investigate_pipeline` | Guided workflow for investigating an OTel pipeline: processor ordering, filelog safety, sampling config, and enrichment profile | `collector_name`, `namespace` |
| `otel_cardinality_audit` | Guided workflow for auditing metric cardinality: detect high-cardinality dimensions and generate transform processor remediation YAML | `collector_name`, `namespace` |
| `otel_sampling_review` | Guided workflow for reviewing and optimizing sampling strategy across Instrumentation CRDs and collector config | `collector_name`, `namespace` |
| `otel_security_audit` | Guided workflow for auditing OTel security posture: eBPF privileges, init containers, RBAC, and sensitive attribute exposure | `namespace` |

---

## Usage

Supported workflows with prompt examples and links to detailed guides:

| Workflow | Prompt Example | Documentation |
|----------|----------------|---------------|
| **Service Onboarding** | `"Onboard my Python app 'api-server' in the 'production' namespace to OpenTelemetry."` | [OTEL_ONBOARDING_TEST_GUIDE.md](docs/OTEL_ONBOARDING_TEST_GUIDE.md) |
| **Pipeline Investigation** | `"Investigate the OTel collector 'otel-gateway' in the 'monitoring' namespace."` | [OTEL_PIPELINE_INVESTIGATION_TEST_GUIDE.md](docs/OTEL_PIPELINE_INVESTIGATION_TEST_GUIDE.md) |
| **Cardinality Audit** | `"Audit metric cardinality for collector 'otel-metrics' in 'monitoring'."` | [OTEL_CARDINALITY_AUDIT_TEST_GUIDE.md](docs/OTEL_CARDINALITY_AUDIT_TEST_GUIDE.md) |
| **Sampling Review** | `"Review sampling for collector 'otel-traces' in 'monitoring'."` | [OTEL_SAMPLING_TEST_GUIDE.md](docs/OTEL_SAMPLING_TEST_GUIDE.md) |
| **Security Audit** | `"Audit OTel security posture in the 'production' namespace."` | [OTEL_SECURITY_AUDIT_TEST_GUIDE.md](docs/OTEL_SECURITY_AUDIT_TEST_GUIDE.md) |

See [WORKFLOW_JOURNEYS.md](docs/WORKFLOW_JOURNEYS.md) for the full workflow reference and [PROMPT_REFERENCE.md](docs/PROMPT_REFERENCE.md) for natural-language prompts.

---

## Project Structure

```text
opentelemetry-mcp-server/
├── opentelemetry_mcp_server/      # Main package
│   ├── tools/                     # MCP Tools (7 tool groups, 19 tools)
│   │   ├── discovery/             # Collector & service discovery
│   │   ├── collector/             # Collector CRD management
│   │   │   ├── collector_tools.py # Expert-level CRD create/replace
│   │   │   └── provision_tools.py # Intent-driven smart provisioning (NEW)
│   │   ├── instrumentation/       # Language lookup & CRD management
│   │   ├── validation/            # Pipeline validation & safety checks
│   │   ├── governance/            # Cardinality & eBPF governance
│   │   ├── sampling/              # Sampling inspection & toggle
│   │   └── spanmetrics/           # SpanMetrics connector management
│   ├── resources/                 # MCP Resources (9 URIs)
│   │   └── otel_resources.py      # Collector, enrichment, logs, spanmetrics,
│   │                              # instrumentation, target allocator, language,
│   │                              # and system health resources
│   ├── prompts/                   # MCP Prompts (5 guided workflows)
│   │   └── otel_prompts.py        # Onboarding, investigation, cardinality,
│   │                              # sampling, and security audit prompts
│   ├── services/                  # Business logic
│   │   ├── kubernetes_service.py  # K8s API wrapper (CRDs, Deployments, Pods, Services)
│   │   ├── collector_config_service.py  # Collector YAML parser & analyzer
│   │   └── collector_config_builder.py  # Intent→config generation engine (NEW)
│   ├── server/                    # FastMCP server setup
│   │   ├── core.py                # Server creation
│   │   ├── bootstrap.py           # Component initialization
│   │   └── middleware.py          # 7-layer middleware stack
│   ├── models/                    # Pydantic data models
│   ├── utils/                     # Helpers
│   │   ├── k8s_labels.py          # Annotation keys, eBPF agent labels, language detection
│   │   ├── yaml_helpers.py        # YAML parsing, pipeline extraction
│   │   ├── pagination.py          # Cursor-based pagination
│   │   └── duration.py            # OTel duration string parsing (e.g., "2ms" → 2.0)
│   ├── static/                    # Static data files
│   │   ├── otel_lang_registry.json   # Language support matrix
│   │   └── OTEL_MCP_INSTRUCTIONS.md  # MCP system instructions
│   ├── exceptions/                # Custom exception hierarchy
│   ├── config.py                  # Environment parsing & config dataclasses
│   └── main.py                    # Entry point
├── tests/                         # Test suites (371 tests)
├── docs/                          # Documentation
├── pyproject.toml                 # Package definitions (Python 3.12)
├── Dockerfile                     # Multi-stage Docker build
└── README.md                      # This documentation
```

---

## Roadmap

**Shipped:**

- [x] Collector discovery with namespace filtering, label selectors, and pagination
- [x] Deep collector inspection with full pipeline topology and raw YAML
- [x] Language instrumentation lookup with framework-specific guidance
- [x] Instrumentation CRD creation/patching with dry-run safety
- [x] Deployment annotation for auto-instrumentation injection
- [x] Instrumented service listing with annotation and init container detection
- [x] Processor ordering validation against OTel best practices
- [x] Filelog receiver safety auditing
- [x] Target Allocator state inspection
- [x] Collector topology recommendation engine
- [x] SpanMetrics cardinality analysis and series estimation
- [x] Transform processor YAML generation for attribute dropping
- [x] eBPF instrumentation security auditing
- [x] Sampling configuration inspection (head + tail cross-reference)
- [x] Sampling strategy toggle with config patch generation
- [x] SpanMetrics connector enablement with custom dimensions
- [x] Collector CRD management (create/replace with dry-run safety)
- [x] 4-tier language detection (annotations → images → names → runtime env vars)
- [x] OTel duration string parsing in histogram bucket configs
- [x] 5 guided workflow prompts for onboarding, investigation, cardinality, sampling, and security
- [x] 7-layer middleware stack (rate limiting, response limiting, caching)
- [x] **Intent-driven collector provisioning** (`otel_provision_collector`) — auto-discovery, best-practice configs, smart mode selection
- [x] Auto-discovery engine: existing collectors → K8s services → debug fallback
- [x] 10 backend patterns: Jaeger, Tempo, Zipkin, Prometheus, Thanos, Mimir, VictoriaMetrics, OpenSearch, Elasticsearch, Loki
- [x] Cluster auto-sizing (node count → resource recommendations)
- [x] SpanMetrics connector wiring with correct pipeline topology
- [x] Filelog safety built-in (self-exclusion, namespace scoping, checkpoints)

**Coming next:**

- [ ] Collector config diffing (before/after patch comparison)
- [ ] Alerting rule integration (OTel → PrometheusRule CRD bridging)
- [ ] Multi-cluster support
- [ ] Collector health metrics dashboard generation

See [open issues](https://github.com/talkops-ai/talkops-mcp/issues) for the full list of proposed features.

---

## Contributing

Contributions are welcome. The process is straightforward:

1. Fork the repo
2. Create a branch (`git checkout -b feature/TailSamplingPolicies`)
3. Make your changes and commit
4. Push and open a PR

If you're considering something bigger, open an issue first so we can align on the approach.

---

## FAQ

<details>
<summary><b>Which MCP clients work with this?</b></summary>
Any MCP-compatible client including Claude Desktop, Cline, Cursor, and custom clients. Connect via <code>http://localhost:8771/mcp</code> for HTTP transport, or configure stdio for direct process communication.
</details>

<details>
<summary><b>Does this require the OpenTelemetry Operator?</b></summary>
The OTel Operator is required for Instrumentation CRD features (auto-instrumentation, annotation-based injection). Collector discovery and pipeline validation work with any OpenTelemetryCollector CRD in the cluster.
</details>

<details>
<summary><b>Does this modify my cluster?</b></summary>
Most tools are read-only. The exceptions are: <code>otel_provision_collector</code> (smart provisioning — auto-discovers and creates collectors), <code>otel_patch_collector</code> (expert-level CRD create/replace), <code>otel_patch_instrumentation</code> (creates/patches Instrumentation CRDs), and <code>otel_annotate_deployment</code> (adds annotations to Deployment pod templates, triggering rolling restarts). All four default to <code>dry_run=True</code> and require explicit opt-in to apply. All other tools generate YAML output only — they do NOT apply changes.
</details>

<details>
<summary><b>What's the difference between dry_run=True and dry_run=False?</b></summary>
With <code>dry_run=True</code> (default), mutating tools preview the change and return the spec/annotation without modifying any Kubernetes resources. With <code>dry_run=False</code>, the change is applied. The server always returns the generated spec so you can review before applying.
</details>

<details>
<summary><b>Can I use this without Kubernetes?</b></summary>
The server is designed for Kubernetes environments. Set <code>K8S_ENABLED=false</code> to disable Kubernetes integration, but most tools will return errors since they depend on CRD access. The language lookup tool (<code>otel_lookup_instrumentation</code>), topology recommendation (<code>otel_recommend_collector_topology</code>), and transform rule generation (<code>otel_gen_drop_attribute_rules</code>) work without K8s since they are pure recommendation engines.
</details>

<details>
<summary><b>What RBAC does `otel_provision_collector` create?</b></summary>
When provisioning a collector with <code>dry_run=False</code>, the tool automatically creates a <code>ClusterRole</code> and <code>ClusterRoleBinding</code> for the <code>k8sattributes</code> processor. The k8sattributes processor enriches telemetry with Kubernetes metadata (pod name, namespace, deployment name, etc.) and needs <code>get</code>, <code>list</code>, <code>watch</code> permissions on Pods, ReplicaSets, Namespaces, Nodes, and Jobs. The OTel Operator does <b>not</b> create these RBAC resources automatically. The created resources are labeled with <code>app.kubernetes.io/managed-by: talkops-mcp</code> for easy identification. In dry-run mode, the RBAC manifests are included in the <code>rbac_resources</code> field of the response for review.
</details>

---

## Troubleshooting

### Kubernetes Connection Issues

1. Verify `K8S_ENABLED=true` and your kubeconfig is accessible.
2. Load the `otel://system/health` resource to check connectivity status.
3. Run the MCP server with `uv run mcp-server`
4. The server will use your active kubeconfig context by default.

### OTel Operator / CRD Issues

1. Ensure the OpenTelemetry Operator is installed: `kubectl get crd opentelemetrycollectors.opentelemetry.io`.
2. Verify `OTEL_CRD_GROUP` and `OTEL_CRD_API_VERSION` match your operator version.
3. For Instrumentation CRDs, verify: `kubectl get crd instrumentations.opentelemetry.io`.
4. Check RBAC: the server's service account needs `get`, `list`, `watch`, `create`, `patch` on OTel CRDs.

### No Collectors Found

1. Run `otel_list_collectors()` without namespace filter to search all namespaces.
2. Check if collectors exist: `kubectl get opentelemetrycollectors --all-namespaces`.
3. Verify the `OTEL_COLLECTOR_PLURAL` env var matches your CRD plural name.

### Auto-Instrumentation Not Working

1. Verify an Instrumentation CR exists in the target namespace.
2. Check that the Deployment has the correct annotation (e.g., `instrumentation.opentelemetry.io/inject-python: "true"`).
3. Look for init container injection: `kubectl describe pod <pod-name>`.
4. Use `otel_list_instrumented_services` to diagnose annotation vs. injection mismatches.

---

## Security Considerations

- **Never expose the MCP server to the public internet** without proper authentication.
- **`otel_provision_collector` creates OpenTelemetryCollector CRDs** — always review the dry_run output before setting `dry_run=False`. The tool auto-discovers backends and generates configs, so verify the discovered endpoints are correct.
- **`otel_patch_collector` creates or replaces OpenTelemetryCollector CRDs** — review the spec before setting `dry_run=False`.
- **`otel_patch_instrumentation` creates real Kubernetes CRDs** — review the spec before setting `dry_run=False`.
- **`otel_annotate_deployment` modifies Deployments** — this triggers a rolling restart of all pods.
- **eBPF instrumentation pods may run with elevated privileges** — use `otel_analyze_ebpf_footprint` to audit.

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
- [OpenTelemetry](https://opentelemetry.io/) for the industry-standard observability framework.
- [Kubernetes](https://kubernetes.io/) for container orchestration APIs.
- [OpenTelemetry Operator](https://github.com/open-telemetry/opentelemetry-operator) for Kubernetes-native OTel lifecycle management.
