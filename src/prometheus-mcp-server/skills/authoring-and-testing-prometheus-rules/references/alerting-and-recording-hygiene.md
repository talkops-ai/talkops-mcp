# Alerting and Recording Rule Hygiene Standards

## 1. Recording Rule Naming Convention (`level:metric:operations`)

All recording rules MUST follow the colon-separated 3-part naming format:
- **`level`**: Aggregation labels preserved in the output (e.g., `job`, `namespace_service`, `instance_mode`).
- **`metric`**: Base metric name without `_total` when `rate()` is applied (e.g., `http_requests`, `node_cpu_seconds`).
- **`operations`**: Functions and window applied (e.g., `rate5m`, `ratio_rate5m`, `p99_5m`).

### Examples
```yaml
groups:
  - name: api-recording-rules
    interval: 30s
    rules:
      - record: job:http_requests:rate5m
        expr: sum by (job) (rate(http_requests_total[5m]))
      - record: job:http_errors:ratio_rate5m
        expr: |
          sum by (job) (rate(http_requests_total{status=~"5.."}[5m]))
          /
          clamp_min(job:http_requests:rate5m, 1e-9)
```

## 2. Alerting Rule Hygiene Checklist

| Field | Requirement | Purpose |
| :--- | :--- | :--- |
| `alert` | `PascalCase` name indicating symptom + scope (e.g., `CheckoutHighErrorRatio`) | Groups related instances cleanly in Alertmanager. |
| `for` | $\ge 2\text{m}$ for critical pages; $\ge 15\text{m}$ for warnings | Prevents transient 1-scrape blips from paging on-call (`MISSING_FOR_DURATION`). |
| `keep_firing_for` | `5m`–`10m` (Prometheus 2.42+ / 3.0+) | Prevents flapping resolution/re-firing when a metric hovers near the threshold. |
| `labels.severity` | `critical`, `warning`, or `info` | Required by Alertmanager routing trees (`MISSING_SEVERITY_LABEL`). |
| `annotations.summary` | Concise 1-line summary using `{{ $labels.job }}` and `{{ $value \| humanizePercentage }}` | Rendered in PagerDuty/Slack titles (`MISSING_SUMMARY_ANNOTATION`). |
| `annotations.runbook_url` | Direct URL to operational runbook | Enables automated incident triage. |
