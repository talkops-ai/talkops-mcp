# Loki Ruler HTTP API and Operator CRD Specification

## Table of Contents
1. [Loki Ruler Rule Group YAML Schema (`/loki/api/v1/rules/{namespace}`)](#1-loki-ruler-rule-group-yaml-schema-lokiapiv1rulesnamespace)
2. [Kubernetes Loki Operator `AlertingRule` CRD (`loki.grafana.com/v1`)](#2-kubernetes-loki-operator-alertingrule-crd-lokigrafanacomv1)
3. [Kubernetes Loki Operator `RecordingRule` CRD (`loki.grafana.com/v1`)](#3-kubernetes-loki-operator-recordingrule-crd-lokigrafanacomv1)

---

## 1. Loki Ruler Rule Group YAML Schema (`/loki/api/v1/rules/{namespace}`)

When calling `loki_upsert_rule_group`, pass a single rule group YAML document:

```yaml
name: checkout-service-slo
interval: 1m
limit: 100
rules:
  - record: service_name:loki_http_requests:rate5m
    expr: |
      sum by (service_name, namespace) (
        rate({service_name="checkout", namespace="prod"}[5m])
      )
    labels:
      team: payments

  - alert: CheckoutHighErrorLogRate
    expr: |
      (
        sum by (service_name, namespace) (
          rate({service_name="checkout", namespace="prod"} |= "error" | json level="level" | level="error" | __error__="" [5m])
        )
        /
        (
          sum by (service_name, namespace) (
            rate({service_name="checkout", namespace="prod"}[5m])
          ) > 0
        )
      ) > 0.05
      and
      sum by (service_name, namespace) (
        count_over_time({service_name="checkout", namespace="prod"}[5m])
      ) >= 25
    for: 5m
    labels:
      severity: critical
      service_name: checkout
    annotations:
      summary: "High error log ratio (>5%) in {{ $labels.service_name }}"
      description: "Error log ratio is {{ $value | humanizePercentage }} over the last 5m in namespace {{ $labels.namespace }}."
      runbook_url: "https://runbooks.example.internal/checkout-errors"
```

---

## 2. Kubernetes Loki Operator `AlertingRule` CRD (`loki.grafana.com/v1`)

When managing rules declaratively via `loki_apply_operator_cr`:

```yaml
apiVersion: loki.grafana.com/v1
kind: AlertingRule
metadata:
  name: checkout-alerting-rules
  namespace: prod
spec:
  tenantID: application
  groups:
    - name: checkout-alerts
      interval: 1m
      rules:
        - alert: CheckoutPanicDetected
          expr: |
            sum by (service_name, namespace) (
              count_over_time({service_name="checkout", namespace="prod"} |= "panic:" [5m])
            ) > 0
          for: 1m
          labels:
            severity: page
          annotations:
            summary: "Runtime panic detected in {{ $labels.service_name }}"
```

---

## 3. Kubernetes Loki Operator `RecordingRule` CRD (`loki.grafana.com/v1`)

```yaml
apiVersion: loki.grafana.com/v1
kind: RecordingRule
metadata:
  name: checkout-recording-rules
  namespace: prod
spec:
  tenantID: application
  groups:
    - name: checkout-slo-metrics
      interval: 1m
      rules:
        - record: service_name:loki_checkout_p95_latency_seconds:5m
          expr: |
            quantile_over_time(0.95,
              {service_name="checkout", namespace="prod"}
                |= "duration_ms"
                | json duration_ms="duration_ms"
                | unwrap duration_ms
                | __error__="" [5m]
            ) by (service_name, namespace) / 1000
```
