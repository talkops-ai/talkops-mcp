# ArgoCD Rollback Mechanics and Auto-Sync Interaction Reference

## Table of Contents
1. [How ArgoCD History IDs Work](#1-how-argocd-history-ids-work)
2. [Why Automated Sync Blocks Rollback](#2-why-automated-sync-blocks-rollback)
3. [Choosing Between History-ID Rollback and Target-Revision Pinning](#3-choosing-between-history-id-rollback-and-target-revision-pinning)
4. [Pruning Considerations During Rollback](#4-pruning-considerations-during-rollback)

---

## 1. How ArgoCD History IDs Work

Every successful synchronization in ArgoCD appends an entry to `status.history` (up to `revisionHistoryLimit`, default `10`):

```json
{
  "id": 14,
  "revision": "8f3c1a9d4e2b...",
  "deployedAt": "2026-10-30T14:22:10Z",
  "deployStartedAt": "2026-10-30T14:21:55Z",
  "initiatedBy": {"username": "ci-bot"},
  "source": {
    "repoURL": "https://github.com/org/gitops.git",
    "path": "apps/api",
    "targetRevision": "HEAD"
  }
}
```

- **Important**: The ArgoCD REST API (`POST /api/v1/applications/{name}/rollback`) requires the integer `id` field (`14`), **not** the Git commit SHA string.
- `get_application_details` and `argocd://applications/{app_name}/history` return normalized history entries sorted ascending by `id`, where `[-1]` is the active deployment and `[-2]` is the previous deployment.

---

## 2. Why Automated Sync Blocks Rollback

When `spec.syncPolicy.automated` is non-empty:
1. ArgoCD's API server returns an error on `/rollback` (`rollback cannot be initiated when auto-sync is enabled`), or
2. Even if forced, the application controller immediately detects that the live cluster state (at old commit `A`) differs from `spec.source.targetRevision` (`HEAD` at faulty commit `B`) and re-syncs commit `B`.

Therefore, `rollback_application` checks `spec.syncPolicy.automated`:
- During `dry_run=True`, it sets `"auto_sync_blocker": true` and returns an actionable `"warning"` without failing.
- During `dry_run=False`, it blocks execution with `SyncOperationFailed` if auto-sync is still active, instructing the agent to disable auto-sync via `update_application` first.

---

## 3. Choosing Between History-ID Rollback and Target-Revision Pinning

| Approach | Tool Sequence | Best Used When | Post-Action State |
|---|---|---|---|
| **History-ID Rollback** | `update_application(sync_policy={"automated": False})` -> `rollback_application(history_id=N, dry_run=False)` | Fast incident mitigation when the app tracks a moving branch (`HEAD`/`main`) and a Git revert PR is still being prepared | `health_status: Healthy`, `sync_status: OutOfSync` (until Git revert merges) |
| **Target-Revision Pinning** | `update_application(target_revision="<previous-tag>")` -> `sync_application(dry_run=False)` | Application tracks immutable release tags (`v1.3.0` -> `v1.2.9`) | `health_status: Healthy`, `sync_status: Synced` (auto-sync can remain enabled) |

---

## 4. Pruning Considerations During Rollback

- **`prune=False` (Default)**: Reverts modified resources (such as `Deployment` image tags and `ConfigMap` values) to the target history revision, but leaves any new Kubernetes resources introduced in the bad release untouched.
- **`prune=True`**: Also deletes Kubernetes resources that were newly created after the target history ID. Enable `prune=True` only when a newly introduced resource (e.g., a broken `ValidatingWebhookConfiguration`, `NetworkPolicy`, or `HorizontalPodAutoscaler`) is causing the outage.
