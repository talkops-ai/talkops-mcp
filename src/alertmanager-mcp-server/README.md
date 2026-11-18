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

## Architecture: Skill Layer vs. Execution Layer

`talkops-alertmanager-mcp-server` strictly separates **procedural SRE playbooks** (Agent Skills) from **deterministic API execution** (FastMCP server):

```text
src/alertmanager-mcp-server/
├── plugin.json                              # Agent Plugins v1.0.0 manifest (talkops-alertmanager v0.2.0)
├── mcp.json                                 # Default stdio MCP server wiring (read-only by default)
├── skills/                                  # 5 Progressive-Disclosure Agent Skills (4 scripts, 11 references)
│   ├── triaging-alertmanager-alerts/
│   ├── diagnosing-missed-notifications/
│   ├── managing-alert-silences/
│   ├── validating-alertmanager-routing/
│   └── auditing-alertmanager-governance/
└── alertmanager_mcp_server/                 # FastMCP Execution Plane
    ├── domain/                              # Matcher grammar, recursive route tree, inhibition algebra, SP001-SP010
    ├── services/                            # Multi-backend Alertmanager v2 HTTP client & /metrics exposition parser
    ├── resources/                           # 10 live am:// URI resources (deeply redacted)
    └── tools/                               # 14 tools across 4 selectable toolsets (all <= 8 params, 0 prompts)
```

---

## 5 Bundled Agent Skills (`skills/`)

| Skill Directory | Purpose | Offline Scripts (`scripts/`) | Reference Guides (`references/`) |
|---|---|---|---|
| `triaging-alertmanager-alerts` | Structured on-call alert triage, storm correlation, inhibition awareness, and shift handovers | *(uses `am_summarize_oncall`)* | `severity-response-matrix.md`, `handover-template.md` |
| `diagnosing-missed-notifications` | 6-gate missed-notification decision tree across Prometheus firing state, route tree, mute intervals, inhibition, silences, and receiver `/metrics` | *(uses `am_explain_routing` & `am_check_notification_health`)* | `notification-pipeline-decision-tree.md`, `integration-failure-catalog.md` |
| `managing-alert-silences` | Safe maintenance window planning, blast-radius preview, `SP001`–`SP010` policy enforcement, atomic in-place updates, and controlled expiration | `plan_maintenance_window.py`, `validate_silence_request.py` | `silence-policy.md`, `matcher-cookbook.md` |
| `validating-alertmanager-routing` | Static Alertmanager YAML linting (`LINT001`–`LINT010`), recursive `continue: true` route simulation, and time-interval testing | `lint_alertmanager_config.py`, `test_routes.py` | `config-lint-rules.md`, `routing-best-practices.md` |
| `auditing-alertmanager-governance` | Fleet governance audit across default-route leakage, missing `summary`/`runbook_url` annotations, Watchdog health, and silence debt | *(uses `am_audit_alert_hygiene` & `am_audit_silences`)* | `alert-hygiene-standards.md`, `governance-checklist.md`, `governance-report-template.md` |

---

## 14 MCP Tools Across 4 Selectable Toolsets

Control exposed toolsets via `--toolsets` or `MCP_TOOLSETS` (`all` or comma-separated `triage,routing,silences,governance`). Mutating tools are unregistered when `MCP_ALLOW_WRITE=false` (the default).

| Toolset | Tool | Access | Max Params | Description |
|---|---|---|---|---|
| `triage` | `am_list_alerts` | Read-only | 8 | Query alerts from Alertmanager with full matcher grammar (`=`, `!=`, `=~`, `!~`), receiver/state filters, and pagination |
| `triage` | `am_list_alert_groups` | Read-only | 6 | List Alertmanager dispatch groups from `/api/v2/alerts/groups` grouped by route `group_by` labels |
| `triage` | `am_summarize_oncall` | Read-only | 5 | Generate a structured on-call triage summary of active and suppressed alerts filtered by `env`, `service`, `team`, or `severity` |
| `routing` | `am_explain_routing` | Read-only | 5 | Simulate Alertmanager's nested routing tree (`continue`, inherited `group_by`/timers, `mute_time_intervals`) and live inhibition rules for labels or a live `fingerprint` |
| `routing` | `am_check_notification_health` | Read-only | 2 | Inspect Alertmanager readiness, config reload status, HA gossip cluster peers, and `/metrics` receiver delivery failure counters |
| `routing` | `am_push_test_alert` | Write (`confirm=True`) | 6 | Push a time-bounded synthetic test alert tagged with `mcp_test=true` to verify end-to-end receiver delivery |
| `silences` | `am_list_silences` | Read-only | 7 | List silences by state (`active`, `pending`, `expired`), matcher filter, `created_by`, or comment substring |
| `silences` | `am_preview_silence` | Read-only | 7 | Dry-run a silence against active alerts, affected receivers, overlapping silences, and `SilencePolicy` (`SP001`–`SP010`) |
| `silences` | `am_create_silence` | Write | 8 | Create a silence after enforcing `SilencePolicy` (`SP001`–`SP010`), overlapping-silence deduplication, and blast-radius confirmation |
| `silences` | `am_silence_alert` | Write | 8 | Derive scoped matchers (`instance` or `service`) from a firing alert's `fingerprint` or labels and create a policy-validated silence |
| `silences` | `am_update_silence` | Write | 7 | Atomically update/extend an active silence in-place (`POST /api/v2/silences` with `id`), enforcing the total lifetime cap (`SP007`) |
| `silences` | `am_expire_silence` | Destructive (`confirm=True`) | 5 | Expire an active silence after previewing how many suppressed alerts will immediately resume paging |
| `governance` | `am_audit_alert_hygiene` | Read-only | 5 | Audit active alerts for default-route leakage, missing `summary`/`runbook_url` annotations, invalid severities, chronic long-firing alerts, and `Watchdog` presence |
| `governance` | `am_audit_silences` | Read-only | 3 | Audit silence history, active silence policy compliance (`SP001`–`SP009`), stale 0-match silences, and silences expiring soon |

---

## 10 Live `am://` Resources

| URI | Description |
|---|---|
| `am://backends` | Configured Alertmanager backends with live health, version, and default flag |
| `am://backends/{backend_id}` | Detailed status, readiness, version, uptime, and HA gossip cluster peers for `{backend_id}` |
| `am://backends/{backend_id}/config` | Deeply redacted Alertmanager YAML configuration, nested routing tree, inhibition rules, and time intervals |
| `am://backends/{backend_id}/receivers` | Configured receivers (Slack, PagerDuty, email, webhook, OpsGenie) with redacted integration credentials |
| `am://backends/{backend_id}/alerts/active` | Bounded live snapshot of active firing alerts on `{backend_id}` |
| `am://backends/{backend_id}/alerts/groups` | Live snapshot of Alertmanager dispatch groups on `{backend_id}` |
| `am://backends/{backend_id}/alerts/{fingerprint}` | Full labels, annotations, receivers, and suppression status for alert `{fingerprint}` |
| `am://backends/{backend_id}/silences/active` | Live snapshot of active silences on `{backend_id}` |
| `am://backends/{backend_id}/silences/{silence_id}` | Full matcher details, author, comment, and status for `{silence_id}` |
| `am://audit-log` | Recent MCP-initiated operations (create/update/expire silence, push test alert, policy denials) |

---

## Quick Start & Configuration

### CLI Usage

```bash
# Default safe mode: Read-only over stdio
uv run alertmanager-mcp-server --transport stdio --alertmanager-url http://localhost:9093

# Enable mutating tools (silence creation/updates & synthetic test alerts)
uv run alertmanager-mcp-server --allow-write --alertmanager-url http://localhost:9093

# Restrict to specific toolsets
uv run alertmanager-mcp-server --read-only --toolsets triage,routing,governance

# Run over Streamable HTTP on port 8769
uv run alertmanager-mcp-server --transport http --host 0.0.0.0 --port 8769
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ALERTMANAGER_BASE_URL` / `ALERTMANAGER_URL` | `http://localhost:9093` | Single-backend Alertmanager base URL |
| `ALERTMANAGER_BACKENDS` | `""` | JSON array of multi-backend configs (`id`, `base_url`, `auth_header`, `headers`, `path_prefix`, `is_default`) |
| `MCP_ALLOW_WRITE` | `false` | Set `true` (or pass `--allow-write`) to register mutating silence and test-alert tools |
| `MCP_READ_ONLY` | *(unset)* | When `true`, forces read-only mode (overrides `MCP_ALLOW_WRITE=true`) |
| `MCP_TOOLSETS` | `all` | Comma-separated toolsets (`triage,routing,silences,governance` or `all`) |
| `MCP_TRANSPORT` | `stdio` | Transport protocol (`stdio` or `http`) |
| `MCP_PORT` | `8769` | HTTP bind port when `MCP_TRANSPORT=http` |
| `AM_MAX_SILENCE_MINUTES` | `1440` | Maximum allowed silence lifetime in minutes (`SP007`) |
| `AM_SILENCE_CONFIRM_THRESHOLD` | `50` | Matched-alert blast-radius threshold requiring explicit confirmation (`SP010`) |
| `AM_AUDIT_LOG_PATH` | `""` | Optional JSONL file path for durable write audit logging |

---

## Development & Verification

```bash
# Run full unit, tool, regression, and skill/manifest test suite
uv run pytest -v

# Run static type checking
uv run pyright .

# Build wheel and sdist
uv build
```
