# Governance & Routing Test Guide — Alertmanager MCP Server

**Target workflows**: Routing & Notification Audit, Integration Testing, Governance & Compliance Review
**Tools tested**: `am_explain_routing`, `am_audit_default_route`, `am_list_recent_changes`, `am_validate_silence_policy`, `am_push_test_alert`
**Resources used**: `am://system/config`, `am://system/receivers`, `am://system/audit-log`
**Guided prompt**: `am-integration-test-guided`

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Alertmanager instance | Running with configured routing and receivers |
| Alertmanager MCP Server | Running (`uv run alertmanager-mcp-server`) |

---

## 2. Test Scenarios

### Scenario A: Routing Tree Inspection

| Step | Action | Resource |
|------|--------|----------|
| 1 | Inspect routing tree | **Resource**: `am://system/config` |

**Expected**: Returns the full routing tree with nested route structure, matchers, `group_by` labels, receivers, and inhibition rules (secrets redacted).

### Scenario B: Receiver Enumeration

| Step | Action | Resource |
|------|--------|----------|
| 1 | List receivers | **Resource**: `am://system/receivers` |

**Expected**: Returns configured receivers with names, integration types (slack, pagerduty, email, webhook, opsgenie, sns, victorops, pushover, wechat, or unknown), and redacted config details.

### Scenario C: Routing Simulation

| Step | Action | Tool | Expected |
|------|--------|------|----------|
| 1 | Critical alert routing | `am_explain_routing(backend_id="default", labels={"alertname": "HighCPU", "service": "api", "severity": "critical", "env": "prod"})` | Routes to PagerDuty/critical receiver |
| 2 | Warning alert routing | `am_explain_routing(backend_id="default", labels={"alertname": "HighCPU", "service": "api", "severity": "warning", "env": "prod"})` | Routes to Slack/warning receiver |
| 3 | Unknown alert routing | `am_explain_routing(backend_id="default", labels={"alertname": "NewAlert"})` | Falls through to default receiver |

**Expected for each**: Returns `{matched_route, receivers, group_labels, inhibited_by, explanation}`

### Scenario D: Default Route Audit

| Step | Action | Tool |
|------|--------|------|
| 1 | Full audit | `am_audit_default_route(backend_id="default")` |
| 2 | Limited results | `am_audit_default_route(backend_id="default", limit=5)` |

**Expected**:
- If no alerts hit default: `summary_text` confirms "No active alerts are hitting the default route. Routing looks well configured."
- If alerts hit default: `summary_text` lists alert names and recommends adding specific routes

### Scenario E: Integration Testing (Full Pipeline)

| Step | Action | Tool / Resource |
|------|--------|-----------------|
| 1 | Check receivers | **Resource**: `am://system/receivers` |
| 2 | Simulate routing | `am_explain_routing(backend_id="default", labels={"alertname": "MCPIntegrationTest", "team": "sre", "severity": "warning"})` |
| 3 | Push test alert | `am_push_test_alert(backend_id="default", alert_labels={"alertname": "MCPIntegrationTest", "team": "sre", "severity": "warning"}, annotations={"summary": "Test alert from Alertmanager MCP"})` |
| 4 | Verify in alert list | `am_list_alerts(backend_id="default", alertname="MCPIntegrationTest")` |

**Expected**:
- Step 2: Confirms which receiver handles the test alert
- Step 3: Returns `{status: "ok", result: {...}}`
- Step 4: Test alert appears in active alert list

### Scenario F: Config Export & Inspection

| Step | Action | Resource |
|------|--------|----------|
| 1 | Export current config | **Resource**: `am://system/config` |

**Expected**: Returns the full effective configuration including the routing tree and inhibition rules with secrets redacted. Use this for Git diffing or compliance review.

### Scenario G: Silence Change Audit

| Step | Action | Tool |
|------|--------|------|
| 1 | Last 24 hours | `am_list_recent_changes(backend_id="default", hours=24)` |
| 2 | Last 48 hours | `am_list_recent_changes(backend_id="default", hours=48)` |

**Expected**: Returns `{changes: [{silence_id, action, matchers_summary, created_by, comment, timestamp}, ...], summary_text}` where action is "created" or "expired".

### Scenario H: MCP Audit Log

| Step | Action | Resource |
|------|--------|----------|
| 1 | View audit log | `am://system/audit-log` |

**Expected**: Returns `{entries: [{backend_id, operation, principal, summary, timestamp}, ...]}`

---

## 3. Natural Language Prompts

```text
Show me the current routing tree and inhibition rules.
```

```text
List all notification receivers — Slack, PagerDuty, email, webhooks.
```

```text
Who gets paged when a critical alert fires for the api-server in prod?
```

```text
Are any alerts falling through to the default route?
```

```text
Push a test alert to verify that the slack-sre receiver is working.
```

```text
Show me the current Alertmanager configuration for compliance review.
```

```text
Show me all silence changes in the last 24 hours — who created or expired silences?
```

```text
Help me test the notification pipeline for the sre team's Slack channel.
```
