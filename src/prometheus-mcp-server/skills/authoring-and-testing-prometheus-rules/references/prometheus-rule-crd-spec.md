# Kubernetes `PrometheusRule` CRD & Multi-Backend Ruler Specification

## 1. `PrometheusRule` CRD Structure (`monitoring.coreos.com/v1`)

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: checkout-slo-rules
  namespace: monitoring
  labels:
    app.kubernetes.io/managed-by: prometheus-mcp-server
    release: kube-prometheus-stack   # Must match Prometheus CR spec.ruleSelector.matchLabels
spec:
  groups:
    - name: checkout-slo.rules
      interval: 30s
      rules:
        - alert: CheckoutHighErrorRate
          expr: job:http_errors:ratio_rate5m{job="checkout"} > 0.05
          for: 5m
          keep_firing_for: 5m
          labels:
            severity: critical
            service: checkout
          annotations:
            summary: "High error rate on {{ $labels.job }} ({{ $value | humanizePercentage }})"
            runbook_url: "https://runbooks.example.com/checkout-errors"
```

## 2. Non-Destructive Multi-Group Merge Invariant
- A single `PrometheusRule` CRD often contains multiple rule groups (`spec.groups[]`).
- `prom_upsert_rule_group` automatically inspects existing `PrometheusRule` CRDs in the target `namespace`, merges or replaces **only** the matching `group.name`, and preserves all sibling rule groups (`sibling_group_count`) and operator `ruleSelector` labels.
- Similarly, `prom_delete_rule_group` removes only the specified `group_name` from `spec.groups[]` and only deletes the `PrometheusRule` CRD if `remaining_group_count == 0`.
