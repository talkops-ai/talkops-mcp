# Metric Cardinality Playbooks & Cost Governance

## Table of Contents

1. [What Causes Metric Cardinality Explosion](#1-what-causes-metric-cardinality-explosion)
2. [High-Risk OpenTelemetry Semantic Attributes](#2-high-risk-opentelemetry-semantic-attributes)
3. [Dropping Unbounded Metric Dimensions via `otel_configure_processing`](#3-dropping-unbounded-metric-dimensions-via-otel_configure_processing)
4. [Filtering Chatty Runtime & Container Metrics](#4-filtering-chatty-runtime--container-metrics)
5. [Capping `spanmetrics` & `servicegraph` Dimensions](#5-capping-spanmetrics--servicegraph-dimensions)

---

## 1. What Causes Metric Cardinality Explosion

Every unique combination of metric name + label key-value pairs creates a new active time series in Prometheus, Mimir, VictoriaMetrics, or SaaS APM backends.

$$\text{Total Series} = \prod_{i=1}^{k} |\text{Unique Values of Label } i|$$

Adding a single label with 10,000 unique values (e.g., `user.id` or `k8s.pod.uid` on churned jobs) to a 12-bucket histogram multiplies active time series by $120,000\times$.

---

## 2. High-Risk OpenTelemetry Semantic Attributes

| Attribute Key | Why It Explodes | Action |
|---|---|---|
| `url.full`, `url.query`, `http.target` | Unique query strings, pagination tokens, and IDs per request | Delete from metrics; normalize `url.path` on spans |
| `user.id`, `enduser.id`, `session.id`, `client.address` | Unbounded user/IP population | Delete from `datapoint` attributes via `otel_configure_processing` |
| `container.id`, `k8s.pod.uid` | Ephemeral IDs on CronJobs and autoscaled pods | Retain `k8s.deployment.name` and `k8s.namespace.name`; drop `container.id` on long-term aggregated metrics |
| `net.peer.port`, `client.port` | Ephemeral source ports (`32768–60999`) | Always drop `client.port` and `net.peer.port` from metric datapoints |

---

## 3. Dropping Unbounded Metric Dimensions via `otel_configure_processing`

Call `otel_configure_processing` with `rules.drop_attributes`:

```json
{
  "namespace": "opentelemetry-system",
  "collector_name": "otel-agent",
  "signals": ["metrics"],
  "rules": {
    "drop_attributes": [
      "url.query",
      "http.target",
      "client.port",
      "net.peer.port",
      "user.id",
      "session.id"
    ]
  },
  "dry_run": true
}
```

---

## 4. Filtering Chatty Runtime & Container Metrics

When `hostmetrics` or `kubeletstats` emits unused granular metrics (e.g., per-CPU core interrupts or per-interface loopback packets), drop them in the `filter` processor:

```yaml
processors:
  filter/metrics:
    error_mode: ignore
    metrics:
      metric:
        - 'name == "system.network.connections" and attributes["state"] == "TIME_WAIT"'
        - 'IsMatch(name, "^runtime\\.go\\.mem\\..*")'
```

---

## 5. Capping `spanmetrics` & `servicegraph` Dimensions

When configuring trace-derived metrics via `otel_configure_connectors`, restrict `dimensions` to low-cardinality status and method fields (`http.request.method`, `http.response.status_code`, `rpc.grpc.status_code`).
