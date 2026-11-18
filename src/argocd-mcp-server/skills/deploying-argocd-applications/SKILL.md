---
name: deploying-argocd-applications
description: Deploys, updates, and synchronizes Kubernetes applications in ArgoCD with mandatory pre-flight diff validation, dry-run sync previews, post-sync health verification, and declarative YAML manifest generation. Use when deploying a new application, promoting a release tag or Git revision, syncing an OutOfSync application, or generating Application and ApplicationSet manifests.
allowed-tools:
  - list_applications
  - get_application_details
  - get_application_diff
  - sync_application
  - get_sync_status
  - refresh_application
  - create_application
  - update_application
  - delete_application
  - cancel_deployment
---

# Deploying ArgoCD Applications

Execute safe, auditable GitOps deployments in ArgoCD by following a strict **Discover -> Diff & Validate -> Dry-Run Preview -> Execute -> Verify** workflow.

## Mandatory Safety Rules

1. **Always diff before syncing**: Call `get_application_diff(app_name=..., validate=True)` before any sync operation to inspect resource changes and verify Kubernetes manifest schemas. If `validation.valid == False`, **stop immediately**—never attempt to bypass schema errors with `force=True` (`force=True` performs destructive delete-and-recreate, not schema bypass).
2. **Always preview with `dry_run=True` first**: Never call `sync_application(..., dry_run=False)` without first running `sync_application(..., dry_run=True)` and presenting the preview to the operator.
3. **Explicit confirmation for `prune=True` and `delete_application`**: Pruning or deleting permanently removes live resources. Always run the pre-flight diff/preview (`get_application_diff` + `dry_run=True` or `get_application_details`) first; if the operator already approved the change in their request and validation passes, pass `confirm=True` to execute—otherwise stop after the preview and ask for approval.
4. **Verify health after sync**: An ArgoCD sync phase of `Succeeded` only means `kubectl apply` completed; always poll `get_sync_status` and `get_application_details` until `health_status == "Healthy"`.
5. **MCP-first execution**: Use ArgoCD MCP tools and resources (`argocd://repositories`, `argocd://projects/{name}`) rather than raw `argocd` or `kubectl` CLI commands.

---

## Standard Deployment Workflow (Existing Application)

### Step 1: Discover & Inspect Current State
1. Call `get_application_details(app_name="<app>", detail_level="summary")` (or `list_applications` if the exact name is unknown).
2. Check:
   - `sync_status` (`Synced` vs `OutOfSync`)
   - `health_status` (`Healthy`, `Progressing`, `Degraded`)
   - `current_revision` and `auto_sync_enabled`
3. If recent Git commits are not visible, call `refresh_application(app_name="<app>", mode="hard")` to invalidate ArgoCD's Git manifest cache.

### Step 2: Compute Live-vs-Target Diff & Validate Manifests
1. Call `get_application_diff(app_name="<app>", revision="<target_revision>", validate=True)`.
2. Inspect `validation.valid`. If `False`, **stop immediately** and report `validation.error` to the user.
3. Review `diffs` to identify every Kubernetes resource that will be created, modified, or out-of-sync.

### Step 3: Execute Dry-Run Sync Preview
1. Call `sync_application(app_name="<app>", revision="<target_revision>", dry_run=True, prune=False)`.
2. Present a concise deployment plan to the user:
   - Target application, namespace, and Git revision
   - Number and kinds of modified resources (`diff_count`)
   - Dry-run result (`status == "Succeeded"`)
   - Whether `prune` or `force` is requested (whenever `prune=True` is requested, explicitly warn the operator in your response that pruning permanently deletes live Kubernetes resources removed from Git and list the specific candidate resources to be deleted)

### Step 4: Execute Live Sync
1. If updating the tracked branch/tag permanently in the Application spec, call `update_application(app_name="<app>", target_revision="<target_revision>")`.
2. Call `sync_application(app_name="<app>", revision="<target_revision>", dry_run=False, prune=<bool>, confirm=<bool>)`.
3. If an operation hangs or applies unintended changes, call `cancel_deployment(app_name="<app>")` to terminate the active operation, follow up immediately with `get_sync_status(app_name="<app>")` and `get_application_details(app_name="<app>")` to confirm termination and report current state, and suggest investigating failure logs/events (`troubleshooting-argocd-applications`) or rolling back (`rolling-back-argocd-applications`) if live pods are degraded.

### Step 5: Verify Convergence
1. Call `get_sync_status(app_name="<app>")` to check `last_operation.phase` (`Running` -> `Succeeded`) and per-resource statuses.
2. Confirm final state via `get_application_details(app_name="<app>", detail_level="summary")`:
   - `sync_status == "Synced"`
   - `health_status == "Healthy"`
3. If `health_status` becomes `Degraded` or `last_operation.phase == "Failed"`, transition to the `troubleshooting-argocd-applications` or `rolling-back-argocd-applications` skill.

---

## Creating a New Application

1. Verify the repository and project exist via `argocd://repositories` and `argocd://projects/{project_name}` (or use the `onboarding-argocd-repositories-and-projects` skill first).
2. To register directly via API, call `create_application`:
   ```json
   {
     "app_name": "payments-service",
     "project": "production",
     "repo_url": "https://github.com/org/gitops-manifests.git",
     "path": "apps/payments/overlays/prod",
     "destination_namespace": "payments-prod",
     "target_revision": "v1.4.0",
     "sync_policy": {
       "automated": false,
       "prune": false,
       "self_heal": true,
       "create_namespace": true
     }
   }
   ```
3. Follow Steps 2-5 above to validate, dry-run, and sync the newly created application.

---

## Decommissioning / Deleting an Application

1. Inspect live child resources via `get_application_details(app_name="<app>", detail_level="summary")` before deletion.
2. Decide between:
   - `cascade=True`: Deletes both the ArgoCD `Application` CRD and all managed Kubernetes child resources (via `resources-finalizer.argocd.argoproj.io`).
   - `cascade=False`: Removes only the ArgoCD `Application` registration while leaving live Kubernetes workloads running in-cluster.
3. Require explicit operator confirmation before invoking `delete_application(app_name="<app>", cascade=<bool>, confirm=True)`.

---

## Generating Declarative YAML Manifests (`Application` / `ApplicationSet`)

For GitOps App-of-Apps repositories where manifests are committed to Git rather than created imperatively via API, run the bundled manifest generator script:

```bash
python3 scripts/generate_argocd_manifests.py application \
  --name payments-service \
  --project production \
  --repo-url https://github.com/org/gitops-manifests.git \
  --path apps/payments/overlays/prod \
  --dest-namespace payments-prod \
  --revision v1.4.0 \
  --auto-sync --self-heal --create-namespace
```

To generate a multi-environment `ApplicationSet` (List or Git directory generator):

```bash
python3 scripts/generate_argocd_manifests.py applicationset \
  --name payments-appset \
  --project production \
  --repo-url https://github.com/org/gitops-manifests.git \
  --path-template "apps/payments/overlays/{{env}}" \
  --environments dev=https://k8s-dev.internal:6443,staging=https://k8s-stg.internal:6443,prod=https://kubernetes.default.svc
```

See [scripts/generate_argocd_manifests.py](scripts/generate_argocd_manifests.py) (`--help`) for all options and [references/sync-strategies.md](references/sync-strategies.md) for sync waves, hooks, and selective sync patterns.
