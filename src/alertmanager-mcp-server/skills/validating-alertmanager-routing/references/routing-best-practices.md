# Alertmanager Routing Tree Best Practices

## 1. Root Route Design
- Always configure a dedicated catch-all receiver on the root route (e.g., `receiver: default-triage-slack`) so unrouted alerts are visible and auditable via `am_audit_alert_hygiene`.
- Set sensible root `group_by` defaults: `['alertname', 'cluster', 'service']`. Avoid `group_by: ['...']` (which disables grouping) except on `Watchdog`.

## 2. First-Child `Watchdog` Route
Place the `Watchdog` / `DeadMansSwitch` route as the **first child** of the root route with `continue: false` and a short `repeat_interval` (`1m`–`5m`):
```yaml
route:
  receiver: default-slack
  group_by: ["alertname", "service", "env"]
  routes:
    - matchers:
        - alertname="Watchdog"
      receiver: deadmanssnitch
      group_wait: 0s
      group_interval: 1m
      repeat_interval: 1m
      continue: false
```

## 3. Dual Delivery via `continue: true`
When an alert should both post to a team Slack channel AND page PagerDuty for `severity="critical"`:
- Either nest the `severity="critical"` PagerDuty route inside the team route with `continue: true` on the first child, or place the Slack archive route first with `continue: true` followed by the PagerDuty route (`continue: false`).
- Remember: in Alertmanager `Route.Match`, if any child route matches, the parent route's own `receiver` is **not** used unless no child matches!

## 4. Safe `inhibit_rules` Design
- Always specify non-overlapping `source_matchers` and `target_matchers` (e.g., `source_matchers: ['severity="critical"']`, `target_matchers: ['severity="warning"']`).
- Always include scoping labels in `equal` (e.g., `equal: ['env', 'cluster', 'service']`) so a critical alert in `service="auth"` never inhibits a warning in `service="payments"`.
