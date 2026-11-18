# Argo Rollouts Error & Diagnosis Code Catalog

## Table of Contents

1. [INVALID_SPEC_STRATEGY_CONFLICT](#1-invalid_spec_strategy_conflict)
2. [ANALYSIS_RUN_FAILED](#2-analysis_run_failed)
3. [ROLLOUT_ABORTED](#3-rollout_aborted)
4. [IMAGE_PULL_BACKOFF](#4-image_pull_backoff)
5. [CRASH_LOOP_BACKOFF](#5-crash_loop_backoff)
6. [PROGRESS_DEADLINE_EXCEEDED](#6-progress_deadline_exceeded)
7. [PAUSED_AWAITING_PROMOTION](#7-paused_awaiting_promotion)
8. [ARGOCD_TRAFFIC_ROUTING_DRIFT](#8-argocd_traffic_routing_drift)
9. [REPLICA_DEGRADED](#9-replica_degraded)
10. [HEALTHY](#10-healthy)

---

## 1. `INVALID_SPEC_STRATEGY_CONFLICT`

- **Symptom**: Rollout phase is `Degraded` with condition `InvalidSpec`: `"Rollout has invalid spec: spec.strategy may not specify both canary and blueGreen"`.
- **Root Cause**: A patch added `spec.strategy.canary` (for example, `canary.analysis`) to a `blueGreen` Rollout.
- **Remediation**:
  1. Preview removal of the conflicting `canary` block:
     `argo_configure_rollout_strategy(name, namespace, repair_conflicts=True, dry_run=True)`
  2. `[GATE]` Apply the fix:
     `argo_configure_rollout_strategy(name, namespace, repair_conflicts=True, dry_run=False)`

## 2. `ANALYSIS_RUN_FAILED`

- **Symptom**: `AnalysisRun` in `argorollout://rollouts/{namespace}/{name}/analysisruns` has `phase: "Failed"`, `"Error"`, or `"Inconclusive"`.
- **Root Cause**:
  - Canary error rate or latency breached `AnalysisTemplate` `successCondition`.
  - Prometheus returned empty data (`0/0 -> NaN`), marking the run `Inconclusive`.
  - Prometheus endpoint is unreachable (check `argorollout://metrics/prometheus/status`).
- **Remediation**:
  - If genuine regression: keep the rollout aborted, deploy a fixed image via `argo_set_rollout_image`, or re-run `argo_manage_rollout_lifecycle(action="abort", confirm=True)`.
  - If false positive due to threshold/query bug: update the template via `argo_configure_analysis_template(..., dry_run=False)`, then call `argo_manage_rollout_lifecycle(name, action="retry", namespace)`.

## 3. `ROLLOUT_ABORTED`

- **Symptom**: Rollout `status.abort == true` and canary weight is reverted to `0`.
- **Root Cause**: Manual `abort` call or automated `AnalysisRun` failure.
- **Remediation**:
  - Once the underlying issue is resolved, call `argo_manage_rollout_lifecycle(name, action="retry", namespace)` to clear the abort state, or push a new image with `argo_set_rollout_image`.

## 4. `IMAGE_PULL_BACKOFF`

- **Symptom**: Canary or preview pods are stuck in `Waiting: ImagePullBackOff` or `ErrImagePull`.
- **Root Cause**: Non-existent image tag, private registry authentication missing (`imagePullSecrets`), or registry rate limit.
- **Remediation**:
  1. `[GATE]` Abort the rollout to clean up broken canary pods:
     `argo_manage_rollout_lifecycle(name, action="abort", namespace, confirm=True)`
  2. Set a valid container image tag:
     `argo_set_rollout_image(name, image="<valid-image>", namespace)`

## 5. `CRASH_LOOP_BACKOFF`

- **Symptom**: Canary pods repeatedly restart with `Waiting: CrashLoopBackOff`.
- **Root Cause**: Application panic on startup, missing ConfigMap/Secret env var, or failing `livenessProbe`.
- **Remediation**:
  1. Inspect `argorollout://rollouts/{namespace}/{name}/manifest` to check container ports, probes, and environment references.
  2. `[GATE]` Abort the rollout via `argo_manage_rollout_lifecycle(name, action="abort", namespace, confirm=True)`.

## 6. `PROGRESS_DEADLINE_EXCEEDED`

- **Symptom**: Condition `Progressing=False` with reason `ProgressDeadlineExceeded`.
- **Root Cause**: Canary/preview pods did not pass `readinessProbe` within `spec.progressDeadlineSeconds` (default 600s), or insufficient cluster CPU/memory prevented scheduling (check `argorollout://cluster/health`).
- **Remediation**:
  1. Check `argorollout://cluster/health` and `warning_events` in `argo_diagnose_rollout`.
  2. Abort (`action="abort", confirm=True`) or retry (`action="retry"`) once capacity or probe configuration is fixed.

## 7. `PAUSED_AWAITING_PROMOTION`

- **Symptom**: Rollout phase is `Paused` with `pauseConditions` populated.
- **Root Cause**: Normal progressive delivery pause step (`pause: {}` or timed pause) or blue-green preview gate (`autoPromotionEnabled: false`).
- **Remediation**:
  1. Compare canary vs. stable metrics with `argo_compare_canary_metrics(rollout_name=name, namespace=namespace)`.
  2. Advance to next step with `argo_manage_rollout_lifecycle(name, action="promote", namespace)` or resume with `action="resume"`.

## 8. `ARGOCD_TRAFFIC_ROUTING_DRIFT`

- **Symptom**: Rollout has `argocd.argoproj.io/tracking-id` annotation and `spec.strategy.canary.trafficRouting` configured; weights or `trafficRouting` get reset on ArgoCD sync.
- **Remediation**:
  - Run `skills/onboarding-and-migrating-to-argo-rollouts/scripts/generate_argocd_ignore_differences.py --include-rollout-traffic-routing --include-traefik-service` and add the snippet to the ArgoCD `Application` spec.

## 9. `REPLICA_DEGRADED`

- **Symptom**: Rollout phase is `Degraded` without an explicit abort or strategy conflict.
- **Root Cause**: Available replicas are fewer than desired replicas due to node eviction, OOMKill, or Service selector mismatch.
- **Remediation**: Inspect `warning_events` and `pods` from `argo_diagnose_rollout(name, namespace, include_pods=True)`.

## 10. `HEALTHY`

- **Symptom**: Rollout phase is `Healthy`, all desired replicas are ready and updated, and no warning conditions are active.
- **Action**: No remediation needed.
