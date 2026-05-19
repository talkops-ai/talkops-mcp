# Alertmanager MCP Server — Natural Language Prompt Reference

**For every tool, resource, and prompt documented in [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md), this guide provides ready-to-use natural language prompts you can give to an AI agent.**

Copy any prompt below exactly or adapt it for your backend, service, and environment names.

> **Design**: Read-only context uses **resources** (`am://...`). State-changing actions use **tools**.

---

## Table of Contents

1. [Alert Triage](#alert-triage)
2. [Silence Lifecycle](#silence-lifecycle)
3. [Silence Helpers](#silence-helpers)
4. [Routing & Notifications](#routing--notifications)
5. [Governance & Audit](#governance--audit)
6. [On-Call Triage](#on-call-triage)
7. [Guided Workflow Prompts](#guided-workflow-prompts)
8. [Resource Reads](#resource-reads)

---

## Alert Triage

> **Tool**: `am_list_alerts`

```
Show me all active critical alerts on backend "default".
```
```
List alerts for the "checkout" service in the "prod" environment.
```
```
Show me suppressed alerts — what's currently silenced or inhibited?
```
```
List the next 50 alerts starting from offset 50 on the default backend.
```

> **Tool**: `am_list_alert_groups`

```
Show me how Alertmanager groups the active alerts on backend "default".
```
```
What alert groups are currently firing?
```

> **Tool**: `am_push_test_alert`

```
Push a test alert with alertname "MCPIntegrationTest" and severity "warning" to the default backend.
```
```
Fire a test alert for service "payments" with env "staging" to verify the Slack integration.
```

---

## Silence Lifecycle

> **Tool**: `am_list_silences`

```
Show me all active silences on backend "default".
```
```
List expired silences — I want to see the history.
```

> **Tool**: `am_create_silence`

```
Create a 2-hour silence for service "checkout" in env "prod" with comment "Deploying v2.3".
```
```
Silence all alerts matching alertname="HighCPU" for 60 minutes. Created by alice, comment: "Known issue, fix in progress".
```
```
Create a silence for the payments service in production for 4 hours during the maintenance window.
```

> **Tool**: `am_update_silence`

```
Extend silence abc-123 by 30 minutes — the deployment is taking longer than expected.
```
```
Update silence abc-123 to end at 2025-06-15T18:00:00Z.
```

> **Tool**: `am_expire_silence`

```
Expire silence abc-123 — the maintenance is done.
```
```
Remove the silence on the checkout service — we need alerts back.
```

---

## Silence Helpers

> **Tool**: `am_preview_silence`

```
Preview the blast radius: how many alerts would be silenced if I match service="checkout" and env="prod"?
```
```
Before I create a silence for severity="warning", show me how many alerts that would affect.
```

> **Tool**: `am_silence_alert`

```
Silence the alert with fingerprint "abc123def456" for 1 hour. Use service scope.
```
```
Silence this alert: alertname=HighLatency, service=api-server, env=prod. Scope to service level, 2 hours.
```
```
Quick-silence the HighMemory alert for the checkout service using instance scope.
```

---

## Routing & Notifications

> **Tool**: `am_explain_routing`

```
Who gets paged when a critical alert fires for service "api-server" in env "prod"?
```
```
Explain the routing for an alert with labels: alertname=HighErrorRate, service=checkout, severity=critical, env=prod.
```
```
Why didn't I get notified for the HighCPU alert? Simulate the routing for these labels.
```

> **Tool**: `am_audit_default_route`

```
Are any alerts falling through to the default route?
```
```
Show me alerts hitting the default receiver — these might be misconfigured.
```

---

## Governance & Audit

> **Tool**: `am_list_recent_changes`

```
Show me all silence changes in the last 24 hours — who created or expired what?
```
```
Audit silence activity for the last 48 hours on the prod backend.
```

> **Tool**: `am_validate_silence_policy`

```
Validate this proposed silence before I create it: match service="checkout" for 120 minutes, comment "Deploy v2.3", created by alice.
```
```
Check if a silence matching only severity="critical" would violate our policy.
```

---

## On-Call Triage

> **Tool**: `am_summarize_oncall`

```
Give me an on-call summary — what's firing right now?
```
```
Summarize active alerts for the checkout service in prod.
```
```
On-call handoff: show me the current alert landscape grouped by severity and service.
```
```
What critical alerts are active in the staging environment?
```

---

## Guided Workflow Prompts

These invoke MCP prompts that return structured multi-step workflows:

> **Prompt**: `am-alert-triage-guided`

```
Guide me through triaging active alerts for the checkout service in the prod environment on backend "default".
```

> **Prompt**: `am-maintenance-silence-guided`

```
Walk me through creating a maintenance silence for the payments service in prod for 2 hours on backend "default".
```

> **Prompt**: `am-integration-test-guided`

```
Help me test whether the slack-sre receiver is working — push a test alert and verify it arrives.
```

---

## Resource Reads

> **Resource**: `am://system/backends`

```
Show me all Alertmanager backends and their health.
```

> **Resource**: `am://system/backends/{backend_id}`

```
Show me detailed status for the "default" Alertmanager backend.
```
```
What version of Alertmanager is running on the prod backend? Is it clustered?
```

> **Resource**: `am://system/status`

```
What version of Alertmanager is running? Show me the uptime and cluster info.
```

> **Resource**: `am://system/receivers`

```
List the configured notification receivers.
```

> **Resource**: `am://system/config`

```
Show me the current routing tree and inhibition rules.
```

> **Resource**: `am://system/audit-log`

```
Show me the MCP operation audit log — what actions have been taken?
```

> **Resource**: `am://alerts/active`

```
Give me a quick snapshot of active alerts.
```

> **Resource**: `am://alerts/groups`

```
Show me the alert groups as computed by Alertmanager.
```

> **Resource**: `am://silences/active`

```
Show me all currently active silences.
```

> **Resource**: `am://best-practices`

```
Show me alerting best practices.
```

> **Resource**: `am://onboarding-guide`

```
Show me the alert onboarding guide.
```

---

*Document Version: 1.0 | Companion to [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md)*
