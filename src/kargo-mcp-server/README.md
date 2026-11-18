<p align="center">
  <img src="https://raw.githubusercontent.com/akuity/kargo/main/docs/static/img/kargo.png" alt="Kargo logo" height="100"/>
</p>

<h1 align="center">Kargo MCP Server &amp; Agent Plugin</h1>

<p align="center">
  An Agent Plugin v1.0.0 package that pairs <strong>5 Agent Skills</strong> with a <strong>20-tool, 18-resource execution-only MCP server</strong> for <strong>Kargo v1.10+</strong> (tested against v1.12.5) progressive delivery pipelines.
</p>

<p align="center">
  <a href="https://pypi.org/project/talkops-kargo-mcp-server/"><img src="https://img.shields.io/pypi/v/talkops-kargo-mcp-server.svg?style=flat-square&logo=pypi&logoColor=white&label=PyPI" alt="PyPI"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://kargo.io/"><img src="https://img.shields.io/badge/Kargo-v1.10%2B-3D7EFF.svg?style=flat-square" alt="Kargo v1.10+"/></a>
</p>

---

Let your AI assistant manage Kargo promotion pipelines: see what's deployed where, promote and approve freight, roll back stages, and find out why a promotion failed. Secrets stay on the server.

## What you get

- **20 MCP tools** (4 read-only) that work against your live Kargo setup
- **18 resources** your assistant can read for context, under `kargo://`
- **5 Agent Skills**: step-by-step playbooks that teach your assistant how to use the tools well
- **Safe by default**: only read-only tools are loaded until you turn on writes, and changes are previewed or confirmed before they happen

## Quick start

**You'll need:**

- Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A Kargo API URL and credentials (admin password or a bearer token)

**1. Add the server to your MCP client.** For Claude Desktop, Cursor, Windsurf, and most other clients, add this to your MCP config file:

```json
{
  "mcpServers": {
    "kargo": {
      "command": "uvx",
      "args": [
        "--from",
        "talkops-kargo-mcp-server",
        "kargo-mcp-server"
      ],
      "env": {
        "KARGO_BASE_URL": "https://kargo.example.com",
        "KARGO_AUTH_MODE": "static",
        "KARGO_STATIC_BEARER_TOKEN": "<your-kargo-token>"
      }
    }
  }
}
```

Using Claude Code? Run this instead:

```bash
claude mcp add kargo -e KARGO_BASE_URL=https://kargo.example.com -e KARGO_AUTH_MODE=static -e KARGO_STATIC_BEARER_TOKEN=<your-kargo-token> -- uvx --from talkops-kargo-mcp-server kargo-mcp-server
```

`uvx` downloads [`talkops-kargo-mcp-server`](https://pypi.org/project/talkops-kargo-mcp-server/) from PyPI and runs it, so there's nothing else to install. Prefer a normal install? Run `pip install talkops-kargo-mcp-server` and use `kargo-mcp-server` as the command.

**2. Restart your client and try asking:**

- *"Show me the pipeline for the `guestbook` project. What's running in each stage?"*
- *"Promote the latest freight to `staging`."*
- *"Why did the last promotion to `prod` fail?"*

## Allowing changes

Out of the box the server is read-only. To let your assistant make changes (creating and changing projects, warehouses, stages, promotions, credentials, and roles), add `"--allow-write"` to `args` (or set `MCP_ALLOW_WRITE=true`). Even then, changes are previewed first and destructive actions ask for confirmation.

## Configuration

Set these as environment variables (the `env` block in your client config) or pass the matching flag.

| Variable | Flag | Default | What it does |
| :--- | :--- | :--- | :--- |
| `KARGO_BASE_URL` | `--kargo-url` | `http://localhost:8080` | Your Kargo API URL |
| `KARGO_AUTH_MODE` | `--auth-mode` | `admin` | `admin`, `static`, or `passthrough` |
| `KARGO_ADMIN_PASSWORD` | — | none | Password when using `admin` mode |
| `KARGO_STATIC_BEARER_TOKEN` | — | none | Token when using `static` mode |
| `KARGO_PROJECT` | `--project` | none | Default project |
| `KARGO_VERIFY_SSL` | `--insecure-skip-tls-verify` | `true` | Verify the Kargo TLS certificate |
| `MCP_ALLOW_WRITE` | `--allow-write` | `false` | Enable tools that change Kargo |
| `MCP_TOOLSETS` | `--toolsets` | `all` | Limit tools: `pipeline`, `promotion`, `verification`, `credentials`, `rbac`, `diagnostics`, `readonly` |
| `MCP_TRANSPORT` | `--transport` | `stdio` | `stdio` or `http` |
| `MCP_PORT` | `--port` | `8766` | Port when using HTTP |

Run `uvx --from talkops-kargo-mcp-server kargo-mcp-server --help` to see every option.

### Running over HTTP

To share one server between several clients or run it remotely, start it in HTTP mode:

```bash
MCP_TRANSPORT=http MCP_PORT=8766 uvx --from talkops-kargo-mcp-server kargo-mcp-server
```

Then point your client at `http://localhost:8766/mcp`:

```json
{
  "mcpServers": {
    "kargo": {
      "url": "http://localhost:8766/mcp"
    }
  }
}
```

## Agent Skills

Skills live in [`skills/`](skills/). Each one is a `SKILL.md` playbook (plus optional `references/` and offline `scripts/`) that teaches your AI assistant *how* to do a job safely, while the MCP server does the actual work. Tools are the hands, skills are the know-how.

To use them, copy the folders into your assistant's skills directory, for example:

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cp -r talkops-mcp/src/kargo-mcp-server/skills/* ~/.claude/skills/
```

This folder is also a portable [Agent Plugin](https://agent-plugins.org) (`plugin.json` + `mcp.json` + `skills/`), so plugin-aware clients can load the server and skills together.

| Skill | Use it to |
| :--- | :--- |
| [`onboarding-kargo-pipelines`](skills/onboarding-kargo-pipelines/SKILL.md) | Set up projects, warehouses, stages, and promotion steps. |
| [`promoting-and-approving-freight`](skills/promoting-and-approving-freight/SKILL.md) | Check which freight can move forward, approve it, and promote it. |
| [`rolling-back-kargo-stages`](skills/rolling-back-kargo-stages/SKILL.md) | Roll a stage back to its last good freight in an emergency. |
| [`troubleshooting-kargo-pipelines`](skills/troubleshooting-kargo-pipelines/SKILL.md) | Find out why a warehouse, promotion, or verification failed. |
| [`managing-kargo-credentials-and-access`](skills/managing-kargo-credentials-and-access/SKILL.md) | Manage repository credentials and roles without exposing secrets. |

## Reference

<details>
<summary><strong>All 20 tools</strong></summary>

| Tool | Access | What it does |
| :--- | :--- | :--- |
| `kargo_apply_analysis_template` | Write | Create or update an Argo Rollouts AnalysisTemplate or ClusterAnalysisTemplate for Kargo Stage verification. |
| `kargo_apply_project_config` | Write | Configure a Kargo ProjectConfig CRD (auto-promotion policies, webhook receivers, and UI links). |
| `kargo_apply_promotion_task` | Write | Create or update a reusable Kargo PromotionTask or ClusterPromotionTask. |
| `kargo_apply_stage` | Write | Create or update a Kargo Stage, merging updates with existing Stage spec and validating DAG cycles. |
| `kargo_apply_warehouse` | Write | Create or update a Kargo Warehouse with Git, Image, or Helm Chart subscriptions. |
| `kargo_approve_freight` | Write (destructive) | Manually approve a Freight bundle (by SHA-1 name or alias) for promotion to a target Stage. |
| `kargo_delete_resource` | Write (destructive) | Delete a Kargo Stage, Warehouse, PromotionTask, ClusterPromotionTask, or ProjectConfig after confirmation. |
| `kargo_diagnose_stage` | Read | Diagnose a Kargo Stage by correlating conditions, Promotion step traces, Verification AnalysisRuns, holds, and events (N-to-1). |
| `kargo_diagnose_warehouse` | Read | Diagnose a Kargo Warehouse by inspecting artifact discovery status, conditions, and deprecated Kargo v1.9–v1.12 fields (N-to-1). |
| `kargo_manage_credentials` | Write (destructive) | Create, update, or delete Kargo repository credentials, generic secrets, or ConfigMaps without exposing secret values. |
| `kargo_manage_freight` | Write (destructive) | Update a Freight human-friendly alias, manually assemble a Freight item, or delete unused Freight. |
| `kargo_manage_project` | Write (destructive) | Create or delete a Kargo Project (cluster-scoped organizational boundary). |
| `kargo_manage_promotion` | Write (destructive) | Abort a running/pending Kargo Promotion or refresh (wake) a waiting Promotion. |
| `kargo_manage_roles` | Write (destructive) | Create or delete a managed Kargo Role, or grant/revoke OIDC user claims and stage permissions. |
| `kargo_manage_verification` | Write (destructive) | Re-run (reverify) or abort a Stage's verification AnalysisRun, or delete an AnalysisTemplate. |
| `kargo_promote` | Write | Promote Freight to a Stage (by SHA-1 name, alias, or origin Warehouse) or to all immediate downstream Stages. |
| `kargo_query_freight` | Read | Query and filter Kargo Freight bundles in a project by stage availability, origin Warehouse, or alias. |
| `kargo_refresh` | Write | Trigger immediate reconciliation or artifact discovery on a Warehouse, Stage, Promotion, ProjectConfig, or ClusterConfig. |
| `kargo_rollback_stage` | Write (destructive) | Roll back a Kargo Stage to a previous known-good Freight using Kargo's roll-forward promotion model (N-to-1). |
| `kargo_trace_freight` | Read | Trace a Freight bundle or versioned artifact across all Stages in a Kargo project (N-to-1). |

</details>

<details>
<summary><strong>All 18 resources</strong></summary>

| Resource | What it returns |
| :--- | :--- |
| `kargo://projects` | List all Kargo Projects with readiness status |
| `kargo://server/capabilities` | Server write mode, enabled toolsets, Kargo API connectivity, and Kargo version |
| `kargo://cluster-promotion-tasks/{task}` | Sanitized YAML manifest for a cluster-scoped ClusterPromotionTask |
| `kargo://projects/{project}` | Project status and ProjectConfig (promotionPolicies, webhookReceivers, generated webhook URLs) |
| `kargo://projects/{project}/analysis-runs/{run}` | Verification AnalysisRun status and metric results |
| `kargo://projects/{project}/analysis-runs/{run}/logs` | Job-metric container logs for a verification AnalysisRun |
| `kargo://projects/{project}/analysis-templates` | Project AnalysisTemplates and cluster-scoped ClusterAnalysisTemplates available for Stage verification |
| `kargo://projects/{project}/credentials` | Redacted repository credentials, generic credentials, and ConfigMaps in a Kargo project (secret values are never exposed) |
| `kargo://projects/{project}/events` | Recent Kubernetes Events in a Kargo project |
| `kargo://projects/{project}/freight/{freight_or_alias}` | Detailed Freight bundle (SHA-1 id, alias, origin Warehouse, commits, images, charts, stage states) |
| `kargo://projects/{project}/pipeline` | Complete pipeline DAG topology (Warehouses -> Stages), current Freight, health, auto-promotion, and holds |
| `kargo://projects/{project}/promotion-tasks/{task}` | Sanitized YAML manifest for a project PromotionTask |
| `kargo://projects/{project}/promotions` | Recent Promotions in a Kargo project with phase and timestamps |
| `kargo://projects/{project}/promotions/{promotion}` | Detailed Promotion execution trace (phase, message, per-step status, timings, outputs) |
| `kargo://projects/{project}/roles` | Kargo RBAC Roles, OIDC claim bindings, and permissions in a project |
| `kargo://projects/{project}/stages/{stage}` | Concise Stage status (phase, health, currentFreight, verification, promotions, holds, conditions) |
| `kargo://projects/{project}/stages/{stage}/manifest` | Sanitized YAML manifest for a Kargo Stage (strips managedFields and redacts literal env secrets) |
| `kargo://projects/{project}/warehouses/{warehouse}` | Concise Warehouse status, subscriptions, lastFreightID, and discoveredArtifacts |

</details>

## Development

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/kargo-mcp-server
uv sync --dev
uv run pytest
uv run kargo-mcp-server --help
```

## Get help

- [Documentation](https://talkops.ai/docs/integrations/kargo-mcp-server/overview)
- [Report a bug or request a feature](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=kargo-mcp-server)
- [Join the TalkOps community on Slack](https://talkops.ai/slack/)

## License

Apache 2.0. See [LICENSE](../../LICENSE).
