---
name: troubleshooting-argo-rollouts
description: Diagnoses and remediates Degraded, Aborted, Paused, and InvalidSpec Argo Rollouts using single-call diagnostic reports, AnalysisRun failure inspection, warning event analysis, and targeted recovery actions. Use when a Rollout is stuck in Progressing, Paused, or Degraded phase, an AnalysisRun fails or aborts a rollout, or an InvalidSpec strategy conflict occurs.
---

# Troubleshooting Argo Rollouts

## Preconditions

1. Read `argorollout://server/capabilities` to check `cluster_connected` and `allow_write`.
2. Call `argo_diagnose_rollout(name, namespace, include_events=True, include_analysis=True, include_pods=True)` as your **first step** to obtain the `RolloutDiagnosisReport` and its deterministic `diagnosis_codes`.
3. For `[GATE]` remediation steps: if the operator only asked to diagnose, inspect, or explain, do **not** mutate the cluster—report the root cause and exact remediation plan. If the operator explicitly asked to repair, abort, retry, or override the Rollout and `allow_write == true`, preview with `dry_run=True` where supported (`argo_configure_rollout_strategy`) and execute the remediation (`dry_run=False`, and `confirm=True` for `abort` or `skip_analysis`), then re-verify recovery.

## Diagnostic Triage Checklist

- [ ] **Step 1 — Collect Single-Call Diagnosis Report**:
  Call `argo_diagnose_rollout(name, namespace, include_events=True, include_analysis=True, include_pods=True)`.
- [ ] **Step 2 — Map `diagnosis_codes` to Root Cause**:
  Look up each code in [references/rollout-error-catalog.md](references/rollout-error-catalog.md):
  - `INVALID_SPEC_STRATEGY_CONFLICT` -> Both `canary` and `blueGreen` blocks exist on `spec.strategy`.
  - `ANALYSIS_RUN_FAILED` -> Metric threshold breached or Prometheus returned `Inconclusive`/`NaN`.
  - `ROLLOUT_ABORTED` -> Rollout aborted and scaled canary/preview to 0.
  - `IMAGE_PULL_BACKOFF` / `CRASH_LOOP_BACKOFF` -> Container image tag invalid or application startup crash.
  - `PROGRESS_DEADLINE_EXCEEDED` -> Pods failed readiness probes within `progressDeadlineSeconds`.
  - `PAUSED_AWAITING_PROMOTION` -> Rollout is paused at a canary step or blue-green preview gate.
  - `ARGOCD_TRAFFIC_ROUTING_DRIFT` -> ArgoCD tracking annotation present with `trafficRouting` enabled.
- [ ] **Step 3 — Inspect Supporting Context When Needed**:
  - Read `argorollout://rollouts/{namespace}/{name}/manifest` to inspect the sanitized Rollout spec.
  - Read `argorollout://cluster/health` to verify node readiness and cluster CPU/memory capacity (e.g., for `PROGRESS_DEADLINE_EXCEEDED` or unscheduled pods) rather than shelling out to `kubectl`.
  - Read `argorollout://rollouts/{namespace}/{name}/analysisruns` to inspect failing metric measurements.
  - Read `argorollout://history/{namespace}/{name}` to review ReplicaSet revisions and condition transitions.
- [ ] **Step 4 — `[GATE]` Execute Targeted Remediation**:
  - **Fix `INVALID_SPEC_STRATEGY_CONFLICT`**:
    Preview with `argo_configure_rollout_strategy(name, namespace, repair_conflicts=True, dry_run=True)`, then `[GATE]` apply with `dry_run=False`.
  - **Recover from `IMAGE_PULL_BACKOFF` or `CRASH_LOOP_BACKOFF`**:
    `[GATE]` Roll back immediately with `argo_manage_rollout_lifecycle(name, action="abort", namespace, confirm=True)` or deploy a fixed image via `argo_set_rollout_image(name, image, namespace)`.
  - **Retry After Fixing Transient Infrastructure (`ROLLOUT_ABORTED`)**:
    Call `argo_manage_rollout_lifecycle(name, action="retry", namespace)`.
  - **Emergency Override of False-Positive Analysis (`ANALYSIS_RUN_FAILED`)**:
    `[GATE]` Only after manual metric verification (`argo_compare_canary_metrics`) and explicit user confirmation, call `argo_manage_rollout_lifecycle(name, action="skip_analysis", namespace, confirm=True)`.
- [ ] **Step 5 — Verify Recovery**:
  Re-run `argo_diagnose_rollout(name, namespace)` and confirm `phase == "Healthy"` and `diagnosis_codes == ["HEALTHY"]`.

## Bundled References

- [references/rollout-error-catalog.md](references/rollout-error-catalog.md) — Complete lookup catalog of all `diagnosis_codes`, root causes, and exact MCP tool remediation steps.
