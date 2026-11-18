# Alertmanager Operational Governance Checklist

1. **Dead-Man's-Switch (`Watchdog`)**:
   - [ ] `Watchdog` alert is actively firing (`watchdog_status == "firing"`).
   - [ ] `Watchdog` is never silenced or inhibited.
2. **Routing Completeness**:
   - [ ] `default_route_count == 0` (every production alert matches an explicit team/service child route).
   - [ ] `alertmanager_config_last_reload_successful == 1`.
   - [ ] Zero receiver integrations have `notifications_failed_total > 0`.
3. **Alert Quality & Taxonomy**:
   - [ ] Every active alert carries `severity` $\in \{\text{critical}, \text{warning}, \text{info}\}$, `service`, and `env`.
   - [ ] Every active alert includes `annotations.summary` and `annotations.runbook_url`.
   - [ ] Alerts firing continuously for $> 24\text{h}$ are reviewed for alert fatigue.
4. **Silence Hygiene**:
   - [ ] Zero active silences violate `SP001`–`SP009`.
   - [ ] Stale silences matching 0 alerts after maintenance completion are expired.
   - [ ] Silences expiring within 2 hours with `silenced_alert_count > 0` have an assigned owner.
