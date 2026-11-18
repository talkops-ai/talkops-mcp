# Tempo MCP Server — Execution Plane Instructions

You are connected to the **Tempo MCP Server** (`v0.2.0`), the Grafana Tempo 2.x/3.x and Tempo Operator (`tempo.grafana.com/v1alpha1`) execution plane.

## Architectural Contract
- **Execution Only**: This server exposes live backend/cluster state (`resources`) and factual telemetry queries or guarded mutations (`tools`). Domain knowledge and operational playbooks reside in `skills/`.
- **Read-Only by Default**: Write tools (`tempo_patch_tenant_overrides`, `tempo_apply_operator_cr`) are disabled unless started with `--allow-write` or `MCP_ALLOW_WRITE=true`. Inspect `tempo://server/capabilities` for active flags.
- **Dry-Run Previews & Elicitation Gates**: All mutating tools default to `dry_run=True`, return a unified YAML diff, and require MCP elicitation (`ctx.elicit()`) or `confirm=True` before applying state changes.
- **Secret Omission**: Raw `/status/config` credentials and Kubernetes secret values are never exposed; only allow-listed operational facts and sanitized manifests are returned.

## Toolsets (18 Tools Max, `<= 8` Parameters Each)
- **`search` (read-only)**: `tempo_get_attribute_names`, `tempo_get_attribute_values`, `tempo_traceql_search`, `tempo_get_trace`, `tempo_summarize_trace`, `tempo_find_related_traces`, `tempo_compare_traces`, `tempo_query_a2ui`
- **`metrics` (read-only)**: `tempo_traceql_metrics_range`, `tempo_traceql_metrics_instant`, `tempo_analyze_service_red`, `tempo_compare_span_cohorts`
- **`diagnostics` (read-only)**: `tempo_get_exemplar_traces`, `tempo_get_trace_from_log`, `tempo_get_service_dependencies`, `tempo_get_diagnostics`
- **`overrides` (write-gated)**: `tempo_patch_tenant_overrides`
- **`operator` (write-gated)**: `tempo_apply_operator_cr`

## Resources (10 Dynamic `tempo://` Resources)
- `tempo://server/capabilities` — Server version, write gate, active toolsets, query guardrails, and per-backend detected features (Tempo 2.x/3.x generation, metrics-generator processors, overrides status, dedicated columns)
- `tempo://system/backends` — Configured Tempo backends with live `/ready` status
- `tempo://system/backends/{backend_id}` — Detailed backend profile (`buildinfo`, `/status/services`, deployment mode, capabilities)
- `tempo://deployment/overview` — Configured backends and Kubernetes-discovered Tempo services and Operator CRDs
- `tempo://schema/{backend_id}/attributes` — Live attribute inventory by scope and detected OpenTelemetry Semantic Conventions
- `tempo://overrides/{backend_id}/{tenant}` — Merged per-tenant overrides and current `ETag` from `/api/overrides`
- `tempo://operator/crs/{namespace}` — Inventory of `TempoStack` and `TempoMonolithic` CRs (`_all` supported)
- `tempo://operator/manifests/{kind}/{namespace}/{name}` — Sanitized and secret-redacted `TempoStack` or `TempoMonolithic` manifest
- `tempo://operator/crd-schema/{kind}` — Installed CRD OpenAPI v3 `spec` schema for `TempoStack` or `TempoMonolithic`
- `tempo://traces/{backend_id}/{trace_id}` — Compact trace summary and bounded spans by trace ID
