---
name: triaging-alertmanager-alerts
description: Triages active and suppressed Prometheus Alertmanager alerts during incidents, alert storms, and on-call shift handovers. Use when asked to summarize firing alerts, run /triage on an alerting incident, prioritize critical incidents, investigate alert storms, inspect Alertmanager dispatch groups, distinguish inhibited vs resolved alerts, or prepare an on-call shift handover report. Do not use for creating silences (use managing-alert-silences), validating routing configs (use validating-alertmanager-routing), or debugging missing receiver notifications (use diagnosing-missed-notifications).
license: Apache-2.0
metadata:
  author: talkops
  version: "0.2.0"
  domain: observability
  component: alertmanager
---

# Triaging Alertmanager Alerts

## Overview

Guides structured, zero-hallucination on-call triage of firing and suppressed alerts across one or more Alertmanager backends. Prioritizes pipeline liveness (`Watchdog`), blast radius across services, root-cause vs. symptom separation via inhibition state, and actionable shift handovers.

When invoked via the `/triage` slash command, read `commands/triage.md` first and execute the Alertmanager incident correlation step alongside available Prometheus RED/SLO telemetry.

## MCP Execution Primitives Used

- **Resources (Read via MCP `read_resource`, never raw `kubectl` or `curl`)**:
  - `am://backends` — discover configured Alertmanager backends and verify live health.
  - `am://backends/{backend_id}` — inspect backend readiness, version, uptime, and HA cluster status.
  - `am://backends/{backend_id}/alerts/active` — bounded snapshot of currently firing alerts.
  - `am://backends/{backend_id}/alerts/groups` — Alertmanager dispatch groups grouped by route `group_by` labels.
  - `am://backends/{backend_id}/alerts/{fingerprint}` — full labels, annotations (`summary`, `runbook_url`), and suppression status for a single alert.
  - `am://backends/{backend_id}/silences/active` — active maintenance silences affecting current shift triage.
- **Tools (`triage` & `routing` toolsets)**:
  - `am_summarize_oncall` — aggregate active and suppressed alerts by severity, environment, service, and team, including `Watchdog` status.
  - `am_list_alerts` — query alerts using exact or regex matchers (`label_filters`), receiver filters, and state filters (`active`, `suppressed`, `silenced`, `inhibited`, `unprocessed`, `all`).
  - `am_list_alert_groups` — inspect grouped alert batches as dispatched to receivers (use `max_alerts_per_group`, `limit`, and `offset` on large queues).
  - `am_explain_routing` — trace which receiver owns a firing alert and whether inhibition rules apply.

## Step-by-Step Triage Workflow

### 1. Verify Backend & Pipeline Liveness (Priority 0)
1. Read `am://backends` to confirm available backends (`default`, regional, DR, or benchmark instances) if not already known.
2. Call `am_summarize_oncall(backend_id=...)` (optionally scoped by `env`, `service`, `team`, or `severity`).
3. Check `watchdog_status` in the response **before trusting low alert counts**:
   - If `watchdog_status == "missing"` or `"suppressed"`, immediately escalate a **Priority-0 monitoring pipeline blind spot**: Prometheus may be failing to push alerts to Alertmanager, or someone silenced `Watchdog`. Cross-check `prom_get_diagnostics` (if Prometheus MCP is mounted) and recommend `diagnosing-missed-notifications`.

### 2. Prioritize by Severity and Blast Radius
Always read [references/severity-response-matrix.md](references/severity-response-matrix.md) to classify response urgency (`critical` vs `warning` vs `info`, including flagging `info` alerts misrouted to paging receivers):
1. Inspect `by_severity`, `by_service`, and `top_alert_groups` from `am_summarize_oncall` (and read `am://backends/{backend_id}/alerts/active` when a bounded active snapshot is helpful).
2. During an **alert storm** ($\ge 20$ firing alerts) or multi-service cascade:
   - Call `am_list_alert_groups(backend_id=..., state="active", max_alerts_per_group=10, limit=50, offset=0)` and read `am://backends/{backend_id}/alerts/groups` to collapse individual pod/instance alerts into receiver dispatch batches.
   - Correlate `startsAt` chronology and shared dependency topology (e.g., `postgresql` or `valkey-cart` failing right before downstream `product-catalog-service`, `recommendation`, `cart-service`, `checkout-service`, and `frontend` errors) so teams fix the single upstream root cause rather than rolling back healthy downstream apps.

### 3. Inspect High-Priority Alerts & Suppressed Context
1. Call `am_list_alerts(backend_id=..., severity="critical", state="active")` (using `limit` and `offset` pagination on large queues) to retrieve critical firing alerts with their live `fingerprint`s.
2. For top critical root-cause alerts, read `am://backends/{backend_id}/alerts/{fingerprint}` to extract `annotations.summary`, `annotations.runbook_url`, and `startsAt`, and call `am_explain_routing(backend_id=..., fingerprint=...)` to verify active paging receivers.
3. Check suppressed alerts by calling `am_list_alerts(backend_id=..., state="inhibited")` or `state="suppressed"`:
   - **Critical Distinction**: Alerts in `inhibited` state (`status.inhibitedBy` non-empty) are **NOT resolved**—they are still actively firing in Prometheus, and Alertmanager is merely muting duplicate downstream notifications while an upstream root-cause alert is active!
   - Read `am://backends/{backend_id}/silences/active` to account for active maintenance silences (`status.silencedBy`).

### 4. Strict Read-Only Triage Boundary & Shift Handover Report
1. **Never mutate silences during triage**: Even if noisy staging alerts appear or an operator casually asks to mute alerts mid-triage without full silence governance parameters/confirmation, do **not** call `am_create_silence` or `am_silence_alert`. Separate staging/noisy alerts cleanly in the report and offer a gated handoff to `managing-alert-silences` (`am_preview_silence` first).
2. Read [references/handover-template.md](references/handover-template.md) and format the final triage or shift handover report with pipeline health, root-cause vs. inhibited symptom correlation, active silences + expiry timestamps, runbook links, and next-shift watch items.
