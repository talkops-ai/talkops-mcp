---
name: provisioning-opentelemetry-collectors
description: Designs, provisions, configures, and validates OpenTelemetry Collector topologies on Kubernetes across DaemonSet agents, Deployment gateways, and StatefulSet tail-samplers or Target Allocator pools. Use when deploying new OpenTelemetry collectors, setting up two-tier Agent-to-Gateway architectures, configuring Kubernetes infrastructure receivers (kubeletstats, hostmetrics, k8s_cluster, k8sobjects, filelog, prometheus_ta), decommissioning retired collectors, or generating offline collector manifests for GitOps. Do not use for application SDK or eBPF workload injection (use instrumenting-kubernetes-workloads), Collector version upgrades (use upgrading-opentelemetry-components), live CrashLoop or OOM triage (use troubleshooting-telemetry-pipelines), OTTL PII or cardinality filtering (use controlling-telemetry-cardinality-and-noise), or Prometheus ServiceMonitor CRD authoring (use configuring-prometheus-scraping-and-discovery).
---

# Provisioning OpenTelemetry Collectors

Designs and provisions production-ready `OpenTelemetryCollector` Custom Resources and least-privilege RBAC on Kubernetes, routing traces to Tempo/Jaeger, metrics to Prometheus/Mimir, and logs to Loki/OpenSearch.

## Preconditions

1. Read `otel://server/capabilities` and `otel://cluster/contexts` via OpenTelemetry MCP resources (never raw `kubectl` CLI commands when MCP is connected) to verify Kubernetes connectivity, active cluster context, enabled toolsets, and whether write operations (`write_enabled`) are permitted.
2. Read `otel://operator/status` and call `otel_survey_cluster` to confirm the OpenTelemetry Operator and admission webhook are healthy, and inspect existing collectors via `otel://collectors/{namespace}`, `otel://collector/{namespace}/{name}`, `otel://collector/{namespace}/{name}/config`, and `otel://k8s-enrichment/{namespace}/{collector}`.
3. If `write_enabled` is `false` or the target namespace is GitOps-managed (`GITOPS_MANAGED`), do not call mutating apply actions (`dry_run=False`); use read-only inspection or `dry_run=True` plus the bundled offline scripts (`scripts/plan_collector_topology.py`, `scripts/lint_collector_config.py`, `scripts/render_collector_cr.py`) and **always output the complete multi-document YAML bundle containing both the `opentelemetry.io/v1beta1` `OpenTelemetryCollector` CR and its companion least-privilege `ClusterRole` + `ClusterRoleBinding` RBAC manifests** in your final response.

## Collector Architecture Selection

| Topology Role | K8s Mode | Primary Responsibilities | When to Select |
|---|---|---|---|
| `agent` | `daemonset` | Node-local `otlp` ingest, `filelog` container logs (`/var/log/pods`), `kubeletstats`, `hostmetrics`, `k8sattributes` enrichment (`K8S_NODE_NAME` filter) | Default node-level collection tier on clusters with $\ge 3$ nodes or container log collection |
| `gateway` | `deployment` | Cross-node batching, OTTL PII redaction, `spanmetrics`/`servicegraph` connectors, authenticated backend export with `sending_queue` + `retry_on_failure` | Central aggregation tier receiving OTLP from DaemonSet agents |
| `tail-sampler` | `statefulset` | Stateful `tail_sampling` trace evaluation with stable Pod DNS (`{name}-collector-0..N`) | Required when `tail_sampling` runs across $>1$ replica fronted by a `loadbalancing` exporter (`routing_key: traceID`) |
| `all-in-one` | `deployment` / `daemonset` / `statefulset` | Single-tier ingest, enrichment, and backend export (`statefulset` when `prometheus_scrape=True`) | Development/staging namespaces or small single-tier clusters ($< 10$ nodes) |

See [references/collector-topology-matrix.md](references/collector-topology-matrix.md), [references/k8s-receivers-and-rbac.md](references/k8s-receivers-and-rbac.md), and [references/exporter-routing-patterns.md](references/exporter-routing-patterns.md) for detailed sizing, RBAC, and exporter patterns.

## End-to-End Provisioning Workflow

- [ ] **Step 1 — Survey Cluster & Backends**: Call `otel_survey_cluster(namespaces=[target_ns], detail="summary")` to inspect Operator readiness, existing `OpenTelemetryCollector` CRs, and discovered backend services (Jaeger, Tempo, Prometheus, VictoriaMetrics, Mimir, Loki, OpenSearch).
- [ ] **Step 2 — Plan Topology & Sizing**: Choose `role` (`agent`, `gateway`, `tail-sampler`, `all-in-one`) and required `infrastructure_receivers` (`kubeletstats`, `hostmetrics`, `k8s_cluster`, `k8sobjects`). Run `python scripts/plan_collector_topology.py --nodes <N> --signals traces,metrics,logs` when target cluster scale (`<N>` nodes) is specified, and pass `pipeline_options={"node_count": <N>, "cluster_size": "small"|"medium"|"large"}` into `otel_provision_collector` so CPU/memory limits and `GOMEMLIMIT` (`80%` of memory limit) match the target cluster scale even when testing on a single-node cluster.
- [ ] **Step 3 — Preview Collector & RBAC (`dry_run=True`)**: Call `otel_provision_collector(namespace=target_ns, signals=[...], role=..., exporter_targets=..., pipeline_options=..., dry_run=True)` and inspect `generated_config_yaml`, `spec_yaml`, `rbac_resources`, and `findings`.
- [ ] **Step 4 — Validate Zero Error Findings**: Ensure no `CFG_*` or `SEC_*` findings have `severity == "error"`. Verify that any backend credentials use `credentials_secret_refs` (`${env:VAR}`) rather than inline plaintext tokens.
- [ ] **Step 5 — [GATE] Confirm & Apply Collector**: Present the `spec_yaml`, `rbac_yaml`, resource sizing (`GOMEMLIMIT`), and any `GITOPS_MANAGED` warning to the user. When applying, always call `otel_provision_collector(..., dry_run=False, confirm=True)` (explicitly passing both `dry_run=False` and `confirm=True`).
- [ ] **Step 6 — Configure Additional Infrastructure Receivers (Optional)**: If adding `kubeletstats`, `hostmetrics`, `k8s_cluster`, `k8s_events`, `filelog`, or `prometheus_ta` to an existing collector, inspect `otel://k8s-enrichment/{namespace}/{collector}` and `otel://target-allocator/{namespace}/{name}` as needed, preview with `otel_configure_receivers(..., dry_run=True)`, and `[GATE]` apply with `dry_run=False, confirm=True`.
- [ ] **Step 7 — Verify Runtime Health**: Call `otel_diagnose_collector(namespace=target_ns, name=collector_name)` and `otel_validate_collector_config` to verify pod readiness, Service endpoints, pipeline wiring, and `:8888/metrics` internal telemetry flow.
- [ ] **Step 8 — Decommission Obsolete Collectors or TargetAllocators (Optional)**: First verify via `otel://instrumentations/{namespace}` and `otel_survey_cluster` that no workloads or `Instrumentation` CRs still target the retired collector, then preview with `otel_delete_resource(kind="OpenTelemetryCollector", namespace=target_ns, name=collector_name, dry_run=True)` and `[GATE]` execute with `dry_run=False, confirm=True`.

## Offline Scripts (Air-Gapped / GitOps Mode)

- `scripts/plan_collector_topology.py`: Computes recommended topology (`single-tier`, `two-tier`, `three-tier-tail-sampling`), CPU/memory limits, `GOMEMLIMIT`, and `memory_limiter` settings from node/workload counts.
- `scripts/lint_collector_config.py`: Lints a raw Collector YAML file offline for pipeline referential integrity, `memory_limiter` ordering, double batching, `filelog` safety, and inline secrets.
- `scripts/render_collector_cr.py`: Renders a complete multi-document YAML manifest (`OpenTelemetryCollector` CR + `ClusterRole` + `ClusterRoleBinding`) without cluster access.
