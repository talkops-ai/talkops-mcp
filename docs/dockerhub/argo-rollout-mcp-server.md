# Argo Rollouts MCP Server

Let your AI assistant run progressive delivery on Kubernetes with Argo Rollouts: migrate standard Deployments to Rollouts, manage canary and blue-green traffic steps, evaluate Prometheus metrics, and abort or recover degraded releases.

## Quick Reference

- **Maintained by:** [TalkOps](https://talkops.ai) ([GitHub repository](https://github.com/talkops-ai/talkops-mcp/tree/main/src/argo-rollout-mcp-server))
- **Supported tags:** `latest`, `0.2.1`
- **Architectures:** `linux/amd64`, `linux/arm64`
- **Documentation:** [https://talkops.ai/docs/integrations/argo-rollout-mcp-server/overview](https://talkops.ai/docs/integrations/argo-rollout-mcp-server/overview)
- **PyPI alternative:** [`talkops-argo-rollout-mcp-server`](https://pypi.org/project/talkops-argo-rollout-mcp-server/)
- **License:** [Apache License 2.0](https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE)

## What You Get

- **15 MCP tools** (3 read-only) built for AI agents and MCP clients
- **13 MCP resources** under `argorollout://` for structured context discovery
- **4 Agent Skills** bundled in `/app/skills` ([browse on GitHub](https://github.com/talkops-ai/talkops-mcp/tree/main/src/argo-rollout-mcp-server/skills))
- **Container ready:** Includes `kubectl` and `kubectl-argo-rollouts` inside a minimal non-root image (`linux/amd64`, `linux/arm64`).
- **Safe by default:** starts in read-only mode until you explicitly set `MCP_ALLOW_WRITE=true`.

---

## Quick Start (MCP Client over `stdio`)

Use this configuration in **Claude Desktop**, **Cursor**, **Windsurf**, or **VS Code** (`mcp.json` / `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "argo-rollout": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "MCP_TRANSPORT=stdio",
        "-v",
        "/path/to/your/kubeconfig:/app/.kube/config:ro",
        "-e",
        "PROMETHEUS_URL",
        "talkopsai/argo-rollout-mcp-server:latest"
      ],
      "env": {
        "PROMETHEUS_URL": "http://prometheus.monitoring:9090"
      }
    }
  }
}
```

Using **Claude Code**? Register it in one command:

```bash
claude mcp add argo-rollout -e PROMETHEUS_URL=http://prometheus.monitoring:9090 -- docker run -i --rm -e MCP_TRANSPORT=stdio -v ~/.kube/config:/app/.kube/config:ro -e PROMETHEUS_URL talkopsai/argo-rollout-mcp-server:latest
```

> **Tip:** If your kubeconfig references external client certificate files (for example with `minikube` or `kind`), mount the full `~/.kube` directory (`-v /path/to/.kube:/app/.kube:ro`) so those files are reachable inside the container.

Restart your MCP client and try asking:

- *"Is the `checkout` Deployment ready to migrate to an Argo Rollout?"*
- *"Start a canary for `checkout` with image `v2.4.0` and pause at 20%."*
- *"My rollout is stuck in Degraded. What happened?"*

---

## Running Standalone (Streamable HTTP)

By default (`MCP_TRANSPORT=http`), the container starts an MCP Streamable HTTP server on port `8768` so multiple clients can share a single instance:

```bash
docker run --rm -p 8768:8768 \
  -v ~/.kube/config:/app/.kube/config:ro \
  -e PROMETHEUS_URL=http://prometheus.monitoring:9090 \
  talkopsai/argo-rollout-mcp-server:latest
```

Point your MCP client at `http://localhost:8768/mcp`:

```json
{
  "mcpServers": {
    "argo-rollout": {
      "url": "http://localhost:8768/mcp"
    }
  }
}
```

---

## Allowing Changes (Write Mode)

Out of the box, the container runs in **read-only mode** (`MCP_ALLOW_WRITE=false`). To allow mutations (creating, converting, promoting, aborting, or deleting rollouts, analysis templates, and experiments), pass `-e MCP_ALLOW_WRITE=true` to `docker run`. Even with writes enabled, changes support dry-run previews and destructive operations require explicit confirmation.

---

## Environment Variables

| Variable | Container Default | Description |
| :--- | :--- | :--- |
| `K8S_KUBECONFIG` | `/app/.kube/config` | Path to mounted kubeconfig inside the container |
| `K8S_CONTEXT` | current context | Kubernetes context name to target |
| `PROMETHEUS_URL` | `http://prometheus:9090` | Prometheus URL for canary metric checks and analysis |
| `MCP_ALLOW_WRITE` | `false` | Set to `true` to enable rollout mutations and migrations |
| `MCP_TOOLSETS` | `all` | Filter tools: `rollouts`, `migration`, `analysis`, `diagnostics`, `readonly` |
| `MCP_TRANSPORT` | `http` | `http` (standalone server) or `stdio` (MCP client subprocess) |
| `MCP_PORT` | `8768` | HTTP listen port inside the container |

---

## Available Tools (15)

| Tool | Access | Description |
| :--- | :--- | :--- |
| `argo_compare_canary_metrics` | Read | Compare live Prometheus HTTP error rate, latency (P95/P99), and RPS between stable and canary Services. |
| `argo_configure_analysis_template` | Write | Create (or preview) an AnalysisTemplate/ClusterAnalysisTemplate and link it to a Rollout. |
| `argo_configure_rollout_strategy` | Write | Configure or repair Rollout strategy steps, Services, and traffic routing. |
| `argo_convert_deployment_to_rollout` | Write | Convert a live Kubernetes Deployment to an Argo Rollout (<= 8 parameters). |
| `argo_convert_rollout_to_deployment` | Write | Reverse-migrate a live Argo Rollout back to a standard Kubernetes Deployment. |
| `argo_create_experiment` | Write | Create a standalone Argo Experiment for baseline vs. |
| `argo_create_rollout` | Write | Create a new Argo Rollout for progressive delivery (<= 8 parameters). |
| `argo_delete_analysis_template` | Write (destructive) | Permanently delete an AnalysisTemplate or ClusterAnalysisTemplate. |
| `argo_delete_experiment` | Write (destructive) | Permanently delete an Argo Experiment and its ephemeral ReplicaSets. |
| `argo_delete_rollout` | Write (destructive) | Permanently delete an Argo Rollout (blocks if workloadRef Deployment has 0 replicas). |
| `argo_diagnose_rollout` | Read | Collect a single-call diagnostic report with deterministic diagnosis codes for a Rollout. |
| `argo_manage_legacy_deployment` | Write (destructive) | Scale, delete, or configure workloadRef scale-down on a legacy Deployment after Rollout migration. |
| `argo_manage_rollout_lifecycle` | Write (destructive) | Execute a progressive delivery lifecycle action on an active Rollout. |
| `argo_set_rollout_image` | Write | Update the container image on an existing Argo Rollout to trigger a rollout cycle. |
| `argo_validate_deployment_readiness` | Read | Validate whether a live Kubernetes Deployment is ready for Argo Rollouts migration. |

---

## Bundled Agent Skills (4)

This image also ships step-by-step operational playbooks (`SKILL.md`) under `/app/skills`:

- [`gating-rollouts-with-analysis-and-experiments`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/argo-rollout-mcp-server/skills/gating-rollouts-with-analysis-and-experiments/SKILL.md)
- [`onboarding-and-migrating-to-argo-rollouts`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/argo-rollout-mcp-server/skills/onboarding-and-migrating-to-argo-rollouts/SKILL.md)
- [`progressing-argo-rollouts`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/argo-rollout-mcp-server/skills/progressing-argo-rollouts/SKILL.md)
- [`troubleshooting-argo-rollouts`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/argo-rollout-mcp-server/skills/troubleshooting-argo-rollouts/SKILL.md)

To copy the skills onto your workstation for Claude Code or Cursor:

```bash
docker run --rm --entrypoint tar talkopsai/argo-rollout-mcp-server:latest -C /app/skills -cf - . | tar -xf - -C ~/.claude/skills/
```

---

## Support & Community

- **Source & full docs:** [github.com/talkops-ai/talkops-mcp/tree/main/src/argo-rollout-mcp-server](https://github.com/talkops-ai/talkops-mcp/tree/main/src/argo-rollout-mcp-server)
- **Issues & feature requests:** [GitHub Issues](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=argo-rollout-mcp-server)
- **Community Slack:** [talkops.ai/slack](https://talkops.ai/slack/)
