# Triage Test Guide — Alertmanager MCP Server

**Target workflow**: On-Call Alert Triage
**Tools tested**: `am_list_alerts`, `am_list_alert_groups`, `am_summarize_oncall`, `am_explain_routing`
**Guided prompt**: `am-alert-triage-guided`

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Alertmanager instance | Running with active alerts |
| Alertmanager MCP Server | Running (`uv run alertmanager-mcp-server`) |

---

## 2. Test Scenarios

### Scenario A: On-Call Summary

| Step | Action | Tool |
|------|--------|------|
| 1 | Full on-call summary | `am_summarize_oncall(backend_id="default")` |
| 2 | Filtered by environment | `am_summarize_oncall(backend_id="default", env="prod")` |
| 3 | Filtered by service | `am_summarize_oncall(backend_id="default", service="checkout")` |
| 4 | Filtered by severity | `am_summarize_oncall(backend_id="default", severity="critical")` |

**Expected**:
- Step 1: Returns `summary_text` with severity/service breakdown, `total_alerts`, `by_severity`, `by_service`, `top_groups`
- Step 2–4: Returns filtered results matching the specified criteria

### Scenario B: Alert Listing with Filters

| Step | Action | Tool | Expected |
|------|--------|------|----------|
| 1 | List all active | `am_list_alerts(backend_id="default")` | Returns `{alerts: [...], has_more, next_offset}` |
| 2 | Filter by alertname | `am_list_alerts(backend_id="default", alertname="HighCPU")` | Only HighCPU alerts |
| 3 | Filter by severity | `am_list_alerts(backend_id="default", severity="critical")` | Only critical alerts |
| 4 | Filter by state | `am_list_alerts(backend_id="default", state="suppressed")` | Only silenced/inhibited alerts |
| 5 | Filter by receiver | `am_list_alerts(backend_id="default", receiver="slack-sre")` | Only alerts routed to slack-sre |
| 6 | Custom label filters | `am_list_alerts(backend_id="default", label_filters={"env": "prod", "service": "api"})` | Alerts matching both labels |
| 7 | Pagination | `am_list_alerts(backend_id="default", limit=10, offset=10)` | Second page of 10 alerts |

### Scenario C: Alert Groups

| Step | Action | Tool |
|------|--------|------|
| 1 | List groups | `am_list_alert_groups(backend_id="default")` |

**Expected**: Returns list of groups with `labels` and `alerts` arrays, reflecting Alertmanager's `group_by` configuration.

### Scenario D: Routing Explanation

| Step | Action | Tool |
|------|--------|------|
| 1 | Explain routing | `am_explain_routing(backend_id="default", labels={"alertname": "HighCPU", "service": "api", "severity": "critical", "env": "prod"})` |
| 2 | Check unknown alert | `am_explain_routing(backend_id="default", labels={"alertname": "NewAlert", "service": "unknown"})` |

**Expected**:
- Step 1: Returns `matched_route`, `receivers`, `group_labels`, `inhibited_by`, `explanation`
- Step 2: Should route to the default receiver (identifies potential misconfiguration)

### Scenario E: Default Route Audit

| Step | Action | Tool |
|------|--------|------|
| 1 | Audit default route | `am_audit_default_route(backend_id="default")` |
| 2 | With custom limit | `am_audit_default_route(backend_id="default", limit=5)` |

**Expected**: Returns `default_receiver`, `alert_count`, `alerts`, `summary_text`

---

## 3. Natural Language Prompts

```text
Give me an on-call summary — what's firing right now on the default backend?
```

```text
Show me all critical alerts for the "api-server" service in prod.
```

```text
How does Alertmanager group the active alerts?
```

```text
Who gets paged when a critical HighLatency alert fires for the checkout service?
```

```text
Are there any alerts falling through to the default route?
```

```text
Guide me through triaging alerts for the checkout service in prod.
```
