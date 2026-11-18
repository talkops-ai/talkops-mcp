<p align="center">
  <img src="https://raw.githubusercontent.com/cncf/artwork/main/projects/argo/icon/color/argo-icon-color.svg" alt="Argo CD logo" height="100"/>
</p>

<h1 align="center">ArgoCD MCP Server &amp; Agent Plugin</h1>

<p align="center">
  An MCP execution server and Agent Skills plugin for managing Kubernetes applications via ArgoCD using GitOps principles.
</p>

<p align="center">
  <a href="https://pypi.org/project/talkops-argocd-mcp-server/"><img src="https://img.shields.io/pypi/v/talkops-argocd-mcp-server.svg?style=flat-square&logo=pypi&logoColor=white&label=PyPI" alt="PyPI"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://argo-cd.readthedocs.io/"><img src="https://img.shields.io/badge/ArgoCD-v2.x-EF7B4D.svg?style=flat-square&logo=argo&logoColor=white" alt="ArgoCD v2.x"/></a>
</p>

---

Let your AI assistant manage your ArgoCD applications: check health, preview and run syncs, roll back, and onboard repositories and projects. Git credentials stay on the server and are never shown to the model.

## What you get

- **24 MCP tools** (13 read-only) that work against your live ArgoCD setup
- **8 resources** your assistant can read for context, under `argocd://`
- **4 Agent Skills**: step-by-step playbooks that teach your assistant how to use the tools well
- **Safe by default**: only read-only tools are loaded until you turn on writes, and changes are previewed or confirmed before they happen

## Quick start

**You'll need:**

- Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)
- An ArgoCD server URL and an API token (`argocd account generate-token`)

**1. Add the server to your MCP client.** For Claude Desktop, Cursor, Windsurf, and most other clients, add this to your MCP config file:

```json
{
  "mcpServers": {
    "argocd": {
      "command": "uvx",
      "args": [
        "--from",
        "talkops-argocd-mcp-server",
        "argocd-mcp-server",
        "--transport",
        "stdio"
      ],
      "env": {
        "ARGOCD_SERVER_URL": "https://argocd.example.com",
        "ARGOCD_AUTH_TOKEN": "<your-argocd-token>"
      }
    }
  }
}
```

Using Claude Code? Run this instead:

```bash
claude mcp add argocd -e ARGOCD_SERVER_URL=https://argocd.example.com -e ARGOCD_AUTH_TOKEN=<your-argocd-token> -- uvx --from talkops-argocd-mcp-server argocd-mcp-server --transport stdio
```

> [!NOTE]
> ArgoCD defaults to HTTP mode, so the examples pass `--transport stdio` for desktop clients.

`uvx` downloads [`talkops-argocd-mcp-server`](https://pypi.org/project/talkops-argocd-mcp-server/) from PyPI and runs it, so there's nothing else to install. Prefer a normal install? Run `pip install talkops-argocd-mcp-server` and use `argocd-mcp-server` as the command.

**2. Restart your client and try asking:**

- *"Which of my ArgoCD applications are out of sync or degraded?"*
- *"Show me the diff for `payments-api`, then do a dry-run sync."*
- *"Roll `checkout` back to its last healthy deployment."*

## Allowing changes

Out of the box the server is read-only. To let your assistant make changes (creating, updating, syncing, rolling back, and deleting apps, repositories, and projects), add `"MCP_ALLOW_WRITE": "true"` to the `env` block. Even then, syncs and rollbacks run as a dry run first, and destructive actions ask for confirmation.

## Configuration

Set these as environment variables (the `env` block in your client config) or pass the matching flag.

| Variable | Flag | Default | What it does |
| :--- | :--- | :--- | :--- |
| `ARGOCD_SERVER_URL` | — | `https://argocd-server.argocd.svc:443` | Your ArgoCD API URL |
| `ARGOCD_AUTH_TOKEN` | — | none | ArgoCD API token (required) |
| `ARGOCD_INSECURE` | — | `false` | Skip TLS verification (self-signed certs only) |
| `MCP_ALLOW_WRITE` | — | `false` | Enable tools that change ArgoCD |
| `MCP_TOOLSETS` | `--toolsets` | `all` | Limit tools: `applications`, `deployments`, `repositories`, `projects`, `readonly` |
| `GIT_USERNAME` / `GIT_PASSWORD` | — | none | Server-side credentials for onboarding HTTPS repos |
| `SSH_PRIVATE_KEY_PATH` | — | `~/.ssh/id_rsa` | Server-side key for onboarding SSH repos |
| `MCP_TRANSPORT` | `--transport` | `http` | `stdio` or `http` |
| `MCP_PORT` | — | `8770` | Port when using HTTP |

Run `uvx --from talkops-argocd-mcp-server argocd-mcp-server --help` to see every option.

### Running over HTTP

To share one server between several clients or run it remotely, start it in HTTP mode:

```bash
MCP_TRANSPORT=http MCP_PORT=8770 uvx --from talkops-argocd-mcp-server argocd-mcp-server
```

Then point your client at `http://localhost:8770/mcp`:

```json
{
  "mcpServers": {
    "argocd": {
      "url": "http://localhost:8770/mcp"
    }
  }
}
```

## Agent Skills

Skills live in [`skills/`](skills/). Each one is a `SKILL.md` playbook (plus optional `references/` and offline `scripts/`) that teaches your AI assistant *how* to do a job safely, while the MCP server does the actual work. Tools are the hands, skills are the know-how.

To use them, copy the folders into your assistant's skills directory, for example:

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cp -r talkops-mcp/src/argocd-mcp-server/skills/* ~/.claude/skills/
```

This folder is also a portable [Agent Plugin](https://agent-plugins.org) (`plugin.json` + `mcp.json` + `skills/`), so plugin-aware clients can load the server and skills together.

| Skill | Use it to |
| :--- | :--- |
| [`deploying-argocd-applications`](skills/deploying-argocd-applications/SKILL.md) | Diff first, dry-run the sync, then deploy and confirm the app is healthy. |
| [`rolling-back-argocd-applications`](skills/rolling-back-argocd-applications/SKILL.md) | Pick a known-good revision, handle auto-sync, preview, and roll back. |
| [`troubleshooting-argocd-applications`](skills/troubleshooting-argocd-applications/SKILL.md) | Figure out why an app is degraded or out of sync using events, resources, and logs. |
| [`onboarding-argocd-repositories-and-projects`](skills/onboarding-argocd-repositories-and-projects/SKILL.md) | Add Git, Helm, or OCI repos and set up projects with the right access limits. |

## Reference

<details>
<summary><strong>All 24 tools</strong></summary>

| Tool | Access | What it does |
| :--- | :--- | :--- |
| `cancel_deployment` | Write | Terminate an ongoing sync operation on an application. |
| `create_application` | Write | Create a new ArgoCD application tracking a Git repository path. |
| `create_project` | Write | Create a new ArgoCD AppProject with source repositories, destinations, and RBAC restrictions. |
| `delete_application` | Write (destructive) | Delete an ArgoCD application and optionally cascade-delete its cluster resources. |
| `delete_project` | Write (destructive) | Delete an ArgoCD AppProject (fails safely if applications still belong to the project). |
| `delete_repository` | Write (destructive) | Delete a registered repository from ArgoCD. |
| `get_application_details` | Read | Get application sync/health state, managed resources, sync policy, and deployment history with history IDs. |
| `get_application_diff` | Read | Compare live cluster state against target Git manifests and optionally validate via dry-run. |
| `get_application_events` | Read | Get recent Kubernetes events for an application sorted newest first. |
| `get_application_logs` | Read | Retrieve and summarize pod logs for an application with NDJSON stream parsing and error detection. |
| `get_application_resource_tree` | Read | Get the Kubernetes resource hierarchy (Deployments, ReplicaSets, Pods, Services) for an application. |
| `get_project` | Read | Get detailed AppProject configuration, allowed repositories, destinations, and resource restrictions. |
| `get_repository` | Read | Get repository connection status and metadata (credentials redacted). |
| `get_sync_status` | Read | Get current sync status, active operation phase, per-resource sync results, and recent history. |
| `list_applications` | Read | List ArgoCD applications with optional filtering and pagination. |
| `list_projects` | Read | List all ArgoCD AppProjects with source repositories and destination rules. |
| `list_repositories` | Read | List all repositories registered in ArgoCD with credentials redacted. |
| `onboard_repository` | Write | Onboard a Git/Helm/OCI repository into ArgoCD using server-side credentials (inferred from URL scheme). |
| `refresh_application` | Read | Trigger a soft ('normal') or manifest-cache-invalidating ('hard') refresh on an application. |
| `rollback_application` | Write (destructive) | Preview (dry_run=True) or execute (dry_run=False) an application rollback to a specific deployment history ID. |
| `sync_application` | Write | Preview (dry_run=True) or execute (dry_run=False) an ArgoCD application sync operation. |
| `update_application` | Write | Update an existing ArgoCD application's revision, path, namespace, or sync policy. |
| `update_project` | Write | Update an existing ArgoCD AppProject's description, repositories, destinations, or resource restrictions. |
| `validate_repository_connection` | Read | Validate repository connectivity using server-configured Git credentials. |

</details>

<details>
<summary><strong>All 8 resources</strong></summary>

| Resource | What it returns |
| :--- | :--- |
| `argocd://applications` | Catalog of all ArgoCD applications with sync and health status. |
| `argocd://clusters` | Registered target Kubernetes clusters with connection state and server version. |
| `argocd://health` | ArgoCD API connectivity, server version, and MCP guardrail posture. |
| `argocd://repositories` | Onboarded Git, Helm, and OCI repositories (credentials redacted). |
| `argocd://applications/{app_name}` | Full state, managed resources, and deployment history for a specific application. |
| `argocd://applications/{app_name}/history` | Deployment revision history with integer history IDs for rollback targeting. |
| `argocd://applications/{app_name}/resource-tree` | Hierarchical Kubernetes resource tree for an application. |
| `argocd://projects/{project_name}` | AppProject RBAC rules, allowed source repositories, and cluster destinations. |

</details>

<details>
<summary><strong>Upgrading from an older version</strong></summary>

### Migration Guide: v0.3.0 -> v0.4.0

| v0.3.0 Component | v0.4.0 Replacement | Reason |
|---|---|---|
| Required `cluster_name` parameter on per-app tools | Removed (`list_applications` retains optional `cluster` filter; `argocd://clusters` resource added) | ArgoCD REST API identifies applications by `app_name`; `cluster_name` was unused in per-app endpoints |
| `rollback_application` + `rollback_to_revision` | Consolidated `rollback_application(app_name, history_id=None, dry_run=True, prune=False, confirm=False)` | Fixes Git-SHA-as-integer-history-ID bug (`N2`) and detects auto-sync blockers |
| `validate_application_config` | `get_application_diff(app_name, revision=None, validate=True)` | N-to-1 consolidation: computes live-vs-target diffs and validates via dry-run in one call |
| `onboard_repository_https` + `onboard_repository_ssh` | `onboard_repository(repo_url, repo_type="git", project=None, ...)` | Infers HTTPS vs. SSH from `repo_url` and resolves credentials from server env vars |
| `generate_application_manifest` + `create_applicationset_manifest` | `skills/deploying-argocd-applications/scripts/generate_argocd_manifests.py` | Pure offline YAML templating moved to deterministic skill script |
| `generate_repository_secret_manifest` | Removed | Security hardening: prevents secret material from entering LLM context (`N8`) |
| 7 `@mcp.prompt()` workflows + `argocd://workflow` | 4 Agent Skills under `skills/` | Progressive disclosure via Agent Skills Open Spec |

</details>

## Development

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/argocd-mcp-server
uv sync --dev
uv run pytest
uv run argocd-mcp-server --help
```

## Get help

- [Documentation](https://talkops.ai/docs/integrations/argocd-mcp-server/overview)
- [Report a bug or request a feature](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=argocd-mcp-server)
- [Join the TalkOps community on Slack](https://talkops.ai/slack/)

## License

Apache 2.0. See [LICENSE](../../LICENSE).
