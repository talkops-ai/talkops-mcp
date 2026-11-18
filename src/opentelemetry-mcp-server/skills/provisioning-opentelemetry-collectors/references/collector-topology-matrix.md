# Collector Topology & Resource Sizing Matrix

## Table of Contents
1. [Two-Tier Agent + Gateway Pattern](#two-tier-agent--gateway-pattern)
2. [Three-Tier Tail-Sampling Pattern](#three-tier-tail-sampling-pattern)
3. [Memory Sizing & GOMEMLIMIT Rules](#memory-sizing--gomemlimit-rules)
4. [Processor Ordering Invariant](#processor-ordering-invariant)

## Two-Tier Agent + Gateway Pattern

Production Kubernetes clusters ($\ge 10$ nodes) should separate node-local ingestion from cluster-wide aggregation:

- **Tier 1 — DaemonSet Agent (`role="agent"`, `mode="daemonset"`)**:
  - Runs on every node with `K8S_NODE_NAME` injected via the Kubernetes Downward API.
  - Configures `k8sattributes` with `filter.node_from_env_var: K8S_NODE_NAME` so each DaemonSet pod watches only pods on its own node (reducing kube-apiserver watch load by $O(N_{\text{nodes}})$).
  - Collects node-local container logs (`filelog` with `hostPath: /var/lib/otelcol/file_storage` `DirectoryOrCreate` checkpoint storage) and kubelet/host metrics (`kubeletstats`, `hostmetrics`).
  - Forwards telemetry over cluster-internal OTLP gRPC (`:4317`) to the Gateway Service without heavy batching (`CFG_DOUBLE_BATCHING` prevention).
- **Tier 2 — Gateway Deployment (`role="gateway"`, `mode="deployment"`)**:
  - Runs 2+ replicas behind a ClusterIP Service.
  - Performs OTTL PII redaction (`otel_configure_processing`), trace-derived metric generation (`otel_configure_connectors`), full egress compression batching (`batch: {send_batch_size: 4096, send_batch_max_size: 8192, timeout: 1s}`), and resilient backend export (`sending_queue: {enabled: true, queue_size: 1000, num_consumers: 10}` — or `remote_write_queue` on `prometheusremotewrite` — paired with `retry_on_failure: {enabled: true}`).

### Preventing Additive Double Batching (`Agent + Gateway`)
When both Tier 1 DaemonSet `otel-agent` and Tier 2 Gateway configure large `batch` timeouts (e.g., `10s + 10s = 20s` additive latency):
1. **Tier 1 DaemonSet Agent**: Remove `batch` (pass-through over low-latency cluster-local gRPC) or configure ultra-light micro-batching (`timeout: 200ms`, `send_batch_size: 512`).
2. **Tier 2 Gateway Deployment**: Keep full compression `batch` (`send_batch_size: 4096–8192`, `timeout: 1s–5s`) **and explicitly configure `sending_queue` (`enabled: true`) + `retry_on_failure` (`enabled: true`) on every Tier 2 Gateway egress exporter** (`otlp/tempo`, `otlphttp/loki`, etc.).

## Three-Tier Tail-Sampling Pattern

When using `tail_sampling` across multiple replicas:
1. DaemonSet Agents or Stateless Gateways use the `loadbalancing` exporter with `routing_key: traceID` and `resolver.k8s` or `resolver.dns` targeting the headless Service of the Tail-Sampler pool.
2. The Tail-Sampler tier runs as a `statefulset` (`role="tail-sampler"`) so every span sharing a `trace_id` lands on the exact same pod before `decision_wait` expires.

## Memory Sizing & GOMEMLIMIT Rules

| Cluster Scale | Node Count | CPU Request / Limit | Memory Request / Limit | `GOMEMLIMIT` (80%) | `memory_limiter.limit_mib` (80%) |
|---|---|---|---|---|---|
| `small` | $< 20$ | `100m` / `500m` | `256Mi` / `512Mi` | `400MiB` | `400` (`spike_limit_mib: 100`) |
| `medium` | $20 - 100$ | `250m` / `1000m` | `512Mi` / `1Gi` | `800MiB` | `800` (`spike_limit_mib: 200`) |
| `large` | $> 100$ | `500m` / `2000m` | `1Gi` / `2Gi` | `1600MiB` | `1600` (`spike_limit_mib: 400`) |

## Processor Ordering Invariant

Every pipeline must order processors from left to right:
`memory_limiter` $\rightarrow$ `k8sattributes` / `resourcedetection` $\rightarrow$ `transform` / `filter` $\rightarrow$ `tail_sampling` / `probabilistic_sampler` $\rightarrow$ `batch`.
