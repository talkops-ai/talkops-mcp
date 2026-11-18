---
name: onboarding-kargo-pipelines
description: Scaffolds and configures Kargo v1.12 progressive delivery pipelines including Projects, ProjectConfigs, Warehouses, PromotionTasks, Stages, and Argo CD authorization. Use when creating a new Kargo pipeline, adding stages or warehouses, migrating legacy manifests, or configuring auto-promotion policies.
---

# Onboarding Kargo Pipelines

Progressive delivery onboarding workflow for Kargo v1.10+ (v1.12 schema) covering project initialization, credential registration, warehouse artifact discovery, promotion task definitions, stage DAG construction, and project-level policies.

## Preconditions

1. Read `kargo://server/capabilities` and verify `allow_write: true` plus enabled toolsets (`pipeline`, `promotion`, `credentials`).
2. Read `kargo://projects` to check whether the target project already exists.
3. Consult reference documentation before composing specifications:
   - [references/warehouse-subscriptions.md](references/warehouse-subscriptions.md) for Kargo v1.12 git, image (`constraint`, `allowTagsRegexes`, `ignoreTagsRegexes`), and Helm chart subscriptions.
   - [references/promotion-steps-catalog.md](references/promotion-steps-catalog.md) for the Kargo v1.12 61 built-in promotion steps and expression language (`imageFrom()`, `commitFrom()`, `chartFrom()`, `outputs`, `vars`).
   - [references/argocd-integration.md](references/argocd-integration.md) for Argo CD Application authorization annotations and `argocd-update` step wiring.

## Onboarding Checklist

- [ ] **Step 1: Verify Capabilities & Existing Topology**
  - Read `kargo://server/capabilities` and `kargo://projects/{project}/pipeline` (plus `kargo://projects/{project}` if upgrading an existing project).
- [ ] **Step 2: Preview & Create Project (`[GATE]`)**
  - Run `kargo_manage_project(action="create", name=..., dry_run=True)` to inspect the `Project` manifest (`kargo.akuity.io/v1alpha1`, metadata-only in Kargo v1.7+). For offline YAML files, lint with `scripts/validate_pipeline_manifests.py --file <manifests.yaml>`.
  - `[GATE]` If the operator requested a preview/dry-run only, stop and present the manifest; when the operator explicitly requested creating the project live, proceed immediately to `kargo_manage_project(action="create", name=..., dry_run=False)`.
- [ ] **Step 3: Register Repository Credentials**
  - Check existing secrets via `kargo://projects/{project}/credentials`.
  - If private Git, container image, or Helm repositories are required, invoke `kargo_manage_credentials(action="create", project=..., name=..., credential={"kind": "repo", "cred_type": "git"|"image"|"helm", "repo_url": ..., "secret_ref": "<ENV_REF>"})`. Never pass raw passwords or tokens.
- [ ] **Step 4: Preview & Apply Warehouse (`[GATE]`)**
  - Build image subscriptions using `constraint` (not deprecated `image.semverConstraint`), chart/git semver filters using `semverConstraint`, and tag filters using `allowTagsRegexes`/`ignoreTagsRegexes` (not removed `allowTags`/`ignoreTags`).
  - Run `kargo_apply_warehouse(project=..., name=..., subscriptions=[...], interval="5m0s", dry_run=True)`.
  - `[GATE]` Proceed to `kargo_apply_warehouse(..., dry_run=False)` when live onboarding was requested (or hold at preview if preview-only).
- [ ] **Step 5: Preview & Apply PromotionTask & Verification Templates (`[GATE]`)**
  - Optionally generate standard GitOps steps offline with `scripts/render_promotion_steps.py`, and inspect existing tasks via `kargo://projects/{project}/promotion-tasks/{task}` or `kargo://cluster-promotion-tasks/{task}`.
  - Run `kargo_apply_promotion_task(project=..., name=..., steps=[...], vars=[...], dry_run=True)` (or `scope="cluster"` for `ClusterPromotionTask`), and if verification gates are needed, preview `kargo_apply_analysis_template(project=..., name=..., spec=..., dry_run=True)`.
  - `[GATE]` Apply with `dry_run=False` when live configuration was requested.
- [ ] **Step 6: Preview & Apply Stages in DAG Order (`[GATE]`)**
  - Configure root stages with `requested_freight=[{"origin": {"kind": "Warehouse", "name": "<warehouse>"}, "sources": {"direct": True}}]` and downstream stages with `sources.stages: ["<upstream-stage>"]`. Inspect existing stage manifests via `kargo://projects/{project}/stages/{stage}/manifest` when modifying an existing stage.
  - Reference a `PromotionTask` via `promotion_template={"task_name": "<task-name>"}` (with `task_kind="ClusterPromotionTask"` for cluster tasks) or inline `promotion_template={"steps": [...]}` and optional `verification={"analysis_templates": [{"name": "<template-name>"}]}`.
  - Run `kargo_apply_stage(..., dry_run=True)` for each stage (e.g., `dev`, `staging`, `prod`) to verify DAG cycle validation passes.
  - `[GATE]` Apply each stage with `kargo_apply_stage(..., dry_run=False)` when live onboarding was requested.
- [ ] **Step 7: Preview & Apply ProjectConfig (`[GATE]`)**
  - Configure auto-promotion policies (`promotion_policies=[{"stageSelector": {"name": "dev"}, "autoPromotionEnabled": True}]`) and optional webhook receivers in `ProjectConfig` (never inside `Project.spec`).
  - Run `kargo_apply_project_config(project=..., promotion_policies=[...], dry_run=True)`.
  - `[GATE]` Apply with `kargo_apply_project_config(..., dry_run=False)` when live configuration was requested.
- [ ] **Step 8: Trigger Initial Warehouse Discovery, Verify & Decommission When Needed**
  - Invoke `kargo_refresh(project=..., kind="warehouse", name=..., wait=True)` (and `kind="stage"` when reconciling stages).
  - Read `kargo://projects/{project}/pipeline`, `kargo://projects/{project}/warehouses/{warehouse}`, and run `kargo_query_freight(project=...)` to confirm Freight creation and Stage readiness.
  - When decommissioning individual pipeline CRDs (`Stage`, `Warehouse`, `PromotionTask`, `ClusterPromotionTask`, `ProjectConfig`), `[GATE]` confirm with the operator (or execute directly when the operator explicitly requested deletion) via `kargo_delete_resource(project=..., kind=..., name=..., confirm=True)`. To delete an entire Project, `[GATE]` confirm `keep_namespace`, preview with `kargo_manage_project(action="delete", name=..., keep_namespace=..., dry_run=True)`, and execute with `kargo_manage_project(action="delete", name=..., keep_namespace=..., dry_run=False, confirm=True)`.
