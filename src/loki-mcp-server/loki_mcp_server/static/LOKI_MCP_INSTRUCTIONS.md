# TalkOps Loki MCP Server — Execution Plane Instructions

You are connected to the **Loki MCP Server** (`v0.2.0`), the Grafana Loki 3.x and Loki Operator (`loki.grafana.com/v1`) execution plane.

## Architectural Contract
- **Execution Only**: This server exposes live backend/cluster state (`resources`) and factual telemetry queries or guarded mutations (`tools`). Procedural guidance, LogQL syntax guides, and label governance reside in `skills/`.
- **Read-Only by Default**: Write tools (`loki_upsert_rule_group`, `loki_delete_rule_group`, `loki_manage_delete_requests`, `loki_apply_operator_cr`) are disabled unless started with `--allow-write` or `MCP_ALLOW_WRITE=true`. Inspect `loki://server/capabilities` for active flags.
- **Dry-Run Previews & Elicitation Gates**: All mutating tools default to `dry_run=True`, return a blast-radius preview or unified YAML diff, and require MCP elicitation (`ctx.elicit()`) or `confirm=True` before applying state changes.
- **Secret Omission**: Credentials, tokens, and Kubernetes Secret values are automatically redacted across all resources and tool outputs.

## Toolsets (18 Tools Max, `<= 8` Parameters Each)
- **`discovery` (read-only)**: `loki_get_labels`, `loki_get_label_values`, `loki_get_series`, `loki_get_log_patterns`, `loki_get_detected_fields`
- **`query` (read-only)**: `loki_get_query_stats`, `loki_query_instant`, `loki_query_range`, `loki_query_a2ui`
- **`analysis` (read-only)**: `loki_summarize_service_logs`, `loki_compare_periods`, `loki_correlate_trace_logs`, `loki_analyze_volume`
- **`diagnostics` (read-only)**: `loki_get_diagnostics`
- **`rules` (write-gated)**: `loki_upsert_rule_group`, `loki_delete_rule_group`
- **`governance` (write-gated)**: `loki_manage_delete_requests`
- **`operator` (write-gated)**: `loki_apply_operator_cr`

## Dynamic Resources (9 `loki://` URIs)
- `loki://server/capabilities` — Server version, write gate, active toolsets, query guardrails, and detected Loki 3.x backend capabilities
- `loki://system/health` — Live Loki `/ready` status, reachability, and active label count
- `loki://schema/labels` — Live global label taxonomy
- `loki://config/guardrails` — Active query safety guardrails (max bytes, time window, log limit, cardinality cap)
- `loki://config/backends` — Configured Loki backend connection profile (credentials redacted)
- `loki://rules/groups` — Active Loki Ruler alerting and recording rule groups (`/loki/api/v1/rules`)
- `loki://compactor/delete-requests` — Active and historical Compactor log deletion requests (`/loki/api/v1/delete`)
- `loki://operator/crs/{namespace}` — Inventory of Kubernetes `LokiStack`, `RulerConfig`, `AlertingRule`, and `RecordingRule` CRs (`_all` supported)
- `loki://operator/manifests/{kind}/{namespace}/{name}` — Sanitized, secret-redacted Loki Operator CR manifest
