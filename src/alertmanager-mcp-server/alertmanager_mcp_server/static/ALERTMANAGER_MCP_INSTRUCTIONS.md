# Alertmanager MCP Execution Server

Provides typed execution primitives and read-only state resources for Prometheus Alertmanager API v2.

## Capabilities by Toolset
- **triage**: `am_summarize_oncall`, `am_list_alerts`, `am_list_alert_groups`
- **routing**: `am_check_notification_health`, `am_explain_routing`, `am_push_test_alert` (mutating)
- **silences**: `am_list_silences`, `am_preview_silence`, `am_create_silence` (mutating), `am_silence_alert` (mutating), `am_update_silence` (mutating), `am_expire_silence` (mutating)
- **governance**: `am_audit_alert_hygiene`, `am_audit_silences`

## Resources (`am://`)
- `am://backends`, `am://backends/{backend_id}`, `am://backends/{backend_id}/config`, `am://backends/{backend_id}/receivers`
- `am://backends/{backend_id}/alerts/active`, `am://backends/{backend_id}/alerts/groups`, `am://backends/{backend_id}/alerts/{fingerprint}`
- `am://backends/{backend_id}/silences/active`, `am://backends/{backend_id}/silences/{silence_id}`, `am://audit-log`

## Safety Guardrails
- **Read-Only Default**: Mutating tools require `MCP_ALLOW_WRITE=true` (or `--allow-write`).
- **Silence Policy (`SP001`–`SP010`)**: Rejects wildcard/empty matchers, sole broad environment/severity matchers, Watchdog silences, naive timestamps without timezone offsets, durations exceeding `AM_MAX_SILENCE_MINUTES`, and missing `created_by`/`comment`.
- **Confirmation Gate**: High-blast-radius silences, silence expiration, and live test alerts trigger MCP elicitation or require `confirm=True`.
