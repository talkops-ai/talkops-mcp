# Alertmanager Governance Audit Report Template

```markdown
## Alertmanager Governance & Hygiene Audit — `<backend_id>`

### 1. Executive Summary
- **Pipeline Status**: `<healthy|degraded|unhealthy>` | **Watchdog**: `<firing|missing|suppressed>`
- **Active Alerts Audited**: `<total_active_alerts>`
- **Unrouted (Default Route) Alerts**: `<default_route_count>` (Receiver: `<default_receiver>`)
- **Missing Required Annotations**: `<missing_annotations_count>`
- **Active Silences**: `<active_silences_count>` (`<policy_violations_count>` non-compliant, `<stale_count>` matching 0 alerts)

### 2. Routing & Alert Hygiene Findings
- **Default Route Leakage**: `<list alertnames and suggested_matchers>`
- **Annotation Gaps**: `<list alertnames missing summary or runbook_url>`
- **Chronic Long-Firing Alerts (>24h)**: `<list alertnames and firing_hours>`

### 3. Silence Governance Findings
- **Non-Compliant Active Silences**: `<silence IDs, creators, and SP001-SP009 violations>`
- **Stale Zero-Match Cleanup Candidates**: `<silence IDs matching 0 active alerts>`
- **Expiring Soon (<2h)**: `<silence IDs and silenced_alert_count>`
```
