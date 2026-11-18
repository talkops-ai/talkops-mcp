---
name: onboarding-argocd-repositories-and-projects
description: Onboards Git, Helm, and OCI repositories into ArgoCD using server-side credentials and configures multi-tenant AppProject RBAC boundaries, source repository allowlists, cluster/namespace destinations, and resource restrictions. Use when registering or validating a repository, creating or updating an AppProject, or diagnosing repository authentication and project permission errors.
allowed-tools:
  - list_repositories
  - get_repository
  - validate_repository_connection
  - onboard_repository
  - delete_repository
  - list_projects
  - get_project
  - create_project
  - update_project
  - delete_project
  - list_applications
---

# Onboarding ArgoCD Repositories and AppProjects

Onboard repositories and configure multi-tenant `AppProject` RBAC boundaries in ArgoCD without exposing credentials in LLM tool arguments or context windows.

## Security Invariant: Zero Secrets in Tool Arguments

`validate_repository_connection` and `onboard_repository` **never accept passwords, tokens, or SSH private keys as tool arguments**, and you MUST **never embed tokens or credentials inside `repo_url`** (e.g., `https://<pat>@github.com/...`). If a user provides a plaintext PAT/token in chat, refuse to pass or embed it in any URL or tool call, advise rotating the exposed token immediately, and instruct configuring server-side environment variables instead:
- **`https://...` URLs**: Uses `GIT_USERNAME` and `GIT_PASSWORD` from the MCP server environment (public HTTPS Git/Helm repositories validate and onboard without credentials).
- **`ssh://...` or `git@...` URLs**: Reads the SSH private key from `SSH_PRIVATE_KEY_PATH` (default `~/.ssh/id_rsa`) on the MCP server host.
- Always use the ArgoCD MCP tools and resources (`argocd://repositories`, `argocd://clusters`, `argocd://projects/{name}`) rather than raw `argocd` or `kubectl` CLI commands.

---

## Workflow 1: Onboarding a Git, Helm, or OCI Repository

### Step 1: Check Existing Repository Registration
1. Call `list_repositories(repo_filter="<repo_substring>")` (or read `argocd://repositories`).
2. If the repository is already registered, call `get_repository(repo_url="<repo_url>")` to verify `connection_status == "Successful"`.

### Step 2: Validate Connectivity Before Onboarding
1. Call `validate_repository_connection(repo_url="<repo_url>", insecure=False)`.
2. Inspect `valid`:
   - If `valid == False`, inspect `error` and verify that `GIT_PASSWORD` (for `https://`) or `SSH_PRIVATE_KEY_PATH` (for `git@` / `ssh://`) is configured on the server.
   - Do **not** proceed to `onboard_repository` until validation succeeds.

### Step 3: Onboard the Repository
1. Call `onboard_repository`:
   ```json
   {
     "repo_url": "https://github.com/org/gitops-manifests.git",
     "repo_type": "git",
     "project": "production",
     "enable_lfs": false,
     "insecure": false
   }
   ```
2. Verify `created == True`, then call `get_repository(repo_url="<repo_url>")` for each onboarded repository to confirm the live stored registration reports `connection_status == "Successful"`.

---

## Workflow 2: Creating or Updating an AppProject RBAC Boundary

### Step 1: Inspect Existing Projects & Target Clusters
1. Call `list_projects(name_filter="<team_or_env>")`.
2. Read `argocd://clusters` to confirm valid target cluster `server` URLs (e.g., `https://kubernetes.default.svc`).

### Step 2: Create or Update the AppProject
1. Follow least-privilege GitOps design:
   - Scope `source_repos` to explicit repository URLs rather than `"*"` in production projects.
   - Scope `destinations` to explicit `{server, namespace}` pairs (or namespace prefixes such as `team-a-*`).
   - Restrict cluster-scoped resources via `resource_restrictions.cluster_resource_whitelist`.
2. Call `create_project`:
   ```json
   {
     "project_name": "payments-prod",
     "description": "Production AppProject for Payments services",
     "source_repos": [
       "https://github.com/org/gitops-manifests.git"
     ],
     "destinations": [
       {
         "server": "https://kubernetes.default.svc",
         "namespace": "payments-prod"
       }
     ],
     "resource_restrictions": {
       "cluster_resource_whitelist": [
         {"group": "", "kind": "Namespace"}
       ],
       "namespace_resource_blacklist": [
         {"group": "", "kind": "ResourceQuota"}
       ],
       "orphaned_resources_warn": true
     }
   }
   ```
3. Confirm the resulting project policy by calling `get_project(project_name="payments-prod")` (or reading `argocd://projects/payments-prod`).
4. **Before calling `update_project`**: Always call `get_project(project_name="<project_name>")` first so existing `source_repos`, `destinations`, and `namespace_resource_blacklist` rules are preserved while applying minimum-privilege additions (e.g., adding `{"group": "", "kind": "Namespace"}` to `cluster_resource_whitelist`).

---

## Workflow 3: Safe Decommissioning of Repositories & Projects

1. **Before `delete_project`**: Call `list_applications(project="<project_name>")` to verify `total == 0`. If `total > 0`, **block `delete_project`** and instruct migrating (`update_application`) or deleting child applications first.
2. **Built-in `default` project**: ArgoCD forbids deleting the built-in `default` `AppProject`. To lock down `default`, verify `list_applications(project="default")` has `0` active workloads and restrict it via `update_project(project_name="default", source_repos=[], destinations=[])`.
3. **Before `delete_repository`**: Call `list_applications()` and verify no active application tracks `repo_url`.
4. Present the impact preview to the operator and call `delete_project(project_name=..., confirm=True)` or `delete_repository(repo_url=..., confirm=True)` (if the operator already approved deletion in their request and zero active applications reference the target, proceed with `confirm=True` after verifying `total == 0`; otherwise pause for confirmation).
5. Confirm post-deletion removal by calling `list_projects()` (for deleted projects) and/or `list_repositories()` (for deleted repositories).

---

## Bootstrapping `ARGOCD_AUTH_TOKEN` Locally

If the operator needs to generate or validate `ARGOCD_AUTH_TOKEN` for the MCP server environment without printing secrets to terminal stdout, run:

```bash
python3 scripts/fetch_argocd_token.py \
  --server https://argocd.example.com \
  --username admin \
  --env-file .env
```

- Pass `ARGOCD_PASSWORD` via environment variable rather than CLI flags whenever possible; `--env-file` writes `0600` owner-only permissions and prints only a masked `token_preview` to stdout.
- **TLS Security Warning**: Only pass `--insecure` (or `ARGOCD_INSECURE=true`) against local/dev self-signed certificates (e.g., `https://localhost:8080`) — **never** disable TLS verification in production.

See [scripts/fetch_argocd_token.py](scripts/fetch_argocd_token.py) (`--help`) and [references/rbac-and-repo-onboarding.md](references/rbac-and-repo-onboarding.md) for credential setup and AppProject RBAC patterns.
