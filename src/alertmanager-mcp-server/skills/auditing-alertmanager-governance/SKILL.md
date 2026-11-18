---
name: auditing-alertmanager-governance
description: Audits Prometheus Alertmanager alert taxonomy, default-route catch-all leakage, missing runbook/summary annotations, chronic long-firing alerts, control-plane config reload/delivery health, and silence governance compliance across single or multiple backends. Use when asked to run an Alertmanager governance review or scorecard, find unrouted alerts hitting the catch-all route, audit stale zero-match or expiring silences, review denied silence attempts in the audit log, or compare regional Alertmanager posture. Do not use for active incident triage (use triaging-alertmanager-alerts) or creating maintenance silences (use managing-alert-silences).
license: Apache-2.0
metadata:
  author: talkops
  version: "0.2.0"
  domain: observability
  component: alertmanager
---

# Auditing Alertmanager Hygiene & Governance

## Overview

Conducts comprehensive operational governance reviews across one or more Alertmanager backends to eliminate catch-all default-route leakage, enforce label/annotation taxonomy (`severity`, `env`, `service`, `team`, `summary`, `runbook_url`), remediate chronic alert fatigue ($> 24\text{h}$), clean up stale zero-match or non-compliant silences, and audit denied policy attempts and control-plane reload health.

## MCP Execution Primitives Used

- **Resources (Read via MCP `read_resource`)**:
  - `am://backends` — discover all configured Alertmanager backends (`default`, `otel-us`, `otel-eu`, `otel-dr`, etc.).
  - `am://backends/{backend_id}` — inspect backend version, readiness, uptime, and HA cluster peer health.
  - `am://backends/{backend_id}/config` — inspect nested routing tree, `inhibit_rules`, and `time_intervals`.
  - `am://backends/{backend_id}/receivers` — verify receiver integration coverage with secrets redacted.
  - `am://audit-log` — review MCP-initiated silence/test-alert operations and `outcome == "denied"` policy violations.
- **Tools (`governance` & `routing` toolsets)**:
  - `am_audit_alert_hygiene` — audit active alerts for default-route leakage, missing required annotations (`summary`, `runbook_url`), non-canonical `severity` values, chronic long-firing alerts (`check_long_firing_hours`), and `Watchdog` heartbeat status.
  - `am_audit_silences` — audit silence change history (`since_minutes`), active silence policy compliance (`SP001`–`SP009`), `stale_zero_match_silences`, `long_running_silences`, and `expiring_soon_silences` (`expiring_within_minutes`).
  - `am_check_notification_health` — verify `config_reload_successful` and `notifications_failed_total` across integrations.
  - `am_explain_routing` — verify proposed child routes resolve `fell_back_to_default` leakage.

## Step-by-Step Governance Audit Workflow

Always read [references/governance-checklist.md](references/governance-checklist.md), [references/alert-hygiene-standards.md](references/alert-hygiene-standards.md), and [references/governance-report-template.md](references/governance-report-template.md):

### 1. Discover Backends & Audit Alert Routing / Annotation Hygiene
1. Read `am://backends` (and `am://backends/{backend_id}` + `am://backends/{backend_id}/config`) to establish backend scope. For multi-region comparisons (e.g., `otel-us` vs `otel-eu`), run the audit primitives against **each** backend ID and present a side-by-side table.
2. Call `am_audit_alert_hygiene(backend_id=..., check_default_route=True, check_missing_annotations=True, check_long_firing_hours=24)` (or user-specified hour threshold):
   - **Heartbeat Priority (`watchdog_status`)**: Treat any silenced or missing `Watchdog` (`"missing"` or `"suppressed"`, or any historical/hypothetical `Watchdog` mute incident) as a **P0 monitoring blindness finding** (`SP005` violation). Always prescribe **both** immediate remediation (expiring or narrowing the offending broad silence immediately via `am_expire_silence` / `managing-alert-silences`) **and** structural prevention (placing `alertname="Watchdog"` as child route #1 with `continue: false` plus `SP005` heartbeat silence blocks).
   - **Default-Route Leakage (`default_route_alerts`)**: Use `suggested_matchers` and `am://backends/{backend_id}/config` to design explicit team/service child routes while keeping a valid root catch-all receiver, and always recommend verifying the new routes live post-deploy via `am_explain_routing`.
   - **Taxonomy & Annotation Enforcement**: Flag non-standard `severity` values outside `{"critical", "warning", "info"}` (e.g., `severity="urgent"`), missing `env`/`service`/`team` labels, missing `summary`/`runbook_url` annotations, and `severity="info"` alerts routed to paging PagerDuty/OpsGenie receivers.
   - **Chronic Long-Firing Alerts (`long_firing_alerts`)**: Recommend resetting left-on feature/chaos flags, tuning static thresholds, or converting capacity warnings to tickets—explicitly exempting `Watchdog` (which must always fire).

### 2. Audit Silence Governance & Imminent Expirations
1. Call `am_audit_silences(backend_id=..., since_minutes=1440, expiring_within_minutes=120)`:
   - **`non_compliant_silences` & `long_running_silences`**: Flag out-of-band silences violating `SP001`–`SP009` (e.g., $> 24\text{h}$ duration, `unknown`/`anonymous` author, missing ticket ID, or wildcard matchers).
   - **`stale_zero_match_silences`**: Flag active silences matching `0` alerts (including service-name typos like `product_catalog` vs `product-catalog-service`) for cleanup via `managing-alert-silences` (`am_expire_silence`).
   - **`expiring_soon_silences`**: Highlight silences expiring soon with `silenced_alert_count > 0`—warn on-call how many suppressed critical alerts will immediately page when the window expires!

### 3. Audit MCP Policy Denials & Control-Plane Delivery Health
1. Read `am://audit-log` to inspect `outcome == "denied"` entries, mapping rejected automation or operator calls to specific `SP001`–`SP010` remediation steps.
2. Call `am_check_notification_health(backend_id=...)` and read `am://backends/{backend_id}/receivers`:
   - `config_reload_successful == False` means Alertmanager rejected a broken `alertmanager.yml` reload and is running stale in-memory routing (config drift!).
   - `total_failed_notifications > 0` indicates active notification loss; recommend `validating-alertmanager-routing` and `diagnosing-missed-notifications` without ever exposing raw receiver secrets.
3. Structure the output using [references/governance-report-template.md](references/governance-report-template.md).
