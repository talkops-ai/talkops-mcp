<p align="center">
  <img src="https://raw.githubusercontent.com/cncf/artwork/main/projects/argo/icon/color/argo-icon-color.svg" alt="Argo Rollouts logo" height="100"/>
</p>

<h1 align="center">Argo Rollout MCP Server &amp; Agent Plugin</h1>

<p align="center">
  An Agent Plugin (v1.0.0) and FastMCP Execution Server for Kubernetes Progressive Delivery with Argo Rollouts — separating reasoning workflows (<code>SKILL.md</code>) from live cluster execution (MCP Tools & Resources).
</p>

<p align="center">
  <a href="https://pypi.org/project/talkops-argo-rollout-mcp-server/"><img src="https://img.shields.io/pypi/v/talkops-argo-rollout-mcp-server.svg?style=flat-square&logo=pypi&logoColor=white&label=PyPI" alt="PyPI"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://argoproj.github.io/argo-rollouts/"><img src="https://img.shields.io/badge/Argo%20Rollouts-v1.6%2B-EF7B4D.svg?style=flat-square&logo=argo&logoColor=white" alt="Argo Rollouts v1.6+"/></a>
</p>

---

Let your AI assistant run progressive delivery with Argo Rollouts: move Deployments to Rollouts, run canary and blue-green releases, gate them on Prometheus metrics, and recover when something goes wrong.

## What you get

- **15 MCP tools** (3 read-only) that work against your live Argo Rollouts setup
- **13 resources** your assistant can read for context, under `argorollout://`
- **4 Agent Skills**: step-by-step playbooks that teach your assistant how to use the tools well
- **Safe by default**: only read-only tools are loaded until you turn on writes, and changes are previewed or confirmed before they happen

## Quick start

**You'll need:**

- Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Access to a Kubernetes cluster with Argo Rollouts installed
- Optional: a Prometheus URL for metric comparisons and analysis

**1. Add the server to your MCP client.** For Claude Desktop, Cursor, Windsurf, and most other clients, add this to your MCP config file:

```json
{
  "mcpServers": {
    "argo-rollout": {
      "command": "uvx",
      "args": [
        "--from",
        "talkops-argo-rollout-mcp-server",
        "argo-rollout-mcp-server"
      ],
      "env": {
        "KUBECONFIG": "/path/to/your/kubeconfig",
        "PROMETHEUS_URL": "http://prometheus.monitoring:9090"
      }
    }
  }
}
```

Using Claude Code? Run this instead:

```bash
claude mcp add argo-rollout -e KUBECONFIG=/path/to/your/kubeconfig -e PROMETHEUS_URL=http://prometheus.monitoring:9090 -- uvx --from talkops-argo-rollout-mcp-server argo-rollout-mcp-server
```

`uvx` downloads [`talkops-argo-rollout-mcp-server`](https://pypi.org/project/talkops-argo-rollout-mcp-server/) from PyPI and runs it, so there's nothing else to install. Prefer a normal install? Run `pip install talkops-argo-rollout-mcp-server` and use `argo-rollout-mcp-server` as the command.

**2. Restart your client and try asking:**

- *"Is the `checkout` Deployment ready to migrate to an Argo Rollout?"*
- *"Start a canary for `checkout` with image `v2.4.0` and pause at 20%."*
- *"My rollout is stuck in Degraded. What happened?"*

## Allowing changes

Out of the box the server is read-only. To let your assistant make changes (creating, converting, promoting, aborting, and deleting rollouts, analysis templates, and experiments), add `"--allow-write"` to `args` (or set `MCP_ALLOW_WRITE=true`). Even then, changes are previewed first and destructive actions ask for confirmation.

## Configuration

Set these as environment variables (the `env` block in your client config) or pass the matching flag.

| Variable | Flag | Default | What it does |
| :--- | :--- | :--- | :--- |
| `K8S_KUBECONFIG` / `KUBECONFIG` | `--kubeconfig` | `~/.kube/config` | Kubeconfig file to use |
| `K8S_CONTEXT` | `--context` | current context | Kubernetes context to use |
| `PROMETHEUS_URL` | `--prometheus-url` | `http://prometheus:9090` | Prometheus for metric checks |
| `MCP_ALLOW_WRITE` | `--allow-write` | `false` | Enable tools that change your cluster |
| `MCP_TOOLSETS` | `--toolsets` | `all` | Limit tools: `rollouts`, `migration`, `analysis`, `diagnostics`, `readonly` |
| `MCP_TRANSPORT` | `--transport` | `stdio` | `stdio` or `http` |
| `MCP_PORT` | `--port` | `8768` | Port when using HTTP |

Run `uvx --from talkops-argo-rollout-mcp-server argo-rollout-mcp-server --help` to see every option.

### Running over HTTP

To share one server between several clients or run it remotely, start it in HTTP mode:

```bash
MCP_TRANSPORT=http MCP_PORT=8768 uvx --from talkops-argo-rollout-mcp-server argo-rollout-mcp-server
```

Then point your client at `http://localhost:8768/mcp`:

```json
{
  "mcpServers": {
    "argo-rollout": {
      "url": "http://localhost:8768/mcp"
    }
  }
}
```

## Agent Skills

Skills live in [`skills/`](skills/). Each one is a `SKILL.md` playbook (plus optional `references/` and offline `scripts/`) that teaches your AI assistant *how* to do a job safely, while the MCP server does the actual work. Tools are the hands, skills are the know-how.

To use them, copy the folders into your assistant's skills directory, for example:

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cp -r talkops-mcp/src/argo-rollout-mcp-server/skills/* ~/.claude/skills/
```

This folder is also a portable [Agent Plugin](https://agent-plugins.org) (`plugin.json` + `mcp.json` + `skills/`), so plugin-aware clients can load the server and skills together.

| Skill | Use it to |
| :--- | :--- |
| [`onboarding-and-migrating-to-argo-rollouts`](skills/onboarding-and-migrating-to-argo-rollouts/SKILL.md) | Check a Deployment and move it to a Rollout, including zero-downtime migrations. |
| [`progressing-argo-rollouts`](skills/progressing-argo-rollouts/SKILL.md) | Run canary, blue-green, and multi-cluster rollouts step by step. |
| [`gating-rollouts-with-analysis-and-experiments`](skills/gating-rollouts-with-analysis-and-experiments/SKILL.md) | Use Prometheus analysis and experiments to decide whether a rollout continues. |
| [`troubleshooting-argo-rollouts`](skills/troubleshooting-argo-rollouts/SKILL.md) | Diagnose degraded, paused, or aborted rollouts and fix them. |

## Reference

<details>
<summary><strong>All 15 tools</strong></summary>

| Tool | Access | What it does |
| :--- | :--- | :--- |
| `argo_compare_canary_metrics` | Read | Compare live Prometheus HTTP error rate, latency (P95/P99), and RPS between stable and canary Services. |
| `argo_configure_analysis_template` | Write | Create (or preview) an AnalysisTemplate/ClusterAnalysisTemplate and link it to a Rollout. |
| `argo_configure_rollout_strategy` | Write | Configure or repair Rollout strategy steps, Services, and traffic routing. |
| `argo_convert_deployment_to_rollout` | Write | Convert a live Kubernetes Deployment to an Argo Rollout (<= 8 parameters). |
| `argo_convert_rollout_to_deployment` | Write | Reverse-migrate a live Argo Rollout back to a standard Kubernetes Deployment. |
| `argo_create_experiment` | Write | Create a standalone Argo Experiment for baseline vs. canary comparison. |
| `argo_create_rollout` | Write | Create a new Argo Rollout for progressive delivery (<= 8 parameters). |
| `argo_delete_analysis_template` | Write (destructive) | Permanently delete an AnalysisTemplate or ClusterAnalysisTemplate. |
| `argo_delete_experiment` | Write (destructive) | Permanently delete an Argo Experiment and its ephemeral ReplicaSets. |
| `argo_delete_rollout` | Write (destructive) | Permanently delete an Argo Rollout (blocks if workloadRef Deployment has 0 replicas). |
| `argo_diagnose_rollout` | Read | Collect a single-call diagnostic report with deterministic diagnosis codes for a Rollout. |
| `argo_manage_legacy_deployment` | Write (destructive) | Scale, delete, or configure workloadRef scale-down on a legacy Deployment after Rollout migration. |
| `argo_manage_rollout_lifecycle` | Write (destructive) | Execute a progressive delivery lifecycle action on an active Rollout. |
| `argo_set_rollout_image` | Write | Update the container image on an existing Argo Rollout to trigger a rollout cycle. |
| `argo_validate_deployment_readiness` | Read | Validate whether a live Kubernetes Deployment is ready for Argo Rollouts migration. |

</details>

<details>
<summary><strong>All 13 resources</strong></summary>

| Resource | What it returns |
| :--- | :--- |
| `argorollout://cluster/contexts` | Get active and available kubeconfig contexts (no credentials). |
| `argorollout://cluster/health` | Get overall cluster node readiness and capacity. |
| `argorollout://cluster/namespaces` | Get list of namespaces in the cluster. |
| `argorollout://metrics/prometheus/status` | Get Prometheus connectivity status. |
| `argorollout://rollouts/list` | List all rollouts across namespaces with health scores. |
| `argorollout://server/capabilities` | Get server capabilities, write mode, enabled toolsets, and CRD availability. |
| `argorollout://analysistemplates/{namespace}` | List namespace AnalysisTemplates and ClusterAnalysisTemplates. |
| `argorollout://experiments/{namespace}/{name}/status` | Get Argo Experiment status. |
| `argorollout://history/{namespace}/{deployment}` | Get ReplicaSet revision history and status conditions for a Rollout. |
| `argorollout://metrics/{namespace}/{service}/summary` | Get real Prometheus metrics for a service, or explicit unavailable status (fixes B9 & B12). |
| `argorollout://rollouts/{namespace}/{name}/analysisruns` | Get the 5 most recent AnalysisRuns for a Rollout. |
| `argorollout://rollouts/{namespace}/{name}/detail` | Get concise Rollout status (phase, step, weights, hashes, healthScore, conditions) without YAML bloat. |
| `argorollout://rollouts/{namespace}/{name}/manifest` | Get sanitized YAML manifest for a Rollout (strips managedFields and redacts literal env values). |

</details>

## Development

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/argo-rollout-mcp-server
uv sync --dev
uv run pytest
uv run argo-rollout-mcp-server --help
```

## Get help

- [Documentation](https://talkops.ai/docs/integrations/argo-rollout-mcp-server/overview)
- [Report a bug or request a feature](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=argo-rollout-mcp-server)
- [Join the TalkOps community on Slack](https://talkops.ai/slack/)

## License

Apache 2.0. See [LICENSE](../../LICENSE).
