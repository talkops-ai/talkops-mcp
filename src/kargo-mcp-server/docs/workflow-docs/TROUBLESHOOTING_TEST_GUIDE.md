# Workflow 5 Test Guide: Troubleshooting Kargo Pipelines (`v0.2.0`)

Companion Skill: [`skills/troubleshooting-kargo-pipelines/SKILL.md`](../../skills/troubleshooting-kargo-pipelines/SKILL.md)
Diagnosis Reference: [`skills/troubleshooting-kargo-pipelines/references/diagnosis-catalog.md`](../../skills/troubleshooting-kargo-pipelines/references/diagnosis-catalog.md)

## Step-by-Step Verification

1. **Diagnose Warehouse Discovery**:
   - Call `kargo_diagnose_warehouse(project="guestbook", warehouse="main-warehouse")`.
   - Check `diagnosis_codes` (`DEPRECATED_SUBSCRIPTION_FIELDS`, `REPOSITORY_AUTH_FAILED`, `WAREHOUSE_DISCOVERY_FAILED`, `NO_ARTIFACTS_DISCOVERED`, or `HEALTHY`).
2. **Diagnose Stage, Promotion Steps & Verification**:
   - Call `kargo_diagnose_stage(project="guestbook", stage="dev")`.
   - Check `diagnosis_codes` (`PROMOTION_STEP_FAILED`, `GIT_OR_REGISTRY_AUTH_ERROR`, `ARGOCD_SYNC_OR_AUTH_FAILED`, `VERIFICATION_FAILED`, `STAGE_HEALTH_DEGRADED`, `AUTO_PROMOTION_ON_HOLD`, `PROMOTION_IN_PROGRESS`, `VERIFICATION_IN_PROGRESS`, `NO_FREIGHT_DEPLOYED`, or `HEALTHY`).
3. **Trace Freight Progression Blockers**:
   - Call `kargo_trace_freight(project="guestbook", freight_or_alias="vivid-falcon")` to identify upstream verification or soak-time blockers.
4. **Offline Failure Summary Script**:
   - Run `python3 skills/troubleshooting-kargo-pipelines/scripts/summarize_promotion_failure.py --input tests/fixtures/promotion-failed.json`.
