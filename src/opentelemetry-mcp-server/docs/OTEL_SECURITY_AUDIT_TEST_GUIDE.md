# Security Audit Test Guide — OpenTelemetry MCP Server

**Phase 5 of 5** in the OTel Demo end-to-end journey.
**Previous phase**: [Sampling Review](OTEL_SAMPLING_TEST_GUIDE.md)

> This is the final phase. Everything is onboarded, pipelines are validated, cardinality
> is controlled, and sampling is configured. Now you audit the security posture of all
> OTel components — eBPF agents, RBAC surface, TLS configuration, and endpoint exposure.

---

## Prerequisites (Completed in Phase 4)

| Component | Status |
|-----------|--------|
| ✅ Services onboarded | Phase 1 — collectors provisioned, instrumentation active |
| ✅ Pipelines validated | Phase 2 — processor ordering, filelog safety confirmed |
| ✅ Cardinality controlled | Phase 3 — SpanMetrics dimensions within limits |
| ✅ Sampling reviewed | Phase 4 — strategies generated and ready to apply |

---

## The Starting Point

Your observability stack is fully operational. Before going to production, you need to answer:

1. **Are there eBPF agents with elevated privileges?** — privileged mode, SYS_ADMIN, hostPID?
2. **What RBAC surface does the collector need?** — ClusterRole for k8sattributes metadata?
3. **Are exporter connections secure?** — TLS enabled or insecure?
4. **Where is telemetry being sent?** — Internal endpoints or external exposure?
5. **Is the Target Allocator adding RBAC surface?** — PrometheusCR access?

---

## Phase 1: eBPF Footprint Analysis

eBPF-based observability agents (like Grafana Beyla or OpenTelemetry eBPF) require elevated
kernel privileges. This scan detects them and assesses risk.

### Step 1.1: Scan OTel Demo Namespace

| Field | Value |
|-------|-------|
| **Prompt** | `Scan for eBPF instrumentation pods in the "otel-demo" namespace and assess their security posture.` |
| **Tool** | `otel_analyze_ebpf_footprint` |
| **Parameters** | `{"namespace": "otel-demo"}` |
| **Internal action** | Scans pods matching known eBPF agent labels: `app.kubernetes.io/name=otel-ebpf`, `app.kubernetes.io/name=beyla`, `app=grafana-beyla`, `app=opentelemetry-ebpf`. For each matching pod: inspects `securityContext.privileged`, `securityContext.capabilities.add`, `hostPID`, and `/sys`/`/proc` volume mounts. Deduplicates by `namespace/name`, limits to 50 pods. |
| **Expected output** | `total_ebpf_pods: 0`, `risk_level: "low"`, `recommendations: ["No security concerns detected"]` |

**Why zero eBPF pods?** The OTel Demo uses SDK-based (manual) instrumentation, not eBPF agents.
eBPF agents are an alternative approach that instruments at the kernel level without code changes.

### Step 1.2: Scan Entire Cluster

| Field | Value |
|-------|-------|
| **Prompt** | `Are there any eBPF agents running with privileged mode in the cluster?` |
| **Tool** | `otel_analyze_ebpf_footprint` |
| **Parameters** | `{}` (no namespace — scans all) |
| **Internal action** | Same but uses `list_pod_for_all_namespaces()` instead of namespace-scoped |
| **Expected output** | `namespace: "all"`, `total_ebpf_pods: 0`, `risk_level: "low"` |

**Risk level thresholds:**

| Condition | Risk Level | Recommendation |
|-----------|-----------|----------------|
| No eBPF pods | `low` | No security concerns |
| eBPF pods with `hostPID` | `medium` | Review hostPID requirement — newer agents may not need it |
| eBPF pods with `privileged: true` | `high` | Replace privileged mode with minimal capabilities (BPF, PERFMON, SYS_PTRACE) |
| eBPF pods with `SYS_ADMIN` capability | `critical` | Replace SYS_ADMIN with fine-grained capabilities (BPF, PERFMON) |

**Manual validation:**
```bash
# Check for eBPF-related pods across the cluster
kubectl get pods -A -l "app.kubernetes.io/name=otel-ebpf" 2>/dev/null
kubectl get pods -A -l "app.kubernetes.io/name=beyla" 2>/dev/null
kubectl get pods -A -l "app=grafana-beyla" 2>/dev/null
# Expected: no resources found for all
```

---

## Phase 2: Collector Security Review

### Step 2.1: List All Collectors

| Field | Value |
|-------|-------|
| **Prompt** | `List all OTel collectors in the "otel-demo" namespace.` |
| **Tool** | `otel_list_collectors` |
| **Parameters** | `{"namespace": "otel-demo"}` |
| **Internal action** | Lists OpenTelemetryCollector CRDs, returns pipeline topology and features |
| **Expected output** | 1+ collectors with pipeline details |

**Security-relevant collector findings (OTel Demo):**

| Finding | Detail | Severity |
|---------|--------|----------|
| DaemonSet mode | Collector pods run on every node → wider blast radius | ℹ️ Info (expected for filelog) |
| OTLP receivers on `0.0.0.0` | `grpc: 0.0.0.0:4317`, `http: 0.0.0.0:4318` → any pod in cluster can send telemetry | ⚠️ Review |
| Insecure exporters | All exporters use `tls.insecure: true` | ⚠️ Acceptable for demo, not production |

### Step 2.2: RBAC Surface via K8s Enrichment

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the k8sattributes enrichment profile for collector "otel-demo-collector" in "otel-demo".` |
| **Resource** | `otel://k8s-enrichment/otel-demo/otel-demo-collector` |
| **Internal action** | Parses k8sattributes config, determines RBAC requirements based on extracted metadata fields |
| **Key output** | `requires_cluster_role: true` (13 metadata fields including cross-namespace resources) |

**RBAC implications per metadata field:**

| Metadata Field | Required RBAC |
|----------------|---------------|
| `k8s.pod.name`, `k8s.pod.uid`, `k8s.pod.start_time` | Role: pods GET/LIST |
| `k8s.namespace.name` | Role: namespaces GET |
| `k8s.container.name`, `container.image.*` | Role: pods GET (container spec) |
| `k8s.deployment.name` | **ClusterRole**: deployments GET/LIST |
| `k8s.replicaset.name` | **ClusterRole**: replicasets GET/LIST |
| `k8s.daemonset.name` | **ClusterRole**: daemonsets GET/LIST |
| `k8s.node.name` | **ClusterRole**: nodes GET/LIST |
| `service.name`, `service.version` | Role: pods GET (labels/env) |

**Least-privilege recommendation:** If you only need `k8s.pod.name` and `k8s.namespace.name`,
remove the deployment/replicaset/daemonset/node fields to downgrade from ClusterRole to namespace Role.

### Step 2.3: Target Allocator Security

| Field | Value |
|-------|-------|
| **Prompt** | `Check the Target Allocator configuration for "otel-demo-collector" in "otel-demo".` |
| **Tool** | `otel_inspect_target_allocator_state` |
| **Parameters** | `{"namespace": "otel-demo", "name": "otel-demo-collector"}` |
| **Internal action** | Reads `spec.targetAllocator` from CRD |
| **Expected output** | `enabled: false` — no additional RBAC surface from TA |

**If TA were enabled, additional RBAC needed:**
- `servicemonitors.monitoring.coreos.com` GET/LIST/WATCH
- `podmonitors.monitoring.coreos.com` GET/LIST/WATCH
- `endpoints` GET/LIST/WATCH
- `services` GET/LIST/WATCH

---

## Phase 3: Service Telemetry Endpoint Review

### Step 3.1: List Instrumented Services

| Field | Value |
|-------|-------|
| **Prompt** | `List all instrumented services in "otel-demo" and check for security concerns.` |
| **Tool** | `otel_list_instrumented_services` |
| **Parameters** | `{"namespace": "otel-demo"}` |
| **Internal action** | Lists all Deployments; for each, checks OTel annotations, init containers, OTEL_* env vars, and telemetry endpoint |

**Security-relevant output fields:**

| Field | What to Check |
|-------|---------------|
| `endpoint_configured` | Where telemetry is sent — should be internal cluster DNS (e.g., `http://otel-collector:4317`), NOT external |
| `signals_detected` | Which signals are emitted — sensitive data may be in traces (SQL queries, user data) |
| `sdk_env_vars_present` | Are OTEL_* env vars set correctly? |
| `warnings` | Mismatches that could indicate misconfiguration |

**Manual validation:**
```bash
# Check telemetry endpoint for a specific service
kubectl get deploy recommendation -n otel-demo \
  -o jsonpath='{.spec.template.spec.containers[0].env}' | python3 -m json.tool | grep -A1 "OTEL_EXPORTER"
# Expected: OTEL_EXPORTER_OTLP_ENDPOINT = http://otel-collector:4317
# ✅ Internal endpoint (not exposed externally)
```

### Step 3.2: Inspect Exporter TLS Configuration

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the full configuration of the collector "otel-demo-collector" in "otel-demo".` |
| **Tool** | `otel_get_collector` |
| **Parameters** | `{"namespace": "otel-demo", "name": "otel-demo-collector", "detail_level": "full"}` |
| **What to check** | In the `raw_config_yaml`, look at each exporter's `tls` section |

**OTel Demo exporter TLS status:**

| Exporter | Endpoint | TLS | Production Recommendation |
|----------|----------|-----|---------------------------|
| `otlp/jaeger` | `jaeger:4317` | `insecure: true` ❌ | Enable mTLS with cert rotation |
| `otlphttp/prometheus` | `prometheus:9090/api/v1/otlp` | `insecure: true` ❌ | Enable TLS |
| `opensearch` | `opensearch:9200` | `insecure: true` ❌ | Enable TLS with CA cert |

---

## Phase 4: Full Security Audit Flow

This is the recommended end-to-end security audit:

| Step | Prompt | Tool / Resource | What It Checks |
|------|--------|----------------|----------------|
| 1 | `Scan eBPF in "otel-demo"` | `otel_analyze_ebpf_footprint(namespace="otel-demo")` | Privileged pods, capabilities, host mounts |
| 2 | `List collectors in "otel-demo"` | `otel_list_collectors(namespace="otel-demo")` | Collector count, modes, listener bindings |
| 3 | `Inspect enrichment RBAC` | `otel://k8s-enrichment/otel-demo/otel-demo-collector` | Metadata fields → RBAC requirements |
| 4 | `Check Target Allocator` | `otel_inspect_target_allocator_state(ns, name)` | Additional CRD access needed? |
| 5 | `List instrumented services` | `otel_list_instrumented_services(namespace="otel-demo")` | Endpoint exposure, signal types |
| 6 | `Get full collector config` | `otel_get_collector(detail_level="full")` | Exporter TLS, receiver bindings |

---

## OTel Demo Security Summary

| Category | Finding | Severity | Action Required |
|----------|---------|----------|-----------------|
| **eBPF agents** | None deployed (SDK-based instrumentation) | ✅ Low | None |
| **Telemetry endpoints** | All internal (`otel-collector:4317`) | ✅ Good | None |
| **Exporter TLS** | `insecure: true` on all 3 exporters | ⚠️ Warning | Enable TLS for production |
| **Receiver binding** | `0.0.0.0:4317/4318` — accepts from any pod | ⚠️ Warning | Use NetworkPolicy to restrict |
| **RBAC surface** | ClusterRole required (13 metadata fields) | ⚠️ Review | Consider reducing metadata fields |
| **Target Allocator** | Not enabled | ✅ Low | No additional RBAC |
| **DaemonSet mode** | Runs on every node | ℹ️ Info | Expected for filelog collection |

---

## Phase Summary — End of Journey

You've completed all 5 phases of the OTel Demo journey:

| Phase | Guide | What You Did |
|-------|-------|--------------|
| **1. Onboarding** | [OTEL_ONBOARDING_TEST_GUIDE](OTEL_ONBOARDING_TEST_GUIDE.md) | Discovered services → looked up languages → provisioned collectors → created Instrumentation CRs → annotated deployments |
| **2. Pipeline Investigation** | [OTEL_PIPELINE_INVESTIGATION_TEST_GUIDE](OTEL_PIPELINE_INVESTIGATION_TEST_GUIDE.md) | Verified collector health → validated processor ordering → audited filelog safety → inspected enrichment → checked topology |
| **3. Cardinality Audit** | [OTEL_CARDINALITY_AUDIT_TEST_GUIDE](OTEL_CARDINALITY_AUDIT_TEST_GUIDE.md) | Detected cardinality issues → inspected SpanMetrics → generated drop rules → enabled SpanMetrics on new collectors |
| **4. Sampling Review** | [OTEL_SAMPLING_TEST_GUIDE](OTEL_SAMPLING_TEST_GUIDE.md) | Inspected current sampling → generated head and tail sampling patches → reviewed trade-offs |
| **5. Security Audit** | *(this guide)* | Scanned eBPF → reviewed RBAC → checked TLS → audited endpoint exposure → generated summary |

### Total Tools & Resources Exercised

| Category | Count | Examples |
|----------|-------|---------|
| **Discovery tools** | 3 | `otel_list_collectors`, `otel_get_collector`, `otel_list_instrumented_services` |
| **Instrumentation tools** | 3 | `otel_lookup_instrumentation`, `otel_patch_instrumentation`, `otel_annotate_deployment` |
| **Provisioning tools** | 2 | `otel_provision_collector`, `otel_patch_collector` |
| **Validation tools** | 3 | `otel_validate_k8sattributes_order`, `otel_check_filelog_safety`, `otel_recommend_collector_topology` |
| **Cardinality tools** | 3 | `otel_detect_cardinality`, `otel_gen_drop_attribute_rules`, `otel_inspect_spanmetrics_config` |
| **SpanMetrics tools** | 1 | `otel_enable_spanmetrics_for_service` |
| **Sampling tools** | 2 | `otel_inspect_sampling_configuration`, `otel_toggle_sampling_strategy` |
| **Security tools** | 2 | `otel_analyze_ebpf_footprint`, `otel_inspect_target_allocator_state` |
| **Resources** | 9 | `otel://system/health`, `otel://collector/*`, `otel://k8s-enrichment/*`, `otel://logs-profile/*`, `otel://spanmetrics/*`, `otel://target-allocator/*`, `otel://instrumentation/*`, `otel://lang/*`, `otel://registry/languages` |
