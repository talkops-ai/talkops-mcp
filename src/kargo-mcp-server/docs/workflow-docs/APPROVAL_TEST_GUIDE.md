# Workflow 2 Test Guide: Approving Freight (`v0.2.0`)

Companion Skill: [`skills/promoting-and-approving-freight/SKILL.md`](../../skills/promoting-and-approving-freight/SKILL.md)

## Step-by-Step Verification

1. **Discover Candidate Freight**:
   - Call `kargo_query_freight(project="guestbook", stage="dev")` to list Freight bundles verified in `dev`.
2. **Trace Freight Eligibility Across Stages**:
   - Call `kargo_trace_freight(project="guestbook", freight_or_alias="vivid-falcon")` to inspect `currently_in`, `verified`, `approved`, `eligible_for_promotion`, and `blockers`.
3. **Inspect Freight Artifact Metadata**:
   - Read `kargo://projects/guestbook/freight/vivid-falcon`.
4. **Approve Freight for Restricted Stage (`[GATE]`)**:
   - Call `kargo_approve_freight(project="guestbook", freight_or_alias="vivid-falcon", stage="prod", confirm=False)` → verify `"status": "cancelled"` when unconfirmed.
   - After operator confirmation, call `kargo_approve_freight(project="guestbook", freight_or_alias="vivid-falcon", stage="prod", confirm=True)` → verify `"status": "success"`.
