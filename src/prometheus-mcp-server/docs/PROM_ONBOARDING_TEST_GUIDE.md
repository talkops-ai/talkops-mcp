# Onboarding Test Guide — Prometheus MCP Server

**Target workflows**: K8s App Onboarding, Exporter Onboarding, VM/Legacy Onboarding
**Tools tested**: `prom_recommend_instrumentation`, `prom_test_endpoint`, `prom_apply_servicemonitor`
**Strategies**: Direct instrumentation, Exporter-based, Builtin metrics

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Test Scenarios](#2-test-scenarios)
3. [Natural Language Prompts](#3-natural-language-prompts)

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Prometheus instance | Accessible at `PROMETHEUS_BASE_URL` |
| Prometheus MCP Server | Running (`uv run prometheus-mcp-server`) |
| Kubernetes cluster | Accessible via kubeconfig (for K8s scenarios) |
| Prometheus Operator | Installed (for ServiceMonitor scenarios) |

---

## 2. Test Scenarios

### Scenario A: K8s App Onboarding (Full Lifecycle)

| Step | Action | Tool / Resource |
|------|--------|-----------------|
| 1 | Verify backend | **Resource**: `prom://system/backends/default` |
| 2 | Recommend strategy | **Tool**: `prom_recommend_instrumentation(workload_type="custom_app", language="python", environment="kubernetes")` |
| 3 | User deploys app | *(Manual)* |
| 4 | Test endpoint | **Tool**: `prom_test_endpoint(endpoint_url="http://my-app.default:8080/metrics")` |
| 5 | Apply ServiceMonitor | **Tool**: `prom_apply_servicemonitor(namespace="default", service_name="my-app")` |
| 6 | Explore labels | **Tool**: `prom_explore_labels(backend_id="default", metric_name="http_requests_total")` |
| 7 | Verify ingestion | **Tool**: `prom_query_instant(backend_id="default", query="rate(http_requests_total[5m])")` |

**Expected Results**:
- Step 2: Returns `strategy: "direct_instrumentation"` with `recommended_client_library: "prometheus_client"`
- Step 4: Returns `ok: true` with metrics count and format
- Step 5: Returns ServiceMonitor YAML with auto-detected operator labels

### Scenario B: Strategy Recommendations by Workload

| Workload | Language | Framework | Expected Strategy |
|----------|----------|-----------|-------------------|
| `custom_app` | `python` | — | `direct_instrumentation` |
| `custom_app` | `go` | — | `direct_instrumentation` |
| `custom_app` | `java` | `spring_boot` | `builtin_metrics` |
| `postgres` | — | — | `exporter` (postgres_exporter) |
| `redis` | — | — | `exporter` (redis_exporter) |
| `nginx` | — | — | `exporter` (nginx_exporter) |
| `unknown_system` | — | — | `exporter` (unknown_system_exporter) |



### Scenario D: VM/Legacy Onboarding (file_sd)

| Step | Action | Tool |
|------|--------|------|
| 1 | Recommend strategy | `prom_recommend_instrumentation(workload_type="custom_app", language="python", environment="vm")` |
| 2 | Test endpoint | `prom_test_endpoint(endpoint_url="http://10.0.1.5:8080/metrics")` |
| 3 | Add file_sd target | `prom_manage_file_sd(file_sd_path="/tmp/targets.json", targets=["10.0.1.5:8080"], target_labels={"job": "my-app"}, backend_id="default")` |
| 4 | Verify | `prom_query_instant(backend_id="default", query="up{job='my-app'}")` |

### Scenario E: ServiceMonitor with Custom Labels

| Step | Action | Tool |
|------|--------|------|
| 1 | Apply with custom labels | `prom_apply_servicemonitor(namespace="default", service_name="my-app", port_name="http", path="/metrics", interval="15s", labels={"release": "kube-prometheus"})` |

**Expected**: ServiceMonitor YAML includes both auto-detected operator labels and user-provided `release` label.

---

## 3. Natural Language Prompts

```text
What's the best way to add Prometheus monitoring to my Python web application running on Kubernetes?
```

```text
Generate Prometheus instrumentation code for my Go HTTP server.
```

```text
Test if http://my-app.default:8080/metrics exposes valid Prometheus metrics.
```

```text
Create a ServiceMonitor for service "my-app" in the "default" namespace with a 15-second scrape interval.
```

```text
Add my VM target 10.0.1.5:8080 to the file_sd config at /etc/prometheus/file_sd/targets.json with job label "api-server".
```

```text
Guide me through the full onboarding flow for my Python app "api-server" in the "production" namespace.
```
