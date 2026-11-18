# ArgoCD Sync Strategies, Waves, and Selective Sync Reference

## Table of Contents
1. [Manual vs Automated Sync Policies](#1-manual-vs-automated-sync-policies)
2. [Sync Options Reference](#2-sync-options-reference)
3. [Sync Waves and Resource Hooks](#3-sync-waves-and-resource-hooks)
4. [Selective Resource Synchronization](#4-selective-resource-synchronization)
5. [Normal vs Hard Refresh](#5-normal-vs-hard-refresh)

---

## 1. Manual vs Automated Sync Policies

| Policy Setting | Field in `sync_policy` | Production Recommendation | Behavior |
|---|---|---|---|
| **Automated Sync** | `automated: true/false` | `false` for critical tier-1 services requiring change windows; `true` for stateless/dev workloads | Automatically applies Git commits when drift is detected |
| **Auto-Prune** | `prune: true/false` | `false` by default; enable only when Git deletions are peer-reviewed | Deletes Kubernetes objects removed from Git manifests |
| **Self-Heal** | `self_heal: true/false` | `true` when `automated: true` | Reverts out-of-band `kubectl edit` changes back to Git state (default 5s reconciliation timeout) |
| **Create Namespace** | `create_namespace: true/false` | `true` for isolated per-service namespaces | Adds `CreateNamespace=true` to `spec.syncPolicy.syncOptions` |

---

## 2. Sync Options Reference

Common `syncOptions` entries in ArgoCD `Application.spec.syncPolicy.syncOptions`:

- `CreateNamespace=true`: Ensures target namespace exists before applying resources.
- `PruneLast=true`: Delays pruning removed resources until after all new/updated resources are healthy.
- `ApplyOutOfSyncOnly=true`: Reduces API server load on large applications by applying only resources marked `OutOfSync`.
- `ServerSideApply=true`: Uses Kubernetes Server-Side Apply instead of client-side 3-way merge (recommended for CRDs with large schemas such as Prometheus/Istio).
- `Replace=true`: Uses `kubectl replace` instead of `kubectl apply` (use with caution on immutable fields).
- `FailOnSharedResource=true`: Fails the sync if another ArgoCD Application already manages the same Kubernetes object.

---

## 3. Sync Waves and Resource Hooks

ArgoCD orders resource application during a sync operation by:
1. **Phase**: `PreSync` -> `Sync` -> `PostSync` (and `SyncFail` on failure)
2. **Sync Wave** (`argocd.argoproj.io/sync-wave: "<integer>"`, default `0`, ascending from negative to positive)
3. **Resource Kind** (Namespaces -> Secrets/ConfigMaps -> CRDs -> Roles -> Services -> Deployments/StatefulSets -> Ingresses)

### Common Wave Ordering Pattern
- **Wave `-2`**: Namespace, ResourceQuota, LimitRange, NetworkPolicy
- **Wave `-1`**: ConfigMaps, Secrets, ServiceAccounts, RBAC Roles, DB Migration `PreSync` Jobs (`argocd.argoproj.io/hook: PreSync`, `argocd.argoproj.io/hook-delete-policy: BeforeHookCreation`)
- **Wave `0`**: StatefulSets, Deployments, DaemonSets
- **Wave `1`**: Services, Ingresses, HorizontalPodAutoscalers
- **Wave `2`**: Smoke-test `PostSync` Jobs (`argocd.argoproj.io/hook: PostSync`, `argocd.argoproj.io/hook-delete-policy: BeforeHookCreation`)

---

## 4. Selective Resource Synchronization

When only a subset of resources in an application should be synchronized (for example, syncing a `ConfigMap` and `Deployment` without touching a `StatefulSet`), pass the `resources` filter list to `sync_application`:

```json
{
  "app_name": "payments-service",
  "dry_run": true,
  "resources": [
    {
      "group": "",
      "kind": "ConfigMap",
      "name": "payments-config",
      "namespace": "payments-prod"
    },
    {
      "group": "apps",
      "kind": "Deployment",
      "name": "payments-api",
      "namespace": "payments-prod"
    }
  ]
}
```

---

## 5. Normal vs Hard Refresh

- **`refresh_application(app_name, mode="normal")`**: Asks `argocd-repo-server` to compare live cluster state against the latest Git commit using the cached manifest build if the commit SHA has not changed.
- **`refresh_application(app_name, mode="hard")`**: Forces `argocd-repo-server` to invalidate its manifest cache and re-render Helm charts / Kustomize overlays from scratch. Use `mode="hard"` when a mutable Git tag (e.g., `latest` or `stable`) or upstream Helm chart dependency was updated without changing the commit reference.
