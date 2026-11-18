<p align="center">
  <img src="https://raw.githubusercontent.com/grafana/loki/main/docs/sources/logo.png" alt="Grafana Loki logo" height="100"/>
</p>

<h1 align="center">Grafana Loki MCP Server &amp; Agent Plugin</h1>

<p align="center">
  Production-ready <strong>Agent Plugin (v1.0.0)</strong> and <strong>FastMCP Execution Server</strong> for <strong>Grafana Loki 3.x</strong> and the <strong>Kubernetes Loki Operator</strong> (<code>loki.grafana.com/v1</code>).
</p>

<p align="center">
  <a href="https://pypi.org/project/talkops-loki-mcp-server/"><img src="https://img.shields.io/pypi/v/talkops-loki-mcp-server.svg?style=flat-square&logo=pypi&logoColor=white&label=PyPI" alt="PyPI"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://grafana.com/oss/loki/"><img src="https://img.shields.io/badge/Grafana%20Loki-3.x-F46800.svg?style=flat-square&logo=grafana&logoColor=white" alt="Grafana Loki 3.x"/></a>
</p>

Following the TalkOps **Skill & Execution Layer Separation** architecture:
- **Procedural Intelligence (`skills/`)**: 6 modular Agent Skills containing progressive-disclosure SOPs (`SKILL.md` $\le 250$ lines), deep domain references (`references/*.md`), and deterministic local Python CLI helpers (`scripts/*.py`).
- **Execution Plane (`loki_mcp_server/`)**: 18 bounded, type-annotated MCP tools across 7 selectable toolsets + 9 live `loki://` state resources, with read-only defaults (`MCP_ALLOW_WRITE=false`), mandatory `dry_run=True` previews, and interactive `ctx.elicit()` / `confirm=True` mutation gates.

---

## Architecture Overview

```
src/loki-mcp-server/
├── plugin.json                              # Agent Plugins v1.0.0 manifest (talkops-loki v0.2.0)
├── mcp.json                                 # Default stdio MCP server wiring (read-only by default)
├── skills/                                  # 6 Modular Agent Skills (Procedural Layer)
│   ├── authoring-logql-and-analyzing-logs/
│   ├── triaging-loki-incidents-and-errors/
│   ├── discovering-loki-schema-and-log-structure/
│   ├── optimizing-loki-cardinality-and-finops/
│   ├── authoring-loki-alerting-and-recording-rules/
│   └── operating-loki-deployments-and-ingestion/
└── loki_mcp_server/                         # FastMCP Execution Plane
    ├── config.py                            # Frozen config + CLI flags (--read-only, --allow-write, --toolsets)
    ├── services/
    │   ├── loki_service.py                  # Async HTTP client (Query, Volume, Ruler, Compactor, Diagnostics)
    │   └── kubernetes_service.py            # Async K8s client (LokiStack, RulerConfig, AlertingRule, RecordingRule)
    ├── resources/
    │   └── loki_resources.py                # 9 live dynamic loki:// resources (zero static markdown bloat)
    └── tools/                               # 18 tools across 7 selectable toolsets (all <= 8 params)
```

---

## 6 Bundled Agent Skills (`skills/`)

| Skill Name | Purpose | Local Deterministic Script |
|------------|---------|----------------------------|
| `authoring-logql-and-analyzing-logs` | 4-stage LogQL pipeline construction, cost preflight checks, metric unwrap queries, and A2UI visualization | `scripts/lint_logql.py` |
| `triaging-loki-incidents-and-errors` | $N \to 1$ service log summarization, period-over-period regression diffs, and cross-service `trace_id` correlation | `scripts/extract_error_signatures.py` |
| `discovering-loki-schema-and-log-structure` | Progressive schema discovery (`labels` $\to$ `values` $\to$ `series` $\to$ `detected_fields` $\to$ `patterns`) and OTLP mapping | `scripts/infer_log_parser.py` |
| `optimizing-loki-cardinality-and-finops` | Log volume attribution, high-cardinality label detection, Alloy/Promtail `structured_metadata` migration, and Bloom filters | `scripts/audit_label_cardinality.py` |
| `authoring-loki-alerting-and-recording-rules` | Noise-free Loki Ruler alerting/recording rules, backtesting, and Kubernetes `AlertingRule`/`RecordingRule` CRDs | `scripts/validate_loki_rules.py` |
| `operating-loki-deployments-and-ingestion` | `loki_discarded_samples_total` diagnostics, Compactor PII log deletions, and Loki 3.x / `LokiStack` sizing | `scripts/render_loki_architecture_config.py` |

---

## 18 MCP Tools Across 7 Selectable Toolsets

All 18 tools follow the `loki_*` namespace convention across 7 selectable toolsets ($\le 8$ parameters per tool):

| Toolset | Tool Name | Mode | Description |
|---------|-----------|------|-------------|
| `discovery` | `loki_get_labels` | Read-Only | List indexed label names (`service_name`, `namespace`, `cluster`) |
| `discovery` | `loki_get_label_values` | Read-Only | List values for a specific label, optionally scoped by `query` |
| `discovery` | `loki_get_series` | Read-Only | Inspect active label combinations and stream count |
| `discovery` | `loki_get_log_patterns` | Read-Only | Discover recurring `<_>` structural templates and line volumes |
| `discovery` | `loki_get_detected_fields` | Read-Only | Discover JSON/logfmt keys and Loki 3.x structured metadata fields |
| `query` | `loki_get_query_stats` | Read-Only | Preflight query cost check (`streams`, `chunks`, `entries`, `bytes`) |
| `query` | `loki_query_instant` | Read-Only | Execute point-in-time LogQL metric queries |
| `query` | `loki_query_range` | Read-Only | Execute range LogQL log/metric queries with size and cost guardrails |
| `query` | `loki_query_a2ui` | Read-Only | Execute LogQL and render an interactive A2UI dashboard component |
| `analysis` | `loki_summarize_service_logs` | Read-Only | $N \to 1$ service digest: volume, error ratio, top signatures, sample errors, and `trace_id`s |
| `analysis` | `loki_compare_periods` | Read-Only | Compare current vs. baseline window to isolate newly introduced error signatures |
| `analysis` | `loki_correlate_trace_logs` | Read-Only | Reconstruct chronological cross-service log timelines by `trace_id` / `request_id` |
| `analysis` | `loki_analyze_volume` | Read-Only | Attribute ingested log bytes by label dimension (`/loki/api/v1/index/volume` + fallback) |
| `diagnostics` | `loki_get_diagnostics` | Read-Only | Inspect `/ready`, `/loki/api/v1/status/buildinfo`, and `/metrics` `loki_discarded_samples_total` |
| `rules` | `loki_upsert_rule_group` | Write-Gated | Validate, diff (`dry_run=True`), and upsert a Loki Ruler rule group |
| `rules` | `loki_delete_rule_group` | Write/Destructive | Preview (`dry_run=True`) and delete a Loki Ruler rule group |
| `governance` | `loki_manage_delete_requests` | Write/Destructive | Preview blast radius (`dry_run=True`), create, or cancel Compactor `/loki/api/v1/delete` requests |
| `operator` | `loki_apply_operator_cr` | Write-Gated | Server-side dry-run diff and apply for `LokiStack`, `RulerConfig`, `AlertingRule`, and `RecordingRule` CRs |

---

## 9 Dynamic `loki://` Resources

| Resource URI | Description |
|--------------|-------------|
| `loki://server/capabilities` | Server version, active toolsets, `allow_write` gate, guardrails, and Loki 3.x feature flags |
| `loki://system/health` | Live Loki reachability and readiness status |
| `loki://schema/labels` | Live indexed label inventory |
| `loki://config/guardrails` | Query byte, time window, line limit, and cardinality thresholds |
| `loki://config/backends` | Redacted Loki backend URL, timeout, tenant (`X-Scope-OrgID`), and auth mode |
| `loki://rules/groups` | Active Loki Ruler alerting and recording rule groups across namespaces |
| `loki://compactor/delete-requests` | Active and completed Compactor log deletion requests |
| `loki://operator/crs/{namespace}` | Inventory of Kubernetes Loki Operator custom resources in `{namespace}` |
| `loki://operator/manifests/{kind}/{namespace}/{name}` | Sanitized, secret-redacted Kubernetes manifest for a Loki Operator CR |

---

## CLI Flags & Environment Configuration

```bash
# Default: Read-only mode (14 read-only tools registered, write tools hidden)
loki-mcp-server --read-only

# Enable write/governance/operator tools (18 tools registered; still guarded by dry_run=True & confirm=True)
loki-mcp-server --allow-write

# Register only specific toolsets
loki-mcp-server --toolsets discovery,query,analysis,diagnostics
```

| Environment Variable | Default | Description |
|----------------------|---------|-------------|
| `LOKI_URL` | `http://localhost:3100` | Base URL of the Grafana Loki instance |
| `LOKI_ORG_ID` | *(optional)* | Multi-tenant `X-Scope-OrgID` header |
| `LOKI_AUTH_TOKEN` | *(optional)* | Bearer token for Loki authentication |
| `MCP_ALLOW_WRITE` | `false` | Set `true` (or pass `--allow-write`) to register write/destructive tools |
| `MCP_TOOLSETS` | `all` | Comma-separated subset of `discovery,query,analysis,diagnostics,rules,governance,operator` |
| `KUBERNETES_ENABLED` | `false` | Enable live Kubernetes API queries for Loki Operator CRDs |

---

## Running Tests

```bash
pytest
```
