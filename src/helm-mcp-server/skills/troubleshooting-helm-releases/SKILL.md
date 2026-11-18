---
name: troubleshooting-helm-releases
description: Diagnoses and resolves failed or degraded Helm releases, Kubernetes rollout failures, pod CrashLoopBackOff, ImagePullBackOff, OOMKilled containers, Pending pods, and CRD ownership conflicts. Use when helm_monitor_deployment reports failed or timeout status, when helm install or upgrade fails, or when investigating unhealthy Helm workloads.
---

# Troubleshooting Helm Releases Procedure

## Overview

When a Helm installation, upgrade, or running workload fails, follow this structured diagnostic workflow to isolate the root cause and remediate safely without guessing.

---

## Phase 1: Collect Release & Workload Diagnostics

> **MCP-Only Diagnostics:** Execute all cluster, release, and chart inspections strictly through the Helm MCP server (`helm_*` tools, `kubernetes_*` tools, and `kubernetes://` / `helm://` resources). Never run raw `kubectl` or `helm` shell commands.

1. **Verify Active Context First:**
   - Always read `kubernetes://contexts` in your very first step before calling release tools to ensure diagnostics run against the right cluster.
2. **Inspect Release State, Dependencies & History:**
   - Call `helm_get_release_status(release_name="<release>", namespace="<ns>")` (and `helm_list_releases(namespace="<ns>")` if verifying whether a release is installed).
   - If an `initContainer` or startup check waits on a peer dependency release (such as `valkey-cart`, `postgresql`, or `flagd`), call `helm_get_release_status` for that dependency release as well to confirm it is `deployed` and healthy.
   - Read `helm://releases/{namespace}/{release}/history` to see whether a recent upgrade or hook failed.
3. **Run Multi-Layer Deployment Monitor:**
   - Call `helm_monitor_deployment(release_name="<release>", namespace="<ns>", max_wait_seconds=15, check_interval=5)`.
   - Inspect the structured `issues` array. Each issue contains `severity` (`error` | `warning`), `resource`, `reason`, and `message`.

---

## Phase 2: Branch by Failure Reason

Match the `reason` from `helm_monitor_deployment` or the error message from `helm_install_chart` / `helm_upgrade_release` against the table below and consult [error-catalog.md](./references/error-catalog.md) for detailed remediation steps:

| Issue Reason / Error Signature | Root Cause Category | Immediate Diagnostic / Remediation Action |
|---|---|---|
| `CrashLoopBackOff` / `HighRestartCount` | Application crash, bad config, or failing liveness probe | Read `helm://releases/{namespace}/{release}/values` and `helm://releases/{namespace}/{release}/manifest` to check env vars, command args, and probe paths. |
| `ImagePullBackOff` / `ErrImagePull` / `InvalidImageName` | Non-existent image tag, private registry auth missing | Verify `image.repository`, `image.tag`, and `imagePullSecrets` in `helm://releases/{namespace}/{release}/values`. |
| `OOMKilledRecurring` | Container memory limit exceeded | Upgrade release with increased `resources.limits.memory` via `helm_upgrade_release`. |
| `FailedScheduling` / `Unschedulable` (`Pending`) | Insufficient cluster CPU/memory, unbound PVC, or node taint/affinity mismatch | Read `kubernetes://cluster-info` and check storageClass / resource requests in `helm://releases/{namespace}/{release}/values`. |
| `ProgressDeadlineExceeded` | Rollout stalled due to failing readiness probe or image/config error | Correlate with container-level issues in `helm_monitor_deployment`; rollback via `helm_rollback_release` if caused by a bad upgrade. |
| `invalid ownership metadata` / `CRD conflict` | CRDs or cluster-scoped resources already owned by another release | Check existing releases with `helm_list_releases`. **Never delete shared cluster CRDs** (deleting a CRD cascade-deletes all custom resources cluster-wide); reuse/upgrade the owning release or pass `skip_crds=True` to `helm_install_chart`. |
| `cannot re-use a name that is still in use` | Release already exists in target namespace | Call `helm_get_release_status`; use `helm_upgrade_release` if `deployed`, or if `failed` at revision `1` with no prior `deployed` revision, run `helm_uninstall_release(..., keep_history=False)`, **preview via `helm_plan_release`**, and install via `helm_install_chart`. |
| `another operation (install/upgrade/rollback) is in progress` | Release stuck in `pending-upgrade` or `pending-install` | Call `helm_rollback_release` to the last `deployed` revision from `helm://releases/{namespace}/{release}/history`. |

---

## Phase 3: Remediation & Verification

1. **If caused by a recent upgrade:** Follow the `upgrading-and-rolling-back-helm-releases` skill to roll back to the previous working revision via `helm_rollback_release`.
2. **If caused by misconfigured values:**
   - Check `helm://repositories` first (Helm release metadata stores `<chart>-<version>` without its source repo URL); if the chart's repository is missing, register it via `helm_ensure_repository` (see canonical repository URLs in [error-catalog.md](./references/error-catalog.md)).
   - Preview the fix using `helm_plan_release(chart_ref="<repo>/<chart>", release_name="<release>", namespace="<ns>", values={...})`.
   - Apply the fix with `helm_upgrade_release(release_name="<release>", chart_ref="<repo>/<chart>", namespace="<ns>", values={...}, values_strategy="reuse")`.
3. **Verify Resolution:**
   - Call `helm_monitor_deployment(release_name="<release>", namespace="<ns>", max_wait_seconds=120, check_interval=5)` and confirm `status == "ready"` and `issues == []`.
