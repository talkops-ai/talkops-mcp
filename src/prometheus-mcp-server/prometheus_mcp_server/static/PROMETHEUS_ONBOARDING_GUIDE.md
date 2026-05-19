# Prometheus Onboarding Guide

## Getting Started

This guide helps you onboard your application to Prometheus monitoring with zero prior experience.

## Step 1: Choose Your Approach

| Your Situation | Approach | Tool |
|---|---|---|
| Custom app (Go/Java/Python/Node) | Direct instrumentation | `prom_instrumentation_mgmt(action="recommend_strategy")` |
| Third-party system (DB, web server) | Exporter | `prom_exporter_mgmt(action="recommend")` |
| Spring Boot / Django (with builtin) | Builtin metrics | `prom_instrumentation_mgmt(action="recommend_strategy")` |

## Step 2: Instrument or Deploy

### For Direct Instrumentation:
1. Generate code: `prom_instrumentation_mgmt(action="generate_snippet", language="python", metrics_profile="http_server")`
2. Add the snippet to your app
3. Deploy your app

### For Exporters:
1. Choose exporter: `prom_exporter_mgmt(action="recommend", service_type="postgres")`
2. Install: `prom_exporter_mgmt(action="install", exporter_type="postgres_exporter", namespace="default")`

## Step 3: Validate

Test that your app/exporter exposes valid metrics:
```
prom_instrumentation_mgmt(action="test_endpoint", endpoint_url="http://your-service:port/metrics")
```

## Step 4: Wire to Prometheus

### Kubernetes (ServiceMonitor):
```
prom_scrape_config_mgmt(action="apply_servicemonitor", namespace="default", service_name="my-app")
```

### VM/Legacy (file_sd):
```
prom_scrape_config_mgmt(action="manage_file_sd", file_sd_path="/etc/prometheus/file_sd/targets.json", targets=["host:9090"])
```

## Step 5: Verify

Query Prometheus to confirm metrics are flowing:
```
prom_query_mgmt(action="instant", backend_id="default", query="up{job='my-app'}")
```
