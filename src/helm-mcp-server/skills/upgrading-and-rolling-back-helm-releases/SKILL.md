---
name: upgrading-and-rolling-back-helm-releases
description: Plans, diffs, upgrades, and rolls back existing Helm releases on Kubernetes clusters with revision history inspection and rollout health verification. Use when upgrading a Helm release to a new chart version or values configuration, comparing live vs. proposed manifests, or rolling back a failed or degraded release to a previous revision.
---

# Upgrading and Rolling Back Helm Releases Procedure

## Overview

Mutating an active Helm release carries high blast radius. Follow these low-freedom operational sequences to prevent configuration drift, unintended value resets, or blind rollbacks.

---

## Workflow A: Safe Release Upgrade

### Step 1: Inspect Current Release State & Values
1. Read `kubernetes://contexts` to verify the active cluster context.
2. Call `helm_get_release_status(release_name="<release>", namespace="<ns>")` to record the current `revision`, `chart`, `chart_version`, and `status`.
3. Read `helm://releases/{namespace}/{release}/values` to inspect the currently applied user overrides.
4. Read `helm://releases/{namespace}/{release}/history` to identify the last known-good `deployed` revision number in case a rollback is needed.

### Step 2: Compute Server-Side Diff (`helm_plan_release`)
1. Consult [upgrade-checklist.md](./references/upgrade-checklist.md) to select the appropriate `values_strategy` (`reuse`, `reset`, or `reset_then_reuse`).
2. Call `helm_plan_release(chart_ref="<repo>/<chart>", release_name="<release>", namespace="<ns>", values={...}, version="<target-version>")`.
3. Review the returned `diff` object (`added_resources`, `removed_resources`, `modified_resources`, `image_changes`, `replica_changes`) before executing the upgrade.

### Step 3: Execute Upgrade & Monitor Rollout
1. **Always run `helm_plan_release` to preview the diff before calling `helm_upgrade_release` in every environment** (both `atomic=True` production upgrades and `atomic=False` dev/debugging upgrades).
2. Call `helm_upgrade_release`:
   - Pass explicit `chart_ref`, `version`, `values`, and `values_strategy`.
   - Use `atomic=True` with an explicit `wait_timeout` (e.g., `"5m"`) for production / tier-1 releases so Helm automatically reverts on readiness timeout or failure; use `atomic=False` in dev/debugging environments when you need failing pods left in place to inspect crash logs and Kubernetes events, and monitor explicitly via `helm_monitor_deployment`.
3. Call `helm_monitor_deployment(release_name="<release>", namespace="<ns>", max_wait_seconds=120, check_interval=5)`.
4. If `status == "failed"` or `"timeout"`, immediately execute **Workflow B (Rollback)** below.

---

## Workflow B: Controlled Release Rollback

### Step 1: Identify Target Revision
1. Call `helm_get_release_status(release_name="<release>", namespace="<ns>")` and read `helm://releases/{namespace}/{release}/history` to list all revisions and their statuses.
2. Select the most recent revision with `status: "deployed"` or `"superseded"` prior to the faulty upgrade. Never guess a revision number or run `dry_run=False` blindly—if asked to roll back without checking history, refuse the blind `dry_run=False` execution, immediately run read-only `helm_get_release_status` + `helm://releases/{namespace}/{release}/history` (and a `dry_run=True` preview on the verified revision), and present the verified revision for operator confirmation.
3. Consult [rollback-sop.md](./references/rollback-sop.md) for stateful workload and CRD caveats.

### Step 2: Dry-Run Rollback Preview
1. Call `helm_rollback_release(release_name="<release>", namespace="<ns>", revision=<target-revision>, dry_run=True)`.
2. Verify the dry-run succeeds without hook or webhook errors.

### Step 3: Execute Rollback & Verify Recovery
1. Call `helm_rollback_release(release_name="<release>", namespace="<ns>", revision=<target-revision>, dry_run=False, wait_timeout="5m")`.
2. Call `helm_monitor_deployment(release_name="<release>", namespace="<ns>", max_wait_seconds=120, check_interval=5)` to confirm all Deployments and StatefulSets return to `ready`.
3. Call `helm_get_release_status(release_name="<release>", namespace="<ns>")` to confirm the new revision is in `deployed` state.

---

## Workflow C: Controlled Release Decommission (`helm_uninstall_release`)

1. **Audit-Retaining Uninstall (`keep_history=True`):** Deletes all live Kubernetes workloads and resources managed by the release while preserving the Helm release ledger (`sh.helm.release.v1.*`) in the namespace so revision history remains queryable for compliance audits or `helm_rollback_release` recovery.
2. **Permanent Purge (`keep_history=False`):** Permanently removes both live Kubernetes resources (if any remain) and all stored Helm release history Secrets once retention requirements expire.
