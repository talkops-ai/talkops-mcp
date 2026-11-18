# Kargo MCP Server

Let your AI assistant operate Kargo multi-stage promotion pipelines: inspect stages and warehouses, verify and approve freight, promote releases across environments, roll back stages, and diagnose failed promotions without exposing secrets.

## Quick Reference

- **Maintained by:** [TalkOps](https://talkops.ai) ([GitHub repository](https://github.com/talkops-ai/talkops-mcp/tree/main/src/kargo-mcp-server))
- **Supported tags:** `latest`, `0.2.1`
- **Architectures:** `linux/amd64`, `linux/arm64`
- **Documentation:** [https://github.com/talkops-ai/talkops-mcp/tree/main/src/kargo-mcp-server](https://github.com/talkops-ai/talkops-mcp/tree/main/src/kargo-mcp-server)
- **PyPI alternative:** [`talkops-kargo-mcp-server`](https://pypi.org/project/talkops-kargo-mcp-server/)
- **License:** [Apache License 2.0](https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE)

## What You Get

- **20 MCP tools** (4 read-only) built for AI agents and MCP clients
- **18 MCP resources** under `kargo://` for structured context discovery
- **5 Agent Skills** bundled in `/app/skills` ([browse on GitHub](https://github.com/talkops-ai/talkops-mcp/tree/main/src/kargo-mcp-server/skills))
- **Container ready:** Runs as a minimal non-root image (`linux/amd64`, `linux/arm64`) talking directly to the Kargo REST API.
- **Safe by default:** starts in read-only mode until you explicitly set `MCP_ALLOW_WRITE=true`.

---

## Quick Start (MCP Client over `stdio`)

Use this configuration in **Claude Desktop**, **Cursor**, **Windsurf**, or **VS Code** (`mcp.json` / `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "kargo": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "MCP_TRANSPORT=stdio",
        "-e",
        "KARGO_BASE_URL",
        "-e",
        "KARGO_AUTH_MODE",
        "-e",
        "KARGO_STATIC_BEARER_TOKEN",
        "talkopsai/kargo-mcp-server:latest"
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

Using **Claude Code**? Register it in one command:

```bash
claude mcp add kargo -e KARGO_BASE_URL=https://kargo.example.com -e KARGO_AUTH_MODE=static -e KARGO_STATIC_BEARER_TOKEN=<your-kargo-token> -- docker run -i --rm -e MCP_TRANSPORT=stdio -e KARGO_BASE_URL -e KARGO_AUTH_MODE -e KARGO_STATIC_BEARER_TOKEN talkopsai/kargo-mcp-server:latest
```

Restart your MCP client and try asking:

- *"Show me the pipeline for the `guestbook` project. What's running in each stage?"*
- *"Promote the latest verified freight to `staging`."*
- *"Why did the last promotion to `prod` fail?"*

---

## Running Standalone (Streamable HTTP)

By default (`MCP_TRANSPORT=http`), the container starts an MCP Streamable HTTP server on port `8766` so multiple clients can share a single instance:

```bash
docker run --rm -p 8766:8766 \
  -e KARGO_BASE_URL=https://kargo.example.com \
  -e KARGO_AUTH_MODE=static \
  -e KARGO_STATIC_BEARER_TOKEN=<your-kargo-token> \
  talkopsai/kargo-mcp-server:latest
```

Point your MCP client at `http://localhost:8766/mcp`:

```json
{
  "mcpServers": {
    "kargo": {
      "url": "http://localhost:8766/mcp"
    }
  }
}
```

---

## Allowing Changes (Write Mode)

Out of the box, the container runs in **read-only mode** (`MCP_ALLOW_WRITE=false`). To allow mutations (creating or updating projects, warehouses, stages, promotions, credentials, and RBAC roles), pass `-e MCP_ALLOW_WRITE=true` to `docker run`. Even with writes enabled, changes support dry-run previews and destructive operations require explicit confirmation.

---

## Environment Variables

| Variable | Container Default | Description |
| :--- | :--- | :--- |
| `KARGO_BASE_URL` | `http://localhost:8080` | Kargo API URL (use `http://host.docker.internal:8080` if port-forwarded locally) |
| `KARGO_AUTH_MODE` | `admin` | Authentication mode: `admin`, `static`, or `passthrough` |
| `KARGO_ADMIN_PASSWORD` | none | Admin password when `KARGO_AUTH_MODE=admin` |
| `KARGO_STATIC_BEARER_TOKEN` | none | Bearer token when `KARGO_AUTH_MODE=static` |
| `KARGO_PROJECT` | none | Default Kargo project name |
| `KARGO_VERIFY_SSL` | `true` | Verify TLS certificates when connecting to Kargo |
| `MCP_ALLOW_WRITE` | `false` | Set to `true` to enable promotions, approvals, and resource mutations |
| `MCP_TOOLSETS` | `all` | Filter tools: `pipeline`, `promotion`, `verification`, `credentials`, `rbac`, `diagnostics`, `readonly` |
| `MCP_TRANSPORT` | `http` | `http` (standalone server) or `stdio` (MCP client subprocess) |
| `MCP_PORT` | `8766` | HTTP listen port inside the container |

---

## Available Tools (20)

| Tool | Access | Description |
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

---

## Bundled Agent Skills (5)

This image also ships step-by-step operational playbooks (`SKILL.md`) under `/app/skills`:

- [`managing-kargo-credentials-and-access`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/kargo-mcp-server/skills/managing-kargo-credentials-and-access/SKILL.md)
- [`onboarding-kargo-pipelines`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/kargo-mcp-server/skills/onboarding-kargo-pipelines/SKILL.md)
- [`promoting-and-approving-freight`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/kargo-mcp-server/skills/promoting-and-approving-freight/SKILL.md)
- [`rolling-back-kargo-stages`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/kargo-mcp-server/skills/rolling-back-kargo-stages/SKILL.md)
- [`troubleshooting-kargo-pipelines`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/kargo-mcp-server/skills/troubleshooting-kargo-pipelines/SKILL.md)

To copy the skills onto your workstation for Claude Code or Cursor:

```bash
docker run --rm --entrypoint tar talkopsai/kargo-mcp-server:latest -C /app/skills -cf - . | tar -xf - -C ~/.claude/skills/
```

---

## Support & Community

- **Source & full docs:** [github.com/talkops-ai/talkops-mcp/tree/main/src/kargo-mcp-server](https://github.com/talkops-ai/talkops-mcp/tree/main/src/kargo-mcp-server)
- **Issues & feature requests:** [GitHub Issues](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=kargo-mcp-server)
- **Community Slack:** [talkops.ai/slack](https://talkops.ai/slack/)
