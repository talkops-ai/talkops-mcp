# ArgoCD MCP Server & Agent Plugin — User Guide (v0.4.0)

## Table of Contents

1. [Overview](#1-overview)
2. [Safety Guardrails & Read-Only Mode](#2-safety-guardrails--read-only-mode)
3. [Using the 4 Bundled Agent Skills](#3-using-the-4-bundled-agent-skills)
   - [Skill 1: Deploying ArgoCD Applications](#skill-1-deploying-argocd-applications)
   - [Skill 2: Rolling Back ArgoCD Applications](#skill-2-rolling-back-argocd-applications)
   - [Skill 3: Troubleshooting ArgoCD Applications](#skill-3-troubleshooting-argocd-applications)
   - [Skill 4: Onboarding Repositories and AppProjects](#skill-4-onboarding-repositories-and-appprojects)
4. [Using `argocd://` URI Resources](#4-using-argocd-uri-resources)
5. [Using Offline Helper Scripts](#5-using-offline-helper-scripts)

---

## 1. Overview

The ArgoCD MCP package combines:
- **An MCP Execution Server (`argocd-mcp-server`)** exposing 24 tools and 8 read-only resources.
- **An Agent Plugin (`plugin.json` + `mcp.json` + `skills/`)** providing 4 progressive-disclosure Agent Skills that teach AI coding assistants safe GitOps operating procedures.

---

## 2. Safety Guardrails & Read-Only Mode

1. **Read-Only by Default (`MCP_ALLOW_WRITE=false`)**:
   - When `MCP_ALLOW_WRITE=false` (or `--read-only` is passed on the CLI), pure mutating tools (`create_application`, `update_application`, `delete_application`, `cancel_deployment`, `onboard_repository`, `delete_repository`, `create_project`, `update_project`, `delete_project`) are not registered in `list_tools()`.
   - Preview-capable tools (`sync_application` and `rollback_application`) remain available for `dry_run=True` previews and reject `dry_run=False`.
2. **Dry-Run First**:
   - Both `sync_application` and `rollback_application` default to `dry_run=True`.
3. **Destructive Action Confirmation**:
   - High-blast-radius operations (`delete_application`, `delete_repository`, `delete_project`, `rollback_application(dry_run=False)`, and `sync_application(prune=True, dry_run=False)`) request interactive operator confirmation via MCP Elicitation (`ctx.elicit()`), or return a structured `confirmation_required` preview requiring `confirm=True`.

---

## 3. Using the 4 Bundled Agent Skills

### Skill 1: Deploying ArgoCD Applications
- **Location**: `skills/deploying-argocd-applications/SKILL.md`
- **Workflow**:
  1. `get_application_details(app_name="<app>", detail_level="summary")`
  2. `get_application_diff(app_name="<app>", revision="<rev>", validate=True)`
  3. `sync_application(app_name="<app>", revision="<rev>", dry_run=True)`
  4. `sync_application(app_name="<app>", revision="<rev>", dry_run=False)`
  5. `get_sync_status(app_name="<app>")`

### Skill 2: Rolling Back ArgoCD Applications
- **Location**: `skills/rolling-back-argocd-applications/SKILL.md`
- **Workflow**:
  1. Inspect integer history IDs via `get_application_details(app_name="<app>", detail_level="full")` or `argocd://applications/{app_name}/history`.
  2. Preview rollback via `rollback_application(app_name="<app>", history_id=<id>, dry_run=True)`.
  3. If `auto_sync_blocker` is `True`, disable auto-sync first via `update_application(app_name="<app>", sync_policy={"automated": False})`.
  4. Execute rollback via `rollback_application(app_name="<app>", history_id=<id>, dry_run=False, confirm=True)`.
  5. Verify recovery via `get_sync_status` and `get_application_details`.

### Skill 3: Troubleshooting ArgoCD Applications
- **Location**: `skills/troubleshooting-argocd-applications/SKILL.md`
- **Workflow**:
  1. `get_application_details(app_name="<app>", detail_level="full")`
  2. `get_sync_status(app_name="<app>")` and `get_application_diff(app_name="<app>", validate=True)`
  3. `get_application_resource_tree(app_name="<app>")` to locate `Degraded` or `Missing` pods
  4. `get_application_events(app_name="<app>", warnings_only=True)`
  5. `get_application_logs(app_name="<app>", pod_name="<pod>", errors_only=True)`

### Skill 4: Onboarding Repositories and AppProjects
- **Location**: `skills/onboarding-argocd-repositories-and-projects/SKILL.md`
- **Workflow**:
  1. `validate_repository_connection(repo_url="<url>")` (uses server-side `GIT_PASSWORD` or `SSH_PRIVATE_KEY_PATH`)
  2. `onboard_repository(repo_url="<url>", repo_type="git", project="<project>")`
  3. `create_project(project_name="<project>", description="...", source_repos=[...], destinations=[...], resource_restrictions={...})`

---

## 4. Using `argocd://` URI Resources

MCP clients can read live state directly via URI resources without invoking tools:
- `argocd://applications` — All applications summary
- `argocd://applications/{app_name}` — Full application details
- `argocd://applications/{app_name}/history` — Deployment history with integer `id`s
- `argocd://applications/{app_name}/resource-tree` — Kubernetes resource tree
- `argocd://clusters` — Target Kubernetes clusters (credentials redacted)
- `argocd://repositories` — Registered repositories (credentials redacted)
- `argocd://projects/{project_name}` — AppProject RBAC configuration
- `argocd://health` — Server connectivity, ArgoCD version, and write-guard status

---

## 5. Using Offline Helper Scripts

### Generate Declarative `Application`, `ApplicationSet`, and `AppProject` YAML
```bash
python3 skills/deploying-argocd-applications/scripts/generate_argocd_manifests.py --help
```

### Fetch and Validate `ARGOCD_AUTH_TOKEN` Without Leaking Secrets to Stdout
```bash
python3 skills/onboarding-argocd-repositories-and-projects/scripts/fetch_argocd_token.py \
  --server https://argocd.example.com \
  --username admin \
  --env-file .env
```
