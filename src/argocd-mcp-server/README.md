<p align="center">
  <img src="https://argo-cd.readthedocs.io/en/stable/assets/logo.png" alt="ArgoCD MCP Server" width="140"/>
</p>

<h1 align="center">ArgoCD MCP Server & Agent Plugin (v0.4.0)</h1>

<p align="center">
  An MCP execution server and Agent Skills plugin for managing Kubernetes applications via ArgoCD using GitOps principles.
</p>

<p align="center">
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://argo-cd.readthedocs.io/"><img src="https://img.shields.io/badge/ArgoCD-v2.x-0F1689.svg?style=flat-square&logo=argo&logoColor=white" alt="ArgoCD v2.x"/></a>
</p>

---

## Architecture: Skill Layer vs. Execution Layer

Version `0.4.0` separates **procedural GitOps knowledge** from **deterministic API execution**:

1. **Execution Layer (`argocd_mcp_server/`)**:
   - **24 high-signal MCP tools** across 4 toolset profiles (`applications`, `deployments`, `repositories`, `projects`), each with $\le 8$ parameters and full MCP `ToolAnnotations`.
   - **8 URI-addressed `argocd://` resources** for zero-side-effect context loading.
   - **Non-blocking async HTTP (`httpx.AsyncClient`)** with automatic retry on transient `GET` failures and model-directed error messages.
   - **Safe read-only default (`MCP_ALLOW_WRITE=false`)**, `dry_run=True` defaults on `sync_application` and `rollback_application`, and human-in-the-loop confirmation via **MCP Elicitation** (`ctx.elicit()`) with a two-step `confirm=True` fallback.

2. **Skill Layer (`skills/` + `plugin.json` + `mcp.json`)**:
   - Packaged as an **Agent Plugin v1.0.0** (`plugin.json` + `mcp.json`) containing **4 progressive-disclosure Agent Skills** (`SKILL.md` + `references/` + stdlib-only `scripts/`):
     - `deploying-argocd-applications`
     - `rolling-back-argocd-applications`
     - `troubleshooting-argocd-applications`
     - `onboarding-argocd-repositories-and-projects`

```
src/argocd-mcp-server/
├── plugin.json                 # Agent Plugin v1.0.0 manifest
├── mcp.json                    # Portable MCP launcher config
├── skills/                     # 4 Progressive-Disclosure Agent Skills
│   ├── deploying-argocd-applications/
│   ├── rolling-back-argocd-applications/
│   ├── troubleshooting-argocd-applications/
│   └── onboarding-argocd-repositories-and-projects/
├── argocd_mcp_server/          # MCP Execution Server (FastMCP + httpx)
│   ├── config.py               # ServerConfig (allow_write=False default, MCP_TOOLSETS)
│   ├── main.py                 # CLI (--transport, --toolsets, --read-only)
│   ├── exceptions/             # Model-directed custom exceptions (401/403/404/409/5xx)
│   ├── server/                 # FastMCP bootstrap & middleware (tool caching disabled)
│   ├── services/               # ArgoCDClient, ArgoCDService, ArgoCDManagementService
│   ├── tools/                  # 24 tools across 4 toolset profiles
│   └── resources/              # 8 argocd:// URI resources
└── tests/                      # 3-Layer Test Suite (Unit, In-Memory MCP, E2E, Skills)
```

---

## Bundled Agent Skills (`skills/`)

| Skill Directory | Purpose | Offline Scripts (`scripts/`) | Reference Guides (`references/`) |
|---|---|---|---|
| `deploying-argocd-applications` | Pre-sync diff validation (`get_application_diff`), dry-run preview, controlled sync execution, and declarative YAML authoring | `generate_argocd_manifests.py` | `sync-strategies.md` |
| `rolling-back-argocd-applications` | Integer history ID resolution, auto-sync blocker detection, preview-first rollback, and recovery verification | *(uses `rollback_application`)* | `rollback-edge-cases.md` |
| `troubleshooting-argocd-applications` | Structured root-cause diagnosis across `OutOfSync`, `Degraded`, `Missing`, warning events, and pod log streams | *(uses live diagnostic tools)* | `argocd-error-catalog.md` |
| `onboarding-argocd-repositories-and-projects` | Credential-isolated HTTPS/SSH/OCI repository onboarding, `AppProject` RBAC scoping, and safe local token setup | `fetch_argocd_token.py` | `rbac-and-credentials.md` |

---

## Tool Catalog (24 Tools)

### 1. `applications` Toolset (7 Tools)

| Tool | Read-Only | Destructive | Parameters ($\le 8$) | Description |
|---|---|---|---|---|
| `list_applications` | Yes | No | `cluster`, `namespace`, `project`, `sync_status`, `health_status`, `limit`, `offset` | List applications with filtering and pagination |
| `get_application_details` | Yes | No | `app_name`, `detail_level` (`"summary"` \| `"full"`) | Get sync/health status, problem resources, and deployment history with history IDs |
| `get_application_resource_tree` | Yes | No | `app_name` | Get Kubernetes resource hierarchy (`Deployment -> ReplicaSet -> Pod`) |
| `get_application_events` | Yes | No | `app_name`, `limit`, `warnings_only` | Get recent Kubernetes events sorted newest first |
| `create_application` | No | No | `app_name`, `project`, `repo_url`, `path`, `destination_namespace`, `target_revision`, `destination_server`, `sync_policy` | Register a new ArgoCD application |
| `update_application` | No | No | `app_name`, `target_revision`, `sync_policy`, `path`, `destination_namespace` | Update tracked revision, path, namespace, or sync policy |
| `delete_application` | No | **Yes** | `app_name`, `cascade`, `confirm` | Delete an application (gated by MCP Elicitation / `confirm=True`) |

### 2. `deployments` Toolset (7 Tools)

| Tool | Read-Only | Destructive | Parameters ($\le 8$) | Description |
|---|---|---|---|---|
| `get_application_diff` | Yes | No | `app_name`, `revision`, `validate` | Compare live cluster state vs. target Git manifests and optionally validate via dry-run sync |
| `sync_application` | Preview / Write | Conditional (`prune=True`) | `app_name`, `revision`, `dry_run` (`True`), `prune`, `force`, `resources`, `confirm` | Preview (`dry_run=True`) or execute (`dry_run=False`) an application sync |
| `get_sync_status` | Yes | No | `app_name` | Get active operation phase, per-resource sync results, and recent history |
| `get_application_logs` | Yes | No | `app_name`, `pod_name`, `container`, `tail_lines`, `since_seconds`, `errors_only` | Fetch and parse ArgoCD NDJSON pod log streams with error extraction |
| `rollback_application` | Preview / Write | **Yes** | `app_name`, `history_id`, `dry_run` (`True`), `prune`, `confirm` | Preview or execute a rollback to a deployment history ID with auto-sync blocker detection |
| `refresh_application` | Yes | No | `app_name`, `mode` (`"normal"` \| `"hard"`) | Trigger soft (`normal`) or manifest-cache-invalidating (`hard`) refresh |
| `cancel_deployment` | No | No | `app_name` | Terminate an ongoing sync operation |

### 3. `repositories` Toolset (5 Tools)

| Tool | Read-Only | Destructive | Parameters ($\le 8$) | Description |
|---|---|---|---|---|
| `list_repositories` | Yes | No | `repo_filter` | List onboarded Git/Helm/OCI repositories (credentials redacted) |
| `get_repository` | Yes | No | `repo_url` | Get repository connection status and metadata (credentials redacted) |
| `validate_repository_connection` | Yes | No | `repo_url`, `insecure` | Validate connectivity using server-configured Git credentials |
| `onboard_repository` | No | No | `repo_url`, `repo_type`, `project`, `enable_lfs`, `insecure`, `force_http_basic_auth` | Onboard HTTPS or SSH repository using server-side credentials |
| `delete_repository` | No | **Yes** | `repo_url`, `confirm` | Delete a registered repository (gated by MCP Elicitation / `confirm=True`) |

### 4. `projects` Toolset (5 Tools)

| Tool | Read-Only | Destructive | Parameters ($\le 8$) | Description |
|---|---|---|---|---|
| `list_projects` | Yes | No | `name_filter` | List AppProjects with source repos and destination rules |
| `get_project` | Yes | No | `project_name` | Get detailed AppProject RBAC rules and resource restrictions |
| `create_project` | No | No | `project_name`, `description`, `source_repos`, `destinations`, `resource_restrictions` | Create an AppProject with RBAC restrictions |
| `update_project` | No | No | `project_name`, `description`, `source_repos`, `destinations`, `resource_restrictions` | Update an existing AppProject |
| `delete_project` | No | **Yes** | `project_name`, `confirm` | Delete an AppProject (gated by MCP Elicitation / `confirm=True`) |

---

## Resource Catalog (8 URI-Addressed Resources)

| Resource URI | Description |
|---|---|
| `argocd://applications` | Catalog of all ArgoCD applications with sync and health status |
| `argocd://applications/{app_name}` | Full state, resources, and deployment history for a specific application |
| `argocd://applications/{app_name}/history` | Deployment revision history with integer `id`s for rollback targeting |
| `argocd://applications/{app_name}/resource-tree` | Hierarchical Kubernetes resource tree for an application |
| `argocd://clusters` | Registered target Kubernetes clusters with connection state and version |
| `argocd://repositories` | Onboarded Git, Helm, and OCI repositories (credentials redacted) |
| `argocd://projects/{project_name}` | AppProject RBAC rules, allowed source repositories, and destinations |
| `argocd://health` | ArgoCD API connectivity, server version, and `MCP_ALLOW_WRITE` posture |

---

## Quick Start & Configuration

### Installation

```bash
cd src/argocd-mcp-server
uv sync --dev
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ARGOCD_SERVER_URL` | `https://argocd-server.argocd.svc:443` | ArgoCD API server URL |
| `ARGOCD_AUTH_TOKEN` | `None` | ArgoCD Bearer JWT token |
| `ARGOCD_INSECURE` | `false` | Skip TLS verification for self-signed ArgoCD certs |
| `ARGOCD_TIMEOUT` | `300` | HTTP request timeout in seconds |
| `ARGOCD_MAX_RETRIES` | `2` | Automatic retries for transient `GET` failures |
| `MCP_ALLOW_WRITE` | **`false`** | **Safe default**: read-only mode (`true` enables mutating tools) |
| `MCP_TOOLSETS` | `all` | Comma-separated toolsets (`all,readonly,applications,deployments,repositories,projects`) |
| `MCP_TRANSPORT` | `http` | Transport mode (`stdio` or `http`) |
| `GIT_USERNAME` | `""` | Server-side username for HTTPS repository onboarding |
| `GIT_PASSWORD` | `None` | Server-side PAT/token for HTTPS repository onboarding |
| `SSH_PRIVATE_KEY_PATH` | `~/.ssh/id_rsa` | Server-side SSH private key path for SSH repository onboarding |

### Running the Server

```bash
# Default stdio transport in safe read-only mode
uv run argocd-mcp-server --transport stdio --read-only

# Enable specific toolsets
uv run argocd-mcp-server --transport stdio --toolsets applications,deployments

# Streamable HTTP transport
uv run argocd-mcp-server --transport http
```

---

## Migration Guide: v0.3.0 -> v0.4.0

| v0.3.0 Component | v0.4.0 Replacement | Reason |
|---|---|---|
| Required `cluster_name` parameter on per-app tools | Removed (`list_applications` retains optional `cluster` filter; `argocd://clusters` resource added) | ArgoCD REST API identifies applications by `app_name`; `cluster_name` was unused in per-app endpoints |
| `rollback_application` + `rollback_to_revision` | Consolidated `rollback_application(app_name, history_id=None, dry_run=True, prune=False, confirm=False)` | Fixes Git-SHA-as-integer-history-ID bug (`N2`) and detects auto-sync blockers |
| `validate_application_config` | `get_application_diff(app_name, revision=None, validate=True)` | N-to-1 consolidation: computes live-vs-target diffs and validates via dry-run in one call |
| `onboard_repository_https` + `onboard_repository_ssh` | `onboard_repository(repo_url, repo_type="git", project=None, ...)` | Infers HTTPS vs. SSH from `repo_url` and resolves credentials from server env vars |
| `generate_application_manifest` + `create_applicationset_manifest` | `skills/deploying-argocd-applications/scripts/generate_argocd_manifests.py` | Pure offline YAML templating moved to deterministic skill script |
| `generate_repository_secret_manifest` | Removed | Security hardening: prevents secret material from entering LLM context (`N8`) |
| 7 `@mcp.prompt()` workflows + `argocd://workflow` | 4 Agent Skills under `skills/` | Progressive disclosure via Agent Skills Open Spec |

---

## Testing & Verification

```bash
# Run all 58 Unit, In-Memory FastMCP Integration, E2E Workflow, and Skill Contract tests
uv run pytest tests/ -v --tb=short

# Run static type checking
uv run pyright .
```
