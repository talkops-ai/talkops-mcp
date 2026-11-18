# Notification Pipeline Diagnostic Decision Tree

```mermaid
flowchart TD
    A["User reports missed notification"] --> G1["Gate 1: am_list_alerts(state='all')"]
    G1 -- "Not found" --> P1["Alert never reached Alertmanager (check Prometheus rules & Watchdog)"]
    G1 -- "Found" --> G2["Gate 2 & 3: am_explain_routing(fingerprint=...)"]
    G2 -- "matching_silences non-empty" --> P2["Suppressed by active silence (inspect am://backends/{id}/silences/{sid})"]
    G2 -- "is_inhibited == true" --> P3["Suppressed by firing source alert via inhibit_rules"]
    G2 -- "Not silenced/inhibited" --> G4["Gate 4: Inspect route_trace & receivers"]
    G4 -- "Wrong receiver or default fallback" --> P4["Routing mismatch (sibling continue:false shadow or label mismatch)"]
    G4 -- "Expected receiver matched" --> G5["Gate 5: Check muted_receivers & timers"]
    G5 -- "muted == true" --> P5["Suppressed by mute_time_intervals or outside active_time_intervals"]
    G5 -- "Active receiver" --> G6["Gate 6: am_check_notification_health()"]
    G6 -- "notifications_failed_total > 0" --> P6["Downstream integration HTTP/auth/TLS error"]
    G6 -- "0 failures" --> P7["Delayed by group_wait / group_interval / repeat_interval or filtered downstream"]
```

## Timing & Deduplication Nuances

- **`group_wait` (default `30s`)**: Initial buffer before sending the first notification for a newly created alert group.
- **`group_interval` (default `5m`)**: Minimum wait before sending a notification when a *new* alert is added to an *already-notified* group.
- **`repeat_interval` (default `4h`)**: Minimum wait before re-sending the exact same group if no alerts were added or resolved.
- **`send_resolved` (default varies by integration)**: If a brief spike resolved before `group_wait` elapsed, or if `send_resolved: false`, no recovery notification is sent.
