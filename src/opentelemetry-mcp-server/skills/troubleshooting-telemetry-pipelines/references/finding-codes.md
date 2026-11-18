# Deterministic Finding Codes Reference (`FindingCode`)

## Table of Contents

1. [Configuration Findings (`CFG_*`)](#1-configuration-findings-cfg_)
2. [Runtime & Pipeline Findings (`RT_*`)](#2-runtime--pipeline-findings-rt_)
3. [Operator & Cluster Findings (`OP_*`)](#3-operator--cluster-findings-op_)
4. [Instrumentation Findings (`INST_*`)](#4-instrumentation-findings-inst_)
5. [Security & Governance Findings (`SEC_*` & `GITOPS_MANAGED`)](#5-security--governance-findings-sec_--gitops_managed)

---

## 1. Configuration Findings (`CFG_*`)

| Finding Code | Default Severity | Root Cause | Recommended Remediation Tool |
|---|---|---|---|
| `CFG_UNDECLARED_COMPONENT` | `ERROR` | A pipeline references a receiver, processor, exporter, or connector not defined in its top-level section | `otel_patch_collector` |
| `CFG_ORPHAN_COMPONENT` | `WARNING` | A component is defined at the top level but not wired into any `service.pipelines.*` entry | `otel_patch_collector` |
| `CFG_PROCESSOR_ORDER_INVALID` | `ERROR` | Processor order violates `memory_limiter` first and `batch` last invariant | `otel_patch_collector` |
| `CFG_MISSING_MEMORY_LIMITER` | `WARNING` | Pipeline lacks `memory_limiter`, risking Go runtime OOMKills under traffic spikes | `otel_patch_collector` |
| `CFG_MISSING_BATCH_PROCESSOR` | `WARNING` | Pipeline lacks `batch` processor and exporter sending queue batching | `otel_patch_collector` |
| `CFG_K8SATTRIBUTES_NO_NODE_FILTER` | `WARNING` | DaemonSet collector runs `k8sattributes` without `filter.node_from_env_var: K8S_NODE_NAME` | `otel_configure_receivers` |
| `CFG_TAIL_SAMPLING_ON_DAEMONSET` | `ERROR` | `tail_sampling` is configured on a `daemonset` collector or multi-replica deployment without trace-ID loadbalancing | `otel_configure_sampling` |
| `CFG_FILELOG_NO_STORAGE_EXT` | `WARNING` | `filelog` receiver has no `storage: file_storage` extension, losing offsets on pod restart | `otel_configure_receivers` |
| `CFG_EXPORTER_NO_RETRY_QUEUE` | `WARNING` | Exporter lacks `retry_on_failure` or `sending_queue`, causing data loss during backend blips | `otel_patch_collector` |
| `CFG_CONNECTOR_LOOP` | `ERROR` | A connector reads from and writes to the same signal pipeline, creating an infinite telemetry loop | `otel_configure_connectors` |
| `CFG_PROMETHEUS_TA_MISSING` | `WARNING` | TargetAllocator is enabled on a multi-replica collector without `prometheus` receiver allocation config | `otel_patch_collector` |

---

## 2. Runtime & Pipeline Findings (`RT_*`)

| Finding Code | Default Severity | Root Cause | Recommended Remediation Tool |
|---|---|---|---|
| `RT_POD_CRASHLOOP` | `ERROR` | Collector pod is in `CrashLoopBackOff` or waiting state | `otel_diagnose_collector` / `otel_revert_collector_config` |
| `RT_POD_OOMKILLED` | `ERROR` | Collector container was terminated with `OOMKilled` (exit code 137) | `otel_patch_collector` |
| `RT_EXPORTER_DROPPING_DATA` | `ERROR` | `otelcol_exporter_send_failed_*` or `otelcol_exporter_enqueue_failed_*` > 0 | `otel_diagnose_collector` / `otel_patch_collector` |
| `RT_RECEIVER_REFUSING_DATA` | `ERROR` | `otelcol_receiver_refused_*` or `otelcol_processor_refused_*` > 0 due to memory limiter backpressure | `otel_patch_collector` |
| `RT_QUEUE_SATURATED` | `WARNING` | `otelcol_exporter_queue_size / otelcol_exporter_queue_capacity > 0.80` | `otel_patch_collector` |
| `RT_MEMORY_PRESSURE` | `WARNING` | `otelcol_process_memory_rss` exceeds 85% of container memory limit | `otel_patch_collector` |
| `RT_ZERO_THROUGHPUT` | `WARNING` | All receivers report 0 accepted items despite active instrumented workloads | `otel_verify_instrumentation` |
| `RT_RBAC_FORBIDDEN` | `ERROR` | Collector logs or RBAC check show missing ClusterRoleBinding for `k8sattributes`/`k8s_cluster`/`k8sobjects`/`kubeletstats` | `otel_configure_receivers` |

---

## 3. Operator & Cluster Findings (`OP_*`)

| Finding Code | Default Severity | Root Cause | Recommended Remediation Tool |
|---|---|---|---|
| `OP_NOT_INSTALLED` | `ERROR` | OpenTelemetry Operator CRDs (`opentelemetrycollectors.opentelemetry.io`) are missing from the cluster | Install Operator via Helm/OLM |
| `OP_WEBHOOK_UNHEALTHY` / `OP_WEBHOOK_CERT_ERROR` | `ERROR` | Operator webhook service has 0 ready endpoints or expired/mismatched `cert-manager` TLS certificate (`x509` / `tls: bad certificate` on `:9443`) | **Never blindly delete `MutatingWebhookConfiguration` or `ValidatingWebhookConfiguration`** (deleting them silently disables workload auto-instrumentation injection and `OpenTelemetryCollector` defaulting/validation cluster-wide). Instead inspect `otel://operator/status`, verify/renew the `cert-manager` `Certificate` + webhook TLS `Secret` (`cert-manager-cainjector` `caBundle`), and perform a rolling restart of `deploy/opentelemetry-operator` |
| `OP_CRD_VERSION_DEPRECATED` | `WARNING` | Collector uses deprecated `v1alpha1` schema instead of `v1beta1` | `otel_patch_collector` |

---

## 4. Instrumentation Findings (`INST_*`)

| Finding Code | Default Severity | Root Cause | Recommended Remediation Tool |
|---|---|---|---|
| `INST_CR_MISSING` | `ERROR` | Namespace has no `Instrumentation` CR (`opentelemetry.io/v1alpha1`) | `otel_patch_instrumentation` |
| `INST_ANNOTATION_MISSING` | `WARNING` | Workload pod template has no `instrumentation.opentelemetry.io/inject-*` annotation | `otel_manage_workload_instrumentation` |
| `INST_WEBHOOK_NOT_INJECTED` | `ERROR` | Workload has `inject-*` annotation, but running pods lack `opentelemetry-auto-instrumentation-*` initContainer (needs rolling restart or webhook fix) | `otel_manage_workload_instrumentation` |
| `INST_PROTOCOL_MISMATCH` | `ERROR` | Python or .NET workload targets gRPC port `:4317` with `http/protobuf` default protocol | `otel_patch_instrumentation` |
| `INST_GO_MISSING_TARGET_EXE` | `ERROR` | Go workload has `inject-go: "true"` without `instrumentation.opentelemetry.io/otel-go-auto-target-exe` | `otel_manage_workload_instrumentation` |
| `INST_ENDPOINT_UNREACHABLE` | `ERROR` | `Instrumentation` CR `spec.exporter.endpoint` references a non-existent Collector Service | `otel_patch_instrumentation` |

---

## 5. Security & Governance Findings (`SEC_*` & `GITOPS_MANAGED`)

| Finding Code | Default Severity | Root Cause | Recommended Remediation Tool |
|---|---|---|---|
| `SEC_PLAINTEXT_SECRET` | `ERROR` | Literal API key, bearer token, or password embedded in Collector YAML instead of `${env:SECRET_KEY}` | `otel_patch_collector` |
| `SEC_INSECURE_TLS` | `WARNING` | `tls.insecure: true` or `tls.insecure_skip_verify: true` on non-cluster-local exporter endpoint | `otel_patch_collector` |
| `SEC_PII_REDACTION_MISSING` | `WARNING` | Logs or traces pipeline lacks PII redaction / attribute scrubbing processor | `otel_configure_processing` |
| `SEC_OVERPRIVILEGED_RBAC` | `WARNING` | Collector ClusterRole grants write verbs (`create`, `update`, `delete`, `*`) | `otel_audit_security_posture` |
| `SEC_PRIVILEGED_CONTAINER` | `WARNING` | Collector or eBPF agent container runs with `securityContext.privileged: true` | `otel_audit_security_posture` |
| `SEC_BIND_ALL_INTERFACES_NO_AUTH` | `WARNING` | Receiver binds `0.0.0.0` without an authenticator extension | `otel_patch_collector` |
| `GITOPS_MANAGED` | `INFO` | Resource carries Argo CD, Flux, or Helm ownership markers; direct cluster mutation may be overwritten by GitOps sync | Commit rendered manifest to Git |
