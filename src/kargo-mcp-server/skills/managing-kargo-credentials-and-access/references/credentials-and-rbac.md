# Kargo Credentials & RBAC Reference (v1.12)

## Table of Contents
1. [Zero-Secret (`0->1`) Architecture & `secret_ref`](#zero-secret-0-1-architecture--secret_ref)
2. [Credential Scopes & Shared Replication](#credential-scopes--shared-replication)
3. [Webhook Receiver Secrets in `ProjectConfig`](#webhook-receiver-secrets-in-projectconfig)
4. [Kargo RBAC Roles, `promote` Verb & OIDC Claims](#kargo-rbac-roles-promote-verb--oidc-claims)

## Zero-Secret (`0->1`) Architecture & `secret_ref`

To prevent sensitive credentials from entering LLM conversation transcripts or audit logs, `kargo_manage_credentials` **never accepts raw passwords, tokens, or SSH private keys**. Instead, callers pass `credential={"secret_ref": "<REF>", ...}` (or rely on the `default` ref), and the MCP server resolves secret material strictly on the server side:

1. **Named Environment Variables** (for `secret_ref: "<REF>"`):
   - `KARGO_CRED_<REF>_USERNAME`
   - `KARGO_CRED_<REF>_PASSWORD`
   - `KARGO_CRED_<REF>_SSH_PRIVATE_KEY`
   - `KARGO_CRED_<REF>_DATA_JSON` (for `credential={"kind": "generic"}`)
2. **Default Fallback Environment Variables** (when `secret_ref="default"`):
   - `KARGO_REPO_USERNAME`
   - `KARGO_REPO_PASSWORD`
   - `KARGO_REPO_SSH_PRIVATE_KEY`
3. **Mounted Credentials File** (`KARGO_CREDENTIALS_FILE`):
   - Path to a server-side JSON or YAML file mapping `<secret_ref>` keys to `{username, password, sshPrivateKey, data}` objects.

All responses from `kargo_manage_credentials` and `kargo://projects/{project}/credentials` replace secret values with `***REDACTED***`.

## Credential Scopes & Shared Replication

Kargo v1.12 supports three credential scopes via `kargo_manage_credentials(..., scope=...)`:
- `project` (default): Stored in the project's namespace; accessible only to Warehouses and Promotions in that Project.
- `shared`: Stored in `kargo-shared-resources`; accessible across all Projects.
  - In Kargo v1.11+, setting `credential={"replicate_to_all_projects": True, ...}` adds label `kargo.akuity.io/replicate: "true"` on a shared Secret so the Kargo management controller replicates it into every Project namespace (enabling expression access via `${{ secret('<name>') }}`).
- `system`: Stored in `kargo-system-resources` for controller/cluster-level Secrets and ConfigMaps (such as cluster webhook or system-wide integration secrets).

## Webhook Receiver Secrets in `ProjectConfig`

To configure a GitHub, GitLab, Gitea, Bitbucket, Quay, DockerHub, Harbor, or generic webhook receiver:
1. Create a generic secret with the webhook token/secret via `kargo_manage_credentials(action="create", project=..., name="github-wh-secret", credential={"kind": "generic", "secret_ref": "GITHUB_WEBHOOK"})`.
2. Preview (`dry_run=True`) and attach (`dry_run=False`) the webhook receiver to `ProjectConfig` using `kargo_apply_project_config(project=..., webhook_receivers=[{"name": "github-wh", "github": {"secretRef": {"name": "github-wh-secret"}}}], dry_run=True)` followed by `dry_run=False`.
3. Trigger `kargo_refresh(project=..., kind="project_config")` (and `kind="cluster_config"` when cluster receivers change), then inspect generated receiver URLs via `kargo://projects/{project}`.

## Kargo RBAC Roles, `promote` Verb & OIDC Claims

Kargo v1.12 combines Kubernetes `ServiceAccount`, `Role`, and `RoleBinding` objects inside a Project namespace into a unified Kargo `Role` representation (`kargo://projects/{project}/roles`), managed via `kargo_manage_roles`:

- **Stage-Specific Promotion Access**:
  Grant the custom `promote` verb on specific `stages` (`resourceName: "dev"` / `"staging"`) so a team can promote to non-production stages without full `update`/`patch` permissions on Stage specs:
  ```json
  {
    "resourceType": "stages",
    "resourceName": "dev",
    "verbs": ["promote"]
  }
  ```
- **OIDC Claim Mappings**:
  Pass `claims={"groups": ["sre-team"], "email": ["oncall@example.com"]}` to `kargo_manage_roles(action="create"|"grant"|"revoke", role=..., ...)`.
