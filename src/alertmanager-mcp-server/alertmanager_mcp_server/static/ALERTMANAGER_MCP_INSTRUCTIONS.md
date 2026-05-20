# Alertmanager MCP Server Instructions

You are connected to the **Alertmanager MCP Server**, which provides tools, resources, and prompts for AI-native alert management and incident response.

## Core Concepts

| Concept | Description |
|---------|-------------|
| **Backend** | An Alertmanager-compatible endpoint (vanilla, AMP, Grafana Cloud) |
| **Alert** | A firing notification with labels, annotations, severity, and routing info |
| **Silence** | A time-bounded suppression of alerts matching specific label matchers |
| **Receiver** | A notification channel (Slack, PagerDuty, email, webhook) |
| **Inhibition** | A rule that suppresses alerts when a higher-priority alert is firing |

## Available Tools (Actions & Reasoning)

### Alert Triage & On-Call
- `am_summarize_oncall` — On-call alert summarization grouped by severity/service
- `am_list_alerts` — Filter alerts by label/state/severity
- `am_list_alert_groups` — View Alertmanager's native grouping
- `am_push_test_alert` — Inject test alerts for integration verification

### Silence Lifecycle
- `am_list_silences` — View active or expired silences
- `am_create_silence` — Create a new silence
- `am_update_silence` — Extend duration or update end time
- `am_expire_silence` — Remove a silence
- `am_preview_silence` — Dry-run blast radius estimation
- `am_silence_alert` — Narrowly-scoped silence generation

### Routing & Governance
- `am_explain_routing` — Route simulation with explanation
- `am_audit_default_route` — Find misconfigured alerts
- `am_list_recent_changes` — Audit silence creation/expiration
- `am_validate_silence_policy` — Check silence compliance

## MCP Resources (Read-Only Snapshots)

| Resource URI | Description |
|---|---|
| `am://system/backends` | All backends with health |
| `am://system/backends/{backend_id}` | Detailed backend status and version |
| `am://system/status` | Version, uptime, cluster info |
| `am://system/receivers` | Configured receivers (redacted) |
| `am://system/config` | Routing tree and inhibition rules |
| `am://system/audit-log` | MCP operation history |
| `am://alerts/active` | Active alerts snapshot |
| `am://alerts/groups` | Alert groups snapshot |
| `am://silences/active` | Active silences snapshot |
| `am://best-practices` | Alerting best practices |
| `am://onboarding-guide` | Alert onboarding guide |

## Safety Rules

1. **Stateless**: Every tool requires explicit `backend_id`
2. **Silence Cap**: Max silence duration is 24 hours by default
3. **Preview Mandatory**: Always call `am_preview_silence` before broad silences
4. **Narrow Matchers**: `am_silence_alert` derives matchers from alertname + service + env to avoid broad suppression
5. **Auditable**: All silences require `created_by` and `comment`

## Workflow Patterns

### Alert Triage
1. Resource: `am://system/backends` → find backend
2. `am_summarize_oncall` → high level summary
3. `am_list_alerts` → detail view
4. `am_explain_routing` → check who gets paged

### Maintenance Silence
1. `am_preview_silence` → estimate impact
2. `am_validate_silence_policy` → check compliance
3. `am_create_silence` → create
4. `am_update_silence` → extend if needed
5. `am_expire_silence` → clean up

### Integration Testing
1. Resource: `am://system/receivers` → verify receiver exists
2. `am_explain_routing` → predict routing
3. `am_push_test_alert` → fire test alert
