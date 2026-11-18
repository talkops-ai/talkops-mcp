---
name: troubleshooting-argocd-applications
description: Diagnoses degraded, out-of-sync, or failing ArgoCD applications by correlating application details, Kubernetes resource trees, warning events, sync operation phases, and pod logs into a structured root-cause report. Use when an application is Degraded, OutOfSync, Missing, or Progressing, when a sync operation fails, or when pods crash or fail readiness checks.
allowed-tools:
  - list_applications
  - get_application_details
  - get_application_resource_tree
  - get_application_events
  - get_application_logs
  - get_application_diff
  - get_sync_status
  - refresh_application
  - get_repository
  - get_project
---

# Troubleshooting ArgoCD Applications

Systematically isolate the root cause of ArgoCD sync failures, `Degraded` workloads, and configuration drift using **strictly read-only ArgoCD MCP diagnostic tools** before proposing any remediation. Never invoke mutating tools (`sync_application`, `rollback_application`, `update_application`, `delete_application`) or shell `kubectl`/`argocd` CLI commands during triage.

## 5-Step Diagnostic Triage Workflow

### Step 1: Assess High-Level Application State & Conditions
1. Call `get_application_details(app_name="<app>", detail_level="full")` (or `list_applications(health_status="Degraded")` for fleet-wide triage, prioritizing foundational databases/caches/queues before downstream microservices).
2. Classify the failure domain based on `sync_status`, `health_status`, and `conditions`:
   - **`ComparisonError` / `InvalidSpecError` in `conditions`**: Repository access, Helm/Kustomize rendering, or AppProject RBAC violation. Call `refresh_application(app_name="<app>", mode="hard")` when checking stale repo/tag caches.
   - **`sync_status == "OutOfSync"` with `last_operation.phase == "Failed"`**: Sync hook failure, schema validation error, or immutable field conflict (for immutable `Job` templates, recommend `argocd.argoproj.io/hook-delete-policy: BeforeHookCreation` or resource-level `Replace=true` rather than whole-app `force=True`).
   - **`sync_status == "Synced"` but `health_status == "Degraded"` or `"Progressing"`**: Kubernetes runtime failure (CrashLoopBackOff, ImagePullBackOff, failing readiness probe, Pending PVC/scheduling).
   - **Perpetual `OutOfSync` on HPA-managed `spec.replicas`**: Confirm `/spec/replicas` drift via `get_application_diff(..., validate=True)` and prescribe omitting `spec.replicas` when HPA is active plus `ignoreDifferences` (`jsonPointers: ["/spec/replicas"]`) with `RespectIgnoreDifferences=true`.

### Step 2: Inspect Sync Operation Status & Resource Diffs
1. Call `get_sync_status(app_name="<app>")` to inspect `last_operation.phase`, `last_operation.message`, and per-resource `syncResult.resources` messages.
2. If the application is `OutOfSync`, call `get_application_diff(app_name="<app>", validate=True)`:
   - Check `validation.valid` and `validation.error` for server-side dry-run failures.
   - Check `diffs` to see which specific resources drifted from Git.

### Step 3: Traverse the Resource Tree to Pinpoint Unhealthy Nodes
1. Call `get_application_resource_tree(app_name="<app>")`.
2. Filter `nodes` where `health` is `Degraded`, `Progressing`, or `Missing`.
3. Follow `parent_refs` (e.g., `Deployment/api` -> `ReplicaSet/api-7c9f` -> `Pod/api-7c9f-x2k`) to identify the exact failing pod(s) or child resources.

### Step 4: Correlate Kubernetes Warning Events & Pod Logs
1. Call `get_application_events(app_name="<app>", warnings_only=True, limit=50)` to capture scheduling, image pull, volume mount, or probe warnings (`FailedScheduling`, `BackOff`, `Unhealthy`, `FailedMount`).
2. For unhealthy pods identified in Step 3, call `get_application_logs(app_name="<app>", pod_name="<pod>", errors_only=True, tail_lines=100)`.
   - If `errors_only=True` returns no lines (e.g., non-standard error formatting), re-run with `errors_only=False, tail_lines=50` to inspect the startup sequence.

### Step 5: Check Repository & AppProject Permissions (If Sync/Comparison Blocked)
1. If Step 1 or Step 2 indicates a repository error, call `get_repository(repo_url="<source.repo_url>")` to verify `connection_status`.
2. If Step 1 or Step 2 indicates `application repo ... is not permitted in project` or `destination ... is not permitted`, call `get_project(project_name="<project>")` to inspect `source_repos`, `destinations`, and resource whitelist/blacklist rules.

---

## Structured Root-Cause Report Format

Present findings to the operator in four concise sections:
1. **Symptom Summary**: Application name, project, cluster/namespace, `sync_status`, `health_status`, and active revision.
2. **Failing Component(s)**: Exact `Kind/Name` from the resource tree and the error message from `get_sync_status` or `conditions`.
3. **Root Cause Evidence**: Correlated log lines (`get_application_logs`) and Kubernetes events (`get_application_events`).
4. **Recommended Remediation**:
   - Runtime regression after a recent deploy -> Recommend `rolling-back-argocd-applications`.
   - Manifest/drift issue or unpruned orphan resource (`PruneSkipped`) -> Recommend `deploying-argocd-applications` (for orphaned resources after a Git rename/removal, advise verifying no downstream consumers still reference the old resource and running a dry-run pruned sync preview `sync_application(..., dry_run=True, prune=True)` before executing live deletion).
   - Missing repo credential or AppProject destination -> Recommend `onboarding-argocd-repositories-and-projects`.

See [references/argocd-failure-modes.md](references/argocd-failure-modes.md) for a diagnostic lookup table of common ArgoCD and Kubernetes failure signatures.
