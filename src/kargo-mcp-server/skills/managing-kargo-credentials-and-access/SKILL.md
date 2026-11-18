---
name: managing-kargo-credentials-and-access
description: Manages Kargo v1.12 repository credentials, generic secrets, shared credentials replication, webhook receiver secrets, and OIDC-mapped RBAC roles without exposing raw secrets in context. Use when configuring Git, image, or Helm repository credentials, rotating secrets via secret_ref, or granting Kargo RBAC roles and stage promote permissions.
---

# Managing Kargo Credentials and Access

Security and access control workflow for managing Kargo repository credentials (`git`, `image`, `helm`), generic secrets, shared credential replication, and Kargo RBAC roles/grants with strict `0->1` secret omission.

## Preconditions

1. Read `kargo://server/capabilities` to verify `allow_write: true` and confirm `credentials` and `rbac` toolsets are enabled.
2. Read `kargo://projects/{project}/credentials` and `kargo://projects/{project}/roles` to inspect current redacted secrets, ConfigMaps, and RBAC roles.
3. Consult [references/credentials-and-rbac.md](references/credentials-and-rbac.md) for server-side `secret_ref` resolution rules, `kargo-shared-resources` replication, and OIDC claim bindings.

## Credentials & RBAC Checklist

- [ ] **Step 1: Audit Existing Credentials & Scopes**
  - Read `kargo://projects/{project}/credentials` to inspect project-scoped (`<project>` namespace), shared (`kargo-shared-resources`), and system-scoped (`kargo-system-resources`) credentials and ConfigMaps (all secret values are redacted to `***REDACTED***`).
- [ ] **Step 2: Create or Rotate Credentials & ConfigMaps via Server-Side `secret_ref` (`[GATE]`)**
  - Never request or pass raw passwords, tokens, or SSH private keys in tool arguments. If a user pastes a raw token or password in chat, refuse to pass it in tool calls and instruct them to mount it in the MCP server's environment (`KARGO_CRED_<REF>_USERNAME` / `KARGO_CRED_<REF>_PASSWORD` or `KARGO_CREDENTIALS_FILE`).
  - `[GATE]` Confirm the target `scope` (`project`, `shared`, or `system`), `repo_url`, and `secret_ref` (executing directly when the operator explicitly specified them in their request):
    - Repository credential: `kargo_manage_credentials(action="create"|"update", project=..., name=..., scope="project"|"shared", credential={"kind": "repo", "cred_type": "git"|"image"|"helm", "repo_url": ..., "secret_ref": "<REF>", "repo_url_is_regex": False, "replicate_to_all_projects": False})`
    - Generic secret (e.g., webhook receiver or Slack secret): `kargo_manage_credentials(action="create"|"update", project=..., name=..., scope="project"|"shared"|"system", credential={"kind": "generic", "secret_ref": "<REF>", "data_keys": [...], "replicate_to_all_projects": False})` — in `shared` scope, `replicate_to_all_projects=True` sets `kargo.akuity.io/replicate: "true"` on the `kargo-shared-resources` Secret so Kargo replicates it into every Project namespace for `${{ secret('<name>') }}`.
    - Non-secret ConfigMap: `kargo_manage_credentials(action="create"|"update", project=..., name=..., scope="project"|"shared"|"system", credential={"kind": "configmap", "config_data": {...}, "replicate_to_all_projects": False})`
    - When wiring webhook receivers on `ProjectConfig`, preview (`dry_run=True`) and apply (`dry_run=False`) via `kargo_apply_project_config`, then trigger `kargo_refresh(project=..., kind="project_config"|"cluster_config")` so Kargo reloads receiver endpoints.
- [ ] **Step 3: Delete Obsolete Credentials (`[GATE]`)**
  - `[GATE]` Confirm with the operator (or execute directly when deletion was explicitly requested) via `kargo_manage_credentials(action="delete", project=..., name=..., credential={"kind": "repo"|"generic"|"configmap"}, scope=..., confirm=True)`.
- [ ] **Step 4: Manage Kargo RBAC Roles & OIDC Claim Grants (`[GATE]`)**
  - Inspect existing roles via `kargo://projects/{project}/roles` (each Kargo `Role` unifies an underlying Kubernetes `ServiceAccount`, `Role`, and `RoleBinding` in the Project namespace).
  - `[GATE]` Confirm policy permissions and OIDC claim mappings with the operator (or execute directly when explicitly specified in the operator's request):
    - Create role: `kargo_manage_roles(action="create", project=..., role=..., permissions=[{"resourceType": "stages", "resourceName": "dev", "verbs": ["promote"]}], claims={"groups": ["dev-engineers"]})`
    - Grant claims or permissions: `kargo_manage_roles(action="grant", project=..., role=..., claims={...}, permissions=[...])`
    - Revoke claims or permissions: `kargo_manage_roles(action="revoke", project=..., role=..., claims={...}, permissions=[...], confirm=True)`
    - Delete role: `kargo_manage_roles(action="delete", project=..., role=..., confirm=True)`
