# Alertmanager Severity & Triage Response Matrix

| Severity | Expected Action | Grouping Strategy | Escalation & Suppression Guidance |
| :--- | :--- | :--- | :--- |
| **`Watchdog` missing / suppressed** | Immediate pipeline check | Global (`alertname="Watchdog"`) | Verify Prometheus $\to$ Alertmanager connectivity and expire any silence matching `Watchdog`. |
| **`critical` / `page`** | Immediate human response | Group by `cluster`, `service`, `alertname` | Identify upstream infrastructure failures first; check `inhibitedBy` to avoid chasing downstream symptoms. |
| **`warning` / `ticket`** | Sub-hour investigation or shift queue | Group by `service`, `alertname` | Correlate with recent deployments or expiring maintenance silences. |
| **`info` / `none`** | Informational context only | Group by `team`, `service` | Should never page on-call; if routing to paging receivers, flag for `auditing-alertmanager-governance`. |

## Alert Storm Heuristics

1. **Shared Node / Zone Failure**: Multiple services firing `InstanceDown`, `PodCrashLooping`, or `HighLatency` in the same `zone` or `node` $\to$ treat the infrastructure alert as primary.
2. **Database / Dependency Saturation**: Upstream `PostgresConnectionsExhausted` firing alongside downstream `API5xxSpike` $\to$ prioritize the upstream dependency; verify whether an inhibition rule should suppress downstream paging.
3. **Flapping Alerts**: Alerts with recent `startsAt` resets across multiple instances $\to$ inspect `group_wait` and `group_interval` on the matched route via `am_explain_routing`.
