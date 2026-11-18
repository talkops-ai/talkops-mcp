<p align="center">
  <img src="https://raw.githubusercontent.com/cncf/artwork/main/projects/prometheus/icon/color/prometheus-icon-color.svg" alt="Prometheus logo" height="100"/>
</p>

<h1 align="center">Prometheus MCP Server &amp; Agent Plugin</h1>

<p align="center">
  An Agent Plugins v1.0.0 compliant Prometheus observability suite combining <strong>6 Progressive-Disclosure Agent Skills</strong> (methodology, runbooks, and zero-network local CLI generators) with a focused <strong>19-Tool / 11-Resource MCP Execution Server</strong> for Prometheus 3.0+, Thanos, Mimir, Cortex, and VictoriaMetrics.
</p>

<p align="center">
  <a href="https://pypi.org/project/talkops-prometheus-mcp-server/"><img src="https://img.shields.io/pypi/v/talkops-prometheus-mcp-server.svg?style=flat-square&logo=pypi&logoColor=white&label=PyPI" alt="PyPI"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://prometheus.io/"><img src="https://img.shields.io/badge/Prometheus-3.0%2B-E6522C.svg?style=flat-square&logo=prometheus&logoColor=white" alt="Prometheus 3.0+"/></a>
</p>

---

## Architecture: Strict Skill & Execution Separation

Following the TalkOps Skill & Execution Separation Architecture (`docs/skill-and-execution-separation.md`), this repository separates **how to think** (Agent Skills) from **how to act** (MCP Execution Layer):

```text
src/prometheus-mcp-server/
├── plugin.json                                     # Agent Plugins v1.0.0 manifest
├── mcp.json                                        # Portable MCP launcher config
├── skills/                                         # 6 Progressive-Disclosure Agent Skills
│   ├── triaging-prometheus-incidents-and-slos/     # RED/USE triage, multi-window SLOs, exemplars
│   ├── authoring-promql-and-analyzing-metrics/     # PromQL 3.0, Native Histograms, UTF-8 syntax
│   ├── authoring-and-testing-prometheus-rules/     # Alerting/recording rules & promtool testing
│   ├── optimizing-tsdb-cardinality-and-finops/     # Cardinality FinOps, relabeling, remote-write
│   ├── configuring-prometheus-scraping-and-discovery/ # ServiceMonitor/PodMonitor/Probe/ScrapeConfig/file_sd
│   └── onboarding-exporters-and-instrumentation/   # OpenMetrics snippets & 19-exporter K8s catalog
└── prometheus_mcp_server/                          # FastMCP Execution Server (19 Tools, 11 Resources)
    ├── tools/                                      # 5 Toolsets (diagnostics, query, rules, scrape, exporters)
    ├── resources/                                  # 11 Dynamic prom:// Resources
    ├── services/                                   # Prometheus HTTP API v1 + Kubernetes CRD merge services
    └── utils/                                      # Redaction, JSONL audit trail, PromQL 3.0 token-boundary AST
```

### Clear Bounded Context (Zero Overlap with Sibling MCP Servers)
- **`prometheus-mcp-server`** strictly owns Prometheus signal generation, PromQL querying (including Native Histograms and UTF-8 names), Exemplar extraction (`/api/v1/query_exemplars`), TSDB cardinality & health (`/api/v1/status/tsdb`, `/api/v1/status/walreplay`), scrape targets (`ServiceMonitor`, `PodMonitor`, `Probe`, `ScrapeConfig`, `file_sd`), `promtool` validation/unit testing, and Prometheus's own `/api/v1/rules` & `/api/v1/alerts` rule evaluation state.
- **`alertmanager-mcp-server`** (`src/alertmanager-mcp-server`) exclusively owns Alertmanager v2 APIs (`/api/v2/alerts`, `/api/v2/silences`, routing trees, receivers, and inhibition rules).
- **`tempo-mcp-server`** (`src/tempo-mcp-server`) owns distributed trace retrieval using `trace_id` values extracted via `prom_query_exemplars`.

---

## 6 Bundled Agent Skills (`skills/`)

| Skill Directory | Purpose | Local Deterministic Script (`scripts/`) |
|---|---|---|
| `triaging-prometheus-incidents-and-slos` | Incident triage using RED/USE, Google SRE multi-window multi-burn-rate SLOs, and Exemplar-to-Trace handoffs | `scripts/generate_slo_rules.py` |
| `authoring-promql-and-analyzing-metrics` | Safe PromQL 3.0 query construction, Native Histograms, and anomaly period comparisons | `scripts/lint_promql.py` |
| `authoring-and-testing-prometheus-rules` | Alerting & recording rule lifecycle, `promtool` unit tests, and safe multi-group CRD merges | `scripts/build_promtool_test_suite.py` |
| `optimizing-tsdb-cardinality-and-finops` | TSDB cardinality investigation, `metric_relabel_configs`, and remote-write FinOps | `scripts/generate_finops_config.py` |
| `configuring-prometheus-scraping-and-discovery` | Kubernetes Operator CRDs (`ServiceMonitor`, `PodMonitor`, `Probe`, `ScrapeConfig`) and VM `file_sd` | `scripts/validate_scrape_manifest.py` |
| `onboarding-exporters-and-instrumentation` | Language SDK instrumentation (Go/Python/Java/Node) and 19-exporter K8s lifecycle | `scripts/render_exporter_bundle.py` |

---

## 19 MCP Tools Across 5 Toolsets

Every tool has $\le 8$ parameters and explicit MCP `ToolAnnotations` (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`).

### 1. `diagnostics` Toolset (2 Read-Only Tools)
| Tool | Description |
|---|---|
| `prom_get_diagnostics` | Consolidated control-plane & TSDB diagnostics (`overview`, `runtime_config`, `tsdb`, `wal_replay`, `scrape_pools`). |
| `prom_analyze_cardinality` | Live TSDB cardinality analysis combining `/api/v1/status/tsdb` with per-metric label fanout via `/api/v1/series`. |

### 2. `query` Toolset (7 Read-Only Tools)
| Tool | Description |
|---|---|
| `prom_explore_metrics` | Unified discovery of metric names, metadata (`TYPE`/`HELP`/`UNIT`), series matches, or label values. |
| `prom_query_instant` | Execute point-in-time PromQL query (or `validate_only=True` syntax/counter preflight check). |
| `prom_query_range` | Execute time-range PromQL query with automatic downsampling and `summary`/`full`/`chart` response modes. |
| `prom_query_exemplars` | Query `/api/v1/query_exemplars` to extract OpenTelemetry `trace_id`/`span_id` exemplars for `tempo-mcp-server`. |
| `prom_compare_periods` | Compare current range query against a baseline offset (e.g. `1d`, `7d`) with delta% and z-score shift. |
| `prom_analyze_service_red` | Compound RED (Rate, Error ratio, Latency p50/p95/p99) analysis supporting classic and Native Histograms. |
| `prom_evaluate_slo_burn` | Compound Google SRE multi-window multi-burn-rate SLO evaluation (1h/5m, 6h/30m, 24h/2h, 72h/6h). |

### 3. `rules` Toolset (3 Read-Only, 1 Write, 1 Destructive)
| Tool | Description |
|---|---|
| `prom_get_firing_alerts` | Inspect active (`pending`/`firing`) alerts from Prometheus `/api/v1/alerts` & `/api/v1/rules`. |
| `prom_validate_rules` | Validate rule group YAML via `promtool check rules` and optional `promtool test rules` unit tests. |
| `prom_simulate_rule_firing` | Backtest an alert expression against historical range data (`mode="historical"`) or synthetic series (`mode="synthetic"`). |
| `prom_upsert_rule_group` | Create/update a rule group via `yaml_only`, `local_file`, `k8s_crd` (non-destructive group merge), or `http_ruler`. |
| `prom_delete_rule_group` | Delete a rule group (preserves sibling groups in `PrometheusRule` CRDs; deletes CRD only when last group removed). |

### 4. `scrape` Toolset (1 Read-Only, 1 Write, 1 Destructive)
| Tool | Description |
|---|---|
| `prom_verify_metrics_endpoint` | Scrape and validate a `/metrics` endpoint + optional Prometheus `up{}` series verification. |
| `prom_apply_scrape_config` | Apply `servicemonitor`, `podmonitor`, `probe`, `scrapeconfig`, or `file_sd` target configuration. |
| `prom_delete_scrape_config` | Delete a Kubernetes scrape CRD or remove a `file_sd` job entry. |

### 5. `exporters` Toolset (1 Write, 1 Destructive)
| Tool | Description |
|---|---|
| `prom_install_exporter` | Deploy one of 19 supported exporters to Kubernetes (`dry_run=True` by default). |
| `prom_uninstall_exporter` | Uninstall a previously deployed exporter from Kubernetes (`confirm=True` required). |

---

## 11 Dynamic `prom://` Resources

| Resource URI | Description |
|---|---|
| `prom://system/backends` | All configured Prometheus backends with health status |
| `prom://system/backends/{backend_id}` | Detailed capabilities, version, and build info for a single backend |
| `prom://config/runtime` | Secret-redacted runtime configuration, flags, and TSDB summary |
| `prom://topology/targets` | Consolidated service topology and failed/down scrape targets |
| `prom://metadata/catalog` | Live metric catalog (`TYPE`, `HELP`, `UNIT`) |
| `prom://tsdb/cardinality` | Live TSDB cardinality overview from `/api/v1/status/tsdb` |
| `prom://rules/groups` | Summary of all alerting and recording rule groups |
| `prom://rules/{backend_id}/groups/{group_name}` | Full YAML/JSON definition and evaluation health of a specific rule group |
| `prom://kubernetes/scrape-crds` | Inventory of `ServiceMonitor`, `PodMonitor`, `Probe`, `ScrapeConfig`, and `PrometheusRule` CRDs |
| `prom://kubernetes/manifests/{kind}/{namespace}/{name}` | Secret-redacted Kubernetes CRD manifest |
| `prom://audit/recent` | Recent mutating action audit log entries (ring buffer + optional JSONL persistence) |

---

## CLI Flags & Environment Configuration

```bash
# Default (Read-Only safe mode: mutating tools are hidden unless --allow-write is set)
uv run prometheus-mcp-server --prometheus-url http://localhost:9090

# Enable write tools and restrict to specific toolsets
uv run prometheus-mcp-server \
  --prometheus-url http://localhost:9090 \
  --allow-write \
  --toolsets diagnostics,query,rules \
  --tenant-id team-payments \
  --audit-log-path ./audit.jsonl
```

| Environment Variable | CLI Flag | Default | Description |
|---|---|---|---|
| `PROMETHEUS_BASE_URL` | `--prometheus-url` | `http://localhost:9090` | Prometheus HTTP API base URL |
| `PROMETHEUS_ALLOW_WRITE` | `--allow-write` / `--read-only` | `false` | Register mutating/destructive tools (`false` = read-only) |
| `PROMETHEUS_TOOLSETS` | `--toolsets` | `all` | Comma-separated toolsets (`diagnostics,query,rules,scrape,exporters`) |
| `PROMETHEUS_TENANT_ID` | `--tenant-id` | *(none)* | Default `X-Scope-OrgID` header for Mimir/Cortex/Thanos |
| `PROMETHEUS_RULER_URL` | — | *(none)* | Optional Mimir/Thanos Ruler base URL |
| `PROMETHEUS_AUDIT_LOG_PATH` | `--audit-log-path` | *(none)* | Optional JSONL file path for persistent mutation audit trail |

---

## Running Tests

The repository includes a 3-tier verification suite (115 tests across unit, integration, and skill/plugin compliance):

```bash
cd src/prometheus-mcp-server
uv run pytest -v
```

---

## License

Apache 2.0 — see [LICENSE](../../LICENSE).
