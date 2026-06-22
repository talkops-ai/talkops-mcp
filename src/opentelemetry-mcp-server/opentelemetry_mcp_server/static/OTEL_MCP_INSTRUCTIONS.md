# OpenTelemetry MCP Server — Agent Instructions

You are connected to the **OpenTelemetry MCP Server for Kubernetes**. This server provides read-only and mutating capabilities for managing OpenTelemetry Collector deployments, auto-instrumentation, and observability governance on Kubernetes clusters.

## Capabilities Overview

### Resources (Read-Only State)
Resources expose the current state of the OTel deployment. Use resources to **understand** the system before taking action.

| URI Pattern | Description |
|:---|:---|
| `otel://collector/{namespace}/{name}` | Collector CRD config, pipelines, and status |
| `otel://k8s-enrichment/{namespace}/{collector}` | k8sattributes processor profile |
| `otel://logs-profile/{namespace}/{collector}` | Filelog receiver and log pipeline config |
| `otel://spanmetrics/{namespace}/{collector}` | SpanMetrics connector configuration |
| `otel://instrumentation/{namespace}/{name}` | Instrumentation CRD details |
| `otel://service/{namespace}/{name}` | Workload instrumentation status |
| `otel://target-allocator/{namespace}/{name}` | Target Allocator state and assignments |
| `otel://lang/{language}` | Language instrumentation support matrix |
| `otel://system/health` | Server and K8s connectivity health |
| `otel://registry/languages` | Full language support catalog |

### Tools (Actions)
Tools perform validations, generate configs, and optionally mutate cluster state.

**Read-Only Tools:**
- `otel_list_collectors` — List collectors with filtering
- `otel_get_collector` — Get collector details
- `otel_list_instrumented_services` — List workloads with OTel status
- `otel_lookup_instrumentation` — Language/library → OTel support
- `otel_validate_k8sattributes_order` — Check processor ordering
- `otel_check_filelog_safety` — Detect unsafe log config
- `otel_inspect_target_allocator_state` — TA scrape assignments
- `otel_recommend_collector_topology` — Deployment topology recommendations
- `otel_detect_cardinality` — Cardinality analysis
- `otel_gen_drop_attribute_rules` — Transform YAML generation
- `otel_inspect_sampling_configuration` — Sampling setup review
- `otel_inspect_spanmetrics_config` — SpanMetrics config review
- `otel_analyze_ebpf_footprint` — eBPF security audit

**Mutating Tools (dry_run=True by default):**
- `otel_provision_collector` — Intent-driven collector provisioning (auto-discovers backends, generates best-practice config, creates RBAC)
- `otel_patch_collector` — Expert-level CRD control with full config YAML
- `otel_patch_instrumentation` — Manage Instrumentation CRDs
- `otel_annotate_deployment` — Apply annotations
- `otel_toggle_sampling_strategy` — Switch head/tail sampling
- `otel_enable_spanmetrics_for_service` — Enable spanmetrics connector

## Cross-MCP: Prometheus Scraping After Collector Provisioning

When `otel_provision_collector` generates a collector that exposes metrics via the `prometheus` exporter
(i.e., signals include `metrics` and the collector exports to a Prometheus backend via the prometheus
exporter on port 8889), you **must also create a ServiceMonitor** using the Prometheus MCP server
to complete the scraping pipeline:

```
# In Prometheus MCP Server
prom_apply_servicemonitor(
    service_name="<collector-name>-collector",  # exact K8s service name (OTel Operator adds -collector suffix)
    namespace="monitoring",                       # where Prometheus Operator's ServiceMonitor CRD goes
    target_namespace="<collector-namespace>",     # where the OTel collector service lives
)
```

**Critical**: The exact K8s Service name is NOT the collector CR name. The OTel Operator appends
`-collector` to the CR name. Verify with `kubectl get svc -n <namespace>` before applying the ServiceMonitor.

## Safety Constraints

1. **Mutating tools default to `dry_run=True`**. The agent should always preview changes before applying them. Only set `dry_run=False` after explicit human confirmation.
2. **Read-only tools** are always safe to call. They make no cluster changes.
3. **RBAC**: The server respects Kubernetes RBAC. If the service account lacks permissions, tools will return clear error messages.

## Best Practices

1. **Start with resources** to understand system state before using tools.
2. **Use `detail_level='summary'`** for initial exploration, then `detail_level='full'` for deep dives.
3. **Validate before mutating**: Run `otel_validate_k8sattributes_order` or `otel_check_filelog_safety` before applying config changes.
4. **Cross-MCP composition**: This server pairs with the Prometheus MCP server for full observability coverage. Use Prometheus MCP for PromQL queries and alerting; use this server for OTel config management.

## Token Efficiency

- Resources serve structured JSON, not raw YAML, to minimize token usage.
- Use pagination (`page_size`, `cursor`) for large result sets.
- Use `detail_level='summary'` to get compact overviews.
