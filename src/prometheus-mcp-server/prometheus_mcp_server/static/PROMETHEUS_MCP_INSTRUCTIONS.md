# TalkOps Prometheus MCP Server

Execution plane for Prometheus, Thanos, Mimir, Cortex, and VictoriaMetrics observability workflows.

## Toolsets (19 Tools)
- **`diagnostics` (Read-Only)**: `prom_get_diagnostics`, `prom_analyze_cardinality`
- **`query` (Read-Only)**: `prom_explore_metrics`, `prom_query_instant`, `prom_query_range`, `prom_query_exemplars`, `prom_compare_periods`, `prom_analyze_service_red`, `prom_evaluate_slo_burn`
- **`rules` (Read/Write)**: `prom_get_firing_alerts`, `prom_validate_rules`, `prom_simulate_rule_firing`, `prom_upsert_rule_group`, `prom_delete_rule_group`
- **`scrape` (Read/Write)**: `prom_verify_metrics_endpoint`, `prom_apply_scrape_config`, `prom_delete_scrape_config`
- **`exporter` (Write)**: `prom_install_exporter`, `prom_uninstall_exporter`

## Dynamic Resources (11 URIs)
- `prom://system/backends`, `prom://system/backends/{backend_id}`, `prom://config/runtime`
- `prom://topology/targets`, `prom://metadata/catalog`, `prom://tsdb/cardinality`
- `prom://rules/groups`, `prom://rules/{backend_id}/groups/{group_name}`
- `prom://kubernetes/scrape-crds`, `prom://kubernetes/manifests/{kind}/{namespace}/{name}`
- `prom://audit/recent`

## Core Safety Invariants
1. **Schema First**: Read `prom://metadata/catalog` or call `prom_explore_metrics` before constructing PromQL. Never run unbounded `{__name__=~".+"}` queries.
2. **Counter Guardrail**: Always wrap counter (`*_total`, `*_count`, `*_sum`, `*_bucket`) metrics in `rate()`, `irate()`, `increase()`, or `resets()`.
3. **Dry-Run Before Mutation**: All write/destructive tools default to `dry_run=True` and require `confirm=True` (or interactive elicitation) when `dry_run=False`.
4. **Bounded Context**: Alertmanager silences, routing trees, and inhibitions belong to `alertmanager-mcp-server` (`am_*`). Trace span inspection belongs to `tempo-mcp-server` (`tempo_*`).
