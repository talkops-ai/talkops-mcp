---
name: validating-alertmanager-routing
description: Simulates, lints, designs, and validates Prometheus Alertmanager routing trees, inhibition rules, mute/active time intervals, and receiver configurations. Use when asked who gets paged for an alert, to review or lint alertmanager.yml for shadowed routes or undefined receivers, migrate match/match_re to matchers, design inhibit_rules or calendar time_intervals, or run /setup-monitoring routing checks. Do not use for active incident triage (use triaging-alertmanager-alerts), ad-hoc maintenance silences (use managing-alert-silences), or testing rotated receiver webhooks and missed deliveries (use diagnosing-missed-notifications).
license: Apache-2.0
metadata:
  author: talkops
  version: "0.2.0"
  domain: observability
  component: alertmanager
---

# Validating Alertmanager Routing & Configuration

## Overview

Designs, lints, and simulates Alertmanager routing trees (`route`), `inhibit_rules`, `time_intervals`, and `receivers` both offline against candidate `alertmanager.yml` files using deterministic Python scripts and live against running Alertmanager backends via MCP resources and tools.

When invoked via `/setup-monitoring`, read `commands/setup-monitoring.md` first, check live Alertmanager alerts/hygiene (`am_audit_alert_hygiene` / `am_list_alerts`) and routing config (`am://backends/{backend_id}/config`, `am_explain_routing`) concisely to discover the target service's `team` label and whether it falls into the catch-all route, and output both the multi-burn-rate SLO `PrometheusRule` manifest (with `service`, `team`, `severity`, `env`, `summary`, `runbook_url`) and the linted `alertmanager.yaml` child route.

## MCP Execution Primitives & Bundled Scripts

- **Bundled Scripts (Always Run Offline Linting & Simulation Helpers)**:
  - [scripts/lint_alertmanager_config.py](scripts/lint_alertmanager_config.py) — static analyzer detecting missing root receiver (`LINT001`), undefined receivers (`LINT002`), unused receivers (`LINT003`), undefined `time_intervals` (`LINT004`), deprecated `match`/`match_re` (`LINT005`), shadowed sibling routes (`LINT006`), invalid Go RE2 regexes (`LINT007`), and un-scoped/self-matching `inhibit_rules` (`LINT008`).
  - [scripts/test_routes.py](scripts/test_routes.py) — offline `amtool config routes test` equivalent implementing exact depth-first `Route.Match` traversal, parameter inheritance (`group_by`, `group_wait`, `group_interval`, `repeat_interval`), `continue` fan-out, IANA `time_intervals`, and `inhibit_rules`.
- **Resources (Read via MCP `read_resource` to Inspect Live Config)**:
  - `am://backends` — list configured Alertmanager backends (`default`, `prod`, `staging`, etc.).
  - `am://backends/{backend_id}/config` — read the active nested routing tree, `inhibit_rules`, `time_intervals`, and redacted YAML config from a live backend.
  - `am://backends/{backend_id}/receivers` — read configured receiver names and integration types (`slack`, `pagerduty`, `webhook`, `opsgenie`, `email`) with secrets redacted.
- **Tools (`routing` & `governance` toolsets)**:
  - `am_explain_routing` — simulate routing tree traversal, `at_time` time-interval muting, active silences, and live `inhibit_rules` (`check_live_state=True`) on a running backend.
  - `am_audit_alert_hygiene` — detect active live alerts falling back to the root catch-all route (`fell_back_to_default == True`) and retrieve `suggested_matchers`.
  - `am_push_test_alert` — send a time-bounded synthetic test alert (`resolve_after_minutes=5`, `confirm=True`) to verify end-to-end delivery when explicitly requested.

## Step-by-Step Routing Validation Workflow

### 1. Read References & Inspect Live Routing Configuration
Always consult [references/config-lint-rules.md](references/config-lint-rules.md) and [references/routing-best-practices.md](references/routing-best-practices.md):
1. When evaluating a live Alertmanager backend, read `am://backends/{backend_id}/config` and `am://backends/{backend_id}/receivers` to inspect the active routing hierarchy, `time_intervals`, `inhibit_rules`, and receivers.
2. Call `am_explain_routing(backend_id=..., labels={...}, at_time=..., check_live_state=True)` to trace:
   - `matched_routes` & `route_trace`: exact tree nodes visited, inherited `group_by` and timers (`group_wait`, `group_interval`, `repeat_interval`), and `continue: true` fan-out vs. `continue: false` stop.
   - **Regex Anchoring Rule**: Alertmanager implicitly anchors regex matchers across the full label value (`^(?:pattern)$`), so `service=~"frontend"` does **not** match `frontend-proxy`—use `service=~"frontend|frontend-proxy"` or `service=~"frontend(-proxy)?"`.
   - `active_receivers` vs. `muted_receivers`: calendar `mute_time_intervals` / `active_time_intervals` evaluation at `at_time`.
   - `is_inhibited` & `inhibition_details`: active upstream inhibition with matching `equal` labels.

### 2. Offline Linting & Simulation for Candidate `alertmanager.yml` Configs
Whenever reviewing, migrating, or authoring an `alertmanager.yml` snippet (even if the user only pastes a partial `inhibit_rules:` or `time_intervals:` block—wrap partial blocks in a minimal `route:`/`receivers:` YAML file first so the linter executes programmatically!):
1. Write the candidate YAML (and any corrected version!) to a file in the workspace and **always** run:
   ```bash
   python3 <skill-dir>/scripts/lint_alertmanager_config.py --config candidate-alertmanager.yml
   ```
2. Simulate representative alert label sets (including `at_time` and `--active-alerts` JSON when testing `time_intervals` or `inhibit_rules`):
   ```bash
   python3 <skill-dir>/scripts/test_routes.py \
     --config candidate-alertmanager.yml \
     --labels '{"alertname":"OtelCartServiceErrors","service":"cart-service","severity":"warning","env":"prod"}' \
     --at-time "2026-11-15T03:00:00Z"
   ```
3. Enforce architectural best practices:
   - Place `alertname="Watchdog"` as child route #1 (`continue: false`, `group_wait: 0s`, `repeat_interval: 1m`–`5m`).
   - Always include `equal: ['env', 'cluster', 'namespace']` on `inhibit_rules` so staging alerts never mute production.
   - Within `time_intervals`, always explain **both** boolean rules clearly: fields inside a single `time_intervals` list entry are **ANDed** together (e.g., combining `days_of_month: ['-1']` and `weekdays` in one entry would only match when the last day of the month falls on a weekend!), whereas separate list entries are **ORed** together (keep `days_of_month: ['-1']` and `weekdays: ['saturday', 'sunday']` in separate list items when OR semantics are intended). Note: Go `time.Weekday` orders `sunday=0 .. saturday=6`, so weekends MUST be written as `weekdays: ['saturday', 'sunday']` rather than `'saturday:sunday'` (which fails Alertmanager reload with `start day cannot be before end day`).
   - Never hardcode plaintext Slack webhooks or PagerDuty keys; use `api_url_file` / `routing_key_file` backed by Kubernetes `Secret`s.

### 3. Auditing Catch-All Leakage & Post-Deploy Synthetic Verification
1. Before refactoring live routes, call `am_audit_alert_hygiene(backend_id=..., check_default_route=True)` to identify live alerts hitting the catch-all default receiver and use `suggested_matchers` to close routing gaps.
2. When explicitly asked to verify a staging/new route end-to-end, preview with `am_explain_routing` first, then call `am_push_test_alert(backend_id=..., labels={...}, resolve_after_minutes=5, confirm=True)`.
