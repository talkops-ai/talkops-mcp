# Tempo MCP Server — Natural Language Prompt Reference (OTel Demo)

**For every tool, resource, and prompt documented in [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md), this guide provides ready-to-use natural language prompts — tested against the OpenTelemetry Demo microservices in the `otel-demo` namespace.**

Copy any prompt below exactly or adapt it for your service names, attributes, and time ranges.

> **Design**: All 22 tools are **read-only** except `tempo_create_operator_cr` and `tempo_patch_operator_cr` (which default to `dry_run=true`).

---

## Table of Contents

1. [Discovery](#discovery)
2. [Schema](#schema)
3. [Search & Retrieval](#search--retrieval)
4. [Metrics](#metrics)
5. [Cross-Pillar Pivots](#cross-pillar-pivots)
6. [Diagnostics](#diagnostics)
7. [Topology](#topology)
8. [Operator CRD Management](#operator-crd-management)
9. [Trace Comparison](#trace-comparison)
10. [Alerting](#alerting)
11. [Guided Workflow Prompts](#guided-workflow-prompts)
12. [Resource Reads](#resource-reads)

---

## Discovery

> **Tool**: `tempo_list_backends`

```
What Tempo backends are available?
```
```
List all configured Tempo backends with their health status.
```
```
Show me all Tempo backends and which ones are healthy.
```

> **Tool**: `tempo_get_backend`

```
Show me the detailed profile for the "default" Tempo backend.
```
```
What version of Tempo is running on the "default" backend?
```
```
What capabilities does the "default" Tempo backend support?
```

> **Tool**: `tempo_get_query_policies`

```
What are the query guardrails and limits for the "default" backend?
```
```
What's the maximum lookback and search limit?
```
```
Show me the current query policies — max time range, search limits, SPSS.
```

---

## Schema

> **Tool**: `tempo_get_attribute_names`

```
What trace attributes are available in Tempo?
```
```
Show me all resource-scoped attributes in the "default" backend.
```
```
What span-level attributes exist in the last hour?
```
```
Discover all attributes across all scopes for the "default" backend.
```

> **Tool**: `tempo_get_attribute_values`

```
What services are sending traces to Tempo?
```
```
Show me all values for the "resource.service.name" attribute.
```
```
What namespaces exist in the traces?
```
```
Show me the HTTP methods in the trace data for the last hour.
```
```
What values does "span.http.status_code" have for error traces?
```

> **Tool**: `tempo_get_k8s_attribute_map`

```
Show me the Kubernetes-to-Tempo attribute mapping.
```
```
What OTel attribute name maps to K8s namespace?
```
```
Validate the K8s attribute mappings against the "default" backend's live tags.
```

---

## Search & Retrieval

> **Tool**: `tempo_traceql_search`

```
Find error traces from "checkout" in the last 30 minutes.
```
```
Search for traces where the frontend calls checkout and it takes longer than 1 second.
```
```
Find all traces in the otel-demo namespace with HTTP 500 errors.
```
```
Search for slow traces from "product-catalog" above 500ms in the last hour.
```
```
Find traces from "payment" in the "otel-demo" namespace with error status.
```
```
Search for traces matching '{ resource.service.name = "frontend" && duration > 2s }'.
```

> **Tool**: `tempo_get_trace`

```
Retrieve trace abc123def456789012345678abcdef01 from the "default" backend.
```
```
Get the full trace for trace ID abc123... with LLM-optimized format.
```
```
Fetch trace abc123... with max 100 spans to avoid truncation.
```

> **Tool**: `tempo_summarize_trace`

```
Summarize trace abc123def456789012345678abcdef01.
```
```
Analyze the critical path and errors in trace abc123...
```
```
What's the root cause of the errors in trace abc123...?
```
```
Give me a headline summary and recommended next queries for trace abc123...
```

> **Tool**: `tempo_find_related_traces`

```
Find traces related to abc123... with the same service errors.
```
```
Show me traces that hit the same endpoint as trace abc123...
```
```
Find traces near the same time as abc123... (temporal neighbors).
```

---

## Metrics

> **Tool**: `tempo_traceql_metrics_range`

```
What's the error rate for "checkout" over the last 6 hours?
```
```
Show me the P99 latency trend for "frontend" in the last hour.
```
```
What's the request rate per service in the last hour?
```
```
Show me the error rate by service across the otel-demo namespace over 6 hours.
```
```
What's the request count over time for "checkout" in the last 3 hours?
```

> **Tool**: `tempo_traceql_metrics_instant`

```
What's the current error rate for "checkout" right now?
```
```
Show me the instant request rate for "frontend".
```
```
What's the current P99 latency for "payment"?
```

---

## Cross-Pillar Pivots

> **Tool**: `tempo_get_exemplar_traces`

```
Get exemplar trace IDs from the error rate metrics for "checkout".
```
```
Pivot from the error rate metric to concrete traces for "payment".
```
```
Show me specific traces that contributed to the error rate spike.
```

> **Tool**: `tempo_get_trace_from_log`

```
Extract and retrieve the trace from this log line: "trace_id=abc123def456789012345678abcdef01 order processed"
```
```
Find the trace ID in this log: "TraceID: abc123def456789012345678abcdef01 - payment failed"
```
```
Get the trace from this log output containing a 32-char hex trace ID.
```

---

## Diagnostics

> **Tool**: `tempo_get_diagnostics`

```
Run comprehensive diagnostics on the "default" Tempo backend.
```
```
Is the Tempo backend healthy? Check everything — readiness, build info, services, rings.
```
```
What's the deployment mode and health status of the Tempo backend?
```
```
Are there any issues with the Tempo backend? Run a full health check.
```

---

## Topology

> **Tool**: `tempo_get_service_dependencies`

```
Map the service dependencies in the otel-demo namespace.
```
```
What services does "checkout" depend on?
```
```
Show me the service topology — which services call which?
```
```
What are the upstream and downstream dependencies of "frontend"?
```

---

## Operator CRD Management

> **Tool**: `tempo_list_operator_crs`

```
List all Tempo Operator custom resources in the cluster.
```
```
Show me all TempoStack and TempoMonolithic instances.
```
```
What Tempo CRDs exist in the "monitoring" namespace?
```

> **Tool**: `tempo_get_operator_cr`

```
Show me the full spec for the TempoStack "tempo" in the "monitoring" namespace.
```
```
What's the retention and storage configuration for the Tempo CR?
```

> **Tool**: `tempo_create_operator_cr`

```
Generate a TempoStack manifest with S3 storage and 7-day retention (dry run).
```
```
Create a TempoMonolithic CR in the "monitoring" namespace with PV storage — preview only.
```

> **Tool**: `tempo_patch_operator_cr`

```
Update the retention to 7 days for the TempoStack "tempo" in "monitoring" — preview the patch.
```
```
Increase memory limits to 4Gi for the TempoStack "tempo" — dry run first.
```

---

## Trace Comparison

> **Tool**: `tempo_compare_traces`

```
Compare traces abc123... (baseline) and def456... (slow trace).
```
```
Diff the good trace abc123... against the problematic trace def456...
```
```
What structural and timing differences exist between these two traces?
```
```
Compare a normal checkout trace against a slow one to find the regression.
```

---

## Alerting

> **Tool**: `tempo_generate_alerting_expression`

```
Generate an error rate alert for the "checkout" service with a 5% threshold.
```
```
Create a P99 latency alert for "frontend" that fires above 500ms.
```
```
Generate a throughput drop alert for "payment" — alert if rate drops below 10 req/s.
```
```
Build a PromQL alerting expression for high error rate on "ad" service.
```

---

## Guided Workflow Prompts

These invoke MCP prompts that return structured multi-step workflows:

> **Prompt**: `tempo-error-triage`

```
Triage errors for "checkout" in the "otel-demo" namespace using backend "default".
```
```
Help me investigate errors from the checkout service — run the full error triage workflow.
```
```
The checkout service is throwing errors. Run the error triage workflow.
```

> **Prompt**: `tempo-latency-investigation`

```
Investigate latency spikes above 500ms for "frontend" using backend "default".
```
```
The frontend is slow — investigate latency spikes above 500ms.
```
```
Run a latency investigation for "frontend" with a 500ms threshold.
```

> **Prompt**: `tempo-missing-traces`

```
No traces found for "payment" — diagnose the issue on backend "default".
```
```
Why can't I find any traces for the payment service?
```
```
Diagnose missing traces for "payment" on the "default" backend.
```

> **Prompt**: `tempo-traceql-builder`

```
Build a TraceQL query to find slow database calls over 100ms in the checkout service.
```
```
Help me construct a TraceQL query for error traces with HTTP 500 in the frontend.
```
```
Create a TraceQL query to find traces where checkout calls payment and it fails.
```

> **Prompt**: `tempo-metrics-first-triage`

```
Run a RED analysis for "checkout" over the last 6 hours.
```
```
Do a metrics-first triage for "frontend" — rate, errors, and P99 duration.
```
```
Analyze the RED metrics for "payment" and investigate anomalies.
```

---

## Resource Reads

> **Resource**: `tempo://system/backends`

```
Show me all configured Tempo backends with health status.
```
```
List the Tempo backend connections.
```

> **Resource**: `tempo://system/backends/{backend_id}`

```
Show me the detailed profile for the "default" Tempo backend.
```

> **Resource**: `tempo://deployment/overview`

```
Show me the Tempo deployment topology.
```
```
What backends, modes, and tenants are configured?
```

> **Resource**: `tempo://reference/traceql`

```
Show me the TraceQL syntax reference.
```
```
How do I write a TraceQL query?
```

> **Resource**: `tempo://reference/traceql-metrics`

```
Show me the TraceQL metrics functions reference.
```
```
What metrics functions are available in TraceQL?
```

> **Resource**: `tempo://reference/k8s-attributes`

```
Show me the K8s-to-Tempo attribute mapping.
```
```
What OTel attributes correspond to Kubernetes concepts?
```

> **Resource**: `tempo://reference/query-policies`

```
What are the current query guardrails and safety limits?
```
```
Show me the max lookback, search limits, and SPSS policies.
```

> **Resource**: `tempo://runbooks/latency-spike`

```
Show me the latency spike investigation runbook.
```

> **Resource**: `tempo://runbooks/error-burst`

```
Show me the error burst investigation runbook.
```

> **Resource**: `tempo://runbooks/no-traces-found`

```
Show me the runbook for troubleshooting missing traces.
```

> **Resource**: `tempo://runbooks/cross-tenant-access`

```
Show me the cross-tenant access configuration guide.
```

> **Resource**: `tempo://examples/common-queries`

```
Show me common TraceQL query examples.
```
```
What are some useful TraceQL queries for the OTel demo?
```

---

*Document Version: 1.0 | OTel Demo (`otel-demo` namespace) | Companion to [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md)*
