# Kargo MCP Server & Agent Skills (`v0.2.0`)

An Agent Plugin v1.0.0 package that pairs **5 Agent Skills** (`skills/<gerund>/SKILL.md`) with a **20-tool, 18-resource execution-only MCP server** for **Kargo v1.10+ (tested against v1.12.5)** progressive delivery pipelines.

---

## Architecture: Skill & Execution Separation

Following the TalkOps **Skill & Execution Separation** specification:

1. **Reasoning Layer (`skills/*/SKILL.md`)**:
   - Progressive-disclosure procedural workflows, GitOps step composition catalogs (61 Kargo v1.12 steps + `expr-lang` functions), diagnosis code runbooks, and offline deterministic Python helper scripts (`skills/*/scripts/*.py`).
   - Zero MCP Prompts (`list_prompts() == []`) and zero static prose MCP Resources.
2. **Execution Data Plane (`kargo_mcp_server/`)**:
   - **18 Live MCP Resources (`kargo://...`)**: Read-only cluster state, pipeline DAG topology, stage YAML manifests, promotion step traces, verification `AnalysisRun` logs, RBAC roles, and redacted credentials.
   - **20 Execution Tools (`kargo_*`)**: Server-side filtering (`kargo_query_freight`), N-to-1 cross-resource correlation (`kargo_trace_freight`, `kargo_diagnose_stage`, `kargo_diagnose_warehouse`), and cluster mutations gated by `--allow-write`, `dry_run=True` previews, and MCP Elicitation / `confirm=True`.
   - **Zero-Secret (`0->1`) Guarantee**: Credential tools never accept or return raw passwords, tokens, or private keys; secrets are resolved strictly on the server side via `secret_ref`.

---

## Bundled Agent Skills (5)

| Skill Directory | Purpose | Companion References & Offline Scripts |
|-----------------|---------|----------------------------------------|
| `skills/onboarding-kargo-pipelines/` | Scaffolds Projects, ProjectConfigs, Warehouses, PromotionTasks, Stages, and Argo CD authorization | `references/warehouse-subscriptions.md`, `references/promotion-steps-catalog.md`, `references/argocd-integration.md`, `scripts/render_promotion_steps.py`, `scripts/validate_pipeline_manifests.py` |
| `skills/promoting-and-approving-freight/` | Evaluates Freight eligibility, approves Freight, promotes single stages or downstream subscribers, and manages verification gates | `references/promotion-gates.md` |
| `skills/rolling-back-kargo-stages/` | Executes emergency roll-forward Stage rollbacks from `freightHistory` and manages Kargo v1.11+ `autoPromotionHolds` | `references/rollback-sop.md` |
| `skills/troubleshooting-kargo-pipelines/` | Diagnoses Warehouse polling failures, Promotion step errors, Argo CD auth mismatches, and Verification failures | `references/diagnosis-catalog.md`, `scripts/summarize_promotion_failure.py` |
| `skills/managing-kargo-credentials-and-access/` | Manages repo/generic credentials via server-side `secret_ref`, shared credential replication, and Kargo RBAC roles/grants | `references/credentials-and-rbac.md` |

---

## MCP Tools (20 Tools across 6 Toolsets)

Every tool enforces `<= 8` parameters and carries explicit `ToolAnnotations`.

| Toolset | Tool Name | Mode | Default Gate | Description |
|---------|-----------|------|--------------|-------------|
| `pipeline` | `kargo_manage_project` | Write / Destructive | `dry_run=True` (create) / `confirm` (delete) | Create or delete a Kargo `Project` (`v1.7+` metadata-only). |
| `pipeline` | `kargo_apply_project_config` | Write | `dry_run=True` | Create/update `ProjectConfig` (`promotionPolicies`, `webhookReceivers`, `freightLinks`, `stageLinks`). |
| `pipeline` | `kargo_apply_warehouse` | Write | `dry_run=True` | Create/update `Warehouse` with Kargo v1.12 `constraint` and `allowTagsRegexes`/`ignoreTagsRegexes`. |
| `pipeline` | `kargo_apply_stage` | Write | `dry_run=True` | Create/update `Stage` (merging existing spec and validating DAG cycles). |
| `pipeline` | `kargo_apply_promotion_task` | Write | `dry_run=True` | Create/update `PromotionTask` or `ClusterPromotionTask` with Kargo v1.12 step validation. |
| `pipeline` | `kargo_delete_resource` | Destructive | `confirm` | Delete a `Stage`, `Warehouse`, `PromotionTask`, `ClusterPromotionTask`, or `ProjectConfig`. |
| `promotion` | `kargo_query_freight` | **Read-Only** | None | Query/filter Freight by stage availability, origin Warehouse, or alias. |
| `promotion` | `kargo_refresh` | Write | None | Trigger immediate reconciliation/discovery on a Warehouse, Stage, Promotion, ProjectConfig, or ClusterConfig. |
| `promotion` | `kargo_promote` | Write | `confirm` (when `downstream=True`) | Promote Freight to a Stage (by ID, alias, or `origin_warehouse`) or downstream subscribers via native REST API. |
| `promotion` | `kargo_rollback_stage` | Destructive (N-to-1) | `confirm` | Roll back a Stage to the previous verified Freight in `status.freightHistory` (and warn on v1.11+ holds). |
| `promotion` | `kargo_approve_freight` | Destructive | `confirm` | Manually approve Freight for a restricted Stage. |
| `promotion` | `kargo_manage_promotion` | Write / Destructive | `confirm` (abort) | Abort a running Promotion or refresh (wake) a Promotion. |
| `promotion` | `kargo_manage_freight` | Write / Destructive | `confirm` (delete) | Update Freight alias (`set_alias`), manually assemble Freight (`create`), or delete unused Freight (`delete`). |
| `verification` | `kargo_apply_analysis_template` | Write | `dry_run=True` | Create/update an `AnalysisTemplate` or `ClusterAnalysisTemplate`. |
| `verification` | `kargo_manage_verification` | Write / Destructive | `confirm` (abort / delete) | Trigger `reverify`, `abort` active Stage verification, or `delete_template`. |
| `credentials` | `kargo_manage_credentials` | Write / Destructive | `confirm` (delete) | Create, update, or delete `repo`/`generic`/`configmap` credentials across `project`/`shared`/`system` scopes using `secret_ref`. |
| `rbac` | `kargo_manage_roles` | Write / Destructive | `confirm` (delete / revoke) | Create/delete Kargo RBAC Roles or grant/revoke OIDC claims and stage `promote` permissions. |
| `diagnostics` | `kargo_trace_freight` | **Read-Only (N-to-1)** | None | Trace a Freight or artifact across the entire Stage DAG, surfacing upstream verification and soak-time blockers. |
| `diagnostics` | `kargo_diagnose_stage` | **Read-Only (N-to-1)** | None | Correlate Stage health, Promotion step errors, Verification AnalysisRuns, holds, and Warning events into diagnosis codes. |
| `diagnostics` | `kargo_diagnose_warehouse` | **Read-Only (N-to-1)** | None | Diagnose Warehouse artifact discovery, conditions, and deprecated Kargo v1.7–v1.12 subscription fields. |

---

## Live MCP Resources (18 URIs)

| URI | Description |
|-----|-------------|
| `kargo://server/capabilities` | Server write mode (`allow_write`), enabled toolsets, Kargo API connectivity, and version |
| `kargo://projects` | List all Kargo Projects with readiness status |
| `kargo://projects/{project}` | Project status and `ProjectConfig` (`promotionPolicies`, `webhookReceivers`, generated webhook URLs) |
| `kargo://projects/{project}/pipeline` | Complete pipeline DAG topology (`Warehouses -> Stages`), current Freight, health, auto-promotion, and holds |
| `kargo://projects/{project}/events` | Recent Kubernetes Events in the project |
| `kargo://projects/{project}/roles` | Kargo RBAC Roles, OIDC claim bindings, and permissions |
| `kargo://projects/{project}/stages/{stage}` | Detailed Stage status, `freightHistory`, `currentPromotion`, verification history, and `autoPromotionHolds` |
| `kargo://projects/{project}/stages/{stage}/manifest` | Sanitized Stage YAML manifest |
| `kargo://projects/{project}/warehouses/{warehouse}` | Warehouse subscriptions, `discoveredArtifacts`, and conditions |
| `kargo://projects/{project}/freight/{freight_or_alias}` | Detailed Freight resource (by SHA-1 ID or alias) with commits, images, charts, and stage states |
| `kargo://projects/{project}/promotions` | Recent Promotions summary list in the project |
| `kargo://projects/{project}/promotions/{promotion}` | Detailed Promotion status and per-step `stepExecutionMetadata` |
| `kargo://projects/{project}/promotion-tasks/{task}` | Project-scoped `PromotionTask` specification |
| `kargo://cluster-promotion-tasks/{task}` | Cluster-scoped `ClusterPromotionTask` specification |
| `kargo://projects/{project}/analysis-templates` | Project `AnalysisTemplates` and shared `ClusterAnalysisTemplates` |
| `kargo://projects/{project}/analysis-runs/{run}` | Verification `AnalysisRun` status and metric results |
| `kargo://projects/{project}/analysis-runs/{run}/logs` | Verification `AnalysisRun` job metric logs |
| `kargo://projects/{project}/credentials` | Redacted repository credentials, generic secrets, and ConfigMaps (`redacted: true`) |

---

## CLI Flags & Environment Variables

By default, `kargo-mcp-server` starts in **read-only mode** (`allow_write=False`) over **stdio** transport. Both `stdio` and `http` (`streamable-http`) transports are supported.

| CLI Flag | Environment Variable | Default | Description |
|----------|----------------------|---------|-------------|
| `--transport {stdio,http,streamable-http}` | `MCP_TRANSPORT` | `stdio` | MCP transport protocol (`streamable-http` normalizes to `http`) |
| `--host` | `MCP_HOST` | `0.0.0.0` | HTTP bind host |
| `--port` | `MCP_PORT` | `8766` | HTTP bind port |
| `--path` | `MCP_PATH` | `/mcp` | HTTP endpoint path |
| `--allow-write` | `MCP_ALLOW_WRITE` | `false` | Enable mutating and destructive tools |
| `--read-only` | `MCP_READ_ONLY` | `false` | Force read-only mode (overrides `--allow-write`) |
| `--toolsets` | `MCP_TOOLSETS` | `all` | Comma-separated toolsets (`all,readonly,pipeline,promotion,verification,credentials,rbac,diagnostics`) |
| `--kargo-url` | `KARGO_BASE_URL` | `http://localhost:8080` | Kargo API server base URL |
| `--auth-mode` | `KARGO_AUTH_MODE` | `admin` | Authentication mode (`admin`, `static`, `passthrough`) |
| `--project` | `KARGO_PROJECT` | `None` | Default Kargo project name |
| `--insecure-skip-tls-verify` | `KARGO_VERIFY_SSL` | `true` | Verify Kargo API TLS certificates |
| — | `KARGO_ADMIN_PASSWORD` | `None` | Admin password when `KARGO_AUTH_MODE=admin` |
| — | `KARGO_STATIC_BEARER_TOKEN` | `None` | Bearer token when `KARGO_AUTH_MODE=static` |
| — | `KARGO_CRED_<REF>_USERNAME` / `_PASSWORD` | `None` | Server-side secret material referenced by `secret_ref` |
| — | `KARGO_CREDENTIALS_FILE` | `None` | Path to server-side YAML/JSON credentials map |

---

## Migration Guide (`v0.1.0` → `v0.2.0`)

| Legacy `v0.1.0` Primitive | New `v0.2.0` Replacement |
|---------------------------|--------------------------|
| `kargo_project_mgmt(action="list"\|"get")` | Read `kargo://projects` or `kargo://projects/{project}` |
| `kargo_project_mgmt(action="create"\|"delete")` | `kargo_manage_project(action="create"\|"delete", ...)` |
| `kargo_project_mgmt(promotion_policies=...)` | `kargo_apply_project_config(project=..., promotion_policies=...)` |
| `kargo_warehouse_mgmt(action="list"\|"get")` | Read `kargo://projects/{project}/pipeline` or `kargo://projects/{project}/warehouses/{warehouse}` |
| `kargo_warehouse_mgmt(action="create"\|"update")` | `kargo_apply_warehouse(...)` |
| `kargo_warehouse_mgmt(action="refresh")` | `kargo_refresh(project=..., kind="warehouse", name=...)` |
| `kargo_warehouse_mgmt(action="delete")` | `kargo_delete_resource(project=..., kind="Warehouse", name=...)` |
| `kargo_stage_mgmt(action="list"\|"get")` | Read `kargo://projects/{project}/pipeline` or `kargo://projects/{project}/stages/{stage}` |
| `kargo_stage_mgmt(action="create"\|"update")` | `kargo_apply_stage(...)` |
| `kargo_stage_mgmt(action="refresh")` | `kargo_refresh(project=..., kind="stage", name=...)` |
| `kargo_stage_mgmt(action="reverify"\|"abort_verification")` | `kargo_manage_verification(action="reverify"\|"abort", ...)` |
| `kargo_stage_mgmt(action="delete")` | `kargo_delete_resource(project=..., kind="Stage", name=...)` |
| `kargo_describe_topology` | Read `kargo://projects/{project}/pipeline` |
| `kargo_freight_mgmt(action="list"\|"get")` | `kargo_query_freight(...)` or read `kargo://projects/{project}/freight/{freight_or_alias}` |
| `kargo_freight_mgmt(action="approve")` | `kargo_approve_freight(...)` |
| `kargo_promotion_mgmt(action="promote"\|"promote_Subscribers")` | `kargo_promote(..., downstream=False\|True)` |
| `kargo_promotion_mgmt(action="abort")` | `kargo_manage_promotion(action="abort", ...)` |
| `kargo_promotion_mgmt(action="list"\|"get")` | Read `kargo://projects/{project}/promotions` or `kargo://projects/{project}/promotions/{promotion}` |
| `kargo_promotion_task_mgmt` | `kargo_apply_promotion_task` / `kargo_delete_resource(kind="PromotionTask")` / `kargo://projects/{project}/promotion-tasks/{task}` |
| `kargo_credentials_mgmt` | `kargo_manage_credentials` (with `secret_ref`) / `kargo://projects/{project}/credentials` |
| `kargo://best-practices`, `kargo://promotion-steps` | Agent Skills under `skills/*/SKILL.md` and `skills/*/references/*.md` |
| MCP Prompts (`kargo_onboard_project`, etc.) | Agent Skills under `skills/*/SKILL.md` |

---

## Running Tests & Type Checking

```bash
uv run pytest -v
uv run pyright kargo_mcp_server tests skills
```
