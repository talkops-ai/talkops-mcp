# Alertmanager MCP Server

Let your AI assistant triage firing alerts, explain why notifications were inhibited or muted, preview and create bounded maintenance silences, test routing trees, and audit alert label hygiene.

## Quick Reference

- **Maintained by:** [TalkOps](https://talkops.ai) ([GitHub repository](https://github.com/talkops-ai/talkops-mcp/tree/main/src/alertmanager-mcp-server))
- **Supported tags:** `latest`, `0.2.1`
- **Architectures:** `linux/amd64`, `linux/arm64`
- **Documentation:** [https://talkops.ai/docs/integrations/alertmanager-mcp-server/overview](https://talkops.ai/docs/integrations/alertmanager-mcp-server/overview)
- **PyPI alternative:** [`talkops-alertmanager-mcp-server`](https://pypi.org/project/talkops-alertmanager-mcp-server/)
- **License:** [Apache License 2.0](https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE)

## What You Get

- **14 MCP tools** (9 read-only) built for AI agents and MCP clients
- **10 MCP resources** under `am://` for structured context discovery
- **5 Agent Skills** bundled in `/app/skills` ([browse on GitHub](https://github.com/talkops-ai/talkops-mcp/tree/main/src/alertmanager-mcp-server/skills))
- **Container ready:** Runs as a minimal non-root image (`linux/amd64`, `linux/arm64`) talking directly to Alertmanager API v2.
- **Safe by default:** starts in read-only mode until you explicitly set `MCP_ALLOW_WRITE=true`.

---

## Quick Start (MCP Client over `stdio`)

Use this configuration in **Claude Desktop**, **Cursor**, **Windsurf**, or **VS Code** (`mcp.json` / `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "alertmanager": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "MCP_TRANSPORT=stdio",
        "-e",
        "ALERTMANAGER_BASE_URL",
        "talkopsai/alertmanager-mcp-server:latest"
      ],
      "env": {
        "ALERTMANAGER_BASE_URL": "http://host.docker.internal:9093"
      }
    }
  }
}
```

Using **Claude Code**? Register it in one command:

```bash
claude mcp add alertmanager -e ALERTMANAGER_BASE_URL=http://host.docker.internal:9093 -- docker run -i --rm -e MCP_TRANSPORT=stdio -e ALERTMANAGER_BASE_URL talkopsai/alertmanager-mcp-server:latest
```

Restart your MCP client and try asking:

- *"Summarize what's firing for the `payments` team right now."*
- *"Why didn't the `HighErrorRate` alert page anyone?"*
- *"Silence `checkout` alerts in `prod` for a 2-hour maintenance window. Show me what it would match first."*

---

## Running Standalone (Streamable HTTP)

By default (`MCP_TRANSPORT=http`), the container starts an MCP Streamable HTTP server on port `8769` so multiple clients can share a single instance:

```bash
docker run --rm -p 8769:8769 \
  -e ALERTMANAGER_BASE_URL=http://host.docker.internal:9093 \
  talkopsai/alertmanager-mcp-server:latest
```

Point your MCP client at `http://localhost:8769/mcp`:

```json
{
  "mcpServers": {
    "alertmanager": {
      "url": "http://localhost:8769/mcp"
    }
  }
}
```

---

## Allowing Changes (Write Mode)

Out of the box, the container runs in **read-only mode** (`MCP_ALLOW_WRITE=false`). To allow mutations (creating, updating, or expiring silences and sending synthetic test alerts), pass `-e MCP_ALLOW_WRITE=true` to `docker run`. Even with writes enabled, changes support dry-run previews and destructive operations require explicit confirmation.

---

## Environment Variables

| Variable | Container Default | Description |
| :--- | :--- | :--- |
| `ALERTMANAGER_BASE_URL` | `http://localhost:9093` | Alertmanager URL (use `http://host.docker.internal:9093` for a host instance) |
| `ALERTMANAGER_AUTH_HEADER` | none | Optional `Authorization` header, e.g. `Bearer <token>` |
| `ALERTMANAGER_BACKENDS` | none | JSON list of multiple Alertmanager instances |
| `MCP_ALLOW_WRITE` | `false` | Set to `true` to enable silence management and test-alert tools |
| `MCP_TOOLSETS` | `all` | Filter tools: `triage`, `routing`, `silences`, `governance` |
| `AM_MAX_SILENCE_MINUTES` | `1440` | Maximum allowed silence duration in minutes |
| `AM_SILENCE_CONFIRM_THRESHOLD` | `50` | Require confirmation if a silence matches more alerts than this |
| `MCP_TRANSPORT` | `http` | `http` (standalone server) or `stdio` (MCP client subprocess) |
| `MCP_PORT` | `8769` | HTTP listen port inside the container |

---

## Available Tools (14)

| Tool | Access | Description |
| :--- | :--- | :--- |
| `am_audit_alert_hygiene` | Read | Audit active alerts for default-route leakage, missing runbook/summary annotations, invalid severity values, chronic long-firing alerts, and Watchdog heartbeat presence. |
| `am_audit_silences` | Read | Audit silence change history, active silence policy compliance (`SP001`–`SP009`), stale 0-match silences, and silences expiring soon. |
| `am_check_notification_health` | Read | Inspect Alertmanager readiness, config reload status, cluster peers, and `/metrics` receiver delivery failure counters. |
| `am_create_silence` | Write | Create an Alertmanager silence after enforcing `SilencePolicy` (`SP001`–`SP010`), deduplication, and blast-radius confirmation. |
| `am_expire_silence` | Write (destructive) | Expire an active silence after previewing how many suppressed alerts will immediately resume paging. |
| `am_explain_routing` | Read | Simulate Alertmanager's nested routing tree (`continue`, inherited `group_by`/timers, `mute_time_intervals`) and live inhibition rules. |
| `am_list_alert_groups` | Read | List Alertmanager dispatch groups grouped by route `group_by` labels. |
| `am_list_alerts` | Read | Query alerts from Alertmanager with full matcher grammar and state filtering. |
| `am_list_silences` | Read | List silences with state, matcher, author, and comment filtering. |
| `am_preview_silence` | Read | Dry-run a silence against active alerts, routing receivers, overlapping silences, and `SilencePolicy` (`SP001`–`SP010`). |
| `am_push_test_alert` | Write | Push a time-bounded synthetic test alert to Alertmanager to verify end-to-end receiver delivery. |
| `am_silence_alert` | Write | Derive scoped matchers (`instance` or `service`) from a firing alert and create a policy-validated silence. |
| `am_summarize_oncall` | Read | Generate a structured on-call triage summary of active and suppressed alerts. |
| `am_update_silence` | Write | Atomically update an active silence via `POST /api/v2/silences` with `id`, enforcing the total lifetime cap (`SP007`). |

---

## Bundled Agent Skills (5)

This image also ships step-by-step operational playbooks (`SKILL.md`) under `/app/skills`:

- [`auditing-alertmanager-governance`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/alertmanager-mcp-server/skills/auditing-alertmanager-governance/SKILL.md)
- [`diagnosing-missed-notifications`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/alertmanager-mcp-server/skills/diagnosing-missed-notifications/SKILL.md)
- [`managing-alert-silences`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/alertmanager-mcp-server/skills/managing-alert-silences/SKILL.md)
- [`triaging-alertmanager-alerts`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/alertmanager-mcp-server/skills/triaging-alertmanager-alerts/SKILL.md)
- [`validating-alertmanager-routing`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/alertmanager-mcp-server/skills/validating-alertmanager-routing/SKILL.md)

To copy the skills onto your workstation for Claude Code or Cursor:

```bash
docker run --rm --entrypoint tar talkopsai/alertmanager-mcp-server:latest -C /app/skills -cf - . | tar -xf - -C ~/.claude/skills/
```

---

## Support & Community

- **Source & full docs:** [github.com/talkops-ai/talkops-mcp/tree/main/src/alertmanager-mcp-server](https://github.com/talkops-ai/talkops-mcp/tree/main/src/alertmanager-mcp-server)
- **Issues & feature requests:** [GitHub Issues](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=alertmanager-mcp-server)
- **Community Slack:** [talkops.ai/slack](https://talkops.ai/slack/)
