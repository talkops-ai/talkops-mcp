# Kargo MCP Execution Server

This MCP server provides the **execution and telemetry data plane** for Kargo v1.10+ (tested against v1.12) progressive delivery pipelines. Procedural workflows, GitOps step composition rules, and diagnostic decision trees live in companion Agent Skills (`skills/*/SKILL.md`).

## Architectural Rules
1. **Execution Only**: Use `kargo://` resources for single-resource reads and `kargo_*` tools for server-side filtering, N-to-1 correlation (`kargo_trace_freight`, `kargo_diagnose_stage`, `kargo_diagnose_warehouse`), and cluster mutations.
2. **Read-Only by Default**: Check `kargo://server/capabilities` first. Mutating tools are only registered when `--allow-write` (`MCP_ALLOW_WRITE=true`) is enabled.
3. **Dry-Run Previews**: All structural creation/update tools (`kargo_manage_project(action="create")`, `kargo_apply_project_config`, `kargo_apply_warehouse`, `kargo_apply_stage`, `kargo_apply_promotion_task`, `kargo_apply_analysis_template`) default to `dry_run=True`. Inspect the preview manifest before calling with `dry_run=False`.
4. **Destructive Confirmations & Zero Secrets**: High-blast-radius operations (`kargo_rollback_stage`, `kargo_approve_freight`, `kargo_delete_resource`, `kargo_manage_project(action="delete")`, `kargo_manage_promotion(action="abort")`, `kargo_manage_freight(action="delete")`, `kargo_manage_verification(action="abort")`, `kargo_manage_credentials(action="delete")`, `kargo_manage_roles(action="delete")`) require `confirm=True` or interactive elicitation. Credential tools never accept raw passwords or tokens; pass a symbolic `secret_ref` resolved server-side.

## Toolsets (20 Tools)
- `pipeline`: `kargo_manage_project`, `kargo_apply_project_config`, `kargo_apply_warehouse`, `kargo_apply_stage`, `kargo_apply_promotion_task`, `kargo_delete_resource`
- `promotion`: `kargo_query_freight`, `kargo_refresh`, `kargo_promote`, `kargo_rollback_stage`, `kargo_approve_freight`, `kargo_manage_promotion`, `kargo_manage_freight`
- `verification`: `kargo_apply_analysis_template`, `kargo_manage_verification`
- `credentials`: `kargo_manage_credentials`
- `rbac`: `kargo_manage_roles`
- `diagnostics`: `kargo_trace_freight`, `kargo_diagnose_stage`, `kargo_diagnose_warehouse`

## Live Resources (18 URIs)
- Server & Projects: `kargo://server/capabilities`, `kargo://projects`, `kargo://projects/{project}`, `kargo://projects/{project}/pipeline`, `kargo://projects/{project}/events`, `kargo://projects/{project}/roles`
- Stages & Warehouses: `kargo://projects/{project}/stages/{stage}`, `kargo://projects/{project}/stages/{stage}/manifest`, `kargo://projects/{project}/warehouses/{warehouse}`
- Freight & Promotions: `kargo://projects/{project}/freight/{freight_or_alias}`, `kargo://projects/{project}/promotions`, `kargo://projects/{project}/promotions/{promotion}`
- Tasks, Verification & Credentials: `kargo://projects/{project}/promotion-tasks/{task}`, `kargo://cluster-promotion-tasks/{task}`, `kargo://projects/{project}/analysis-templates`, `kargo://projects/{project}/analysis-runs/{run}`, `kargo://projects/{project}/analysis-runs/{run}/logs`, `kargo://projects/{project}/credentials`
