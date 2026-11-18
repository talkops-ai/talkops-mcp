<p align="center">
  <img src="https://raw.githubusercontent.com/cncf/artwork/main/projects/prometheus/icon/color/prometheus-icon-color.svg" alt="Prometheus Alertmanager logo" height="100"/>
</p>

<h1 align="center">Alertmanager MCP Server &amp; Agent Plugin</h1>

<p align="center">
  A Model Context Protocol (MCP) execution server and <strong>Agent Plugins v1.0.0</strong> skill package for Prometheus Alertmanager incident triage, routing &amp; inhibition simulation, silence governance (<code>SP001</code>–<code>SP010</code>), and SRE alert hygiene.
</p>

<p align="center">
  <a href="https://pypi.org/project/talkops-alertmanager-mcp-server/"><img src="https://img.shields.io/pypi/v/talkops-alertmanager-mcp-server.svg?style=flat-square&logo=pypi&logoColor=white&label=PyPI" alt="PyPI"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://prometheus.io/docs/alerting/latest/alertmanager/"><img src="https://img.shields.io/badge/Alertmanager-API%20v2-E6522C.svg?style=flat-square&logo=prometheus&logoColor=white" alt="Alertmanager API v2"/></a>
</p>

---

Let your AI assistant help with alerts: see what's firing, find out why an alert didn't notify anyone, create safe silences for maintenance, and check your routing and alert hygiene.

## What you get

- **14 MCP tools** (9 read-only) that work against your live Alertmanager setup
- **10 resources** your assistant can read for context, under `am://`
- **5 Agent Skills**: step-by-step playbooks that teach your assistant how to use the tools well
- **Safe by default**: only read-only tools are loaded until you turn on writes, and changes are previewed or confirmed before they happen

## Quick start

**You'll need:**

- Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)
- An Alertmanager URL

**1. Add the server to your MCP client.** For Claude Desktop, Cursor, Windsurf, and most other clients, add this to your MCP config file:

```json
{
  "mcpServers": {
    "alertmanager": {
      "command": "uvx",
      "args": [
        "--from",
        "talkops-alertmanager-mcp-server",
        "alertmanager-mcp-server"
      ],
      "env": {
        "ALERTMANAGER_BASE_URL": "http://localhost:9093"
      }
    }
  }
}
```

Using Claude Code? Run this instead:

```bash
claude mcp add alertmanager -e ALERTMANAGER_BASE_URL=http://localhost:9093 -- uvx --from talkops-alertmanager-mcp-server alertmanager-mcp-server
```

`uvx` downloads [`talkops-alertmanager-mcp-server`](https://pypi.org/project/talkops-alertmanager-mcp-server/) from PyPI and runs it, so there's nothing else to install. Prefer a normal install? Run `pip install talkops-alertmanager-mcp-server` and use `alertmanager-mcp-server` as the command.

**2. Restart your client and try asking:**

- *"Summarize what's firing for the `payments` team right now."*
- *"Why didn't the `HighErrorRate` alert page anyone?"*
- *"Silence `checkout` alerts in `prod` for a 2-hour maintenance window. Show me what it would match first."*

## Allowing changes

Out of the box the server is read-only. To let your assistant make changes (creating, updating, and expiring silences, and sending test alerts), add `"--allow-write"` to `args` (or set `MCP_ALLOW_WRITE=true`). Even then, changes are previewed first and destructive actions ask for confirmation.

## Configuration

Set these as environment variables (the `env` block in your client config) or pass the matching flag.

| Variable | Flag | Default | What it does |
| :--- | :--- | :--- | :--- |
| `ALERTMANAGER_BASE_URL` | — | `http://localhost:9093` | Your Alertmanager URL |
| `ALERTMANAGER_AUTH_HEADER` | — | none | Authorization header, e.g. `Bearer <token>` |
| `ALERTMANAGER_BACKENDS` | — | none | JSON list of several Alertmanagers (replaces the single URL) |
| `MCP_ALLOW_WRITE` | `--allow-write` | `false` | Enable silence and test-alert tools |
| `MCP_TOOLSETS` | `--toolsets` | `all` | Limit tools: `triage`, `routing`, `silences`, `governance` |
| `AM_MAX_SILENCE_MINUTES` | — | `1440` | Longest silence allowed, in minutes |
| `AM_SILENCE_CONFIRM_THRESHOLD` | — | `50` | Ask for confirmation when a silence would match more alerts than this |
| `MCP_TRANSPORT` | `--transport` | `stdio` | `stdio` or `http` |
| `MCP_PORT` | `--port` | `8769` | Port when using HTTP |

Run `uvx --from talkops-alertmanager-mcp-server alertmanager-mcp-server --help` to see every option.

### Running over HTTP

To share one server between several clients or run it remotely, start it in HTTP mode:

```bash
MCP_TRANSPORT=http MCP_PORT=8769 uvx --from talkops-alertmanager-mcp-server alertmanager-mcp-server
```

Then point your client at `http://localhost:8769/mcp`:

```json
{
  "mcpServers": {
    "alertmanager": {
      "url": "http://localhost:8769/mcp"
    }
  }
}
```

## Agent Skills

Skills live in [`skills/`](skills/). Each one is a `SKILL.md` playbook (plus optional `references/` and offline `scripts/`) that teaches your AI assistant *how* to do a job safely, while the MCP server does the actual work. Tools are the hands, skills are the know-how.

To use them, copy the folders into your assistant's skills directory, for example:

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cp -r talkops-mcp/src/alertmanager-mcp-server/skills/* ~/.claude/skills/
```

This folder is also a portable [Agent Plugin](https://agent-plugins.org) (`plugin.json` + `mcp.json` + `skills/`), so plugin-aware clients can load the server and skills together.

| Skill | Use it to |
| :--- | :--- |
| [`triaging-alertmanager-alerts`](skills/triaging-alertmanager-alerts/SKILL.md) | Sort out what's firing during an incident or shift handover. |
| [`diagnosing-missed-notifications`](skills/diagnosing-missed-notifications/SKILL.md) | Work out why an alert didn't reach Slack, PagerDuty, or email. |
| [`managing-alert-silences`](skills/managing-alert-silences/SKILL.md) | Plan, preview, create, and expire silences safely. |
| [`validating-alertmanager-routing`](skills/validating-alertmanager-routing/SKILL.md) | Test and lint routing trees, inhibition rules, and time intervals. |
| [`auditing-alertmanager-governance`](skills/auditing-alertmanager-governance/SKILL.md) | Check alert labels, runbook links, catch-all routes, and old silences. |

## Reference

<details>
<summary><strong>All 14 tools</strong></summary>

| Tool | Access | What it does |
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

</details>

<details>
<summary><strong>All 10 resources</strong></summary>

| Resource | What it returns |
| :--- | :--- |
| `am://audit-log` | Recent MCP-initiated operations (create/update/expire silence, push test alert, policy denials) |
| `am://backends` | All configured Alertmanager backends with live health, version, and default flag |
| `am://backends/{backend_id}` | Detailed status, readiness, version, uptime, and cluster peers for a specific Alertmanager backend |
| `am://backends/{backend_id}/alerts/active` | Bounded snapshot of active firing alerts for a specific Alertmanager backend |
| `am://backends/{backend_id}/alerts/groups` | Snapshot of Alertmanager dispatch groups for a specific backend |
| `am://backends/{backend_id}/alerts/{fingerprint}` | Full labels, annotations, receivers, and status for a specific alert fingerprint on a backend |
| `am://backends/{backend_id}/config` | Nested routing tree, inhibition rules, time intervals, and redacted configuration for a backend |
| `am://backends/{backend_id}/receivers` | Configured receivers (Slack, PagerDuty, email, webhook, OpsGenie) with redacted credentials for a backend |
| `am://backends/{backend_id}/silences/active` | Snapshot of active silences for a specific Alertmanager backend |
| `am://backends/{backend_id}/silences/{silence_id}` | Full details and status for a specific silence ID on a backend |

</details>

## Development

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/alertmanager-mcp-server
uv sync --dev
uv run pytest
uv run alertmanager-mcp-server --help
```

## Get help

- [Documentation](https://talkops.ai/docs/integrations/alertmanager-mcp-server/overview)
- [Report a bug or request a feature](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=alertmanager-mcp-server)
- [Join the TalkOps community on Slack](https://talkops.ai/slack/)

## License

Apache 2.0. See [LICENSE](../../LICENSE).
