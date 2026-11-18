# OpenTelemetry Operator CRD Migration Reference (`v1alpha1` -> `v1beta1`)

## Table of Contents

1. [CRD Version Matrix (`v1beta1` vs `v1alpha1`)](#1-crd-version-matrix-v1beta1-vs-v1alpha1)
2. [`OpenTelemetryCollector` `v1alpha1` -> `v1beta1` Structural Changes](#2-opentelemetrycollector-v1alpha1---v1beta1-structural-changes)
3. [`TargetAllocator` `v1beta1` Configuration](#3-targetallocator-v1beta1-configuration)
4. [Rolling Upgrade Sequence & Rollback via `otel_revert_collector_config`](#4-rolling-upgrade-sequence--rollback-via-otel_revert_collector_config)

---

## 1. CRD Version Matrix (`v1beta1` vs `v1alpha1`)

| Custom Resource Kind | Current API Version | Status |
|---|---|---|
| `OpenTelemetryCollector` (including embedded `spec.targetAllocator`) | `opentelemetry.io/v1beta1` | Required (`v1alpha1` triggers `OP_CRD_VERSION_DEPRECATED`) |
| `TargetAllocator` (standalone CRD reconciled by Operator) | `opentelemetry.io/v1alpha1` | Current Operator version for standalone TargetAllocator CRs |
| `Instrumentation` | `opentelemetry.io/v1alpha1` | Current Operator version for auto-instrumentation |
| `OpAMPBridge` | `opentelemetry.io/v1alpha1` | Current Operator version for OpAMP fleet visibility |

---

## 2. `OpenTelemetryCollector` `v1alpha1` -> `v1beta1` Structural Changes

Key changes in `opentelemetry.io/v1beta1`:
1. **`spec.config` is a structured YAML object (`dict`) instead of a raw multiline string**:
   - In `v1alpha1`, `spec.config` was a YAML string literal (`config: | ...`).
   - In `v1beta1`, `spec.config` is a structured object (`receivers:`, `processors:`, `exporters:`, `service:`).
   - `otel_provision_collector` and `otel_patch_collector` automatically convert and write structured `v1beta1` `spec.config` dicts.
2. **`spec.ports` follows standard Kubernetes `ServicePort` + `ContainerPort` fields**.
3. **`spec.observability.metrics.enableMetrics: true`** automatically creates `ServiceMonitor` / `PodMonitor` resources when Prometheus Operator CRDs are present.

---

## 3. `TargetAllocator` `v1beta1` Configuration

When enabling TargetAllocator inside `OpenTelemetryCollector` (`v1beta1`):

```yaml
spec:
  mode: statefulset
  targetAllocator:
    enabled: true
    allocationStrategy: consistent-hashing
    prometheusCR:
      enabled: true
```

Inspect active TargetAllocators via `otel://target-allocator/{namespace}/{name}` or `otel_survey_cluster`. Whenever auditing TargetAllocator upgrade compatibility:
1. Explicitly report all four OpenTelemetry Operator CRDs together: **`OpenTelemetryCollector` (`opentelemetry.io/v1beta1`, including embedded `spec.targetAllocator`)** vs. **`opentelemetry.io/v1alpha1` standalone `TargetAllocator`, `Instrumentation`, and `OpAMPBridge` CRDs**.
2. Verify `allocationStrategy: consistent-hashing` and `prometheusCR.enabled` selector settings.
3. **Explicitly check and state TargetAllocator/Operator version alignment**: the `target-allocator` container image version (e.g., `0.162.0`) must stay aligned with the OpenTelemetry Operator controller release version during Operator upgrades.

---

## 4. Rolling Upgrade Sequence & Rollback via `otel_revert_collector_config`

1. Always upgrade **Tier 2 Gateway / Tail-Sampler** collectors before **Tier 1 DaemonSet Agents** so downstream OTLP receivers support newer protocol features first.
2. Every mutation performed via `otel_patch_collector` snapshots the previous configuration into the `otel.mcp/last-known-good` annotation (`otel://collector/{namespace}/{name}/history`).
3. If an upgrade fails, execute `otel_revert_collector_config` (`dry_run=False`, `confirm=True`) to restore the previous working configuration immediately.
