# Workflow 3 Test Guide: Promoting Freight & Verification (`v0.2.0`)

Companion Skill: [`skills/promoting-and-approving-freight/SKILL.md`](../../skills/promoting-and-approving-freight/SKILL.md)

## Step-by-Step Verification

1. **Preview Promotion Plan**:
   - Call `kargo_promote(project="guestbook", stage="prod", freight_alias="vivid-falcon", dry_run=True)` → verify `"status": "preview"` and inspect `manifest`.
2. **Promote to Single Stage**:
   - Call `kargo_promote(project="guestbook", stage="prod", freight_alias="vivid-falcon", dry_run=False)` → verify `"status": "success"` and note the generated `Promotion` name.
3. **Promote to Downstream Subscribers**:
   - Call `kargo_promote(project="guestbook", stage="dev", freight_alias="vivid-falcon", downstream=True, confirm=True)` → verify downstream promotions are created via `/v1beta1/projects/{project}/stages/{stage}/promotions/downstream`.
4. **Monitor Promotion & Verification**:
   - Read `kargo://projects/guestbook/promotions/{promotion}` to inspect `status.phase` and `status.stepExecutionMetadata`.
   - Read `kargo://projects/guestbook/analysis-runs/{run}` and `kargo://projects/guestbook/analysis-runs/{run}/logs`.
   - Re-trigger verification if needed: `kargo_manage_verification(project="guestbook", stage="prod", action="reverify")`.
