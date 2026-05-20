# Silence Test Guide — Alertmanager MCP Server

**Target workflow**: Maintenance Silence Lifecycle
**Tools tested**: `am_list_silences`, `am_create_silence`, `am_update_silence`, `am_expire_silence`, `am_preview_silence`, `am_silence_alert`, `am_validate_silence_policy`
**Guided prompt**: `am-maintenance-silence-guided`
**Cluster impact**: create/update/expire MUTATE Alertmanager state

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Alertmanager instance | Running with active alerts |
| Alertmanager MCP Server | Running (`uv run alertmanager-mcp-server`) |

---

## 2. Test Scenarios

### Scenario A: Full Silence Lifecycle (Preview → Create → Extend → Expire)

| Step | Action | Tool |
|------|--------|------|
| 1 | Preview blast radius | `am_preview_silence(backend_id="default", matchers=[{"name": "service", "value": "checkout", "isRegex": false, "isEqual": true}])` |
| 2 | Validate policy | `am_validate_silence_policy(backend_id="default", matchers=[{"name": "service", "value": "checkout", "isRegex": false, "isEqual": true}], duration_minutes=120, comment="Deploy v2.3", created_by="alice")` |
| 3 | Create silence | `am_create_silence(backend_id="default", matchers=[{"name": "service", "value": "checkout", "isRegex": false, "isEqual": true}], duration_minutes=120, comment="Deploy v2.3", created_by="alice")` |
| 4 | Confirm creation | `am_list_silences(backend_id="default", state="active")` |
| 5 | Extend by 30 min | `am_update_silence(backend_id="default", silence_id="<id_from_step_3>", add_minutes=30)` |
| 6 | Expire silence | `am_expire_silence(backend_id="default", silence_id="<id_from_step_5>")` |
| 7 | Confirm expiration | `am_list_silences(backend_id="default", state="active")` |

**Expected**:
- Step 1: Returns `affected_alert_count`, `affected_alerts_preview`, `would_affect_receivers`, `summary_text`, `warning_flag`
- Step 2: Returns `{allowed: true, violations: []}`
- Step 3: Returns `{silence_id: "...", silence: {...}}`
- Step 5: Returns `{new_silence_id: "...", silence: {...}}`
- Step 6: Returns `{success: true, message: "..."}`

### Scenario B: Safety Guardrails

| Step | Action | Expected |
|------|--------|----------|
| 1 | Duration exceeds cap | `am_create_silence(..., duration_minutes=2000)` | Error: "Duration 2000m exceeds 1440m cap." |
| 2 | Duplicate silence | Create same silence twice | Warning: "An equivalent active silence already exists." |
| 3 | Broad matcher policy | `am_validate_silence_policy(..., matchers=[{"name": "severity", "value": "critical", ...}])` | Violation: severity-only is too broad |
| 4 | Missing comment | `am_validate_silence_policy(..., comment="")` | Violation: non-empty comment required |
| 5 | Missing created_by | `am_validate_silence_policy(..., created_by="")` | Violation: non-empty created_by required |

### Scenario C: Silence Alert Helper (LLM-Friendly)

| Step | Action | Tool |
|------|--------|------|
| 1 | Silence by labels (service scope) | `am_silence_alert(backend_id="default", alert_labels={"alertname": "HighCPU", "service": "api", "env": "prod"}, scope="service", duration_minutes=60)` |
| 2 | Silence by labels (instance scope) | `am_silence_alert(backend_id="default", alert_labels={"alertname": "HighCPU", "service": "api", "env": "prod", "instance": "10.0.1.5:8080"}, scope="instance")` |
| 3 | Silence by labels (env scope) | `am_silence_alert(backend_id="default", alert_labels={"alertname": "HighCPU", "service": "api", "env": "prod"}, scope="env")` |
| 4 | Silence by fingerprint | `am_silence_alert(backend_id="default", alert_fingerprint="abc123def456", scope="service")` |

**Expected**:
- Step 1: Derives matchers from `alertname`, `service`, `env` only (service scope)
- Step 2: Derives matchers from all labels (instance scope)
- Step 3: Derives matchers from `env` only (broadest)
- Step 4: Looks up alert by fingerprint, then derives matchers
- All return: `{silence_id, silence, derived_matchers}`

### Scenario D: Silence Listing with Filters

| Step | Action | Tool |
|------|--------|------|
| 1 | Active silences | `am_list_silences(backend_id="default", state="active")` |
| 2 | Expired silences | `am_list_silences(backend_id="default", state="expired")` |
| 3 | Paginated listing | `am_list_silences(backend_id="default", limit=10, offset=0)` |

**Expected**: Returns `{silences: [...], has_more, next_offset}`

### Scenario E: Update with Explicit End Time

| Step | Action | Tool |
|------|--------|------|
| 1 | Set new end time | `am_update_silence(backend_id="default", silence_id="<id>", new_ends_at="2025-06-15T18:00:00+00:00")` |
| 2 | Update comment | `am_update_silence(backend_id="default", silence_id="<id>", add_minutes=15, comment="Extended — rollback in progress")` |

### Scenario F: Error Cases

| Step | Action | Expected Error |
|------|--------|----------------|
| 1 | Missing both params | `am_update_silence(backend_id="default", silence_id="<id>")` | "Provide 'add_minutes' or 'new_ends_at'." |
| 2 | Missing input for silence_alert | `am_silence_alert(backend_id="default")` | "Either 'alert_fingerprint' or 'alert_labels' is required." |
| 3 | Fingerprint not found | `am_silence_alert(backend_id="default", alert_fingerprint="nonexistent")` | "Alert with given fingerprint not found." |
| 4 | Missing alertname in push | `am_push_test_alert(backend_id="default", alert_labels={"severity": "warning"})` | "alert_labels must include 'alertname'." |

---

## 3. Natural Language Prompts

```text
Preview: how many alerts would be suppressed if I silence service="checkout" in env="prod"?
```

```text
Create a 2-hour silence for the checkout service in production. Comment: "Deploying v2.3". Created by alice.
```

```text
Extend silence abc-123 by 30 minutes — the deployment is still running.
```

```text
Expire silence abc-123 — maintenance is complete.
```

```text
Quickly silence the HighCPU alert for the api-server service. Use service scope, 1 hour.
```

```text
Validate this silence before I create it: match service="payments" for 4 hours, comment "DB migration", created by bob.
```

```text
Walk me through creating a maintenance silence for the payments service in prod for 2 hours.
```
