# ArgoCD Repository Onboarding and AppProject RBAC Reference

## Table of Contents
1. [Server-Side Repository Credential Mapping](#1-server-side-repository-credential-mapping)
2. [AppProject Least-Privilege RBAC Templates](#2-appproject-least-privilege-rbac-templates)
3. [Resource Restriction Rules (`resource_restrictions`)](#3-resource-restriction-rules-resource_restrictions)
4. [Troubleshooting Repository & Project Errors](#4-troubleshooting-repository--project-errors)

---

## 1. Server-Side Repository Credential Mapping

The ArgoCD MCP Server resolves Git/Helm/OCI credentials exclusively from server environment variables so secrets never enter the LLM context window:

| URL Pattern | Inferred Scheme | Server Environment Variables Used | Notes |
|---|---|---|---|
| `https://github.com/org/repo.git` | `https` | `GIT_USERNAME` (optional), `GIT_PASSWORD` (required PAT/token) | Supports GitHub PATs, GitLab project tokens, Bitbucket app passwords, and HTTPS Helm registries |
| `ssh://git@github.com/org/repo.git` | `ssh` | `SSH_PRIVATE_KEY_PATH` (default `~/.ssh/id_rsa`) | Reads PEM/OpenSSH private key file from the MCP server filesystem |
| `git@github.com:org/repo.git` | `ssh` | `SSH_PRIVATE_KEY_PATH` (default `~/.ssh/id_rsa`) | SCP-style SSH URL automatically mapped to SSH key onboarding |

---

## 2. AppProject Least-Privilege RBAC Templates

### Tier-1 Production Project (Strict Isolation)
- **`source_repos`**: Explicit GitOps repository URLs only (never `"*"`).
- **`destinations`**: Explicit cluster server URL and dedicated namespace(s).
- **`cluster_resource_whitelist`**: Empty `[]` (or `[{"group": "", "kind": "Namespace"}]` if `CreateNamespace=true` is used).
- **`namespace_resource_blacklist`**: Block `ResourceQuota` and `LimitRange` so application manifests cannot elevate their own namespace quotas.

### Development / Sandbox Project
- **`source_repos`**: Organization Git repositories or feature branches.
- **`destinations`**: Non-production cluster and `dev-*` namespaces.
- **`orphaned_resources_warn`**: `true` to detect stray manually created resources in shared dev namespaces.

---

## 3. Resource Restriction Rules (`resource_restrictions`)

The `resource_restrictions` dictionary in `create_project` and `update_project` supports:

```json
{
  "cluster_resource_whitelist": [
    {"group": "", "kind": "Namespace"},
    {"group": "rbac.authorization.k8s.io", "kind": "ClusterRole"},
    {"group": "rbac.authorization.k8s.io", "kind": "ClusterRoleBinding"}
  ],
  "cluster_resource_blacklist": [
    {"group": "admissionregistration.k8s.io", "kind": "MutatingWebhookConfiguration"}
  ],
  "namespace_resource_whitelist": [
    {"group": "*", "kind": "*"}
  ],
  "namespace_resource_blacklist": [
    {"group": "", "kind": "ResourceQuota"},
    {"group": "", "kind": "LimitRange"}
  ],
  "orphaned_resources_warn": true
}
```

- By default in ArgoCD, **cluster-scoped resources are denied** (`clusterResourceWhitelist: []`) and **namespaced resources are allowed** (`namespaceResourceWhitelist: [{"group": "*", "kind": "*"}]`).

---

## 4. Troubleshooting Repository & Project Errors

- **`Git HTTPS credentials are not configured on the server`**: Set `GIT_PASSWORD` in the environment where `argocd-mcp-server` runs.
- **`SSH private key file not found`**: Mount the deploy key and set `SSH_PRIVATE_KEY_PATH=/path/to/id_ed25519`.
- **`Cannot delete project '<name>' because applications still belong to it`**: Call `list_applications(project="<name>")`, then delete or reassign each application before deleting the project.
- **`The 'default' ArgoCD project cannot be deleted`**: ArgoCD requires the built-in `default` project to exist; use `update_project(project_name="default", ...)` if you need to tighten its permissions.
