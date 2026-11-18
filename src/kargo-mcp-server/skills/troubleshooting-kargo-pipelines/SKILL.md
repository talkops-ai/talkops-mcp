---
name: troubleshooting-kargo-pipelines
description: Diagnoses and resolves Kargo v1.12 Warehouse discovery failures, Promotion step errors, Argo CD authorization mismatches, AnalysisRun verification failures, and Freight progression blockers. Use when a Warehouse fails to discover artifacts, a Promotion is Errored or Failed, a Stage is Degraded, or Freight cannot advance downstream.
---

# Troubleshooting Kargo Pipelines

Diagnostic workflow for isolating and remediating failures across Kargo `Warehouse` artifact polling, `Promotion` step execution, `AnalysisRun` verifications, and `Freight` stage progression.

## Preconditions

1. Read `kargo://server/capabilities` to check `allow_write` status and active toolsets (`diagnostics`, `pipeline`, `promotion`, `verification`, `credentials`).
2. Read `kargo://projects/{project}/pipeline` and `kargo://projects/{project}/events` for high-level project health and recent Kubernetes events.
3. Consult [references/diagnosis-catalog.md](references/diagnosis-catalog.md) for the complete mapping of diagnosis codes to root causes and MCP remediations.

## Diagnostic & Remediation Checklist

- [ ] **Step 1: Run N-to-1 Diagnostic Tools**
  - **Warehouse Issues**: Run `kargo_diagnose_warehouse(project=..., warehouse=...)` when expected Freight is missing or polling fails.
  - **Stage / Promotion / Verification Issues**: Run `kargo_diagnose_stage(project=..., stage=...)` when a Stage is unhealthy, stuck promoting, or failing verification.
  - **Freight Progression Blockers**: Run `kargo_trace_freight(project=..., freight_or_alias=...)` when Freight is stuck upstream and unavailable to a downstream Stage.
- [ ] **Step 2: Inspect Detailed Step or Verification Telemetry**
  - If `kargo_diagnose_stage` reports `PROMOTION_STEP_FAILED`, `GIT_OR_REGISTRY_AUTH_ERROR`, or `ARGOCD_SYNC_OR_AUTH_FAILED` (or when inspecting a reusable `PromotionTask` directly), read `kargo://projects/{project}/promotions/{promotion}` to inspect `status.stepExecutionMetadata` and read `kargo://projects/{project}/promotion-tasks/{task}` (or `kargo://cluster-promotion-tasks/{task}` / `kargo://projects/{project}/stages/{stage}/manifest`) via Kargo MCP resources rather than raw `kubectl`.
  - If `kargo_diagnose_stage` reports `VERIFICATION_FAILED`, read `kargo://projects/{project}/analysis-runs/{run}` and `kargo://projects/{project}/analysis-runs/{run}/logs`.
  - Optionally run `scripts/summarize_promotion_failure.py --input <file>` on exported promotion or analysis run JSON/YAML payloads.
- [ ] **Step 3: Apply Targeted Remediation (`[GATE]`)**
  - When `allow_write` is `false` or the operator asked for diagnosis only, report the root cause and exact remediation steps without mutating live resources. When `allow_write` is `true` and the operator asked to fix/resolve the issue, preview (`dry_run=True` where supported) and execute the fix via Kargo MCP tools rather than raw `kubectl`:
  - **Auth Failures (`REPOSITORY_AUTH_FAILED`, `GIT_OR_REGISTRY_AUTH_ERROR`)**: Check `kargo://projects/{project}/credentials`. `[GATE]` Create or rotate credentials via `kargo_manage_credentials(action="create"|"update", ..., credential={"kind": "repo", "cred_type": "git"|"image"|"helm", "repo_url": ..., "secret_ref": "<REF>"})` and trigger immediate discovery via `kargo_refresh(project=..., kind="warehouse", name=..., wait=True)`.
  - **Deprecated Warehouse Fields (`DEPRECATED_SUBSCRIPTION_FIELDS`)**: `[GATE]` Preview with `kargo_apply_warehouse(..., dry_run=True)` using `constraint` (for images) and `allowTagsRegexes`/`ignoreTagsRegexes`, then apply with `dry_run=False` and refresh the Warehouse.
  - **Broken PromotionTask / Stage Steps (`PROMOTION_STEP_FAILED` or Git push races)**: Inspect `kargo://projects/{project}/promotion-tasks/{task}`, `[GATE]` preview the fix with `kargo_apply_promotion_task(..., dry_run=True)` or `kargo_apply_stage(..., dry_run=True)`, then apply with `dry_run=False` and re-promote via `kargo_promote` when recovering a Stage.
  - **Verification Failure (`VERIFICATION_FAILED`)**: If caused by a transient metric spike, trigger `kargo_manage_verification(action="reverify", project=..., stage=...)`. If caused by a bad release, `[GATE]` preview and roll back via `kargo_rollback_stage(project=..., stage=..., confirm=True)`.
- [ ] **Step 4: Confirm Recovery**
  - Re-run `kargo_diagnose_warehouse` or `kargo_diagnose_stage` and verify the returned diagnosis code is `HEALTHY`.
