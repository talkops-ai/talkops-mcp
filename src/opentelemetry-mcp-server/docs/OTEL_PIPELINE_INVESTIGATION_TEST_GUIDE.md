# Pipeline Investigation Test Guide — OpenTelemetry MCP Server

**Phase 2 of 5** in the OTel Demo end-to-end journey.
**Previous phase**: [Onboarding](OTEL_ONBOARDING_TEST_GUIDE.md)
**Next phase**: [Cardinality Audit](OTEL_CARDINALITY_AUDIT_TEST_GUIDE.md)

> After onboarding (Phase 1), collectors are running and telemetry is flowing. This phase
> validates that pipelines are healthy, processor ordering follows best practices,
> filelog collection is safe, and enrichment profiles are correct.

---

## Prerequisites (Completed in Phase 1)

| Component | Status |
|-----------|--------|
| ✅ Services discovered | `otel_list_instrumented_services(namespace="otel-demo")` |
| ✅ Collectors running | `otel-demo-collector` (shared) + any provisioned per-app collectors |
| ✅ Instrumentation active | Deployments annotated, init containers injected |

---

## The Starting Point

Phase 1 onboarded your services and provisioned collectors. Now you need to answer:

1. **Are the collectors healthy?** — Are pods running? Are pipelines receiving data?
2. **Is the processor ordering correct?** — `memory_limiter` before `k8sattributes` before `batch`?
3. **Is filelog collection safe?** — No feedback loops? Checkpoints configured?
4. **Is K8s enrichment properly configured?** — Correct metadata fields? RBAC sufficient?
5. **Is the deployment topology optimal?** — Right mode (daemonset/deployment/statefulset)?

---

## Phase 1: Collector Health Check

### Step 1.1: List All Collectors

| Field | Value |
|-------|-------|
| **Prompt** | `List all OTel collectors in the cluster.` |
| **Tool** | `otel_list_collectors` |
| **Parameters** | `{}` |
| **Internal action** | Calls `list_cluster_custom_object()` for `opentelemetrycollectors` CRD across all namespaces; parses config, extracts pipelines, detects features |
| **Expected output** | `otel-demo-collector` (shared) + any collectors provisioned in Phase 1 |

**What to check in the output:**

| Field | What to Verify |
|-------|----------------|
| `status.ready_replicas` | Should match `status.replicas` |
| `mode` | Should match your provisioning intent (daemonset for logs, deployment for OTLP-only) |
| `pipelines` | Should have pipelines for all signals you requested |
| `spanmetrics_enabled` | If you enabled it in Phase 1, should be `true` |

### Step 1.2: Filter by Provisioned Collectors

| Field | Value |
|-------|-------|
| **Prompt** | `List OTel collectors with label "talkops.ai/provisioned=true".` |
| **Tool** | `otel_list_collectors` |
| **Parameters** | `{"label_selector": "talkops.ai/provisioned=true"}` |
| **Internal action** | Same as 1.1 but filters by label selector |
| **Expected output** | Only collectors created via `otel_provision_collector` (they auto-get this label) |

### Step 1.3: Filter by Namespace

| Field | Value |
|-------|-------|
| **Prompt** | `List OTel collectors in the "otel-demo" namespace.` |
| **Tool** | `otel_list_collectors` |
| **Parameters** | `{"namespace": "otel-demo"}` |
| **Internal action** | Scopes to single namespace via `list_namespaced_custom_object()` |
| **Expected output** | All collectors in `otel-demo` |

---

## Phase 2: Full Collector Inspection

### Step 2.1: Get Full Details of the Shared Collector

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the full configuration of the collector "otel-demo-collector" in the "otel-demo" namespace.` |
| **Tool** | `otel_get_collector` |
| **Parameters** | `{"namespace": "otel-demo", "name": "otel-demo-collector", "detail_level": "full"}` |
| **Internal action** | Reads the CRD via `get_namespaced_custom_object()`, parses inline config, builds `CollectorInstance` model with full pipeline topology, status, and raw YAML |
| **Key output to verify** | 3 pipelines (traces/metrics/logs), processor chains, exporter endpoints, features |

**Expected pipeline topology (OTel Demo):**

```
Traces:   otlp → memory_limiter → k8sattributes → resourcedetection → resource → transform → batch → otlp/jaeger + spanmetrics
Metrics:  otlp + spanmetrics → memory_limiter → k8sattributes → resourcedetection → resource → batch → otlphttp/prometheus
Logs:     otlp + filelog → memory_limiter → k8sattributes → resourcedetection → resource → batch → opensearch + debug
```

### Step 2.2: Inspect via Resource (Alternative)

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the full config of collector "otel-demo-collector" in "otel-demo".` |
| **Resource** | `otel://collector/otel-demo/otel-demo-collector` |
| **Internal action** | Same data as `otel_get_collector(detail_level="full")` — resources always return full detail |

**Manual validation:**
```bash
kubectl get opentelemetrycollectors -n otel-demo otel-demo-collector -o yaml
```

---

## Phase 3: Processor Ordering Validation

The processor order in OTel Collector pipelines is critical:
1. `memory_limiter` must be **first** (prevents OOM kills)
2. `k8sattributes` must come **before** `batch` (enriches individual spans/metrics)
3. `batch` should be **last** (batches before export)

### Step 3.1: Validate All Pipelines

| Field | Value |
|-------|-------|
| **Prompt** | `Validate the processor ordering for collector "otel-demo-collector" in "otel-demo".` |
| **Tool** | `otel_validate_k8sattributes_order` |
| **Parameters** | `{"namespace": "otel-demo", "name": "otel-demo-collector"}` |
| **Internal action** | Reads all pipelines in the collector; for each, verifies: (1) `memory_limiter` appears before `k8sattributes`, (2) `k8sattributes` appears before `batch`, (3) no processors are duplicated. Returns per-pipeline validation results. |
| **Expected output** | `all_valid: true` — the demo follows best-practice ordering |

**OTel Demo processor order (all 3 pipelines):**
```
memory_limiter → k8sattributes → resourcedetection → resource → [transform] → batch
```
✅ `memory_limiter` is first, `k8sattributes` before `batch`, `batch` is last.

### Step 3.2: Validate a Specific Pipeline

| Field | Value |
|-------|-------|
| **Prompt** | `Validate the processor ordering for the traces pipeline in "otel-demo-collector".` |
| **Tool** | `otel_validate_k8sattributes_order` |
| **Parameters** | `{"namespace": "otel-demo", "name": "otel-demo-collector", "pipeline_name": "traces"}` |
| **Internal action** | Same but only validates the `traces` pipeline |

**Manual validation:**
```bash
kubectl get opentelemetrycollectors -n otel-demo otel-demo-collector \
  -o jsonpath='{.spec.config.service.pipelines.traces.processors}'
# ["memory_limiter","k8sattributes","resourcedetection","resource","transform","batch"]
```

---

## Phase 4: Filelog Safety Audit

If your collector has a `filelog` receiver (for container log collection), there are critical
safety checks — without them, the collector can create feedback loops or lose log data.

### Step 4.1: Audit Filelog Safety

| Field | Value |
|-------|-------|
| **Prompt** | `Check if the filelog receiver in "otel-demo-collector" has any safety issues.` |
| **Tool** | `otel_check_filelog_safety` |
| **Parameters** | `{"namespace": "otel-demo", "name": "otel-demo-collector"}` |
| **Internal action** | Finds filelog receivers in config. For each, checks: (1) `has_storage_checkpoint` — file_storage configured for offset tracking? (2) `has_exclude_self` — does the exclude pattern prevent collecting the collector's own logs? (3) `has_resource_detection` — does the logs pipeline have `resourcedetection` processor? Generates warnings for any failures. |
| **Expected output** | `safe: true`, `warnings: []` — all 3 safety checks pass |

**OTel Demo filelog config:**

| Safety Check | Expected | Why It Matters |
|---|---|---|
| `has_storage_checkpoint` | ✅ `file_storage` | Prevents log re-processing on collector restart |
| `has_exclude_self` | ✅ `otel-collector*` in exclude | Prevents infinite feedback loop (collector logging its own logs) |
| `has_resource_detection` | ✅ `resourcedetection` in processors | Adds host metadata to log records |

### Step 4.2: Inspect via Resource

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the filelog receiver configuration for collector "otel-demo-collector" in "otel-demo".` |
| **Resource** | `otel://logs-profile/otel-demo/otel-demo-collector` |
| **Internal action** | Returns the full filelog profile including include/exclude paths, operators, storage, and safety checks |
| **Key output** | `include_paths: ["/var/log/pods/otel-demo_*/*/*.log"]`, `exclude_paths: ["/var/log/pods/otel-demo_otel-collector*/*/*.log"]`, `storage: "file_storage"` |

**Manual validation:**
```bash
kubectl get opentelemetrycollectors -n otel-demo otel-demo-collector \
  -o jsonpath='{.spec.config.receivers.filelog.exclude}'
# ["/var/log/pods/otel-demo_otel-collector*/*/*.log"]
```

---

## Phase 5: K8s Enrichment Inspection

The `k8sattributes` processor enriches telemetry with Kubernetes metadata. This requires RBAC
and proper configuration.

### Step 5.1: Inspect Enrichment Profile

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the k8sattributes enrichment profile for collector "otel-demo-collector" in "otel-demo".` |
| **Resource** | `otel://k8s-enrichment/otel-demo/otel-demo-collector` |
| **Internal action** | Parses `k8sattributes` processor config; extracts metadata fields, filter settings, pod association sources, and pipeline positions |
| **Key output** | 13 metadata fields, `filter_node: K8S_NODE_NAME`, `pipeline_positions: [logs[1], metrics[1], traces[1]]`, `requires_cluster_role: true` |

**OTel Demo enrichment profile:**

| Field | Value |
|-------|-------|
| Metadata extracted | 13 fields: `k8s.namespace.name`, `k8s.pod.name`, `k8s.pod.uid`, `k8s.node.name`, `k8s.pod.start_time`, `k8s.deployment.name`, `k8s.replicaset.name`, `k8s.daemonset.name`, `k8s.container.name`, `container.image.tag`, `container.image.name`, `service.name`, `service.version` |
| Filter | Node-level via `K8S_NODE_NAME` env var |
| Pod association | 3 sources: `resource_attribute` (k8s.pod.ip), `resource_attribute` (k8s.pod.uid), `connection` |
| Pipeline positions | Index 1 in all 3 pipelines (after `memory_limiter`) |
| RBAC | ClusterRole required (deployment, replicaset, daemonset metadata) |

---

## Phase 6: Target Allocator & Topology

### Step 6.1: Inspect Target Allocator

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the Target Allocator configuration for "otel-demo-collector" in "otel-demo".` |
| **Resource** | `otel://target-allocator/otel-demo/otel-demo-collector` |
| **Internal action** | Reads `spec.targetAllocator` from CRD |
| **Expected output** | `enabled: false` — the demo includes TA config but doesn't enable it |

### Step 6.2: Get Topology Recommendation

| Field | Value |
|-------|-------|
| **Prompt** | `Recommend a collector topology for traces, metrics, and logs with 20 workloads on a small cluster.` |
| **Tool** | `otel_recommend_collector_topology` |
| **Parameters** | `{"signals": ["traces", "metrics", "logs"], "workload_count": 20, "cluster_size": "small"}` |
| **Internal action** | Evaluates signal requirements: logs → needs DaemonSet (filelog requires node access). Sizes resources for small cluster. |
| **Expected output** | `mode: "daemonset"` (forced by logs signal), `sizing: {cpu_request: "100m", memory_limit: "512Mi"}` |

---

## Phase Summary

At the end of this phase, you've verified:

| What | Tool / Resource | Status |
|------|----------------|--------|
| ✅ All collectors found and healthy | `otel_list_collectors` | Pods running, pipelines active |
| ✅ Full pipeline topology inspected | `otel_get_collector(detail_level="full")` | Receivers → processors → exporters verified |
| ✅ Processor ordering validated | `otel_validate_k8sattributes_order` | `all_valid: true` |
| ✅ Filelog safety audited | `otel_check_filelog_safety` | `safe: true`, no warnings |
| ✅ K8s enrichment verified | `otel://k8s-enrichment/{ns}/{name}` | 13 metadata fields, RBAC assessed |
| ✅ Target Allocator checked | `otel://target-allocator/{ns}/{name}` | State documented |
| ✅ Topology recommendation obtained | `otel_recommend_collector_topology` | Optimal mode confirmed |

**Next step →** [Cardinality Audit](OTEL_CARDINALITY_AUDIT_TEST_GUIDE.md): Now that telemetry is flowing, check if metric cardinality is under control and SpanMetrics are configured optimally.
