# Prometheus Alert Templates for Tempo Span-Metrics & Service-Graphs

## 1. Span-Metrics Error Ratio Alert (`traces_spanmetrics_calls_total`)

```yaml
alert: TempoServiceHighErrorRatio
expr: |
  (
    sum by (service) (rate(traces_spanmetrics_calls_total{service="<service>", span_kind="SPAN_KIND_SERVER", status_code="STATUS_CODE_ERROR"}[5m]))
    /
    clamp_min(sum by (service) (rate(traces_spanmetrics_calls_total{service="<service>", span_kind="SPAN_KIND_SERVER"}[5m])), 0.001)
  ) > 0.05
for: 5m
labels:
  severity: critical
  service: "<service>"
annotations:
  summary: "High trace error ratio (>5%) on {{ $labels.service }}"
```

## 2. Span-Metrics p99 Latency SLO Alert (`traces_spanmetrics_latency_bucket`)

```yaml
alert: TempoServiceHighP99Latency
expr: |
  histogram_quantile(
    0.99,
    sum by (service, le) (rate(traces_spanmetrics_latency_bucket{service="<service>", span_kind="SPAN_KIND_SERVER"}[5m]))
  ) > 1.0
for: 5m
labels:
  severity: warning
  service: "<service>"
annotations:
  summary: "High p99 span latency (>1.0s) on {{ $labels.service }}"
```

## 3. Service-Graph Edge Failure Alert (`traces_service_graph_request_failed_total`)

```yaml
alert: TempoServiceEdgeHighFailureRate
expr: |
  (
    sum by (client, server) (rate(traces_service_graph_request_failed_total[5m]))
    /
    clamp_min(sum by (client, server) (rate(traces_service_graph_request_total[5m])), 0.001)
  ) > 0.05
for: 5m
labels:
  severity: warning
annotations:
  summary: "High failure rate between {{ $labels.client }} and {{ $labels.server }}"
```
