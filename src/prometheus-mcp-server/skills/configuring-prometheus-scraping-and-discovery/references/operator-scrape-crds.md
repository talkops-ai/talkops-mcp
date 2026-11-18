# Prometheus Operator Scrape CRDs & Prometheus 3.0 Ingestion Reference

## Table of Contents
1. [Choosing the Right Scrape CRD](#1-choosing-the-right-scrape-crd)
2. [Zero-Knowledge Kubernetes Service Auto-Discovery (`target_service`)](#2-zero-knowledge-kubernetes-service-auto-discovery-target_service)
3. [Canonical `spec` Templates for `prom_apply_scrape_config`](#3-canonical-spec-templates-for-prom_apply_scrape_config)
4. [Prometheus 3.0 Native Histograms & OTLP Push Ingestion](#4-prometheus-30-native-histograms--otlp-push-ingestion)

## 1. Choosing the Right Scrape CRD

| CRD Kind | API Version | When to Use |
| :--- | :--- | :--- |
| **`ServiceMonitor`** | `monitoring.coreos.com/v1` | Standard Kubernetes workloads backed by a `Service` (preferred default). |
| **`PodMonitor`** | `monitoring.coreos.com/v1` | DaemonSets, batch jobs, or sidecars that do not expose a Kubernetes `Service`. |
| **`Probe`** | `monitoring.coreos.com/v1` | Synthetic HTTP/TCP/ICMP blackbox probing via `blackbox_exporter` (`prober.url`). |
| **`ScrapeConfig`** | `monitoring.coreos.com/v1alpha1` | External non-Kubernetes targets (`staticConfigs`, `httpSDConfigs`, `ec2SDConfigs`). |

## 2. Zero-Knowledge Kubernetes Service Auto-Discovery (`target_service`)

When a user says *"Monitor my `checkout` service in the `production` namespace"* without knowing its labels or named port, pass `target_service` and `target_namespace` in `spec` to `prom_apply_scrape_config`:
```json
{
  "target_service": "checkout",
  "target_namespace": "production",
  "path": "/metrics",
  "interval": "30s"
}
```
The MCP server automatically inspects the live Kubernetes `Service`, strips ephemeral Helm chart labels (`helm.sh/chart`, `app.kubernetes.io/version`), selects the named metrics port, and configures `namespaceSelector.matchNames: ["production"]` when `target_namespace` differs from the `ServiceMonitor` namespace.

## 3. Canonical `spec` Templates for `prom_apply_scrape_config`

### A. `ServiceMonitor` (`spec`)
> [!WARNING]
> `endpoints[].port` in a `ServiceMonitor` MUST reference the **port `name`** string on the Kubernetes `Service` (e.g., `"metrics"` or `"http"`), NOT a numeric port number (use `targetPort` only if unnamed).

```json
{
  "selector": {
    "matchLabels": {
      "app.kubernetes.io/name": "checkout"
    }
  },
  "namespaceSelector": {
    "matchNames": ["production"]
  },
  "endpoints": [
    {
      "port": "metrics",
      "path": "/metrics",
      "interval": "30s",
      "scrapeTimeout": "10s"
    }
  ]
}
```

### B. `PodMonitor` (`spec`)
```json
{
  "selector": {
    "matchLabels": {
      "app": "worker"
    }
  },
  "podMetricsEndpoints": [
    {
      "port": "metrics",
      "path": "/metrics",
      "interval": "30s"
    }
  ]
}
```

### C. `Probe` (`spec`)
```json
{
  "jobName": "blackbox-http-prod",
  "prober": {
    "url": "blackbox-exporter.monitoring.svc:9115"
  },
  "module": "http_2xx",
  "targets": {
    "staticConfig": {
      "static": [
        "https://api.example.com/healthz"
      ]
    }
  },
  "interval": "30s"
}
```

### D. `ScrapeConfig` (`spec`)
```json
{
  "jobName": "external-vms",
  "metricsPath": "/metrics",
  "staticConfigs": [
    {
      "targets": ["10.20.1.15:9100", "10.20.1.16:9100"],
      "labels": {
        "env": "prod-vm"
      }
    }
  ]
}
```

## 4. Prometheus 3.0 Native Histograms & OTLP Push Ingestion

### A. Enabling Native Histograms in `ServiceMonitor` / `prometheus.yml`
In Prometheus 3.0+, enable native exponential histograms (`scrape_native_histograms: true` or `scrapeNativeHistograms: true` in `ServiceMonitor.spec.endpoints[]`) to eliminate classic `_bucket` series explosion:
```yaml
scrape_configs:
  - job_name: "api-server"
    scrape_native_histograms: true
    native_histogram_bucket_limit: 160
```

### B. Native OTLP Receiver (`/api/v1/otlp/v1/metrics`)
When applications or OpenTelemetry Collectors push OTLP HTTP/protobuf metrics directly to Prometheus 3.0 (`--web.enable-otlp-receiver`), promote essential OpenTelemetry resource attributes so series remain filterable without joining `target_info`:
```yaml
otlp:
  promote_resource_attributes:
    - service.instance.id
    - service.name
    - service.namespace
    - deployment.environment.name
    - k8s.namespace.name
    - k8s.pod.name
  translation_strategy: UnderscoreEscapingWithSuffixes # or NoUTF8EscapingWithSuffixes
```
