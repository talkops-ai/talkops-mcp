# On-Call Triage & Shift Handover Template

```markdown
## Alertmanager On-Call Triage Report — `<backend_id>`

- **Timestamp (UTC)**: `<YYYY-MM-DDTHH:MM:SSZ>`
- **Pipeline Health**: Watchdog `<firing|missing|suppressed>` | Active Alerts: `<N>` | Suppressed: `<M>` | Active Silences: `<K>`

### 1. Critical Firing Incidents (Action Required)
| Alertname | Service / Env | Instances | Firing Since | Receiver | Runbook / Summary |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `<alertname>` | `<service>` (`<env>`) | `<count>` | `<startsAt>` | `<receiver>` | `<summary>` (`<runbook_url>`) |

### 2. Root-Cause vs. Symptom Correlation
- **Primary Upstream Alerts**: `<list of root-cause alerts>`
- **Inhibited Downstream Alerts**: `<count and alertnames suppressed by inhibition>`

### 3. Active Maintenance & Silences Affecting Triage
- `<silence_id>` (`<created_by>`): `<comment>` — expires at `<endsAt>`

### 4. Recommended Next Steps for Incoming On-Call
1. `<Immediate action for top critical incident>`
2. `<Follow-up on expiring silences or long-firing warnings>`
```
