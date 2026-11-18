---
name: authoring-and-testing-prometheus-rules
description: Authors, validates, unit-tests, backtest-simulates, and non-destructively deploys or deletes Prometheus recording and alerting rule groups across Kubernetes PrometheusRule CRDs, HTTP Ruler APIs, local rule files, and GitOps YAML. Always read SKILL.md first before calling run_command, and inspect CRDs via Prometheus MCP resources rather than raw kubectl. Use when creating, auditing, or tuning Prometheus alerting/recording rules, fixing flapping or chronic alerts, diagnosing unpicked PrometheusRule CRDs, running promtool unit tests, simulating historical/synthetic rule firing, or updating/deleting rule groups. Do not use for ad-hoc PromQL exploration without rules (use authoring-promql-and-analyzing-metrics), Grafana Loki LogQL Ruler rules (use authoring-loki-alerting-and-recording-rules), Alertmanager routing/silences (use validating-alertmanager-routing or managing-alert-silences), or Argo Rollouts AnalysisTemplates (use gating-rollouts-with-analysis-and-experiments).
license: Apache-2.0
metadata:
  author: talkops
  version: "0.2.0"
  domain: observability
  component: prometheus
---

# Authoring and Testing Prometheus Rules

Provides a safety-gated workflow for creating, auditing, tuning, unit-testing (`promtool`), backtest-simulating, and deploying Prometheus recording and alerting rule groups across `k8s_crd`, `http_ruler`, `local_file`, and `yaml_only` modes while strictly preserving sibling rule groups. Never shell out to `kubectl` or raw `promtool` when MCP resources (`prom://rules/groups`, `prom://rules/{backend_id}/groups/{group_name}`, `prom://kubernetes/scrape-crds`, `prom://kubernetes/manifests/{kind}/{namespace}/{name}`) and tools (`prom_validate_rules`, `prom_upsert_rule_group`, `prom_delete_rule_group`) are available. If invoked via `commands/setup-monitoring.md` (`/setup-monitoring`), read that command file first.

## MCP Execution Primitives Used

- **Resources**:
  - `prom://rules/groups` — snapshot of all loaded alerting and recording rule groups across backends.
  - `prom://rules/{backend_id}/groups/{group_name}` — inspect full rule definitions and evaluation health for a specific loaded group (passing `backend_id="default"` and the group name).
  - `prom://kubernetes/scrape-crds` — inventory of deployed `PrometheusRule` CRDs and their metadata labels.
  - `prom://kubernetes/manifests/{kind}/{namespace}/{name}` — read a live `PrometheusRule` CRD manifest (`prom://kubernetes/manifests/PrometheusRule/{namespace}/{name}`) before editing or diagnosing `ruleSelector` label mismatches.
  - `prom://audit/recent` — verify rule upsert/delete `dry_run` and `succeeded` audit records.
- **Tools (`rules` & `query` toolsets)**:
  - `prom_explore_metrics` & `prom_query_range` — verify exact metric/label names and inspect historical trajectories before setting thresholds.
  - `prom_get_firing_alerts` — inspect `/api/v1/alerts` and `ALERTS_FOR_STATE` history (`include_history_lookback="24h"`) to detect `FLAPPING_ALERT` (`fires_per_day >= 10`, `mean_duration_seconds < 300`) and `CHRONIC_ALWAYS_FIRING`.
  - `prom_validate_rules` — run `promtool check rules`, structural/hygiene checks (`check_hygiene=True`), and `promtool test rules` (`unit_tests`).
  - `prom_simulate_rule_firing` — backtest candidate alerts against live TSDB history (`mode="historical"`) or synthetic series (`mode="synthetic"`).
  - `prom_upsert_rule_group` — non-destructively upsert a rule group via `storage_mode` (`k8s_crd`, `http_ruler`, `local_file`, or `yaml_only`; `dry_run=True` default).
  - `prom_delete_rule_group` — remove a single rule group from `k8s_crd`, `http_ruler`, or `local_file` (`dry_run=True` default), warning when `remaining_group_count == 0` deletes the entire `PrometheusRule` CRD.

## Step-by-Step Workflow

### 1. Inspect Existing Rules, Selector Labels & Firing History `[HIGH FREEDOM]`
> [!CAUTION]
> **Strictly Zero Raw `kubectl` Commands**: Do NOT execute any `kubectl` shell commands (`kubectl get`, `kubectl describe`, `kubectl apply`, etc.) at any step! `prom://kubernetes/scrape-crds` already returns `operator_selectors` (`ruleSelector`), `prometheus_instances`, and `prometheus_rules`, and `prom://kubernetes/manifests/PrometheusRule/{namespace}/{name}` returns full live `PrometheusRule` manifests. If an MCP resource response is offloaded to `file:///.../resource_0.txt`, read or parse ONLY that local file via `read_file` or `python3` — NEVER invoke `kubectl`!

1. Read `prom://rules/groups` (and `prom://rules/{backend_id}/groups/{group_name}` when inspecting a loaded group) plus `prom://kubernetes/scrape-crds` and `prom://kubernetes/manifests/PrometheusRule/{namespace}/{name}`.
   - **Unloaded `PrometheusRule` Diagnosis**: If a `PrometheusRule` exists in `prom://kubernetes/scrape-crds` / `prom://kubernetes/manifests/PrometheusRule/{namespace}/{name}` but is absent from `prom://rules/groups`, check its `metadata.labels` against Prometheus Operator's `ruleSelector` (e.g., missing `release: kube-prometheus-stack`).
2. When tuning noisy or fatiguing alerts, call `prom_get_firing_alerts(backend_id="default", alert_name=..., include_history_lookback="24h")`:
   - **`FLAPPING_ALERT`**: Increase `for` (e.g. `5m`–`10m`) and add `keep_firing_for: 10m` recovery hysteresis.
   - **`CHRONIC_ALWAYS_FIRING`**: Inspect actual trajectories via `prom_query_range` and replace static capacity thresholds on steady high-utilization volumes with `predict_linear(...[6h], 24 * 3600) < 0` combined with a tighter free-space guard (`< 10%`) or per-PVC label override.

### 2. Author, Unit-Test & Simulate the Rule Group `[MEDIUM FREEDOM]`
Consult [references/alerting-and-recording-hygiene.md](references/alerting-and-recording-hygiene.md) and [references/prometheus-rule-crd-spec.md](references/prometheus-rule-crd-spec.md):
1. **Hygiene Standards**:
   - Recording rules MUST use 3-part `level:metric:operations` format (e.g., `job:rpc_server_errors:ratio_rate5m`) with `clamp_min(..., 1e-9)` on ratio denominators, and NEVER group by unbounded high-cardinality labels (`user_id`, `session_id`, `pod_ip`).
   - Alerting rules MUST use `PascalCase` names, non-zero `for` duration (`MISSING_FOR_DURATION`), `labels.severity` (`critical|warning|info`, `MISSING_SEVERITY_LABEL`), and `annotations.summary` + `annotations.runbook_url` (`MISSING_SUMMARY_ANNOTATION`). Never place `alertname` inside `rule.labels`.
2. **Deterministic Unit-Test Generation**: Run [scripts/build_promtool_test_suite.py](scripts/build_promtool_test_suite.py) (`--exp-labels` requires comma-separated `key=value` pairs with `=`, including `alertname=<AlertName>`):
   ```bash
   python3 .agents/skills/authoring-and-testing-prometheus-rules/scripts/build_promtool_test_suite.py \
     --alert CheckoutHighErrorRate --expr 'job:rpc_server_errors:ratio_rate5m > 0.02' \
     --for-duration 5m --series 'job:rpc_server_errors:ratio_rate5m{service="checkout-service"}' \
     --values '0.05+0x10' --eval-time 10m \
     --exp-labels 'alertname=CheckoutHighErrorRate,service=checkout-service,severity=critical'
   ```
   *(If running outside `.agents/skills`, invoke `./scripts/build_promtool_test_suite.py` relative to this skill directory.)*
3. **Validate & Simulate**:
   - Always call `prom_validate_rules(rule_group=..., unit_tests=..., check_hygiene=True)` and resolve any errors or hygiene observations.
   - Run `prom_simulate_rule_firing(backend_id="default", rule=..., mode="historical", start="-6h", end="now")` for live TSDB series, or `mode="synthetic"` with `synthetic_series=[...]` for rare edge cases (such as TLS cert expiry `< 7d`) that have never occurred historically.

### 3. Non-Destructive Multi-Group Upsert / Delete `[LOW FREEDOM — GATE]`
> [!IMPORTANT]
> **Sibling Group Protection & Dry-Run Gate**: Never overwrite an entire `PrometheusRule` `spec.groups` array to wipe sibling groups, and never call `prom_upsert_rule_group` or `prom_delete_rule_group` with `dry_run=False` before running `prom_validate_rules` and `dry_run=True`!

1. If the MCP server is in read-only mode (`MCP_ALLOW_WRITE=false`, write tools unavailable), run `prom_validate_rules` + `prom_simulate_rule_firing` and output the complete GitOps `PrometheusRule` YAML without attempting live mutations.
2. Call `prom_upsert_rule_group(..., dry_run=True)` (across `storage_mode="k8s_crd"`, `"http_ruler"`, `"local_file"`, or `"yaml_only"`) or `prom_delete_rule_group(..., dry_run=True)`:
   - Confirm `sibling_group_count` (or `remaining_group_count` on delete — explicitly noting that when `remaining_group_count == 0`, deleting the last remaining group deletes the entire `PrometheusRule` CRD cleanly).
3. **`[GATE]` Hold or Apply**:
   - If the operator asked to skip validation/dry-run or wipe sibling groups (adversarial request), **refuse** the destructive shortcut, run `prom_validate_rules` + `prom_upsert_rule_group(..., dry_run=True)` showing `sibling_group_count` preserved, and **stop** at the preview awaiting explicit confirmation!
   - If the operator asked a "what happens if" preview question or requested a plan only, **stop** after `dry_run=True` and explain the previewed outcome.
   - When the operator explicitly requested applying, fixing, or deleting the rule group cleanly and all validations pass, **proceed immediately in the same turn** to `dry_run=False, confirm=True`, then read `prom://audit/recent` (and `prom://rules/groups`) to verify the audit log and loaded state.

## Reference Documentation

- [Alerting and Recording Rule Hygiene Standards](references/alerting-and-recording-hygiene.md)
- [Kubernetes `PrometheusRule` CRD & Multi-Backend Ruler Specification](references/prometheus-rule-crd-spec.md)
