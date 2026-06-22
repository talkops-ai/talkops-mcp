# Service Topology & Alerting Test Guide — Tempo MCP Server (OTel Demo)

**Phase 7 of 7** in the Tempo end-to-end journey.
**Previous phase**: [Schema Exploration](TEMPO_SCHEMA_EXPLORATION_TEST_GUIDE.md)

> This final phase maps service dependencies from trace data, generates PromQL alerting
> expressions from trace patterns, and demonstrates Tempo Operator CRD lifecycle management.
> It also covers the cross-MCP workflow for creating PrometheusRule CRDs.
>
> **Use cases**: Service topology mapping, proactive alerting setup, Day 2 Tempo operations.

---

## Prerequisites (Completed in Phase 6)

| Component | Status |
|-----------|--------|
| ✅ Backends discovered | `tempo_list_backends` — `default` backend ready |
| ✅ Services enumerated | `tempo_get_attribute_values` — 14+ services known |
| ✅ K8s mapping validated | `tempo_get_k8s_attribute_map` — attribute names resolved |
| ✅ Diagnostics healthy | `tempo_get_diagnostics` — no critical findings |
| ✅ Metrics-generator working | `tempo_traceql_metrics_range` — required for topology |

---

## The Starting Point

Phase 6 explored the schema. Now you want to operationalize the environment:

1. **What services exist and how do they connect?** — Map the service dependency graph.
2. **Which services need alerting?** — Identify high-error or high-latency services.
3. **How do I set up alerts from trace data?** — Generate PromQL from spanmetrics.
4. **How do I manage Tempo itself?** — Inspect and update Tempo Operator CRDs.

---

## Phase 1: Service Topology

### Step 1.1: Map All Service Dependencies

| Field | Value |
|-------|-------|
| **Prompt** | `Map the service dependencies in the otel-demo namespace.` |
| **Tool** | `tempo_get_service_dependencies` |
| **Parameters** | `{"backend_id": "default", "since": "1h"}` |
| **Internal action** | (1) Attempts TraceQL structural query `{ } >> { } \| by(resource.service.name, span.peer.service.name)` to derive call edges (requires Tempo 2.4+ with metrics-generator). (2) Falls back to service enumeration via `{ } \| by(resource.service.name) \| rate()`. (3) If both fail, uses attribute value lookup for `resource.service.name`. |
| **Expected output** | `{"nodes": [{"service": "ad"}, {"service": "cart"}, {"service": "checkout"}, {"service": "currency"}, {"service": "email"}, {"service": "frontend"}, {"service": "payment"}, ...], "edges": [{"client": "frontend", "server": "checkout"}, {"client": "checkout", "server": "payment"}, {"client": "checkout", "server": "shipping"}, ...], "method": "traceql_structural", "summary": "14 services found"}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `nodes` | All expected OTel Demo services present |
| `edges` | Client → server call relationships |
| `method` | `"traceql_structural"` = full edge data; `"service_enumeration"` = nodes only |
| `edges_note` | If present, indicates structural queries aren't supported — upgrade Tempo or enable metrics-generator |

### Step 1.2: Focused Topology — Checkout Dependencies

| Field | Value |
|-------|-------|
| **Prompt** | `What services does "checkout" depend on?` |
| **Tool** | `tempo_get_service_dependencies` |
| **Parameters** | `{"backend_id": "default", "service": "checkout", "since": "1h"}` |
| **Internal action** | Same as Step 1.1 but filters to edges involving `checkout`. |
| **Expected output** | Nodes and edges related to `checkout` only (e.g., checkout → payment, checkout → shipping, checkout → cart, frontend → checkout) |

### Step 1.3: Focused Topology — Frontend Dependencies

| Field | Value |
|-------|-------|
| **Prompt** | `What are the upstream and downstream dependencies of "frontend"?` |
| **Tool** | `tempo_get_service_dependencies` |
| **Parameters** | `{"backend_id": "default", "service": "frontend", "since": "1h"}` |

### Topology Interpretation

| Pattern | Meaning | Action |
|---------|---------|--------|
| `frontend` is a hub (many edges) | Expected — it's the entry point | Monitor its error/latency |
| `checkout` calls 4+ services | Critical orchestrator | Alert on error rate |
| Service with no edges | Isolated — may be a background job | Verify instrumentation |
| `method: "service_enumeration"` | No edge data available | Enable metrics-generator with `local-blocks` |

---

## Phase 2: Identify Services Needing Alerts

### Step 2.1: Error Rate by Service

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the error rate by service across all services.` |
| **Tool** | `tempo_traceql_metrics_range` |
| **Parameters** | `{"backend_id": "default", "query": "{ status = error } | rate() | by(resource.service.name)", "since": "1h"}` |
| **Internal action** | Returns one time series per service with error rate. |

**Decision**: Services with sustained error rate > 5% should get alerting rules.

### Step 2.2: P99 Latency by Service

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the P99 latency by service.` |
| **Tool** | `tempo_traceql_metrics_range` |
| **Parameters** | `{"backend_id": "default", "query": "{ } | quantile_over_time(duration, 0.99) | by(resource.service.name)", "since": "1h"}` |

**Decision**: Services with P99 > 500ms should get latency alerting rules.

---

## Phase 3: Generate Alerting Expressions

### Step 3.1: Error Rate Alert for Checkout

| Field | Value |
|-------|-------|
| **Prompt** | `Generate an error rate alert for "checkout" with a 5% threshold.` |
| **Tool** | `tempo_generate_alerting_expression` |
| **Parameters** | `{"backend_id": "default", "service": "checkout", "alert_type": "error_rate", "threshold": 0.05, "for_duration": "5m", "severity": "warning"}` |
| **Internal action** | (1) Generates PromQL from spanmetrics template. (2) Builds PrometheusRule YAML snippet. (3) Generates TraceQL annotation for trace correlation. (4) Validates service exists via `tempo_get_attribute_values`. |
| **Expected output** | `{"alert_name": "HighErrorRate_checkout", "alert_type": "error_rate", "service": "checkout", "promql_expr": "sum(rate(traces_spanmetrics_calls_total{service=\"checkout\",status_code=\"STATUS_CODE_ERROR\"}[5m])) / sum(rate(traces_spanmetrics_calls_total{service=\"checkout\"}[5m])) > 0.05", "for_duration": "5m", "severity": "warning", "yaml_snippet": "...", "next_step": "Pass the yaml_snippet to prom_upsert_rule_group in the Prometheus MCP server...", "validation": {"service_exists": true, "warning": null}}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `promql_expr` | Valid PromQL expression referencing `traces_spanmetrics_*` metrics |
| `yaml_snippet` | Complete PrometheusRule CRD YAML ready to apply |
| `validation.service_exists` | `true` = service verified in Tempo data |
| `validation.warning` | If present, the service wasn't found — check spelling |
| `next_step` | Instructions for the cross-MCP workflow |

### Step 3.2: P99 Latency Alert for Frontend

| Field | Value |
|-------|-------|
| **Prompt** | `Create a P99 latency alert for "frontend" that fires above 500ms.` |
| **Tool** | `tempo_generate_alerting_expression` |
| **Parameters** | `{"backend_id": "default", "service": "frontend", "alert_type": "latency_p99", "threshold": 500, "for_duration": "5m", "severity": "warning"}` |

### Step 3.3: Throughput Drop Alert

| Field | Value |
|-------|-------|
| **Prompt** | `Generate a throughput drop alert for "payment" — alert if rate drops below 10 req/s.` |
| **Tool** | `tempo_generate_alerting_expression` |
| **Parameters** | `{"backend_id": "default", "service": "payment", "alert_type": "throughput_drop", "threshold": 10, "for_duration": "10m", "severity": "critical"}` |

### Alert Types Reference

| Type | Threshold | PromQL Template | When to Use |
|------|-----------|-----------------|-------------|
| `error_rate` | Ratio (0.05 = 5%) | `error_calls / total_calls > threshold` | Service error SLO breach |
| `latency_p99` | Milliseconds | `histogram_quantile(0.99, ...) > threshold` | Latency SLO breach |
| `throughput_drop` | Requests/sec | `rate(total_calls) < threshold` | Service down or degraded |

### Cross-MCP Workflow

```
tempo_generate_alerting_expression (Tempo MCP)
  → outputs yaml_snippet (PrometheusRule CRD YAML)
  → AI agent reads next_step instruction
  → passes yaml_snippet to prom_upsert_rule_group (Prometheus MCP)
  → PrometheusRule CRD created in cluster
  → Prometheus picks up the rule and begins evaluating
```

> **Important**: `tempo_generate_alerting_expression` is **read-only** — it generates the YAML but does NOT create any CRD. The actual creation is done by the Prometheus MCP server.

---

## Phase 4: Tempo Operator CRD Management

### Step 4.1: List All Tempo CRs

| Field | Value |
|-------|-------|
| **Prompt** | `List all Tempo Operator custom resources in the cluster.` |
| **Tool** | `tempo_list_operator_crs` |
| **Parameters** | `{}` |
| **Internal action** | Scans cluster for `TempoStack` and `TempoMonolithic` CRDs via `kubernetes_service.list_tempo_operator_crs()`. Returns summary of each instance. |
| **Expected output** | `{"items": [{"name": "tempo", "namespace": "monitoring", "kind": "TempoStack", "storage_type": "s3", "retention": "48h", "status_phase": "Ready", "ready": true}], "total": 1}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `items` | All Tempo CRs found in the cluster |
| `ready` | `true` = Tempo pods are running and reconciled |
| `storage_type` | `s3`, `gcs`, `azure`, or `pv` |
| `retention` | Current trace retention period |

> **Note**: Requires `K8S_ENABLED=true` and the Tempo Operator installed in the cluster.

### Step 4.2: Inspect CR Details

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the full spec for the TempoStack "tempo" in "monitoring".` |
| **Tool** | `tempo_get_operator_cr` |
| **Parameters** | `{"namespace": "monitoring", "name": "tempo", "kind": "TempoStack"}` |
| **Internal action** | Fetches the full CRD including metadata, spec, status, and conditions. |
| **Expected output** | `{"name": "tempo", "namespace": "monitoring", "kind": "TempoStack", "api_version": "tempo.grafana.com/v1alpha1", "spec": {"storage": {...}, "retention": {"global": {"traces": "48h"}}, "resources": {...}, "template": {"queryFrontend": {"jaegerQuery": {"enabled": true}}}}, "status": {...}, "conditions": [...]}` |

### Step 4.3: Create a New CR (Dry Run)

| Field | Value |
|-------|-------|
| **Prompt** | `Generate a TempoStack manifest with S3 storage and 7-day retention — preview only.` |
| **Tool** | `tempo_create_operator_cr` |
| **Parameters** | `{"namespace": "monitoring", "name": "tempo-staging", "kind": "TempoStack", "storage_type": "s3", "storage_secret": "tempo-s3-credentials", "retention": "7d", "jaeger_ui": true, "dry_run": true}` |
| **Internal action** | Builds a complete CRD manifest with storage, retention, resources, and optional search/tenancy config. Returns the YAML for review. Does NOT apply when `dry_run=true`. |
| **Expected output** | `{"action": "dry_run", "dry_run": true, "name": "tempo-staging", "namespace": "monitoring", "kind": "TempoStack", "manifest_yaml": "apiVersion: tempo.grafana.com/v1alpha1\nkind: TempoStack\n...", "message": "🔍 Review the generated manifest above. Set dry_run=False to apply to the cluster."}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `action` | `"dry_run"` — nothing was applied |
| `manifest_yaml` | Complete, valid YAML ready for review |
| `message` | Instructions to set `dry_run=false` to apply |

> **Safety**: `dry_run=true` is the default. Always review the manifest before setting `dry_run=false`.

### Step 4.4: Patch an Existing CR (Dry Run)

| Field | Value |
|-------|-------|
| **Prompt** | `Update the retention to 7 days for TempoStack "tempo" in "monitoring" — preview the patch.` |
| **Tool** | `tempo_patch_operator_cr` |
| **Parameters** | `{"namespace": "monitoring", "name": "tempo", "kind": "TempoStack", "retention": "7d", "dry_run": true}` |
| **Internal action** | Builds a strategic merge patch with only the specified fields. Returns the patch for review. |
| **Expected output** | `{"action": "dry_run", "dry_run": true, "name": "tempo", "namespace": "monitoring", "kind": "TempoStack", "patch_spec": {"retention": {"global": {"traces": "7d"}}}, "message": "🔍 Review the patch above. Set dry_run=False to apply."}` |

### Step 4.5: Patch Resources (Dry Run)

| Field | Value |
|-------|-------|
| **Prompt** | `Increase memory limits to 4Gi for TempoStack "tempo" — dry run.` |
| **Tool** | `tempo_patch_operator_cr` |
| **Parameters** | `{"namespace": "monitoring", "name": "tempo", "kind": "TempoStack", "resources_total": {"limits": {"memory": "4Gi", "cpu": "2000m"}}, "dry_run": true}` |

### Operator Safety Matrix

| Operation | Tool | Destructive? | Default | Review Required? |
|-----------|------|-------------|---------|-----------------|
| List CRs | `tempo_list_operator_crs` | No | — | No |
| Get CR detail | `tempo_get_operator_cr` | No | — | No |
| Create CR | `tempo_create_operator_cr` | **Yes** | `dry_run=true` | **Yes** — review manifest_yaml |
| Patch CR | `tempo_patch_operator_cr` | **Yes** | `dry_run=true` | **Yes** — review patch_spec |

---

## Complete Tool Coverage Verification

All 22 Tempo MCP tools covered across the 7-phase journey:

| # | Tool | Phase(s) |
|---|------|----------|
| 1 | `tempo_list_backends` | 6 |
| 2 | `tempo_get_backend` | 3, 6 |
| 3 | `tempo_get_query_policies` | 4, 6 |
| 4 | `tempo_get_attribute_names` | 3, 4, 6 |
| 5 | `tempo_get_attribute_values` | 3, 4, 6 |
| 6 | `tempo_get_k8s_attribute_map` | 4, 6 |
| 7 | `tempo_traceql_search` | 1, 2, 3, 4, 5 |
| 8 | `tempo_get_trace` | 3 |
| 9 | `tempo_summarize_trace` | 1, 2, 5 |
| 10 | `tempo_find_related_traces` | 1 |
| 11 | `tempo_traceql_metrics_range` | 1, 2, 5, 7 |
| 12 | `tempo_traceql_metrics_instant` | 5 |
| 13 | `tempo_get_exemplar_traces` | 5 |
| 14 | `tempo_get_trace_from_log` | 5 |
| 15 | `tempo_get_diagnostics` | 1, 3, 6 |
| 16 | `tempo_get_service_dependencies` | 7 |
| 17 | `tempo_list_operator_crs` | 7 |
| 18 | `tempo_get_operator_cr` | 7 |
| 19 | `tempo_create_operator_cr` | 7 |
| 20 | `tempo_patch_operator_cr` | 7 |
| 21 | `tempo_compare_traces` | 2 |
| 22 | `tempo_generate_alerting_expression` | 7 |

---

## Phase Summary

At the end of this phase (and the complete 7-phase journey), you've:

| What | Tool / Resource | Status |
|------|----------------|--------|
| ✅ Service topology mapped | `tempo_get_service_dependencies` | Nodes and edges from trace data |
| ✅ High-error services identified | `tempo_traceql_metrics_range` | Error rate per service |
| ✅ Alerting expressions generated | `tempo_generate_alerting_expression` | PromQL + YAML for error rate, latency, throughput |
| ✅ Cross-MCP workflow documented | `next_step` in alert output | Tempo → Prometheus MCP handoff |
| ✅ Operator CRs listed | `tempo_list_operator_crs` | All TempoStack/TempoMonolithic instances |
| ✅ Operator CR inspected | `tempo_get_operator_cr` | Full spec, status, conditions |
| ✅ Operator CR created (dry run) | `tempo_create_operator_cr` | Manifest reviewed |
| ✅ Operator CR patched (dry run) | `tempo_patch_operator_cr` | Patch reviewed |

---

## Journey Complete 🎉

You've completed all 7 phases of the Tempo MCP Server end-to-end journey. Here's the full roadmap of what was covered:

| Phase | Guide | Core Focus |
|-------|-------|------------|
| 1 | [Error Triage](TEMPO_ERROR_TRIAGE_TEST_GUIDE.md) | Metrics-first error investigation |
| 2 | [Latency Investigation](TEMPO_LATENCY_INVESTIGATION_TEST_GUIDE.md) | P99 analysis + trace comparison |
| 3 | [Missing Traces](TEMPO_MISSING_TRACES_TEST_GUIDE.md) | Diagnostic troubleshooting |
| 4 | [TraceQL Builder](TEMPO_TRACEQL_BUILDER_TEST_GUIDE.md) | Query construction from intent |
| 5 | [Metrics-First Triage](TEMPO_METRICS_FIRST_TRIAGE_TEST_GUIDE.md) | RED analysis + cross-pillar pivots |
| 6 | [Schema Exploration](TEMPO_SCHEMA_EXPLORATION_TEST_GUIDE.md) | First-time cluster exploration |
| 7 | [Topology & Alerting](TEMPO_TOPOLOGY_ALERTING_TEST_GUIDE.md) | Dependencies, alerts, Day 2 ops |

**Companion documents:**
- [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md) — All 7 workflows with mermaid diagrams
- [PROMPT_REFERENCE.md](PROMPT_REFERENCE.md) — Natural language prompts for all 22 tools, 11 resources, 5 prompts
