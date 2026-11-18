---
name: authoring-loki-alerting-and-recording-rules
description: Designs, validates, backtests, and deploys Grafana Loki Ruler alerting rules, recording rules, and Kubernetes Loki Operator AlertingRule/RecordingRule CRDs with dry-run and confirmation guardrails. Use when creating or deleting Loki Ruler rule groups, authoring AlertingRule or RecordingRule CRDs, pre-aggregating expensive LogQL queries into Prometheus metrics, tuning noisy/high-series log alerts, or running /setup-monitoring for log alerts. Do not use for Prometheus TSDB PrometheusRule CRDs (use authoring-and-testing-prometheus-rules), ad-hoc LogQL queries (use authoring-logql-and-analyzing-logs), LokiStack cluster provisioning (use operating-loki-deployments-and-ingestion), or Alertmanager routing simulation (use validating-alertmanager-routing).
license: Apache-2.0
metadata:
  author: TalkOps
  version: "0.2.0"
  domain: observability
  service: grafana-loki
---

# Authoring Loki Alerting and Recording Rules

Use this skill to author noise-free Grafana Loki alerting rules and cardinality-safe recording rules, backtest their LogQL expressions over live historical logs, validate YAML locally, and deploy via Loki Ruler or Kubernetes Loki Operator with strict 2-phase `dry_run` safety gates.

## Golden Hygiene Rules ([references/log-alerting-patterns.md](references/log-alerting-patterns.md) & [references/loki-ruler-and-crd-spec.md](references/loki-ruler-and-crd-spec.md))

1. **Always Set `for:` (`>= 2m`–`5m`) & Annotations on Alerts**: Include `for: 5m`, `severity` + `service_name` labels, and `summary`, `description`, and `runbook_url` annotations. Never define both `alert` and `record` on the same rule!
2. **Protect Error Ratios Against Divide-by-Zero + Minimum Volume Floor**: Note that `clamp_min()` is a PromQL-only function and is **rejected with HTTP 400 in Loki LogQL**! Filter the denominator with `> 0` (`... / (sum by (...) (rate(...[5m])) > 0) > 0.05`) AND require a minimum event count (`and sum by (...) (count_over_time(...[5m])) >= 25`) so 1 failed probe or idle traffic never pages on-call or divides by zero.
3. **Strict `level:metric:operations` Colon Naming on Recording Rules**: e.g., `namespace_service_route:loki_http_errors:rate5m` and `namespace_service_route:loki_http_duration_ms:p99_5m` (always append `| __error__=""` after `| unwrap`).
4. **Forbid High-Cardinality Grouping in `by (...)`**: Only aggregate `by (namespace, service_name, route, status_class)`—**never** group Ruler rules `by (session_id, trace_id, user_id, order_id, pod_ip, client_ip)` which explodes remote-write Prometheus TSDB series.
5. **Tune Group `interval` (`>= 1m`)**: Avoid `interval: 15s` on `[30m]` range queries which overloads queriers and hits `maximum of series (500)` limits.

## Step-by-Step Workflow

### Step 1: Inspect Capabilities, References, Ruler Groups & Operator CRDs
1. Read `loki://server/capabilities` first to check `allow_write` (if `allow_write: false`, perform read-only backtesting + local `validate_loki_rules.py` validation and output a copy-pasteable GitOps YAML manifest without calling write tools!). Also read `commands/setup-monitoring.md` when invoked via `/setup-monitoring`.
2. Read [references/log-alerting-patterns.md](references/log-alerting-patterns.md) when designing alerting/recording LogQL expressions and [references/loki-ruler-and-crd-spec.md](references/loki-ruler-and-crd-spec.md) when rendering Ruler YAML or `AlertingRule` / `RecordingRule` CRDs.
3. Read `loki://rules/groups` before creating, updating, or deleting Ruler groups.
4. When working with Kubernetes Loki Operator CRDs (`loki.grafana.com/v1`), inspect `loki://operator/crs/{namespace}` and `loki://operator/manifests/{kind}/{namespace}/{name}` (substituting `{kind}`, `{namespace}`, and `{name}`) via MCP resources rather than raw `kubectl` so existing `spec.tenantID`, labels, and sibling rules are preserved!

### Step 2: Backtest Candidate LogQL Expressions Against Live History
Before deploying or updating thresholds:
1. Call `loki_query_instant` (passing `org_id` for tenant isolation) to confirm clean evaluation with zero syntax/`SampleExtractionErr` errors.
2. Call `loki_query_range` over `1h`–`6h` (`step="1m"` or `"5m"`) to verify historical firing behavior and prevent alert fatigue.

### Step 3: Deterministic Local Validation (`validate_loki_rules.py`)
Always validate rule group YAML or `AlertingRule`/`RecordingRule` CRDs locally using [scripts/validate_loki_rules.py](scripts/validate_loki_rules.py):
```bash
python3 .agents/skills/authoring-loki-alerting-and-recording-rules/scripts/validate_loki_rules.py \
  --file rules.yaml --json
```
When auditing broken rule YAML for a user, run `validate_loki_rules.py` on the broken YAML to surface every error/warning, then validate your fixed YAML to confirm `valid: true`.

### Step 4: Two-Phase Mutation Gate (`dry_run=True` -> `dry_run=False, confirm=True`)
- **Preview-Only Requests**: If the user only asks to author, tune, or preview a rule (or has not asked to deploy/apply live), stop after `dry_run=True`!
- **Deploy / Apply / Delete Requests** (when `allow_write: true`):
  1. **Loki Ruler Upsert**: Call `loki_upsert_rule_group(namespace=..., group_name=..., rules_yaml=..., dry_run=True, org_id=...)` first to inspect the unified diff, then call `loki_upsert_rule_group(..., dry_run=False, confirm=True, org_id=...)`.
  2. **Loki Ruler Delete**: Call `loki_delete_rule_group(namespace=..., group_name=..., dry_run=True, org_id=...)` first, then `loki_delete_rule_group(..., dry_run=False, confirm=True, org_id=...)`.
  3. **Kubernetes Operator CRD (`AlertingRule` / `RecordingRule`)**: Call `loki_apply_operator_cr(manifest_yaml=..., namespace="<namespace>", dry_run=True)` first, then `loki_apply_operator_cr(..., dry_run=False, confirm=True)` when live apply is requested.

## Key Reference Guides & Scripts

- [references/loki-ruler-and-crd-spec.md](references/loki-ruler-and-crd-spec.md) — Schemas for Loki Ruler `/loki/api/v1/rules/{namespace}` YAML and `loki.grafana.com/v1` `AlertingRule` / `RecordingRule` CRDs.
- [references/log-alerting-patterns.md](references/log-alerting-patterns.md) — Error-ratio (`(denominator > 0)` + `>= 25` floor), `absent_over_time` heartbeat (`for: 5m`), and recording-rule templates.
- [scripts/validate_loki_rules.py](scripts/validate_loki_rules.py) — Deterministic validator for Loki Ruler YAML and Operator CRDs.
