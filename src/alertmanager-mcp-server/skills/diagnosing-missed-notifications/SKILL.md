---
name: diagnosing-missed-notifications
description: Diagnoses why an Alertmanager alert did not page or notify a downstream receiver (Slack, PagerDuty, OpsGenie, email, webhook) and verifies receiver delivery end-to-end. Use when asked why on-call was not paged, why Slack or PagerDuty stopped receiving alerts, to troubleshoot missing alert notifications across Prometheus push, silences, inhibition rules, sibling/parent route shadowing, mute time intervals, grouping timers, or failed receiver deliveries, or to push a synthetic test alert after rotating a receiver webhook or key. Do not use for general alert storm triage (use triaging-alertmanager-alerts) or creating maintenance silences (use managing-alert-silences).
license: Apache-2.0
metadata:
  author: talkops
  version: "0.2.0"
  domain: observability
  component: alertmanager
---

# Diagnosing Missed Notifications

## Overview

Systematically isolates the exact stage in the 6-gate Alertmanager notification pipeline where an expected alert notification was never ingested, muted by a silence or inhibition rule, shadowed in the routing tree, delayed by grouping/mute intervals, or rejected by a downstream integration.

## MCP Execution Primitives Used

- **Resources (Read via MCP `read_resource`)**:
  - `am://backends` & `am://backends/{backend_id}` — verify backend health, readiness, version, and HA cluster status.
  - `am://backends/{backend_id}/config` — inspect the active nested routing tree, `inhibit_rules`, and `time_intervals`.
  - `am://backends/{backend_id}/receivers` — inspect configured receiver integrations (`slack`, `pagerduty`, `opsgenie`, `webhook`, `email`) with credentials safely redacted.
  - `am://backends/{backend_id}/alerts/{fingerprint}` — inspect an alert's `status.state`, `status.silencedBy`, and `status.inhibitedBy`.
  - `am://backends/{backend_id}/silences/{silence_id}` — inspect active silence creator, ticket comment, and `endsAt`.
- **Tools (`routing`, `triage`, `silences` toolsets)**:
  - `am_list_alerts` — verify whether the alert reached Alertmanager (`state="all"`).
  - `am_summarize_oncall` — verify `watchdog_status` (`firing` vs `missing` / `suppressed`).
  - `am_explain_routing` — simulate routing tree traversal, `continue` fan-out, parent/child fallback, `at_time` mute intervals, active silences, and live `inhibit_rules` (`check_live_state=True`).
  - `am_list_silences` — inspect active silences matching the alert.
  - `am_check_notification_health` — check `/-/ready`, `config_reload_successful`, and `/metrics` delivery counters (`notifications_failed_total`, `degraded_integrations`).
  - `am_push_test_alert` — send a bounded synthetic test alert (`resolve_after_minutes=5`, `confirm=True`) **only** when explicitly requested and safe.

## 6-Gate Diagnostic Workflow

Always read [references/notification-pipeline-decision-tree.md](references/notification-pipeline-decision-tree.md) and [references/integration-failure-catalog.md](references/integration-failure-catalog.md) and evaluate the 6 gates in strict order:

### Gate 1: Did the Alert Reach Alertmanager?
1. Read `am://backends` first if the backend ID is uncertain (e.g., the primary instance in namespace `observability` uses `backend_id="default"`; if any tool returns `Unknown backend_id`, immediately re-call that MCP tool with the valid `backend_id` from `am://backends` rather than falling back to `curl`).
2. Call `am_list_alerts(backend_id=..., alertname="<name>", state="all")` and `am_summarize_oncall(backend_id=...)` (plus read `am://backends/{backend_id}`).
3. If `0` alerts are returned, **always contrast both cases explicitly** in your explanation:
   - **`watchdog_status == "missing"`**: Broken Prometheus $\to$ Alertmanager push link (check `prom_get_diagnostics` Alertmanager discovery, Service DNS/port `:9093`, TLS/auth, or `NetworkPolicy`).
   - **`watchdog_status == "firing"`**: Prometheus transport is proven healthy; the specific rule is still in `pending` (`for:` window not yet elapsed), its PromQL expression did not fire, or `alert_relabel_configs` dropped it.

### Gate 2: Is the Alert Suppressed by an Active Silence?
1. Whenever a live alert fingerprint is found in Gate 1, **always** read `am://backends/{backend_id}/alerts/{fingerprint}` to inspect raw `status.state`, `status.silencedBy`, and `status.inhibitedBy`, **and** call `am_explain_routing(backend_id=..., fingerprint="<fp>", check_live_state=True)`.
2. If `matching_silences` or `status.silencedBy` is non-empty, read `am://backends/{backend_id}/silences/{silence_id}` to report `createdBy`, `comment`, and `endsAt`.

### Gate 3: Is the Alert Suppressed by Live Inhibition?
1. Inspect `is_inhibited` and `inhibition_details` from `am_explain_routing`.
2. Explain the active source alert (`inhibiting_source_alertnames` / `inhibiting_source_fingerprints`) and shared `equal` labels, and explicitly state that inhibition is **intentional downstream noise reduction by design** (not a bug) that persists until the upstream root-cause service/alert is restored.

### Gate 4: Did the Alert Route to the Expected Receiver?
1. Read `am://backends/{backend_id}/config` and inspect `route_trace` and `matched_routes` in `am_explain_routing`:
   - **Sibling Shadowing (`continue: false`)**: An earlier broad sibling route (e.g., `namespace="payments"` with default `continue: false`) captures the alert before a later specific route (`team="checkout", severity="critical"`). Fix by moving specific routes above catch-all siblings or setting `continue: true` for dual fan-out.
   - **Parent Receiver Fallback Semantics**: A parent route's `receiver` is **only** notified when **zero** child routes match! If a child (`severity="critical"`) matches, the parent's receiver is skipped unless configured as a `continue: true` sibling.

### Gate 5: Is the Route Muted by Time Intervals or Grouping Timers?
1. Pass `at_time` to `am_explain_routing` to verify `muted_receivers` (`mute_time_intervals` or outside `active_time_intervals`).
2. Whenever explaining grouping/batching behavior, **always define and contrast all three route timers explicitly**:
   - `group_wait` (~`30s`): initial buffer before the first notification for a brand-new group.
   - `group_interval` (~`5m`): batch wait before sending updated notifications when a 2nd pod/instance alert joins an *already-notified* group!
   - `repeat_interval` (~`4h`): re-notification interval before re-sending an *unchanged* group when no alerts were added or resolved.

### Gate 6: Did the Downstream Receiver Integration Fail?
1. Call `am_check_notification_health(backend_id=..., integration=...)` and read `am://backends/{backend_id}/receivers`.
2. **Zero-Secret Hygiene (`secret-safety.py`)**: Never run `aws secretsmanager get-secret-value`, read `.env` files, print raw webhook/routing tokens, or pass inline `https://user:pass@host` credentials. Always include a **concrete hardened `alertmanager.yaml` `receivers:` YAML snippet** referencing mounted Kubernetes `Secret` files (`url_file`, `password_file`, `routing_key_file`, `api_url_file`) alongside a Kubernetes `Secret` volume mount example.
3. **Synthetic Test Safety**: Refuse unconfirmed `severity="critical"` pages to production PagerDuty (`am_push_test_alert`). Use read-only `am_explain_routing` + `am_check_notification_health` for unconfirmed prod checks, and only call `am_push_test_alert(..., resolve_after_minutes=5, confirm=True)` on approved staging/verification requests.
