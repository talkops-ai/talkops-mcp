---
name: troubleshooting-telemetry-pipelines
description: Diagnoses silent telemetry drops, exporter queue backpressure, OOMKills, CrashLoopBackOff, RBAC 403 denials, TargetAllocator scrape failures, and stalled Operator admission webhooks across OpenTelemetry Collectors and Kubernetes workloads, with instant last-known-good config rollback. Use when traces, metrics, or logs are missing between workloads and backends, collector pods crash or drop data, or collector internal :8888/metrics show saturation. Do not use for greenfield collector provisioning (use provisioning-opentelemetry-collectors), planned Collector version upgrades (use upgrading-opentelemetry-components), Grafana Tempo backend ingester/ring health (use diagnosing-tempo-ingestion-and-health), or Grafana Loki Compactor/Ruler backend diagnostics (use operating-loki-deployments-and-ingestion).
---

# Troubleshooting Telemetry Pipelines

## Preconditions

- Read `otel://server/capabilities` and `otel://cluster/contexts` via MCP resources (never raw `kubectl` CLI commands when MCP is connected) to inspect active toolsets, cluster context, and write permissions (`allow_write`).
- Read `otel://operator/status` to verify Operator pod health and admission webhook availability, plus `otel://collector/{namespace}/{name}/config`, `otel://collector/{namespace}/{name}/history`, and `otel://target-allocator/{namespace}/{name}` when inspecting collector pipelines, snapshots, or TargetAllocator state.

## Diagnostic Workflow Checklist

- [ ] **Step 1 — Run Single-Call Collector Diagnosis**:
  - Call `otel_diagnose_collector` (`namespace`, `name`, `include=["status", "pods", "service", "events", "logs", "metrics", "config_lint", "target_allocator"]`) to inspect pod phase, OOMKills, Kubernetes warning events, static config findings (`CFG_*`), runtime internal metrics (`RT_*`), log error signatures, RBAC permissions (`nodes/stats` + `nodes/proxy` for `kubeletstats`, `monitoring.coreos.com` `servicemonitors`/`podmonitors`/`probes`/`scrapeconfigs` for TargetAllocator), and TargetAllocator pod/selector state in one execution.
  - When troubleshooting TargetAllocator Prometheus scraping, always read `otel://target-allocator/{namespace}/{name}`, pass `"target_allocator"` in `otel_diagnose_collector(..., include=[..., "target_allocator"])`, and explicitly report TargetAllocator pod readiness, `serviceMonitorSelector`/`podMonitorSelector` matching, **and `monitoring.coreos.com` (`servicemonitors`, `podmonitors`, `probes`, `scrapeconfigs`) ClusterRole RBAC permissions** (`monitoring_coreos_rbac`). When troubleshooting `kubeletstats` `403 Forbidden`, explicitly identify missing `get` permissions on **both `nodes/stats` and `nodes/proxy`** in the collector's `ClusterRole`.
  - Consult `references/finding-codes.md` to map every returned `FindingCode` to its root cause and remediation tool (and never blindly delete `MutatingWebhookConfiguration` or `ValidatingWebhookConfiguration` during webhook TLS incidents).
- [ ] **Step 2 — Analyze Collector Internal Metrics (`:8888/metrics`)**:
  - Inspect `pipeline_throughput` and `findings` from `otel_diagnose_collector`.
  - If raw Prometheus metrics text is captured from an offline bundle, run `scripts/analyze_internal_metrics.py --file metrics.txt` to compute drop ratios, queue utilization, and memory pressure.
  - Consult `references/internal-metrics-guide.md` and `references/collector-log-errors.md`.
- [ ] **Step 3 — Verify End-to-End Workload Instrumentation**:
  - If collector pipelines are healthy (`accepted > 0`, `dropped == 0`) but a specific workload's telemetry is missing, call `otel_verify_instrumentation` (`namespace`, `workload_name`, `workload_kind="Deployment"`).
  - Inspect `INST_WEBHOOK_NOT_INJECTED`, `INST_PROTOCOL_MISMATCH`, `INST_GO_MISSING_TARGET_EXE`, or `INST_ENDPOINT_UNREACHABLE` findings.
- [ ] **Step 4 — Validate & Preview Remediation (`dry_run=True`)**:
  - Prepare the corrective action (`otel_patch_collector`, `otel_revert_collector_config`, `otel_patch_instrumentation`, or `otel_manage_workload_instrumentation`) with `dry_run=True`.
  - When remediating `OOMKilled` (`RT_POD_OOMKILLED`) or missing `memory_limiter` (`CFG_MEMORY_LIMITER_NOT_FIRST`), always place `memory_limiter` first in every pipeline and size **both `memory_limiter` (`limit_percentage: 80`, `spike_limit_percentage: 20` or `limit_mib = 80%` of container limit, e.g. `800` MiB on a `1Gi` pod) and `GOMEMLIMIT` (`80%` of container memory limit, e.g. `800MiB` on `1Gi`)** consistently at `80%`.
  - `[GATE]` Present the root-cause findings, unified diff, and GitOps ownership status (`GITOPS_MANAGED`) to the user before mutating cluster state.
- [ ] **Step 5 — Apply Fix or Revert & Re-Verify**:
  - If a recent config mutation broke the collector, read `otel://collector/{namespace}/{name}/history`, preview rollback via `otel_revert_collector_config(namespace=..., name=..., dry_run=True)`, and `[GATE]` apply with `otel_revert_collector_config(..., dry_run=False, confirm=True)`.
  - Otherwise apply the validated fix (`otel_patch_collector`, `otel_configure_receivers`, or `otel_patch_instrumentation`) with `dry_run=False` (and `confirm=True` when required) after `dry_run=True` preview, and re-run `otel_diagnose_collector` to confirm all `ERROR` findings are resolved.

## Reference & Script Inventory

- `references/finding-codes.md` — Complete mapping of `CFG_*`, `RT_*`, `OP_*`, `INST_*`, `SEC_*`, and `GITOPS_MANAGED` finding codes to root causes and remediation tools.
- `references/internal-metrics-guide.md` — OpenTelemetry Collector `v0.120+` internal telemetry counter formulas and saturation thresholds.
- `references/collector-log-errors.md` — Common collector stderr log patterns (`rpc error`, `401 Unauthorized`, `429 Too Many Requests`, `permanent error`) and fixes.
- `scripts/analyze_internal_metrics.py` — Offline Prometheus `:8888/metrics` parser that computes drop ratios, queue utilization, and `RT_*` findings.
