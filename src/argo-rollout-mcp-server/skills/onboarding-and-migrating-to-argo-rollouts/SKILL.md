---
name: onboarding-and-migrating-to-argo-rollouts
description: Validates Kubernetes Deployments and migrates them to Argo Rollouts using direct or zero-downtime workloadRef patterns, including Service cloning, ArgoCD ignoreDifferences generation, legacy Deployment cleanup, and reverse Rollout-to-Deployment rollback. Use when onboarding a new service to progressive delivery, converting an existing Deployment to a Canary or Blue-Green Rollout, or rolling back a Rollout to a standard Deployment.
---

# Onboarding and Migrating to Argo Rollouts

## Preconditions

1. Read `argorollout://server/capabilities` to check `cluster_connected`, `allow_write`, and `crds_installed.rollout`.
2. Read `argorollout://cluster/contexts` and `argorollout://cluster/namespaces` to confirm the target cluster and namespace.
3. If the user only has local YAML files in Git and no live cluster connection, use the offline scripts in `scripts/` instead of live MCP tools.
4. For `[GATE]` steps: always run `dry_run=True` first (when supported) to preview manifests; if the operator's prompt already explicitly directs applying the live change and validation passes with `allow_write == true`, proceed immediately with `dry_run=False` (and `confirm=True` for destructive scale-to-zero/delete actions) and verify cluster state—otherwise stop after the preview and ask for approval.

## Decision Tree: Choosing a Migration or Onboarding Path

- **Greenfield Rollout Creation (`cluster_connected == true`, no existing Deployment)**:
  - Preview the new Rollout and companion Services with `argo_create_rollout(name, image, namespace, strategy, strategy_options, workload_options, service_options, dry_run=True)`.
  - `[GATE]` After preview (and user approval if not already authorized) with `allow_write == true`, apply with `argo_create_rollout(..., dry_run=False)` and verify `phase == "Healthy"`.
- **Offline / GitOps YAML-Only Workflow**:
  - Run `scripts/lint_deployment_manifest.py` to score readiness.
  - Run `scripts/convert_deployment_to_rollout.py` to generate the Rollout and Service manifests.
  - Run `scripts/generate_scale_down_manifest.py` to generate a declarative `spec.replicas: 0` `Deployment` manifest for GitOps commits (because imperative live scaling is immediately reverted when ArgoCD `selfHeal` is enabled—always explain this `selfHeal` behavior when preparing GitOps scale-down artifacts).
  - Run `scripts/generate_argocd_ignore_differences.py` to prevent ArgoCD `OutOfSync` drift.
- **Live Cluster Migration (`cluster_connected == true`)**:
  - Consult [references/migration-modes.md](references/migration-modes.md) to choose between:
    - **`workload_ref` (Recommended for Zero-Downtime)**: Rollout references the existing Deployment via `spec.workloadRef` and scales it down (`onsuccess` or `progressively`) once Rollout pods are Ready.
    - **`direct`**: Rollout embeds a full copy of `spec.template`. Runs duplicate pods until the legacy Deployment is scaled down via `argo_manage_legacy_deployment`.
  - Consult [references/gitops-integration.md](references/gitops-integration.md) if the application is managed by ArgoCD or Helm.

## Live Cluster Migration Checklist

- [ ] **Step 1 — Validate Deployment Readiness (Read-Only)**:
  Call `argo_validate_deployment_readiness(deployment_name, namespace)` to inspect blocking issues, non-blocking warnings, Service selector compatibility, and `detected_container_port`.
- [ ] **Step 2 — Resolve Blocking Issues**:
  If `ready == false` (e.g., Service selector contains `pod-template-hash`), stop and remediate before converting.
- [ ] **Step 3 — Preview Rollout Conversion (`dry_run=True`)**:
  Call `argo_convert_deployment_to_rollout(deployment_name, namespace, strategy, migration_mode, strategy_options, service_options, dry_run=True)` and present the generated YAML manifest and warnings to the user.
- [ ] **Step 4 — `[GATE]` Apply Rollout Conversion (`dry_run=False`)**:
  After user approval of the previewed manifest and `allow_write == true`, call `argo_convert_deployment_to_rollout(..., dry_run=False)` to clone/create the stable+canary (or active+preview) Services and apply the Rollout CRD.
- [ ] **Step 5 — Verify New Rollout Health**:
  Read `argorollout://rollouts/{namespace}/{name}/detail` (or call `argo_diagnose_rollout`) and confirm `phase == "Healthy"` and `replicas.ready == desired_replicas`.
- [ ] **Step 6 — `[GATE]` Clean Up or Scale Down Legacy Deployment**:
  - For `direct` mode: preview with `argo_manage_legacy_deployment(name, action="scale", replicas=0, rollout_name=name, dry_run=True)`, then after user confirmation execute with `dry_run=False, confirm=True` (or use `scripts/generate_scale_down_manifest.py` for GitOps).
  - For `workload_ref` mode: verify `workloadRef.scaleDown` policy or preview with `argo_manage_legacy_deployment(name, action="set_scale_down_policy", scale_down_policy="onsuccess"|"progressively"|"never", dry_run=True)` and `[GATE]` apply with `dry_run=False`. Note: Argo Rollouts only migrates stateless `apps/v1` `Deployment` workloads (never `StatefulSet`s), and legacy Deployments must never be scaled to `0` before the replacement Rollout is `Healthy`.

## Reverse Migration (Rollout -> Deployment Rollback)

- [ ] **Step 1 — Preview Deployment Manifest**:
  Call `argo_convert_rollout_to_deployment(name, namespace, deployment_strategy="RollingUpdate", dry_run=True)` (or run `scripts/convert_rollout_to_deployment.py` offline for standalone Rollouts). If a Rollout uses `spec.workloadRef` without an inline `spec.template`, it cannot be converted standalone from the Rollout YAML alone—in GitOps, roll back by restoring `spec.replicas` on the referenced `Deployment` manifest in Git before removing the Rollout.
- [ ] **Step 2 — `[GATE]` Apply Standard Deployment**:
  With operator authorization, call `argo_convert_rollout_to_deployment(name, namespace, deployment_strategy="RollingUpdate", dry_run=False)` and verify Deployment pods are Ready.
- [ ] **Step 3 — `[GATE]` Delete Legacy Rollout**:
  Once the Deployment is healthy (note: `argo_delete_rollout` blocks deleting a `workloadRef` Rollout while its referenced `Deployment` still has `0` replicas to prevent total outage), call `argo_delete_rollout(name, namespace, clean_all=True, confirm=True)` to remove the Rollout and its `-stable`/`-canary` Services.

## Bundled References & Offline Scripts

- [references/migration-modes.md](references/migration-modes.md) — Detailed comparison of `direct` vs `workload_ref` migration modes and named-port resolution rules.
- [references/gitops-integration.md](references/gitops-integration.md) — ArgoCD `ignoreDifferences` configurations and GitOps scale-down workflows.
- `scripts/lint_deployment_manifest.py` — Offline Deployment readiness linter and containerPort detector.
- `scripts/convert_deployment_to_rollout.py` — Offline Deployment YAML -> Rollout + Services YAML converter.
- `scripts/convert_rollout_to_deployment.py` — Offline Rollout YAML -> Deployment YAML reverse converter.
- `scripts/generate_scale_down_manifest.py` — Generates `replicas: 0` Deployment manifest for GitOps commits.
- `scripts/generate_argocd_ignore_differences.py` — Generates ArgoCD `Application` `ignoreDifferences` YAML snippet.
