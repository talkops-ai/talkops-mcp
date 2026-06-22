# Tempo MCP Server — Agent Instructions

You are connected to a **Grafana Tempo** distributed tracing backend via the Tempo MCP Server.

## Your Capabilities

### Tools (16 total)
| Category | Tools | Purpose |
|---|---|---|
| **Discovery** | `tempo_list_backends`, `tempo_get_backend`, `tempo_get_query_policies` | Find and inspect Tempo backends |
| **Schema** | `tempo_get_attribute_names`, `tempo_get_attribute_values`, `tempo_get_k8s_attribute_map` | Discover available attributes |
| **Search** | `tempo_traceql_search`, `tempo_get_trace`, `tempo_summarize_trace`, `tempo_find_related_traces` | Find and analyze traces |
| **Metrics** | `tempo_traceql_metrics_range`, `tempo_traceql_metrics_instant` | RED metrics and trends |
| **Pivot** | `tempo_get_exemplar_traces`, `tempo_get_trace_from_log` | Cross-pillar correlation |
| **Diagnostics** | `tempo_get_diagnostics` | Backend health checks |
| **Topology** | `tempo_get_service_dependencies` | Service dependency mapping |

### Resources (static context)
- `tempo://reference/traceql` — TraceQL syntax
- `tempo://reference/traceql-metrics` — Metrics functions
- `tempo://reference/k8s-attributes` — K8s attribute mapping
- `tempo://reference/query-policies` — Query guardrails
- `tempo://runbooks/*` — Operational runbooks
- `tempo://examples/common-queries` — Starter queries

## Recommended Workflow

**Always follow the metrics-first pattern:**

1. **Discover** → `tempo_list_backends` → pick the right backend
2. **Quantify** → `tempo_traceql_metrics_range` → understand the blast radius
3. **Search** → `tempo_traceql_search` → find specific traces
4. **Analyze** → `tempo_summarize_trace` → understand root cause
5. **Correlate** → `tempo_find_related_traces` → find similar incidents

## Key Concepts

### TraceQL
- Queries use `{ predicates }` syntax
- Resource attributes: `resource.service.name`, `resource.k8s.namespace.name`
- Span attributes: `span.http.status_code`, or unscoped `.http.method`
- Structural: `{ } >> { }` (ancestor/descendant), `{ } ~ { }` (sibling)
- Status: `status = error | ok | unset`
- Duration: `duration > 500ms`

### Multi-Tenancy
- Multi-tenant backends require a `tenant` parameter
- Cross-tenant: pipe-separated values (e.g., `"team-a|team-b"`)

### Query Safety
- Always provide a time range (`since` or `start`/`end`)
- Start with specific filters before broadening
- Tempo search is **non-deterministic** — results may vary between calls
- Use `tempo_get_query_policies` to understand limits before complex queries
