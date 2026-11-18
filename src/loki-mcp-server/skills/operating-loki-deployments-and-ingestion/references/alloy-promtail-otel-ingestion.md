# Grafana Alloy, Promtail, and OpenTelemetry Ingestion Guide

## Table of Contents
1. [Troubleshooting `loki_discarded_samples_total` Reasons](#1-troubleshooting-loki_discarded_samples_total-reasons)
2. [Grafana Alloy Kubernetes Pod Log Pipeline](#2-grafana-alloy-kubernetes-pod-log-pipeline)
3. [OpenTelemetry Collector Native OTLP Ingestion (`/otlp/v1/logs`)](#3-opentelemetry-collector-native-otlp-ingestion-otlpv1logs)

---

## 1. Troubleshooting `loki_discarded_samples_total` Reasons

When `loki_get_diagnostics` reports non-zero `loki_discarded_samples_total`, match the `reason` label to its root cause and fix:

| Discard `reason` | Root Cause | Remediation |
|------------------|------------|-------------|
| `rate_limited` | Tenant total ingestion exceeds `ingestion_rate_mb` | Increase `limits_config.ingestion_rate_mb` / `ingestion_burst_size_mb` or drop noisy debug logs in Alloy |
| `per_stream_rate_limit` | A single log stream (`{service_name="x"}`) exceeds `per_stream_rate_limit` (default `3MB/s`) | Increase `per_stream_rate_limit` or split giant monolithic streams across logical `service_name` / `component` labels |
| `max_global_streams_per_user` | High-cardinality label inside `{}` created too many active streams | Run `loki_analyze_volume` and move dynamic labels (`pod`, `request_id`, `ip`) to `structured_metadata` |
| `line_too_long` | Log line exceeds `max_line_size` (default `256KB`) | Enable `limits_config.max_line_size_truncate: true` or truncate giant JSON payloads in Alloy |
| `timestamp_too_old` / `greater_than_max_sample_age` | Backfilled logs older than `reject_old_samples_max_age` (default `168h`) | Fix NTP clock skew or parse the container envelope timestamp instead of stale payload timestamps |
| `out_of_order` | Log entry older than `unordered_writes` window | Ensure `limits_config.unordered_writes: true` (default in Loki 3.x) |

---

## 2. Grafana Alloy Kubernetes Pod Log Pipeline

```alloy
discovery.kubernetes "pods" {
  role = "pod"
}

discovery.relabel "pod_logs" {
  targets = discovery.kubernetes.pods.targets
  rule {
    source_labels = ["__meta_kubernetes_namespace"]
    target_label  = "namespace"
  }
  rule {
    source_labels = ["__meta_kubernetes_pod_label_app_kubernetes_io_name"]
    target_label  = "service_name"
  }
  rule {
    source_labels = ["__meta_kubernetes_pod_name"]
    target_label  = "pod"
  }
  rule {
    source_labels = ["__meta_kubernetes_pod_container_name"]
    target_label  = "container"
  }
  rule {
    source_labels = ["__meta_kubernetes_pod_node_name"]
    target_label  = "node"
  }
}

loki.process "kubernetes_pods" {
  stage.cri {}
  stage.structured_metadata {
    values = {
      pod       = "pod",
      container = "container",
      node      = "node",
    }
  }
  stage.label_drop {
    values = ["pod", "container", "node", "filename"]
  }
  forward_to = [loki.write.cluster.receiver]
}
```

---

## 3. OpenTelemetry Collector Native OTLP Ingestion (`/otlp/v1/logs`)

Configure the OpenTelemetry Collector `otlphttp` exporter to push directly to Loki 3.x (where `service.name` + `service.namespace` / `k8s.namespace.name` become bounded indexed stream labels while `k8s.pod.name`, `k8s.container.name`, and `k8s.node.name` are stored automatically in Loki 3.x `structured_metadata`):
```yaml
exporters:
  otlphttp/loki:
    endpoint: http://loki-gateway.logging.svc.cluster.local/otlp
    headers:
      X-Scope-OrgID: "tenant-prod"
```
