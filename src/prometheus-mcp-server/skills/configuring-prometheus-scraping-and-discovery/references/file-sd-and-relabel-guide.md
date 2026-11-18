# File Service Discovery (`file_sd`) and Target Relabeling Guide

## 1. File SD (`kind="file_sd"`) Target Structure

When Prometheus runs on VMs, Docker Compose, or bare metal with `file_sd_configs`, pass `kind="file_sd"` to `prom_apply_scrape_config`:

```json
{
  "file_path": "/etc/prometheus/file_sd/prod-nodes.json",
  "targets": [
    "10.0.10.11:9100",
    "10.0.10.12:9100"
  ],
  "labels": {
    "job": "node-exporter",
    "env": "production",
    "region": "us-east-1"
  },
  "trigger_reload": true
}
```
- Prometheus watches `file_sd` JSON/YAML files via `inotify` and reloads targets automatically; when `trigger_reload: true`, `prom_apply_scrape_config` also invokes `POST /-/reload`.

## 2. Common Scrape Target Failure Diagnostics (`prom://topology/targets`)

| `lastError` Message | Root Cause | Fix |
| :--- | :--- | :--- |
| `dial tcp ...: connect: connection refused` | Exporter/app is not listening on the target port or bound to `127.0.0.1` instead of `0.0.0.0` | Verify container `ports[].containerPort` and bind address. |
| `context deadline exceeded` | Target took longer than `scrape_timeout` to respond (often heavy database/SNMP queries) | Increase `scrapeTimeout` (must be $\le$ `interval`) or split slow collectors. |
| `server returned HTTP status 401 Unauthorized` / `403 Forbidden` | Missing `bearerTokenSecret` or `basicAuth` in `ServiceMonitor.spec.endpoints[]` | Configure Kubernetes `Secret` reference in endpoint auth block. |
| `expected a valid start token, got "<"` | Scrape path hit an HTML page (e.g. `/` instead of `/metrics`) | Set `path: "/metrics"` (or `/actuator/prometheus` for Spring Boot). |
