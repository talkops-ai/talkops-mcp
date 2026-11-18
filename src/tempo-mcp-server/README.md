<p align="center">
  <img src="https://grafana.com/static/img/logos/logo-tempo.svg" alt="Grafana Tempo MCP Server" width="120" onError="this.style.display='none'"/>
</p>

<h1 align="center">Grafana Tempo MCP Server & Agent Plugin (v0.2.0)</h1>

<p align="center">
  An <strong>Agent Plugins v1.0.0</strong> package combining <strong>6 Progressive-Disclosure Agent Skills</strong> (<code>skills/</code>) with an <strong>18-Tool / 10-Resource FastMCP Execution Server</strong> for <strong>Grafana Tempo 2.x/3.x</strong> and the <strong>Tempo Operator (<code>tempo.grafana.com/v1alpha1</code>)</strong>.
</p>

<p align="center">
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://grafana.com/oss/tempo/"><img src="https://img.shields.io/badge/Grafana%20Tempo-2.x%20%2F%203.x-F46800.svg?style=flat-square&logo=grafana&logoColor=white" alt="Tempo"/></a>
</p>

---

## Architecture: Strict Skill & Execution Separation (`v0.2.0`)

Following the TalkOps [Skill and Execution Separation](../../docs/skill-and-execution-separation.md) standard, all procedural runbooks, TraceQL references, and offline generators live in **Agent Skills**, while the **MCP Server** focuses strictly on live, bounded, secret-redacted execution:

```text
src/tempo-mcp-server/
├── plugin.json                              # Agent Plugins v1.0.0 manifest
├── mcp.json                                 # Default stdio MCP server wiring (read-only by default)
├── skills/                                  # 6 Progressive-Disclosure Agent Skills (8 scripts, 18 references)
│   ├── authoring-traceql-and-metrics-queries/
│   ├── triaging-tempo-service-errors/
│   ├── investigating-tempo-latency-regressions/
│   ├── diagnosing-tempo-ingestion-and-health/
│   ├── mapping-tempo-topology-and-alerts/
│   └── operating-tempo-deployments-and-tenants/
└── tempo_mcp_server/                        # FastMCP Execution Plane
    ├── config.py                            # Multi-backend, multi-tenant, guardrail & toolset config
    ├── services/                            # Async Tempo HTTP API, Prometheus service-graphs, K8s Operator CRDs
    ├── resources/                           # 10 live tempo:// URI resources (zero static markdown bloat)
    └── tools/                               # 18 tools across 5 selectable toolsets (all <= 8 params, 0 prompts)
```

- **Zero MCP Prompts (`0`) & Zero Static-Doc Resources**: Legacy MCP prompt playbooks and static reference/runbook resources have been migrated into `skills/*/SKILL.md` and `skills/*/references/*.md`.
- **Safe Read-Only Default (`MCP_ALLOW_WRITE=false`)**: All 16 read/diagnostic tools are available out-of-the-box; the 2 mutating tools (`tempo_patch_tenant_overrides`, `tempo_apply_operator_cr`) are unregistered unless `--allow-write` / `MCP_ALLOW_WRITE=true` is enabled and still default to `dry_run=True` + ETag / confirmation gates.

---

## 6 Bundled Agent Skills (`skills/`)

| Skill Directory | Purpose | Offline Scripts (`scripts/`) | Reference Guides (`references/`) |
|---|---|---|---|
| `authoring-traceql-and-metrics-queries` | TraceQL 2.x/3.x search authoring, `compare()` cohort ranking, TraceQL Metrics (`rate`, `quantile_over_time`, `histogram_over_time`), and OTel SemConv mapping | `lint_traceql.py` | `traceql-syntax.md`, `traceql-metrics.md`, `otel-semconv-and-k8s-attributes.md`, `query-pack.md` |
| `triaging-tempo-service-errors` | Metrics-first RED triage, Prometheus exemplar & Loki log-line trace pivots, correlated error-origin search, and structured incident briefs | `extract_trace_ids_from_logs.py`, `render_incident_report.py` | `triage-thresholds.md`, `cross-pillar-handoffs.md`, `incident-brief-template.md` |
| `investigating-tempo-latency-regressions` | Critical-path & self-time hotspot analysis, 5-axis baseline vs. slow trace comparison, and `compare()` cohort root-cause isolation | `analyze_otlp_trace_critical_path.py` | `latency-heuristics.md`, `trace-diff-interpretation.md` |
| `diagnosing-tempo-ingestion-and-health` | Missing-traces triage, Tempo 2.x/3.x ring & `/metrics` discarded-span diagnostics, multi-tenant header checks, and OTel exporter verification | `check_otel_exporter_config.py` | `no-traces-decision-tree.md`, `diagnosis-codes.md`, `multi-tenancy.md`, `tempo-3-architecture.md` |
| `mapping-tempo-topology-and-alerts` | Upstream/downstream dependency mapping via service-graphs/TraceQL and spanmetrics Prometheus `PrometheusRule` generation | `generate_spanmetrics_prometheus_rule.py` | `service-graph-and-spanmetrics.md`, `alert-templates.md` |
| `operating-tempo-deployments-and-tenants` | Per-tenant `/api/overrides` RFC 7386 merge patching with optimistic ETag concurrency and Kubernetes `TempoStack` / `TempoMonolithic` lifecycle | `build_overrides_patch.py`, `render_tempo_operator_cr.py` | `overrides-cookbook.md`, `operator-profiles.md`, `production-checklist.md` |

---

## 18 MCP Tools Across 5 Selectable Toolsets

Every tool enforces $\le 8$ parameters and carries explicit MCP `ToolAnnotations`. Control registered toolsets via `--toolsets` or `MCP_TOOLSETS` (`all`, `readonly`, `search`, `metrics`, `diagnostics`, `overrides`, `operator`).

| Toolset | Tool Name | Mode | Max Params | Description |
|---|---|---|---|---|
| `search` | `tempo_traceql_search` | Read-Only | 8 | Search traces using raw TraceQL and/or structured `SearchFilters` with lookback, limit, and `spss` guardrails |
| `search` | `tempo_get_trace` | Read-Only | 5 | Retrieve a trace by ID with optional span-count slicing and time bounds |
| `search` | `tempo_summarize_trace` | Read-Only | 4 | Extract a factual trace summary: critical path, self-time hotspots, error spans, and Kubernetes context |
| `search` | `tempo_query_a2ui` | Read-Only | 3 | Retrieve a DAG-pruned trace payload structured for TalkOps A2UI timeline rendering |
| `search` | `tempo_find_related_traces` | Read-Only | 6 | Find traces correlated with a seed trace by error origin, endpoint, time window, or service cascade |
| `search` | `tempo_compare_traces` | Read-Only | 5 | Compute a 5-axis structural, span-count, timing, error, and attribute diff between two traces |
| `search` | `tempo_get_attribute_names` | Read-Only | 5 | Discover available trace attribute names grouped by scope (`resource`, `span`, `intrinsic`, `event`) |
| `search` | `tempo_get_attribute_values` | Read-Only | 6 | Retrieve distinct values for a trace attribute scoped by time window and optional TraceQL filter |
| `metrics` | `tempo_traceql_metrics_instant` | Read-Only | 7 | Execute a point-in-time TraceQL Metrics instant query (`vector` result) |
| `metrics` | `tempo_traceql_metrics_range` | Read-Only | 8 | Execute a TraceQL Metrics range query returning time-series points and per-series statistics |
| `metrics` | `tempo_analyze_service_red` | Read-Only | 6 | Compute service Rate, Error rate, and P50/P95/P99 latency metrics, optional baseline deltas, and exemplar trace IDs |
| `metrics` | `tempo_compare_span_cohorts` | Read-Only | 6 | Execute a TraceQL `compare()` query to rank attribute values differentiating slow/failing spans from baseline |
| `diagnostics` | `tempo_get_diagnostics` | Read-Only | 3 | Collect Tempo readiness, version (`2.x`/`3.x`), ring health, discarded-span counters, redacted config, and Operator CR status |
| `diagnostics` | `tempo_get_service_dependencies` | Read-Only | 5 | Map `client -> server` call edges via Prometheus `traces_service_graph_*`, TraceQL Metrics, or trace DAG sampling |
| `diagnostics` | `tempo_get_exemplar_traces` | Read-Only | 5 | Extract exemplar trace IDs directly from a TraceQL Metrics range query |
| `diagnostics` | `tempo_get_trace_from_log` | Read-Only | 3 | Extract a trace ID (`traceparent`, JSON, logfmt, or 32-char hex) from a log line and summarize the trace |
| `overrides` | `tempo_patch_tenant_overrides` | Write (`dry_run=True`) | 6 | Preview or apply an RFC 7386 JSON merge patch to Tempo `/api/overrides` with optimistic `expected_etag` concurrency |
| `operator` | `tempo_apply_operator_cr` | Write (`dry_run=True`) | 4 | Validate, server-side dry-run diff, and apply a `TempoStack` or `TempoMonolithic` custom resource manifest |

---

## 10 Live `tempo://` Resources

| Resource URI | Type | Description |
|---|---|---|
| `tempo://server/capabilities` | Static | Server version, write gate status, active toolsets, query guardrails, and detected backend capabilities |
| `tempo://system/backends` | Static | All configured Tempo backends with live health and readiness status |
| `tempo://deployment/overview` | Static | Deployment topology combining configured Tempo HTTP backends and Kubernetes-discovered Tempo installs |
| `tempo://system/backends/{backend_id}` | Template | Detailed live profile, version, and build metadata for `{backend_id}` |
| `tempo://schema/{backend_id}/attributes` | Template | Live trace attribute inventory and detected OpenTelemetry Semantic Conventions (`v1.20` vs `v1.24+`) |
| `tempo://traces/{backend_id}/{trace_id}` | Template | Compact trace summary and bounded spans for `{trace_id}` |
| `tempo://overrides/{backend_id}/{tenant}` | Template | Current per-tenant `/api/overrides` payload and `ETag` header |
| `tempo://operator/crs/{namespace}` | Template | Inventory of `TempoStack` and `TempoMonolithic` CRs in `{namespace}` (or `_all` for cluster-wide) |
| `tempo://operator/manifests/{kind}/{namespace}/{name}` | Template | Sanitized, secret-redacted `TempoStack` or `TempoMonolithic` YAML manifest |
| `tempo://operator/crd-schema/{kind}` | Template | Cluster-installed OpenAPI v3 `spec` schema for `TempoStack` or `TempoMonolithic` |

---

## Configuration & CLI Usage

```bash
# Default: Read-only mode over stdio (16 read-only tools + 10 resources)
uv run tempo-mcp-server --tempo-url http://localhost:3200

# Enable multi-tenant queries + Kubernetes Operator discovery + write tools
uv run tempo-mcp-server \
  --tempo-url http://localhost:3200 \
  --tenant prod-traces \
  --k8s-enabled \
  --allow-write

# Streamable HTTP transport on port 8768
MCP_TRANSPORT=http MCP_PORT=8768 uv run tempo-mcp-server --transport http
```

| CLI Flag | Environment Variable | Default | Description |
|---|---|---|---|
| `--transport` | `MCP_TRANSPORT` | `stdio` | Transport protocol: `stdio`, `http` (`streamable-http`), or `sse` |
| `--toolsets` | `MCP_TOOLSETS` | `all` | Comma-separated toolsets: `all,readonly,search,metrics,diagnostics,overrides,operator` |
| `--allow-write` | `MCP_ALLOW_WRITE` | `false` | Register mutating tools (`tempo_patch_tenant_overrides`, `tempo_apply_operator_cr`) |
| `--read-only` | `MCP_READ_ONLY` | `false` | Force read-only mode (overrides `--allow-write`) |
| `--tempo-url` | `TEMPO_BASE_URL` / `TEMPO_URL` | `http://localhost:3200` | Primary Tempo HTTP API base URL (or JSON array via `TEMPO_BACKENDS`) |
| `--tenant` | `TEMPO_DEFAULT_TENANT` | *(none)* | Default `X-Scope-OrgID` header for multi-tenant Tempo / Grafana Enterprise Traces |
| — | `PROMETHEUS_URL` | *(none)* | Optional Prometheus URL for `traces_service_graph_*` topology queries |
| `--k8s-enabled` | `K8S_ENABLED` | `false` | Enable Kubernetes discovery and Tempo Operator CRD resources/tools |
| `--kubeconfig` / `--context` | `K8S_KUBECONFIG` / `K8S_CONTEXT` | `~/.kube/config` | Kubernetes kubeconfig path and context |
| — | `TEMPO_MAX_LOOKBACK` | `168h` | Maximum allowed TraceQL search lookback window |
| — | `MCP_PORT` | `8768` | HTTP server bind port when `MCP_TRANSPORT=http` |

---

## Development & Verification

```bash
cd src/tempo-mcp-server
uv sync --dev

# Run unit, in-memory MCP protocol, safety gate, and Agent Skill conformance tests
uv run pytest tests/ -v --tb=short

# Run static type checking
uv run pyright .

# Build wheel and sdist
uv build
```

---

## License

Apache 2.0 — see [LICENSE](../../LICENSE).
