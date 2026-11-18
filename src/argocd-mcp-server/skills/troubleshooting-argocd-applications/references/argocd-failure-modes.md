# ArgoCD and Kubernetes Failure Modes Diagnostic Reference

## Table of Contents
1. [ArgoCD Condition & Sync Phase Errors](#1-argocd-condition--sync-phase-errors)
2. [Kubernetes Workload Health Failures](#2-kubernetes-workload-health-failures)
3. [Drift and OutOfSync Edge Cases](#3-drift-and-outofsync-edge-cases)

---

## 1. ArgoCD Condition & Sync Phase Errors

| Error Signature / Condition | Root Cause | Diagnostic Tool | Remediation |
|---|---|---|---|
| `ComparisonError: rpc error: ... authentication required` | Git repository credentials expired, missing, or invalid | `get_repository(repo_url=...)` | Re-onboard repository with updated server credentials via `onboard_repository` |
| `InvalidSpecError: application repo ... is not permitted in project` | `AppProject.spec.sourceRepos` does not include the application's Git URL | `get_project(project_name=...)` | Add `repo_url` to project via `update_project` |
| `InvalidSpecError: application destination ... is not permitted in project` | `AppProject.spec.destinations` does not allow the target cluster or namespace | `get_project(project_name=...)` | Add `{server, namespace}` to `destinations` via `update_project` |
| `resource Kind is not permitted in project` | `clusterResourceWhitelist` or `namespaceResourceBlacklist` blocks the Kubernetes resource kind | `get_project(project_name=...)` | Update `resource_restrictions` via `update_project` |
| `one or more synchronization tasks are not valid ... field is immutable` | Kubernetes rejects `kubectl apply` on an immutable field (e.g., `StatefulSet` volumeClaimTemplates or `Job` selector) | `get_sync_status` + `get_application_diff` | Use `force=True` on `sync_application` (after operator confirmation) or recreate the resource |
| `PreSync hook failed` | Database migration or pre-flight Kubernetes `Job` exited non-zero | `get_application_resource_tree` + `get_application_logs(pod_name=...)` | Fix migration failure or inspect DB connectivity before re-syncing |

---

## 2. Kubernetes Workload Health Failures

| Event Reason / Pod Status | Typical Cause | Evidence Source | Remediation |
|---|---|---|---|
| `CrashLoopBackOff` / `BackOff` | Application process crashes on startup (missing env var, secret, config syntax error, unhandled exception) | `get_application_logs(app_name, pod_name, errors_only=False)` | Roll back to previous history ID (`rolling-back-argocd-applications`) or fix ConfigMap/Secret in Git |
| `ImagePullBackOff` / `ErrImagePull` | Container image tag does not exist in registry or `imagePullSecrets` is missing | `get_application_events(app_name, warnings_only=True)` | Verify image tag in Git manifest or roll back to previous revision |
| `Unhealthy` (Readiness/Liveness probe failed) | Container takes longer than `initialDelaySeconds` to start or health endpoint returns HTTP 5xx | `get_application_events` + `get_application_logs` | Check downstream dependency connectivity or adjust probe thresholds in Git |
| `FailedScheduling` | Insufficient CPU/memory on cluster nodes, nodeSelector/affinity mismatch, or untolerated taint | `get_application_events(app_name, warnings_only=True)` | Reduce resource requests in Git manifest or scale cluster node pool |
| `FailedMount` / `FailedAttachVolume` | Referenced `Secret`, `ConfigMap`, or `PersistentVolumeClaim` does not exist in target namespace | `get_application_events(app_name, warnings_only=True)` | Ensure Secret/ConfigMap is included in sync or created in the namespace |

---

## 3. Drift and OutOfSync Edge Cases

- **Stale Manifest Cache**: If a Git branch or tag was force-pushed and ArgoCD still shows the old commit or manifest, run `refresh_application(app_name=..., mode="hard")`.
- **Mutating Admission Webhooks / HPA Replicas**: If `Deployment.spec.replicas` is managed by an HPA, `get_application_diff` will continuously show `OutOfSync` unless `spec.replicas` is omitted from the Git manifest or configured in `ignoreDifferences`.
- **Orphaned Resources After Rename**: If a resource was renamed in Git and `prune=False` was used during sync, both the old and new resources remain in the cluster. Run `sync_application(app_name=..., dry_run=True, prune=True)` to preview pruning the stale resource.
