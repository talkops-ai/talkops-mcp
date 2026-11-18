# ArgoCD MCP Execution Server

Execution-layer Model Context Protocol (MCP) server for ArgoCD GitOps operations. Procedural workflows, troubleshooting decision trees, and manifest generation scripts live in the companion Agent Skills (`skills/`).

## Capability Surface

- **Application Tools (`applications`)**: `list_applications`, `get_application_details`, `create_application`, `update_application`, `delete_application`, `get_application_events`
- **Deployment Tools (`deployments`)**: `get_application_diff`, `sync_application`, `get_sync_status`, `get_application_logs`, `rollback_application`, `refresh_application`, `cancel_deployment`
- **Repository Tools (`repositories`)**: `list_repositories`, `get_repository`, `validate_repository_connection`, `onboard_repository`, `delete_repository`
- **Project Tools (`projects`)**: `list_projects`, `get_project`, `create_project`, `update_project`, `delete_project`
- **Addressable Resources**: `argocd://applications`, `argocd://applications/{app_name}`, `argocd://applications/{app_name}/history`, `argocd://applications/{app_name}/resource-tree`, `argocd://clusters`, `argocd://repositories`, `argocd://projects/{project_name}`, `argocd://health`

## Execution Guardrails

1. **Read-Only Default (`MCP_ALLOW_WRITE=false`)**: Mutating tools are unregistered when write access is disabled; dry-run-capable tools (`sync_application`, `rollback_application`) remain available strictly in `dry_run=True` preview mode.
2. **Dry-Run Previews First**: `sync_application` and `rollback_application` default to `dry_run=True`. Always inspect `get_application_diff` or a dry-run preview before executing with `dry_run=False`.
3. **Human-in-the-Loop Confirmation**: Destructive operations (`delete_application`, `delete_repository`, `delete_project`, `sync_application(prune=True, dry_run=False)`, `rollback_application(dry_run=False)`) request operator confirmation via MCP Elicitation or require explicit `confirm=True` when the client host does not support elicitation.
4. **Zero Secret Exposure**: No tool accepts or returns raw credentials (`GIT_PASSWORD`, `SSH_PRIVATE_KEY_PATH`, `ARGOCD_AUTH_TOKEN`, cluster tokens). All secrets are resolved server-side from environment variables.
