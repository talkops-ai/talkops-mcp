# ArgoCD MCP Server

Let your AI assistant inspect and operate ArgoCD applications: check sync and health status, preview diffs, run dry-run and live syncs, roll back deployments, and onboard Git/Helm/OCI repositories without exposing credentials to the model.

## Quick Reference

- **Maintained by:** [TalkOps](https://talkops.ai) ([GitHub repository](https://github.com/talkops-ai/talkops-mcp/tree/main/src/argocd-mcp-server))
- **Supported tags:** `latest`, `0.4.1`
- **Architectures:** `linux/amd64`, `linux/arm64`
- **Documentation:** [https://talkops.ai/docs/integrations/argocd-mcp-server/overview](https://talkops.ai/docs/integrations/argocd-mcp-server/overview)
- **PyPI alternative:** [`talkops-argocd-mcp-server`](https://pypi.org/project/talkops-argocd-mcp-server/)
- **License:** [Apache License 2.0](https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE)

## What You Get

- **24 MCP tools** (13 read-only) built for AI agents and MCP clients
- **8 MCP resources** under `argocd://` for structured context discovery
- **4 Agent Skills** bundled in `/app/skills` ([browse on GitHub](https://github.com/talkops-ai/talkops-mcp/tree/main/src/argocd-mcp-server/skills))
- **Container ready:** Runs as a minimal non-root image (`linux/amd64`, `linux/arm64`) talking directly to the ArgoCD API.
- **Safe by default:** starts in read-only mode until you explicitly set `MCP_ALLOW_WRITE=true`.

---

## Quick Start (MCP Client over `stdio`)

Use this configuration in **Claude Desktop**, **Cursor**, **Windsurf**, or **VS Code** (`mcp.json` / `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "argocd": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "MCP_TRANSPORT=stdio",
        "-e",
        "ARGOCD_SERVER_URL",
        "-e",
        "ARGOCD_AUTH_TOKEN",
        "talkopsai/argocd-mcp-server:latest"
      ],
      "env": {
        "ARGOCD_SERVER_URL": "https://argocd.example.com",
        "ARGOCD_AUTH_TOKEN": "<your-argocd-token>"
      }
    }
  }
}
```

Using **Claude Code**? Register it in one command:

```bash
claude mcp add argocd -e ARGOCD_SERVER_URL=https://argocd.example.com -e ARGOCD_AUTH_TOKEN=<your-argocd-token> -- docker run -i --rm -e MCP_TRANSPORT=stdio -e ARGOCD_SERVER_URL -e ARGOCD_AUTH_TOKEN talkopsai/argocd-mcp-server:latest
```

Restart your MCP client and try asking:

- *"Which of my ArgoCD applications are out of sync or degraded?"*
- *"Show me the diff for `payments-api`, then run a dry-run sync."*
- *"Roll `checkout` back to its last healthy deployment."*

---

## Running Standalone (Streamable HTTP)

By default (`MCP_TRANSPORT=http`), the container starts an MCP Streamable HTTP server on port `8770` so multiple clients can share a single instance:

```bash
docker run --rm -p 8770:8770 \
  -e ARGOCD_SERVER_URL=https://argocd.example.com \
  -e ARGOCD_AUTH_TOKEN=<your-argocd-token> \
  talkopsai/argocd-mcp-server:latest
```

Point your MCP client at `http://localhost:8770/mcp`:

```json
{
  "mcpServers": {
    "argocd": {
      "url": "http://localhost:8770/mcp"
    }
  }
}
```

---

## Allowing Changes (Write Mode)

Out of the box, the container runs in **read-only mode** (`MCP_ALLOW_WRITE=false`). To allow mutations (creating, updating, syncing, rolling back, or deleting applications, repositories, and projects), pass `-e MCP_ALLOW_WRITE=true` to `docker run`. Even with writes enabled, changes support dry-run previews and destructive operations require explicit confirmation.

---

## Environment Variables

| Variable | Container Default | Description |
| :--- | :--- | :--- |
| `ARGOCD_SERVER_URL` | `https://argocd-server.argocd.svc:443` | ArgoCD server URL (use `https://host.docker.internal:8080` for local port-forwards) |
| `ARGOCD_AUTH_TOKEN` | *(required)* | ArgoCD API token (`argocd account generate-token`) |
| `ARGOCD_INSECURE` | `false` | Set to `true` only for self-signed ArgoCD TLS certificates |
| `MCP_ALLOW_WRITE` | `false` | Set to `true` to enable sync, rollback, and onboarding tools |
| `MCP_TOOLSETS` | `all` | Filter tools: `applications`, `deployments`, `repositories`, `projects`, `readonly` |
| `GIT_USERNAME` / `GIT_PASSWORD` | none | Server-side HTTPS credentials for onboarding private repos |
| `SSH_PRIVATE_KEY_PATH` | `/app/.ssh/id_rsa` | Mounted SSH private key path for onboarding SSH repos |
| `MCP_TRANSPORT` | `http` | `http` (standalone server) or `stdio` (MCP client subprocess) |
| `MCP_PORT` | `8770` | HTTP listen port inside the container |

---

## Available Tools (24)

| Tool | Access | Description |
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

---

## Bundled Agent Skills (4)

This image also ships step-by-step operational playbooks (`SKILL.md`) under `/app/skills`:

- [`deploying-argocd-applications`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/argocd-mcp-server/skills/deploying-argocd-applications/SKILL.md)
- [`onboarding-argocd-repositories-and-projects`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/argocd-mcp-server/skills/onboarding-argocd-repositories-and-projects/SKILL.md)
- [`rolling-back-argocd-applications`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/argocd-mcp-server/skills/rolling-back-argocd-applications/SKILL.md)
- [`troubleshooting-argocd-applications`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/argocd-mcp-server/skills/troubleshooting-argocd-applications/SKILL.md)

To copy the skills onto your workstation for Claude Code or Cursor:

```bash
docker run --rm --entrypoint tar talkopsai/argocd-mcp-server:latest -C /app/skills -cf - . | tar -xf - -C ~/.claude/skills/
```

---

## Support & Community

- **Source & full docs:** [github.com/talkops-ai/talkops-mcp/tree/main/src/argocd-mcp-server](https://github.com/talkops-ai/talkops-mcp/tree/main/src/argocd-mcp-server)
- **Issues & feature requests:** [GitHub Issues](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=argocd-mcp-server)
- **Community Slack:** [talkops.ai/slack](https://talkops.ai/slack/)
