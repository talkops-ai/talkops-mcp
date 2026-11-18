# Helm MCP Server

Give your AI assistant safe, structured access to Helm v3 and Kubernetes. Search charts, validate values, preview diffs, install or upgrade releases, and roll back broken deployments—with secrets redacted automatically.

## Quick Reference

- **Maintained by:** [TalkOps](https://talkops.ai) ([GitHub repository](https://github.com/talkops-ai/talkops-mcp/tree/main/src/helm-mcp-server))
- **Supported tags:** `latest`, `0.5.1`
- **Architectures:** `linux/amd64`, `linux/arm64`
- **Documentation:** [https://talkops.ai/docs/integrations/helm-mcp-server/overview](https://talkops.ai/docs/integrations/helm-mcp-server/overview)
- **PyPI alternative:** [`talkops-helm-mcp-server`](https://pypi.org/project/talkops-helm-mcp-server/)
- **License:** [Apache License 2.0](https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE)

## What You Get

- **13 MCP tools** (7 read-only) built for AI agents and MCP clients
- **10 MCP resources** under `helm://` for structured context discovery
- **4 Agent Skills** bundled in `/app/skills` ([browse on GitHub](https://github.com/talkops-ai/talkops-mcp/tree/main/src/helm-mcp-server/skills))
- **Container ready:** Includes `helm` v3 and `kubectl` inside a minimal non-root image (`linux/amd64`, `linux/arm64`).
- **Safe by default:** starts in read-only mode until you explicitly set `MCP_ALLOW_WRITE=true`.

---

## Quick Start (MCP Client over `stdio`)

Use this configuration in **Claude Desktop**, **Cursor**, **Windsurf**, or **VS Code** (`mcp.json` / `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "helm": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "MCP_TRANSPORT=stdio",
        "-v",
        "/path/to/your/kubeconfig:/app/.kube/config:ro",
        "talkopsai/helm-mcp-server:latest"
      ]
    }
  }
}
```

Using **Claude Code**? Register it in one command:

```bash
claude mcp add helm -- docker run -i --rm -e MCP_TRANSPORT=stdio -v ~/.kube/config:/app/.kube/config:ro talkopsai/helm-mcp-server:latest
```

> **Tip:** If your kubeconfig references external client certificate files (for example with `minikube` or `kind`), mount the full `~/.kube` directory (`-v /path/to/.kube:/app/.kube:ro`) so those files are reachable inside the container.

Restart your MCP client and try asking:

- *"Install the latest Bitnami PostgreSQL chart into the `database` namespace."*
- *"Show me what would change if I upgrade `my-app` to chart version 2.1.0."*
- *"My `redis` release is failing. What's wrong and how do I roll it back?"*

---

## Running Standalone (Streamable HTTP)

By default (`MCP_TRANSPORT=http`), the container starts an MCP Streamable HTTP server on port `8765` so multiple clients can share a single instance:

```bash
docker run --rm -p 8765:8765 \
  -v ~/.kube/config:/app/.kube/config:ro \
  talkopsai/helm-mcp-server:latest
```

Point your MCP client at `http://localhost:8765/mcp`:

```json
{
  "mcpServers": {
    "helm": {
      "url": "http://localhost:8765/mcp"
    }
  }
}
```

---

## Allowing Changes (Write Mode)

Out of the box, the container runs in **read-only mode** (`MCP_ALLOW_WRITE=false`). To allow mutations (installing, upgrading, rolling back, or uninstalling releases and adding chart repositories), pass `-e MCP_ALLOW_WRITE=true` to `docker run`. Even with writes enabled, changes support dry-run previews and destructive operations require explicit confirmation.

---

## Environment Variables

| Variable | Container Default | Description |
| :--- | :--- | :--- |
| `KUBECONFIG` | `/app/.kube/config` | Path to mounted kubeconfig inside the container |
| `MCP_ALLOW_WRITE` | `false` | Set to `true` to enable install, upgrade, rollback, and uninstall tools |
| `MCP_TOOLSETS` | `all` | Filter tools: `read`, `mutate`, or `all` |
| `HELM_TIMEOUT` | `300` | Timeout in seconds for Helm CLI operations |
| `MCP_TRANSPORT` | `http` | `http` (standalone server) or `stdio` (MCP client subprocess) |
| `MCP_PORT` | `8765` | HTTP listen port inside the container |

---

## Available Tools (13)

| Tool | Access | Description |
| :--- | :--- | :--- |
| `helm_ensure_repository` | Write | Add and index a Helm chart repository if not already configured. |
| `helm_get_release_status` | Read | Get concise current status, revision, resource counts, and resource URIs for a Helm release. |
| `helm_install_chart` | Write (destructive) | Install a new Helm release onto the active Kubernetes cluster context. |
| `helm_list_releases` | Read | List Helm releases in the active cluster with optional namespace/status filtering and pagination. |
| `helm_monitor_deployment` | Read | Evaluate Helm release status, Deployment/StatefulSet rollouts, and container failure states. |
| `helm_plan_release` | Read | Compute a pre-deployment plan for a Helm release (install preview if new; resource/image/replica diff if existing). |
| `helm_render_manifests` | Read | Render Kubernetes manifests from a Helm chart offline with automatic Secret data redaction. |
| `helm_rollback_release` | Write (destructive) | Roll back a Helm release to a previous revision (or simulate with dry_run=True). |
| `helm_search_charts` | Read | Search configured Helm chart repositories by keyword. |
| `helm_uninstall_release` | Write (destructive) | Uninstall a Helm release and delete its managed Kubernetes resources. |
| `helm_upgrade_release` | Write (destructive) | Upgrade an existing Helm release to a new chart version or values configuration. |
| `kubernetes_check_prerequisites` | Read | Verify whether the active cluster meets minimum Kubernetes version and API resource/CRD requirements. |
| `kubernetes_set_context` | Write | Switch the active Kubernetes cluster context for all subsequent Helm and Kubernetes calls in this session. |

---

## Bundled Agent Skills (4)

This image also ships step-by-step operational playbooks (`SKILL.md`) under `/app/skills`:

- [`deploying-helm-charts`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/helm-mcp-server/skills/deploying-helm-charts/SKILL.md)
- [`reviewing-helm-release-security`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/helm-mcp-server/skills/reviewing-helm-release-security/SKILL.md)
- [`troubleshooting-helm-releases`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/helm-mcp-server/skills/troubleshooting-helm-releases/SKILL.md)
- [`upgrading-and-rolling-back-helm-releases`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/helm-mcp-server/skills/upgrading-and-rolling-back-helm-releases/SKILL.md)

To copy the skills onto your workstation for Claude Code or Cursor:

```bash
docker run --rm --entrypoint tar talkopsai/helm-mcp-server:latest -C /app/skills -cf - . | tar -xf - -C ~/.claude/skills/
```

---

## Support & Community

- **Source & full docs:** [github.com/talkops-ai/talkops-mcp/tree/main/src/helm-mcp-server](https://github.com/talkops-ai/talkops-mcp/tree/main/src/helm-mcp-server)
- **Issues & feature requests:** [GitHub Issues](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=helm-mcp-server)
- **Community Slack:** [talkops.ai/slack](https://talkops.ai/slack/)
