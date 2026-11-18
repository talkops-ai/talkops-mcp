# Helm Rollback Standard Operating Procedure (SOP)

## Table of Contents

1. [When to Trigger a Rollback](#1-when-to-trigger-a-rollback)
2. [Selecting the Target Revision](#2-selecting-the-target-revision)
3. [Handling Stuck `pending-upgrade` or `pending-install` States](#3-handling-stuck-pending-upgrade-or-pending-install-states)
4. [Data & Stateful Workload Considerations](#4-data--stateful-workload-considerations)
5. [Post-Rollback Verification](#5-post-rollback-verification)

---

## 1. When to Trigger a Rollback

Initiate a rollback when any of the following conditions occur after `helm_upgrade_release`:
- `helm_monitor_deployment` returns `status: "failed"` with terminal container states (`CrashLoopBackOff`, `ImagePullBackOff`, `ErrImagePull`, `CreateContainerConfigError`, `OOMKilledRecurring`, or `ProgressDeadlineExceeded`).
- `helm_get_release_status` reports `status: "failed"` due to a pre-/post-upgrade hook failure or admission webhook rejection.
- Application health checks or readiness probes fail beyond `max_wait_seconds`.

---

## 2. Selecting the Target Revision

1. Read `helm://releases/{namespace}/{release}/history`.
2. Each entry in the history array contains `revision`, `status`, `chart`, `app_version`, and `description`.
3. Choose the highest revision number prior to the failed upgrade whose status is `"superseded"` or `"deployed"`.
4. Avoid rolling back to revisions marked `"failed"` or `"pending-upgrade"`.

---

## 3. Handling Stuck `pending-upgrade` or `pending-install` States

- If a previous Helm operation was interrupted mid-flight, `helm_get_release_status` will show `status: "pending-upgrade"` or `"pending-rollback"`, and subsequent `helm_upgrade_release` calls will fail with `Error: UPGRADE FAILED: another operation (install/upgrade/rollback) is in progress`.
- **Resolution:** Execute `helm_rollback_release(release_name="<release>", namespace="<ns>", revision=<last-good-revision>)` to clear the pending lock and restore the release to a clean `deployed` state.

---

## 4. Data & Stateful Workload Considerations

- `helm_rollback_release` reverts Kubernetes manifests (Deployments, StatefulSets, ConfigMaps, Secrets, Services) to the target revision's snapshot, creating a new revision number ($N + 1$).
- **PersistentVolumeClaims (PVCs) and database schemas are NOT rolled back by Helm.** If a chart upgrade executed an irreversible database schema migration via a pre-upgrade Job hook, verify backward compatibility of the schema before rolling back application pods.

---

## 5. Post-Rollback Verification

After `helm_rollback_release` completes:
1. Run `helm_monitor_deployment(release_name="<release>", namespace="<ns>")` and confirm `status == "ready"`.
2. Read `helm://releases/{namespace}/{release}/history` to confirm the newly created revision shows `status: "deployed"` with description `"Rollback to <revision>"`.
3. Inspect `helm://releases/{namespace}/{release}/values` to confirm configuration state matches expectations.
