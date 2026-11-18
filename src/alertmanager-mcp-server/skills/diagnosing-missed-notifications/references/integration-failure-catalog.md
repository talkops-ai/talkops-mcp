# Alertmanager Integration Failure Catalog

| Integration | Common Root Causes (`alertmanager_notifications_failed_total`) | Diagnostic Checks in `am://backends/{id}/receivers` |
| :--- | :--- | :--- |
| **`slack`** | Expired/revoked incoming webhook URL, archived channel, rate-limiting (HTTP 429), bot removed from private channel. | Verify `channel`, `http_config` proxy settings, and whether `api_url` is overridden at the receiver level vs. global. |
| **`pagerduty`** | Invalid `routing_key` (Events API v2) vs `service_key` (Events API v1), severity mapping mismatch, outbound firewall blocking `events.pagerduty.com`. | Check whether `routing_key` or `service_key` is present and verify `url` endpoint version. |
| **`opsgenie`** | Team API key lacks alert creation permission, EU vs US API endpoint mismatch (`api.eu.opsgenie.com` vs `api.opsgenie.com`). | Inspect `api_url` region and `responders` structure. |
| **`email`** | SMTP TLS handshake failure (`require_tls`), expired app password, sender domain SPF/DMARC rejection. | Check `smarthost`, `from`, `require_tls`, and `auth_username`. |
| **`webhook`** | Target endpoint returning HTTP 5xx or timing out (>10s), mTLS certificate expiration, bearer token rotation. | Check `url`, `max_alerts`, and `http_config.tls_config`. |
| **Config Reload (`config_reload_successful=false`)** | Syntax error in `alertmanager.yml`, invalid regex in `match_re`/`matchers`, undefined receiver referenced by a route. | Run `validating-alertmanager-routing` skill's `lint_alertmanager_config.py` against the config. |
