# OpenTelemetry Collector Log Error Signatures & Remediation

## Table of Contents

1. [Exporter Network & TLS Errors](#1-exporter-network--tls-errors)
2. [Authentication & HTTP Status Errors](#2-authentication--http-status-errors)
3. [Kubernetes API & RBAC Errors (`RT_RBAC_FORBIDDEN`)](#3-kubernetes-api--rbac-errors-rt_rbac_forbidden)
4. [Memory Limiter & Queue Overflow Logs](#4-memory-limiter--queue-overflow-logs)
5. [Configuration Schema & Startup Errors](#5-configuration-schema--startup-errors)

---

## 1. Exporter Network & TLS Errors

| Log Signature | Root Cause | Remediation |
|---|---|---|
| `rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing: dial tcp: lookup ... no such host"` | Exporter endpoint hostname cannot be resolved by CoreDNS | Check service name and namespace in `otel://collector/{namespace}/{name}/config` and patch via `otel_patch_collector` |
| `x509: certificate signed by unknown authority` | Custom/internal CA certificate not mounted or configured on exporter `tls.ca_file` | Mount CA Secret on collector pod and set `tls.ca_file` via `otel_patch_collector` |
| `http: server gave HTTP response to HTTPS client` | `otlp` or `otlphttp` exporter uses TLS against a plaintext `:4317`/`:4318` in-cluster endpoint | Use `http://` scheme for internal cluster service endpoints |
| `rpc error: code = ResourceExhausted desc = grpc: received message larger than max (6291456 vs. 4194304)` | Downstream Gateway gRPC `otlp` receiver enforces the 4 MiB default `max_recv_msg_size_mib` while upstream collector sends oversized batches | **Apply both fixes together**: (1) raise `receivers.otlp.protocols.grpc.max_recv_msg_size_mib: 16` on the downstream Gateway (`otel_patch_collector`) **AND** (2) bound `processors.batch.send_batch_max_size` (e.g. `2048`–`4096`) on the upstream Agent/Collector (`otel_patch_collector(..., dry_run=True)`) so individual batches stay below the receiver cap |

---

## 2. Authentication & HTTP Status Errors

| Log Signature | Root Cause | Remediation |
|---|---|---|
| `Permanent error: rpc error: code = Unauthenticated` or `status code 401` | Invalid or expired API token in `${env:OTEL_EXPORTER_AUTH_TOKEN}` | Rotate the Kubernetes Secret and restart the collector |
| `status code 429 Too Many Requests` | Backend rate-limiting ingestion | Enable `retry_on_failure` + `sending_queue` and reduce volume via `otel_configure_sampling` or `otel_configure_processing` |
| `Permanent error: status code 400 Bad Request` | Malformed OTLP payload or wrong endpoint path (`otlp` vs `otlphttp`) | Switch exporter type (`otlp` for gRPC, `otlphttp` for HTTP) via `otel_patch_collector` |

---

## 3. Kubernetes API & RBAC Errors (`RT_RBAC_FORBIDDEN`)

| Log Signature | Root Cause | Remediation |
|---|---|---|
| ` pods is forbidden: User "system:serviceaccount:..." cannot list resource "pods"` | `k8sattributes` or `k8s_cluster` lacks ClusterRole/ClusterRoleBinding | Call `otel_configure_receivers` (`namespace`, `collector_name`, `receivers=["k8s_cluster"]`, `dry_run=True -> False`) to provision the required ServiceAccount, ClusterRole, and ClusterRoleBinding |
| `kubeletstatsreceiver: failed to fetch stats from /stats/summary: 403 Forbidden` | Collector ServiceAccount's `ClusterRole` (`otel-k8sattr-<name>`) is missing **both `nodes/stats` and `nodes/proxy`** (`nodes/metrics`) `get` permissions | Explicitly pinpoint missing `nodes/stats` and `nodes/proxy` `get` permissions on `<name>`'s `ClusterRole`, and preview/apply via `otel_configure_receivers` (`namespace`, `collector_name`, `receivers=["kubeletstats"]`, `dry_run=True -> False`) |

---

## 4. Memory Limiter & Queue Overflow Logs

| Log Signature | Root Cause | Remediation |
|---|---|---|
| `Memory usage is above soft limit. Refusing data.` | Collector heap exceeded `memory_limiter.limit_mib` | Increase pod memory limits or add filtering/sampling via `otel_configure_processing` / `otel_configure_sampling` |
| `Dropping data because sending_queue is full` | Downstream backend outage exceeded `sending_queue.queue_size` | Increase `sending_queue.queue_size` or attach `storage: file_storage` |

---

## 5. Configuration Schema & Startup Errors

| Log Signature | Root Cause | Remediation |
|---|---|---|
| `telemetry.metrics.address is not supported` | Collector `>= v0.120.0` started with removed legacy internal metrics syntax | Run `otel_patch_collector` to upgrade `service.telemetry.metrics` to `readers` pull syntax |
| `error decoding 'processors': unknown type: "..."` | Unsupported processor in distribution image | Switch collector image to `otel/opentelemetry-collector-contrib:0.152.1` |
