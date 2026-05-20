# Alertmanager Best Practices

## Silence Safety

- Always preview silence effects before creation using `am_helper_mgmt(action="preview_silence")`
- Keep silences short: use `duration_minutes` instead of open-ended windows
- Max recommended duration: 24 hours (configurable via `AM_MAX_SILENCE_MINUTES`)
- Always include `created_by` and `comment` for auditability
- Prefer narrow matchers: `alertname` + `service` + `env` over broad labels like `severity`

## Alert Hygiene

- Every alert should have `summary`, `description`, and `runbook_url` annotations
- Use a consistent severity taxonomy: `warning`, `critical`
- Use `for` clauses in Prometheus rules to prevent flapping
- Labels are for routing; annotations are for human-readable context

## Routing Best Practices

- Use `simulate_routing` to verify alert routing before production deployment
- Test new receiver integrations with `push_test` before relying on them
- Avoid catch-all routes that send all alerts to a single channel

## Inhibition Rules

- Use inhibitions to suppress symptoms when the root cause alert is already firing
- Example: `DataCenterOffline` should inhibit `ServiceDown` alerts
- Always set `equal` labels to scope inhibition correctly

## Context Window Protection

- Use `limit` and `offset` parameters for large alert sets
- Default limit is 50 alerts per request to protect LLM context
- Use label filters to narrow results instead of paginating through all alerts
