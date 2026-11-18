---
name: rolling-back-kargo-stages
description: Executes emergency rollbacks of Kargo stages by promoting a previously verified Freight from stage freightHistory and manages Kargo v1.11+ auto-promotion holds. Use when a stage deployment is degraded, a bad release must be reverted to a prior known-good version, or auto-promotion holds need clearing after incident recovery.
---

# Rolling Back Kargo Stages

Standard operating procedure for reverting a degraded Kargo `Stage` to a known-good `Freight` using Kargo's GitOps roll-forward model and managing Kargo v1.11+ `autoPromotionHolds`.

## Preconditions

1. Read `kargo://server/capabilities` to verify `allow_write: true` and confirm `promotion` and `diagnostics` toolsets are enabled.
2. Read `kargo://projects/{project}/pipeline` (for pipeline topology and downstream Stage subscribers) and `kargo://projects/{project}/stages/{stage}` (or `kargo://projects/{project}/stages/{stage}/manifest` when raw Stage YAML is needed), or run `kargo_diagnose_stage(project=..., stage=...)` to inspect `status.freightHistory`, `status.currentPromotion`, and `status.autoPromotionHolds`.
3. Consult [references/rollback-sop.md](references/rollback-sop.md) for Kargo's roll-forward promotion semantics and auto-promotion hold lifecycle.

## Rollback Checklist

- [ ] **Step 1: Assess Stage Health & Active Promotions**
  - Run `kargo_diagnose_stage(project=..., stage=...)` to check current health, active promotion status, and `freightHistory`.
  - If a broken promotion is currently stuck in `Running` or `Pending`, `[GATE]` abort it first via `kargo_manage_promotion(action="abort", project=..., promotion=..., confirm=True)` (or let `kargo_rollback_stage(..., abort_running_promotion=True)` abort it automatically when rollback is requested).
- [ ] **Step 2: Select Target Known-Good Freight**
  - Inspect `kargo://projects/{project}/stages/{stage}` (`status.freightHistory`), `kargo://projects/{project}/stages/{stage}/manifest` (for Stage YAML spec), and `kargo://projects/{project}/freight/{freight_or_alias}` (or `kargo_query_freight(project=..., stage=...)`) to verify the exact constituent images, Helm charts, and Git commits via Kargo MCP resources rather than raw `kubectl`.
  - Identify either:
    - The immediate prior verified Freight in `status.freightHistory[1]` (selected automatically when `target_freight` is omitted in `kargo_rollback_stage`), or
    - A specific historical Freight ID or alias (`target_freight="<alias-or-id>"`).
- [ ] **Step 3: Preview & Execute Stage Rollback (`[GATE]`)**
  - Preview the rollback plan with `kargo_rollback_stage(project=..., stage=..., target_freight=..., dry_run=True)`.
  - `[GATE]` Present the currently deployed Freight, the target rollback Freight, and the reason for rollback. If the operator asked for a preview/plan only, stop here; when the operator explicitly requested executing the rollback live, proceed immediately to `kargo_rollback_stage(project=..., stage=..., target_freight=..., abort_running_promotion=True, dry_run=False, confirm=True)`.
- [ ] **Step 4: Verify Rollback Promotion & Stage Recovery**
  - Read `kargo://projects/{project}/promotions/{promotion}` and run `kargo_diagnose_stage(project=..., stage=...)` to confirm the rollback promotion reaches `Succeeded` and Stage health returns to `Healthy`.
  - Note: In Kargo v1.11+, rolling back to an older Freight sets `Stage.status.autoPromotionHolds` so Kargo does not immediately overwrite the rollback with the broken newer Freight.
- [ ] **Step 5: Resume Normal Auto-Promotion After Fix (`[GATE]`)**
  - Once a fixed Freight has been discovered in the Warehouse (never while the broken Freight is still the newest entry in the Warehouse!), preview with `kargo_promote(project=..., stage=..., origin_warehouse=..., dry_run=True)` and then `[GATE]` confirm with the operator (or execute directly when explicitly requested) via `kargo_promote(project=..., stage=..., origin_warehouse=..., dry_run=False)` to clear `autoPromotionHolds` and resume automatic promotions.
