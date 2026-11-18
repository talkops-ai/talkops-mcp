# Workflow 4 Test Guide: Emergency Stage Rollback (`v0.2.0`)

Companion Skill: [`skills/rolling-back-kargo-stages/SKILL.md`](../../skills/rolling-back-kargo-stages/SKILL.md)

## Step-by-Step Verification

1. **Diagnose Stage & Inspect `freightHistory`**:
   - Call `kargo_diagnose_stage(project="guestbook", stage="prod")`.
   - Read `kargo://projects/guestbook/stages/prod` to inspect `status.freightHistory`.
2. **Preview Rollback Plan**:
   - Call `kargo_rollback_stage(project="guestbook", stage="prod", dry_run=True)` → verify `current_freight` and `target_freight` (automatically resolved from `status.freightHistory[1]`).
3. **Execute Rollback (`[GATE]`)**:
   - Call `kargo_rollback_stage(project="guestbook", stage="prod", confirm=True)` → verify `"status": "success"` and note the warning regarding Kargo v1.11+ `autoPromotionHolds`.
4. **Clear Auto-Promotion Hold When Ready**:
   - Call `kargo_promote(project="guestbook", stage="prod", origin_warehouse="main-warehouse")` to clear the hold and resume automatic promotions.
