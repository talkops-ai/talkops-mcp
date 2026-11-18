# Workflow 1 Test Guide: Onboarding a Kargo Pipeline (`v0.2.0`)

Companion Skill: [`skills/onboarding-kargo-pipelines/SKILL.md`](../../skills/onboarding-kargo-pipelines/SKILL.md)

## Step-by-Step Verification

1. **Check Server Capabilities**:
   - Read resource `kargo://server/capabilities` → verify `"allow_write": true` and `"pipeline"` in `"toolsets"`.
2. **Create Project (Preview → Apply)**:
   - Call `kargo_manage_project(action="create", name="guestbook", dry_run=True)` → verify `"status": "preview"`.
   - Call `kargo_manage_project(action="create", name="guestbook", dry_run=False)` → verify `"status": "success"`.
3. **Register Repository Credentials (`0->1` Secret Omission)**:
   - Call `kargo_manage_credentials(action="create", project="guestbook", name="gitops-creds", credential={"kind": "repo", "cred_type": "git", "repo_url": "https://github.com/example/gitops.git", "secret_ref": "GITOPS_MAIN"})`.
   - Read `kargo://projects/guestbook/credentials` → verify `"redacted": true` and no raw secret values appear.
4. **Create Warehouse (Kargo v1.12 Schema)**:
   - Call `kargo_apply_warehouse(project="guestbook", name="main-warehouse", subscriptions=[{"type": "image", "repo_url": "ghcr.io/example/guestbook", "constraint": "^1.0.0", "allow_tags_regexes": ["^v?[0-9]+\\.[0-9]+\\.[0-9]+$"]}], dry_run=True)` → inspect YAML manifest (`constraint` and `allowTagsRegexes`).
   - Re-run with `dry_run=False`.
5. **Create PromotionTask**:
   - Call `kargo_apply_promotion_task(project="guestbook", name="promote-task", steps=[{"uses": "git-clone", "config": {"repoURL": "https://github.com/example/gitops.git"}}, {"uses": "yaml-update", "as": "update-image", "config": {"path": "./out/values.yaml", "updates": [{"key": "image.tag", "value": "${{ quote(imageFrom('ghcr.io/example/guestbook').tag) }}"}]}}], dry_run=False)`.
6. **Create Stages (`dev` -> `prod`)**:
   - Call `kargo_apply_stage(project="guestbook", name="dev", requested_freight=[{"kind": "Warehouse", "name": "main-warehouse"}], promotion_template={"task_name": "promote-task"}, dry_run=False)`.
   - Call `kargo_apply_stage(project="guestbook", name="prod", requested_freight=[{"kind": "Warehouse", "name": "main-warehouse", "stages": ["dev"]}], promotion_template={"task_name": "promote-task"}, dry_run=False)`.
7. **Configure Auto-Promotion in `ProjectConfig`**:
   - Call `kargo_apply_project_config(project="guestbook", promotion_policies=[{"stageSelector": {"name": "dev"}, "autoPromotionEnabled": True}], dry_run=False)`.
8. **Refresh Warehouse & Inspect Pipeline**:
   - Call `kargo_refresh(project="guestbook", kind="warehouse", name="main-warehouse", wait=True)`.
   - Read `kargo://projects/guestbook/pipeline`.
