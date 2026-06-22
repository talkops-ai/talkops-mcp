# Prometheus MCP Server Instructions

You are connected to the **Prometheus MCP Server**, which provides tools, resources, and prompts for AI-native Prometheus observability.

## Core Concepts

| Concept | Description |
|---------|-------------|
| **Backend** | A Prometheus-compatible endpoint (Prometheus, Thanos, Mimir, Cortex, VictoriaMetrics) |
| **Metric** | A named time series with labels, typed as counter, gauge, histogram, or summary |
| **Target** | A scrape endpoint that Prometheus periodically fetches metrics from |
| **ServiceMonitor** | A Kubernetes CRD that configures Prometheus to scrape a Service |
| **Exporter** | A sidecar/standalone process that exposes third-party metrics in Prometheus format |

## MCP Resources (app-controlled context)

Load these resources for background context. They are read-only snapshots the host can pre-load into your context window.

| Resource URI | Description |
|---|---|
| `prom://system/backends` | All backends with health status — use to discover `backend_id` values |
| `prom://system/backends/{id}` | Backend capabilities, version, runtime info |
| `prom://config/runtime` | Scrape settings, retention, TSDB stats |
| `prom://topology/services` | Service catalog from scrape targets |
| `prom://topology/failed_targets` | Failed/down scrape targets |
| `prom://metadata/catalog` | Metric names, types, HELP text |
| `prom://tsdb/cardinality` | TSDB cardinality overview and top-N metrics |
| `prom://rules/groups` | Alerting and recording rule group inventory |
| `prom://exporters/catalog` | Built-in exporter catalog (types, ports, images) |
| `prom://schema/label_values` | Per-metric label values snapshot |
| `prom://best-practices` | Prometheus best practices |
| `prom://onboarding-guide` | App onboarding guide |

## Available Tools (model-controlled actions)

### Query & Exploration
- `prom_validate_promql` — Validate PromQL syntax before executing
- `prom_query_instant` — Point-in-time PromQL query with counter enforcement
- `prom_query_range` — Time-range PromQL query with automatic downsampling
- `prom_explore_labels` — Discover label names and values for a metric
- `prom_suggest_promql` — Generate PromQL from natural language intent

### Application Onboarding
- `prom_recommend_instrumentation` — Recommend instrumentation strategy
- `prom_test_endpoint` — Validate a /metrics endpoint

### Exporter Management
- `prom_recommend_exporter` — Get exporter recommendations for a service type
- `prom_install_exporter` — Deploy an exporter to Kubernetes (MUTATES)
- `prom_uninstall_exporter` — Remove an exporter from Kubernetes (DESTRUCTIVE)
- `prom_verify_exporter` — End-to-end health check for an exporter

### Scrape Configuration
- `prom_apply_servicemonitor` — Generate and apply a ServiceMonitor CRD; supports cross-namespace scraping via `target_namespace` param (MUTATES)
- `prom_delete_servicemonitor` — Delete a ServiceMonitor CRD by name and namespace (DESTRUCTIVE, idempotent)
- `prom_apply_probe` — Apply a Blackbox Probe CRD (MUTATES)
- `prom_manage_file_sd` — Add/remove targets in file_sd_configs (MUTATES)

### FinOps & Cardinality Optimization
- `prom_optimize_cardinality` — Analyze top-N metrics and recommend optimization
- `prom_plan_relabel` — Generate metric_relabel_configs YAML
- `prom_create_recording_rule` — Generate recording rule group YAML
- `prom_configure_remote_write` — Generate remote_write config YAML

### Rule Management
- `prom_get_rule_group` — Get a single rule group with full details
- `prom_upsert_rule_group` — Create or update a rule group (MUTATES)
- `prom_delete_rule_group` — Delete a rule group (DESTRUCTIVE)
- `prom_describe_alert_rule` — Human-readable alert rule explanation

### Rule Validation (promtool)
- `prom_check_rule_group` — Validate rule group syntax
- `prom_run_rule_tests` — Run promtool unit tests

### Simulation & Tuning
- `prom_simulate_firing_historical` — Evaluate alert expr against real historical data
- `prom_simulate_firing_synthetic` — Run synthetic alert firing test
- `prom_analyze_firing_history` — Analyze alert firing frequency and duration

### Authoring
- `prom_draft_alert_rule` — Generate an alert rule from natural language
- `prom_tune_alert_rule` — Suggest rule adjustments based on firing history

## Safety Rules

1. **Backend Discovery**: Use the `prom://system/backends` resource to find valid `backend_id` values
2. **Counter Rule**: Counter metrics must use `rate()`/`increase()` unless `allow_raw_counters=true`
3. **Downsampling**: Range queries are automatically downsampled to ~200 points per series
4. **Declarative**: K8s operations use ServiceMonitor CRDs, not raw SSH/kubectl

## Workflow Patterns

### Application Onboarding (K8s)
1. Load `prom://system/backends` → find backend
2. `prom_recommend_instrumentation(workload_type=..., language=...)` → choose approach
3. User deploys instrumented app
4. `prom_test_endpoint(endpoint_url=...)` → validate /metrics
5. `prom_apply_servicemonitor(service_name=..., namespace="monitoring", target_namespace="...")` → wire to Prometheus
   - **Cross-namespace**: if the service is in namespace X but Prometheus is in Y, set `namespace=Y, target_namespace=X`
   - **Find exact service name**: use `kubectl get svc -n <target_namespace>` first; auto-discovery depends on the exact K8s service name
   - **Cleanup stale SMs**: use `prom_delete_servicemonitor` to remove incorrectly created ServiceMonitors before retrying
6. `prom_query_instant(query="rate(http_requests_total[5m])")` → verify data flows

### Troubleshooting
1. Load `prom://topology/failed_targets` for down targets
2. `prom_query_instant(query="up{job='...'}")` → check status
3. `prom_test_endpoint(endpoint_url=...)` → validate endpoint
4. Load `prom://tsdb/cardinality` → check for cardinality issues
