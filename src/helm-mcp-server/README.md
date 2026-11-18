<p align="center">
  <img src="https://raw.githubusercontent.com/cncf/artwork/main/projects/helm/icon/color/helm-icon-color.svg" alt="Helm logo" height="100"/>
</p>

<h1 align="center">Helm MCP Server &amp; Agent Plugin</h1>

<p align="center">
  A production-grade Model Context Protocol (MCP) execution server and portable Agent Plugin for managing Kubernetes workloads with Helm.
</p>

<p align="center">
  <a href="https://pypi.org/project/talkops-helm-mcp-server/"><img src="https://img.shields.io/pypi/v/talkops-helm-mcp-server.svg?style=flat-square&logo=pypi&logoColor=white&label=PyPI" alt="PyPI"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://helm.sh/"><img src="https://img.shields.io/badge/Helm-v3.x-0F1689.svg?style=flat-square&logo=helm&logoColor=white" alt="Helm v3"/></a>
</p>

Built on the **Two-Layer Separation Principle**:
- **Skill Layer (`skills/` + `plugin.json`):** Procedural runbooks, values-authoring standards, error-recovery decision trees, security review checklists, and zero-network local Python validation scripts (`SKILL.md` progressive disclosure).
- **Execution Layer (`helm_mcp_server/`):** Deterministic, context-isolated, secret-redacted Helm CLI and Kubernetes API execution primitives (13 Tools, 10 URI-addressed Resources, 0 Prompts).

---

Let your AI assistant find, install, upgrade, and roll back Helm charts on your Kubernetes clusters. It plans every change before applying it and hides secrets from the output.

## What you get

- **13 MCP tools** (7 read-only) that work against your live Helm setup
- **10 resources** your assistant can read for context, under `helm://`
- **4 Agent Skills**: step-by-step playbooks that teach your assistant how to use the tools well
- **Safe by default**: only read-only tools are loaded until you turn on writes, and changes are previewed or confirmed before they happen

## Quick start

**You'll need:**

- Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Access to a Kubernetes cluster through a kubeconfig file
- The `helm` CLI installed and on your `PATH`

**1. Add the server to your MCP client.** For Claude Desktop, Cursor, Windsurf, and most other clients, add this to your MCP config file:

```json
{
  "mcpServers": {
    "helm": {
      "command": "uvx",
      "args": [
        "--from",
        "talkops-helm-mcp-server",
        "helm-mcp-server"
      ],
      "env": {
        "KUBECONFIG": "/path/to/your/kubeconfig"
      }
    }
  }
}
```

Using Claude Code? Run this instead:

```bash
claude mcp add helm -e KUBECONFIG=/path/to/your/kubeconfig -- uvx --from talkops-helm-mcp-server helm-mcp-server
```

`uvx` downloads [`talkops-helm-mcp-server`](https://pypi.org/project/talkops-helm-mcp-server/) from PyPI and runs it, so there's nothing else to install. Prefer a normal install? Run `pip install talkops-helm-mcp-server` and use `helm-mcp-server` as the command.

**2. Restart your client and try asking:**

- *"Install the latest Bitnami PostgreSQL chart into the `database` namespace."*
- *"Show me what would change if I upgrade `my-app` to chart version 2.1.0."*
- *"My `redis` release is failing. What's wrong and how do I roll it back?"*

## Allowing changes

Out of the box the server is read-only. To let your assistant make changes (installs, upgrades, rollbacks, uninstalls, and adding chart repositories), add `"--allow-write"` to `args` (or set `MCP_ALLOW_WRITE=true`). Even then, changes are previewed first and destructive actions ask for confirmation.

## Configuration

Set these as environment variables (the `env` block in your client config) or pass the matching flag.

| Variable | Flag | Default | What it does |
| :--- | :--- | :--- | :--- |
| `KUBECONFIG` | — | `~/.kube/config` | Kubeconfig file to use |
| `MCP_ALLOW_WRITE` | `--allow-write` | `false` | Enable tools that change your cluster |
| `MCP_TOOLSETS` | `--toolsets` | `all` | Limit tools: `read`, `mutate`, or `all` |
| `HELM_TIMEOUT` | — | `300` | Seconds to wait for a Helm command |
| `MCP_TRANSPORT` | `--transport` | `stdio` | `stdio` or `http` |
| `MCP_PORT` | `--port` | `8765` | Port when using HTTP |

Run `uvx --from talkops-helm-mcp-server helm-mcp-server --help` to see every option.

### Running over HTTP

To share one server between several clients or run it remotely, start it in HTTP mode:

```bash
MCP_TRANSPORT=http MCP_PORT=8765 uvx --from talkops-helm-mcp-server helm-mcp-server
```

Then point your client at `http://localhost:8765/mcp`:

```json
{
  "mcpServers": {
    "helm": {
      "url": "http://localhost:8765/mcp"
    }
  }
}
```

## Agent Skills

Skills live in [`skills/`](skills/). Each one is a `SKILL.md` playbook (plus optional `references/` and offline `scripts/`) that teaches your AI assistant *how* to do a job safely, while the MCP server does the actual work. Tools are the hands, skills are the know-how.

To use them, copy the folders into your assistant's skills directory, for example:

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cp -r talkops-mcp/src/helm-mcp-server/skills/* ~/.claude/skills/
```

This folder is also a portable [Agent Plugin](https://agent-plugins.org) (`plugin.json` + `mcp.json` + `skills/`), so plugin-aware clients can load the server and skills together.

| Skill | Use it to |
| :--- | :--- |
| [`deploying-helm-charts`](skills/deploying-helm-charts/SKILL.md) | Find a chart, check your values, preview, install, and watch the rollout. |
| [`upgrading-and-rolling-back-helm-releases`](skills/upgrading-and-rolling-back-helm-releases/SKILL.md) | Diff an upgrade before you run it, and roll back safely when needed. |
| [`troubleshooting-helm-releases`](skills/troubleshooting-helm-releases/SKILL.md) | Work out why a release or its pods are failing (CrashLoopBackOff, image pulls, OOM, and more). |
| [`reviewing-helm-release-security`](skills/reviewing-helm-release-security/SKILL.md) | Check rendered manifests for risky settings like privileged containers or `latest` tags. |

## Reference

<details>
<summary><strong>All 13 tools</strong></summary>

| Tool | Access | What it does |
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

</details>

<details>
<summary><strong>All 10 resources</strong></summary>

| Resource | What it returns |
| :--- | :--- |
| `helm://repositories` | List all configured Helm chart repositories. |
| `kubernetes://cluster-info` | Get Kubernetes cluster version, node summary, namespace summary, and active context. |
| `kubernetes://contexts` | List all available Kubernetes contexts from kubeconfig and the active session context. |
| `kubernetes://namespaces` | List all Kubernetes namespace names in the active cluster. |
| `helm://charts/{repository}/{chart_name}` | Get Chart.yaml metadata and sub-chart dependencies for a specific chart. |
| `helm://charts/{repository}/{chart_name}/readme` | Get the README documentation for a specific Helm chart. |
| `helm://charts/{repository}/{chart_name}/values` | Get default values.yaml structure for a specific Helm chart. |
| `helm://releases/{namespace}/{release_name}/history` | Get revision history for a deployed Helm release in a namespace. |
| `helm://releases/{namespace}/{release_name}/manifest` | Get secret-redacted Kubernetes YAML manifest for a deployed Helm release. |
| `helm://releases/{namespace}/{release_name}/values` | Get secret-redacted user override values for a deployed Helm release. |

</details>

## Development

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/helm-mcp-server
uv sync --dev
uv run pytest
uv run helm-mcp-server --help
```

## Get help

- [Documentation](https://talkops.ai/docs/integrations/helm-mcp-server/overview)
- [Report a bug or request a feature](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=helm-mcp-server)
- [Join the TalkOps community on Slack](https://talkops.ai/slack/)

## License

Apache 2.0. See [LICENSE](../../LICENSE).
