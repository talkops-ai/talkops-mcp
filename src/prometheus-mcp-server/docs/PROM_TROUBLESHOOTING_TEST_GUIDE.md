# Troubleshooting Test Guide — Prometheus MCP Server

**Target workflow**: Troubleshooting Failed Targets
**Tools tested**: `prom_query_instant`, `prom_test_endpoint`, `prom_explore_labels`
**Guided prompt**: `prom-troubleshoot-guided`

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Prometheus instance | Running with active scrape targets |
| Prometheus MCP Server | Running |

---

## 2. Test Scenarios

### Scenario A: Full Troubleshooting Flow

| Step | Action | Tool / Resource |
|------|--------|-----------------|
| 1 | Check failed targets | **Resource**: `prom://topology/failed_targets` |
| 2 | Check up status | **Tool**: `prom_query_instant(backend_id="default", query="up{job='api-server'}")` |
| 3 | Check scrape duration | **Tool**: `prom_query_instant(backend_id="default", query="scrape_duration_seconds{job='api-server'}")` |
| 4 | Test endpoint directly | **Tool**: `prom_test_endpoint(endpoint_url="http://api-server.default:8080/metrics")` |
| 5 | Check cardinality | **Tool**: `prom_get_cardinality(backend_id="default")` |

### Scenario B: Common Failure Diagnosis

| Symptom | Diagnostic Query | Root Cause |
|---------|-----------------|------------|
| `up{job="x"} == 0` | Check endpoint directly with test_endpoint | Connection refused, wrong port, pod not running |
| `scrape_duration_seconds > 10` | High cardinality check | Endpoint too slow, too many metrics |
| test_endpoint returns `ok: false` | Check errors array | Invalid format, auth required, endpoint not found |
| No up{} series at all | Check `prom://topology/services` | ServiceMonitor not applied, wrong labels |

### Scenario C: Service Topology Inspection

| Step | Action | Resource |
|------|--------|----------|
| 1 | View all services | `prom://topology/services` |
| 2 | View failed targets | `prom://topology/failed_targets` |
| 3 | View backend health | `prom://system/backends` |
| 4 | Check runtime config | `prom://config/runtime` |

---

## 3. Natural Language Prompts

```text
Show me all failed scrape targets — which services are down?
```

```text
Is the "api-server" job up and being scraped by Prometheus?
```

```text
Test if http://api-server.default:8080/metrics is returning valid metrics.
```

```text
Help me troubleshoot why the "api-server" job is down in the "default" namespace.
```

```text
What is the scrape duration for the "api-server" job — is it timing out?
```

```text
Show me all services being monitored and their health status.
```
