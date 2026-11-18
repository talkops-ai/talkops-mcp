---
name: rolling-back-argocd-applications
description: Safely rolls back degraded or failing ArgoCD applications to a known-good deployment history ID, handling auto-sync blockers, dry-run rollback previews, operator confirmation, and post-rollback health verification. Use when an operator requests a rollback, when a recent deployment causes Degraded health or CrashLoopBackOff, or when reverting an application to an earlier revision.
allowed-tools:
  - get_application_details
  - get_application_diff
  - rollback_application
  - sync_application
  - update_application
  - get_sync_status
  - get_application_events
  - get_application_logs
---

# Rolling Back ArgoCD Applications

Perform controlled, auditable rollbacks in ArgoCD using deployment history IDs while preventing automated sync policies from immediately overwriting the rollback.

## Critical ArgoCD Rollback Invariant: Auto-Sync Blocker

ArgoCD's `/api/v1/applications/{name}/rollback` endpoint **rejects or immediately overwrites rollbacks** if `spec.syncPolicy.automated` is enabled, because the controller continuously reconciles the cluster back to the Git `targetRevision` (e.g., `HEAD`).

Before executing `rollback_application(..., dry_run=False)`:
1. Check `auto_sync_enabled` in `get_application_details` (or `auto_sync_blocker` in the `dry_run=True` rollback preview).
2. If `True`, either:
   - **Temporary Incident Mitigation**: Disable auto-sync first via `update_application(app_name="<app>", sync_policy={"automated": False})` after operator confirmation, execute the rollback, and remind the team to revert the offending commit in Git before re-enabling auto-sync.
   - **Git-Native Rollback**: Preview the target revision first via `get_application_diff` and `sync_application(..., dry_run=True)`, then pin `target_revision` to the known-good tag/SHA via `update_application(app_name="<app>", target_revision="<good_sha>")`, execute `sync_application(..., dry_run=False)`, and verify `Synced` + `Healthy` status (keeping auto-sync intact).

---

## Step-by-Step Rollback Workflow

### Step 1: Capture Failure Evidence, Inspect History IDs & Check Auto-Sync
1. Call `get_application_details(app_name="<app>", detail_level="full")` and read `argocd://applications/{app_name}/history`.
2. If pods are currently `Degraded` (`CrashLoopBackOff` / `OOMKilled`), capture pre-rollback failure evidence via `get_application_events(app_name="<app>", warnings_only=True)` and `get_application_logs(app_name="<app>", errors_only=True)` before pod replacement wipes ephemeral state.
3. Examine `sync_history` entries (`id`, `revision`, `deployed_at`, `initiated_by`):
   - The last entry (`sync_history[-1]`) is the currently active deployment.
   - The second-to-last entry (`sync_history[-2]`) is the immediately preceding deployment.
   - **Initial-deploy guard**: If `len(history) < 2` (only `id: 0` exists), `rollback_application` has no prior revision to restore—explain why and route to forward Git remediation (`deploying-argocd-applications`) or runtime triage (`troubleshooting-argocd-applications`).
   - **History-limit guard**: `rollback_application` requires an integer `history_id` (never a Git SHA string). If a target commit is older than `spec.revisionHistoryLimit` (evicted from `status.history`), use `update_application(target_revision="<sha_or_tag>")` + `sync_application` instead.
4. Record the target integer `history_id` and its `revision`.

### Step 2: Run a Dry-Run Rollback Preview
1. Call `rollback_application(app_name="<app>", history_id=<target_id>, dry_run=True, prune=False)`.
   - If `history_id` is omitted, `rollback_application` automatically selects `sync_history[-2]`.
   - Default `prune=False` reverts modified objects but leaves newly added resources (e.g., a rogue `NetworkPolicy` or `ConfigMap` introduced in the faulty deploy) active in-cluster; pass `prune=True` on the dry-run preview when evaluating removal of newly added resources.
2. Inspect the preview response:
   - `history_id` and `target_revision`
   - `current_revision`
   - `auto_sync_blocker` and `warning`
3. Optionally call `get_application_diff(app_name="<app>", revision="<target_revision>", validate=False)` to show the operator the exact manifest delta between live state and the rollback target.

### Step 3: Present Impact Summary & Obtain Confirmation
Present to the operator:
- Application name and current health/sync status
- Rollback transition: `current_revision` -> `target_revision` (History ID `<id>`, deployed at `<deployed_at>`)
- Whether auto-sync must be disabled first (`auto_sync_blocker == True`)
- Whether `prune=True` will delete resources created since History ID `<id>`

### Step 4: Disable Auto-Sync (If Blocking) & Execute Rollback
1. If the operator has not yet approved a live rollback (or asked only for a check/preview), stop after Step 3 and request approval. When the operator has already approved rolling back in their request, run Steps 1–3 first and proceed directly to execution below.
2. If `auto_sync_blocker` is `True` and rolling back was approved:
   ```json
   {
     "app_name": "<app>",
     "sync_policy": {"automated": false}
   }
   ```
   via `update_application`.
2. Execute the rollback with `dry_run=False` and `confirm=True`:
   ```json
   {
     "app_name": "<app>",
     "history_id": 14,
     "dry_run": false,
     "prune": false,
     "confirm": true
   }
   ```

### Step 5: Verify Post-Rollback Health Recovery
1. Call `get_sync_status(app_name="<app>")` to confirm `last_operation.phase == "Succeeded"` (note: `Succeeded` only confirms manifest apply succeeded, not runtime pod readiness).
2. Call `get_application_details(app_name="<app>", detail_level="summary")` to verify `health_status == "Healthy"`. If `health_status` remains `Degraded` despite `Succeeded`, check upstream/stateful dependencies (e.g., PostgreSQL, Valkey, Kafka, feature flags) via `get_application_events` and `get_application_logs`.
3. Call `get_application_logs(app_name="<app>", errors_only=True)` and `get_application_events(app_name="<app>", warnings_only=True)` to verify no new runtime errors or CrashLoopBackOff events remain.
4. Remind the operator that if `targetRevision` in Git still points to `HEAD`, the application will show `OutOfSync` against `HEAD` until the faulty Git commit is reverted.

See [references/rollback-and-autosync.md](references/rollback-and-autosync.md) for detailed comparison of ArgoCD history-ID rollback vs. Git revert and `targetRevision` pinning.
