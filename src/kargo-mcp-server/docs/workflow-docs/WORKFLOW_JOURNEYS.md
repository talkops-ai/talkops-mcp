# Kargo MCP Server — Workflow Journeys (`v0.2.0`)

This document maps the 5 end-to-end Kargo progressive delivery operational journeys to the **Agent Skills** (`skills/*/SKILL.md`), **18 Live MCP Resources** (`kargo://...`), and **20 Execution Tools** (`kargo_*`) in `kargo-mcp-server` v0.2.0 (tested against Kargo v1.12.5).

---

## Overview of the 5 Operational Workflows

| # | Workflow Journey | Companion Agent Skill | Primary MCP Tools & Resources |
|---|------------------|-----------------------|-------------------------------|
| 1 | **Onboarding a New Pipeline** | `skills/onboarding-kargo-pipelines/SKILL.md` | `kargo_manage_project`, `kargo_manage_credentials`, `kargo_apply_warehouse`, `kargo_apply_promotion_task`, `kargo_apply_stage`, `kargo_apply_project_config`, `kargo_refresh`, `kargo://projects/{project}/pipeline` |
| 2 | **Approving Freight for Restricted Stages** | `skills/promoting-and-approving-freight/SKILL.md` | `kargo_query_freight`, `kargo_trace_freight`, `kargo_approve_freight`, `kargo://projects/{project}/freight/{freight_or_alias}` |
| 3 | **Promoting Freight & Verification Gating** | `skills/promoting-and-approving-freight/SKILL.md` | `kargo_promote`, `kargo_manage_promotion`, `kargo_apply_analysis_template`, `kargo_manage_verification`, `kargo://projects/{project}/promotions/{promotion}`, `kargo://projects/{project}/analysis-runs/{run}` |
| 4 | **Emergency Stage Rollback** | `skills/rolling-back-kargo-stages/SKILL.md` | `kargo_diagnose_stage`, `kargo_rollback_stage`, `kargo_promote(origin_warehouse=...)`, `kargo://projects/{project}/stages/{stage}` |
| 5 | **Troubleshooting Pipeline & Discovery Failures** | `skills/troubleshooting-kargo-pipelines/SKILL.md` | `kargo_diagnose_warehouse`, `kargo_diagnose_stage`, `kargo_trace_freight`, `kargo://projects/{project}/events`, `kargo://projects/{project}/credentials` |

---

## Workflow 1: Onboarding a Kargo Pipeline (`onboarding-kargo-pipelines`)

1. **Precondition Check**: Read `kargo://server/capabilities` to confirm `allow_write: true`.
2. **Create Project (`[GATE]`)**:
   - Preview: `kargo_manage_project(action="create", name="<project>", dry_run=True)`
   - Apply: `kargo_manage_project(action="create", name="<project>", dry_run=False)`
3. **Register Credentials (Zero-Secret `0->1`)**:
   - `kargo_manage_credentials(action="create", project="<project>", name="gitops-creds", credential={"kind": "repo", "cred_type": "git", "repo_url": "https://github.com/org/gitops.git", "secret_ref": "GITOPS_MAIN"})`
4. **Configure Warehouse (`[GATE]`)**:
   - Preview & apply with `kargo_apply_warehouse(project="<project>", name="main-warehouse", subscriptions=[{"type": "image", "repo_url": "ghcr.io/org/app", "constraint": "^1.0.0", "allow_tags_regexes": ["^v?[0-9]+\\.[0-9]+\\.[0-9]+$"]}], dry_run=True|False)`
5. **Define Reusable PromotionTask (`[GATE]`)**:
   - Optionally generate steps offline via `skills/onboarding-kargo-pipelines/scripts/render_promotion_steps.py`.
   - Preview & apply with `kargo_apply_promotion_task(project="<project>", name="promote-task", steps=[...], dry_run=True|False)`.
6. **Create Stage DAG (`[GATE]`)**:
   - Root stage (`dev`): `kargo_apply_stage(project="<project>", name="dev", requested_freight=[{"kind": "Warehouse", "name": "main-warehouse"}], promotion_template={"task_name": "promote-task"}, dry_run=True|False)`
   - Downstream stages (`staging`, `prod`): `kargo_apply_stage(project="<project>", name="prod", requested_freight=[{"kind": "Warehouse", "name": "main-warehouse", "stages": ["dev"]}], promotion_template={"task_name": "promote-task"}, dry_run=True|False)`
7. **Configure Auto-Promotion & Webhooks in `ProjectConfig` (`[GATE]`)**:
   - `kargo_apply_project_config(project="<project>", promotion_policies=[{"stageSelector": {"name": "dev"}, "autoPromotionEnabled": True}], dry_run=True|False)`
8. **Trigger Initial Discovery**:
   - `kargo_refresh(project="<project>", kind="warehouse", name="main-warehouse", wait=True)`
   - Read `kargo://projects/{project}/pipeline`.

---

## Workflow 2: Approving Freight (`promoting-and-approving-freight`)

1. **Query & Trace Freight**:
   - `kargo_query_freight(project="<project>", stage="dev")`
   - `kargo_trace_freight(project="<project>", freight_or_alias="<alias-or-id>")`
2. **Inspect Freight Artifacts**:
   - Read `kargo://projects/{project}/freight/{freight_or_alias}`
3. **Grant Manual Approval (`[GATE]`)**:
   - `kargo_approve_freight(project="<project>", freight_or_alias="<alias-or-id>", stage="prod", confirm=True)`

---

## Workflow 3: Promoting Freight & Verification (`promoting-and-approving-freight`)

1. **Preview Promotion Plan (Optional)**:
   - `kargo_promote(project="<project>", stage="prod", freight_alias="<alias>", dry_run=True)`
2. **Execute Promotion (`[GATE]`)**:
   - Single stage: `kargo_promote(project="<project>", stage="prod", freight_alias="<alias>")`
   - Downstream fan-out: `kargo_promote(project="<project>", stage="dev", freight_alias="<alias>", downstream=True, confirm=True)`
3. **Monitor Step Execution & Verification**:
   - Read `kargo://projects/{project}/promotions/{promotion}`
   - Read `kargo://projects/{project}/analysis-runs/{run}` and `kargo://projects/{project}/analysis-runs/{run}/logs`
   - Re-verify if needed: `kargo_manage_verification(project="<project>", stage="prod", action="reverify")`

---

## Workflow 4: Emergency Stage Rollback (`rolling-back-kargo-stages`)

1. **Diagnose Degraded Stage**:
   - `kargo_diagnose_stage(project="<project>", stage="prod")`
   - Read `kargo://projects/{project}/stages/{stage}` to inspect `status.freightHistory`.
2. **Preview & Execute Rollback (`[GATE]`)**:
   - Preview: `kargo_rollback_stage(project="<project>", stage="prod", dry_run=True)`
   - Execute: `kargo_rollback_stage(project="<project>", stage="prod", confirm=True)`
3. **Resume Auto-Promotion After Fix (Kargo v1.11+ Holds)**:
   - Rolling back places an entry in `Stage.status.autoPromotionHolds`.
   - Clear hold and resume auto-promotion: `kargo_promote(project="<project>", stage="prod", origin_warehouse="main-warehouse")`

---

## Workflow 5: Troubleshooting Pipelines (`troubleshooting-kargo-pipelines`)

1. **Run N-to-1 Diagnostics**:
   - Warehouse issues: `kargo_diagnose_warehouse(project="<project>", warehouse="<warehouse>")`
   - Stage / Promotion / Verification issues: `kargo_diagnose_stage(project="<project>", stage="<stage>")`
   - Freight progression blockers: `kargo_trace_freight(project="<project>", freight_or_alias="<alias>")`
2. **Map Diagnosis Code to Remediation** (see `skills/troubleshooting-kargo-pipelines/references/diagnosis-catalog.md`):
   - `DEPRECATED_SUBSCRIPTION_FIELDS` → Update Warehouse via `kargo_apply_warehouse` (`constraint`, `allowTagsRegexes`, `ignoreTagsRegexes`).
   - `REPOSITORY_AUTH_FAILED` / `GIT_OR_REGISTRY_AUTH_ERROR` → Update credentials via `kargo_manage_credentials` (`secret_ref`).
   - `ARGOCD_SYNC_OR_AUTH_FAILED` → Ensure Argo CD Application has annotation `kargo.akuity.io/authorized-stage: "<project>:<stage>"`.
   - `PROMOTION_STEP_FAILED` → Fix step config via `kargo_apply_promotion_task` or `kargo_apply_stage`.
   - `VERIFICATION_FAILED` → Inspect `kargo://projects/{project}/analysis-runs/{run}/logs`, then `kargo_rollback_stage` or `kargo_manage_verification(action="reverify")`.
