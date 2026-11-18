# Kargo Diagnosis Code Catalog (v1.12)

## Table of Contents
1. [Overview](#overview)
2. [Stage Diagnosis Codes (`kargo_diagnose_stage`)](#stage-diagnosis-codes-kargo_diagnose_stage)
   - [PROMOTION_STEP_FAILED](#promotion_step_failed)
   - [GIT_OR_REGISTRY_AUTH_ERROR](#git_or_registry_auth_error)
   - [ARGOCD_SYNC_OR_AUTH_FAILED](#argocd_sync_or_auth_failed)
   - [VERIFICATION_FAILED](#verification_failed)
   - [STAGE_HEALTH_DEGRADED](#stage_health_degraded)
   - [AUTO_PROMOTION_ON_HOLD](#auto_promotion_on_hold)
   - [PROMOTION_IN_PROGRESS & VERIFICATION_IN_PROGRESS](#promotion_in_progress--verification_in_progress)
   - [NO_FREIGHT_DEPLOYED & HEALTHY](#no_freight_deployed--healthy)
3. [Warehouse Diagnosis Codes (`kargo_diagnose_warehouse`)](#warehouse-diagnosis-codes-kargo_diagnose_warehouse)
   - [DEPRECATED_SUBSCRIPTION_FIELDS](#deprecated_subscription_fields)
   - [REPOSITORY_AUTH_FAILED](#repository_auth_failed)
   - [WAREHOUSE_DISCOVERY_FAILED](#warehouse_discovery_failed)
   - [NO_ARTIFACTS_DISCOVERED & HEALTHY](#no_artifacts_discovered--healthy)

## Overview

The N-to-1 diagnostic tools `kargo_diagnose_stage` and `kargo_diagnose_warehouse` correlate live resource conditions, step execution metadata, verification runs, and credential inventory into deterministic diagnosis codes.

---

## Stage Diagnosis Codes (`kargo_diagnose_stage`)

### `PROMOTION_STEP_FAILED`
- **Severity**: `critical`
- **Symptom**: Latest `Promotion` finished in `Errored` or `Failed` phase, with a failed entry in `status.stepExecutionMetadata`.
- **Root Causes**:
  - Invalid `${{ ... }}` expression syntax or undefined variable in `PromotionTask` (`kargo://projects/{project}/promotion-tasks/{task}`).
  - Missing file path in `yaml-update`, `kustomize-set-image`, or `helm-template`.
  - Git push conflict or non-fast-forward update on target branch.
- **Remediation**:
  1. Read `kargo://projects/{project}/promotions/{promotion}` to inspect the failing step alias and error message.
  2. Preview the corrected step configuration using `kargo_apply_promotion_task(..., dry_run=True)` or `kargo_apply_stage(..., dry_run=True)`.
  3. Apply with `dry_run=False` and re-trigger promotion via `kargo_promote`.

### `GIT_OR_REGISTRY_AUTH_ERROR`
- **Severity**: `critical`
- **Symptom**: Promotion step (`git-clone`, `git-push`, `git-open-pr`, `oci-push`) failed with `401 Unauthorized`, `403 Forbidden`, or `authentication required`.
- **Root Causes**:
  - Missing or expired repository Secret in project or shared credentials namespace.
  - `repoURL` pattern in Secret does not match the repository URL used in `git-clone` (`regex: true` missing when using pattern matching).
- **Remediation**:
  1. Inspect `kargo://projects/{project}/credentials`.
  2. Create or update the credential via `kargo_manage_credentials(action="create"|"update", project=..., name=..., credential={"kind": "repo", "cred_type": "git"|"image"|"helm", "repo_url": ..., "secret_ref": "<REF>", "repo_url_is_regex": True})`.
  3. Re-run `kargo_promote`.

### `ARGOCD_SYNC_OR_AUTH_FAILED`
- **Severity**: `critical`
- **Symptom**: The `argocd-update` step failed with an authorization or sync error.
- **Root Causes**:
  - Target Argo CD `Application` lacks annotation `kargo.akuity.io/authorized-stage: "<project>:<stage>"`.
  - Argo CD `Application` name or namespace in `argocd-update` does not match the cluster resource.
- **Remediation**:
  1. Add `kargo.akuity.io/authorized-stage: "<project>:<stage>"` to the Argo CD `Application` metadata.
  2. Or update the `argocd-update` step configuration via `kargo_apply_promotion_task` / `kargo_apply_stage`.

### `VERIFICATION_FAILED`
- **Severity**: `critical`
- **Symptom**: Post-promotion `AnalysisRun` ended in `Failed` or `Error` phase.
- **Root Causes**:
  - Application metrics breached thresholds defined in the `AnalysisTemplate` (`kargo://projects/{project}/analysis-templates`).
  - Prometheus/DataDog query syntax error or unreachable metric provider in `AnalysisTemplate`.
- **Remediation**:
  1. Inspect `kargo://projects/{project}/analysis-runs/{run}` and `kargo://projects/{project}/analysis-runs/{run}/logs`.
  2. If the regression is real, roll back the stage using `kargo_rollback_stage(project=..., stage=..., confirm=True)`.
  3. If the failure was transient, re-trigger verification via `kargo_manage_verification(action="reverify", project=..., stage=...)`.

### `STAGE_HEALTH_DEGRADED`
- **Severity**: `warning`
- **Symptom**: `Stage.status.health.status` is `Degraded` or `Progressing` with health issues.
- **Root Causes**: Linked Argo CD Application is `OutOfSync` or `Degraded` (e.g., `CrashLoopBackOff`, `ImagePullBackOff`).
- **Remediation**: Inspect `issues` in `kargo_diagnose_stage` output; roll back to the previous verified Freight via `kargo_rollback_stage` if caused by the latest deployment.

### `AUTO_PROMOTION_ON_HOLD`
- **Severity**: `info`
- **Symptom**: `Stage.status.autoPromotionHolds` contains one or more held Warehouse origins (Kargo v1.11+).
- **Root Causes**: A manual rollback or historical Freight promotion paused automatic promotions so Kargo would not immediately overwrite the rollback.
- **Remediation**: When ready to resume automatic promotions from the Warehouse, invoke `kargo_promote(project=..., stage=..., origin_warehouse="<warehouse>")`.

### `PROMOTION_IN_PROGRESS` & `VERIFICATION_IN_PROGRESS`
- **Severity**: `info`
- **Symptom**: A `Promotion` (`Pending`/`Running`) or `AnalysisRun` is actively executing.
- **Remediation**: Monitor progress via `kargo://projects/{project}/promotions/{promotion}` or `kargo://projects/{project}/analysis-runs/{run}`, or abort if stuck using `kargo_manage_promotion(action="abort", ..., confirm=True)` / `kargo_manage_verification(action="abort", ..., confirm=True)`.

### `NO_FREIGHT_DEPLOYED` & `HEALTHY`
- **Severity**: `info`
- **Symptom**: `NO_FREIGHT_DEPLOYED` indicates a newly created Stage with empty `freightHistory`; `HEALTHY` indicates all checks passed.
- **Remediation**: For `NO_FREIGHT_DEPLOYED`, promote initial Freight via `kargo_promote`.

---

## Warehouse Diagnosis Codes (`kargo_diagnose_warehouse`)

### `DEPRECATED_SUBSCRIPTION_FIELDS`
- **Severity**: `warning`
- **Symptom**: Warehouse subscription contains `semverConstraint`, `allowTags`, or `ignoreTags`.
- **Remediation**: Update the Warehouse via `kargo_apply_warehouse` using `constraint`, `allowTagsRegexes`, and `ignoreTagsRegexes`.

### `REPOSITORY_AUTH_FAILED`
- **Severity**: `critical`
- **Symptom**: Warehouse `Ready`/`Healthy` condition is `False` with `401`/`403`/`authentication`/`credentials` errors.
- **Remediation**: Register a matching credential via `kargo_manage_credentials` and trigger `kargo_refresh(project=..., kind="warehouse", name=...)`.

### `WAREHOUSE_DISCOVERY_FAILED`
- **Severity**: `critical`
- **Symptom**: Warehouse condition `Ready=False` due to invalid semver constraint, non-existent Git branch, or unreachable registry URL.
- **Remediation**: Inspect `kargo://projects/{project}/warehouses/{warehouse}`, fix subscription parameters via `kargo_apply_warehouse`, and run `kargo_refresh`.

### `NO_ARTIFACTS_DISCOVERED` & `HEALTHY`
- **Severity**: `warning` / `info`
- **Symptom**: `NO_ARTIFACTS_DISCOVERED` means polling succeeded (`Ready=True`) but zero tags/commits matched subscription filters (`constraint` / `allowTagsRegexes`). `HEALTHY` means Freight is actively discovered.
- **Remediation**: Relax `constraint` or `allowTagsRegexes` via `kargo_apply_warehouse` and run `kargo_refresh`.
