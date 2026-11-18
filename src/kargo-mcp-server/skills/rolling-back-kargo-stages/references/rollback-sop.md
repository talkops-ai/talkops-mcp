# Kargo Stage Rollback Standard Operating Procedure

## Table of Contents
1. [Roll-Forward Paradigm in Kargo](#roll-forward-paradigm-in-kargo)
2. [Selecting Target Freight from `freightHistory`](#selecting-target-freight-from-freighthistory)
3. [Auto-Promotion Holds in Kargo v1.11+](#auto-promotion-holds-in-kargo-v111)

## Roll-Forward Paradigm in Kargo

Kargo does not use `git revert` or imperative `kubectl rollout undo`. Because every `Freight` is an immutable snapshot of Git commits, container image tags/digests, and Helm chart versions, rolling back a `Stage` means **creating a new `Promotion` that re-applies a previously verified `Freight`** through the Stage's `promotionTemplate` steps (updating the stage branch and syncing Argo CD to the known-good artifact versions) and re-running post-promotion **`AnalysisTemplate` (`AnalysisRun`)** verification checks. Out-of-band `git revert` leaves `Stage.status.freightHistory` desynchronized, fails to engage `Stage.status.autoPromotionHolds`, and skips both `promotionTemplate` steps and `AnalysisTemplate` verification.

Before rolling back an upstream Stage (such as `staging`), inspect `kargo://projects/{project}/pipeline` and `kargo://projects/{project}` to check whether downstream Stages have `autoPromotionEnabled: true` (in `ProjectConfig.spec.promotionPolicies`) with `autoPromotionOptions.selectionPolicy: MatchUpstream` (in `Stage.spec.requestedFreight[*].sources`), which will automatically cascade the rollback downstream once upstream verification passes—always confirm with the operator whether downstream production should also roll back or temporarily set `autoPromotionEnabled: false` on the downstream Stage first.

The `kargo_rollback_stage` tool automates this safely:
1. Reads live `Stage.status.freightHistory` (`kargo://projects/{project}/stages/{stage}`).
2. Selects the explicit `target_freight` (if provided) or the most recent prior Freight in `freightHistory` that differs from `freightHistory[0]`.
3. Requires explicit confirmation (`confirm=True` or MCP elicitation).
4. Triggers a native `POST /v1beta1/projects/{project}/stages/{stage}/promotions` promotion for the rollback Freight.

## Selecting Target Freight from `freightHistory`

`Stage.status.freightHistory` is a chronological list (newest at index `0`) of up to 10 Freight collections recently deployed to the Stage:
- `freightHistory[0]`: Currently deployed (degraded) Freight.
- `freightHistory[1]`: Immediate previous Freight deployed to the Stage.

Always verify the candidate rollback Freight's artifact versions via `kargo://projects/{project}/freight/{freight_or_alias}` before confirming `kargo_rollback_stage`.

## Auto-Promotion Holds in Kargo v1.11+

In Kargo v1.11+, when a user promotes a historical Freight (older than the newest Freight from that Warehouse) to an auto-promoted Stage, the Kargo controller automatically records an entry in `Stage.status.autoPromotionHolds`.

While `autoPromotionHolds` is non-empty:
- Automatic promotions from the held Warehouse origin are paused so Kargo does not immediately re-promote the broken newer Freight over the rollback.
- `kargo_diagnose_stage` surfaces `AUTO_PROMOTION_ON_HOLD` (`severity: info`) to make the hold visible.
- To release the hold once a fixed version is ready, run `kargo_promote(project=..., stage=..., origin_warehouse="<warehouse>")`.
