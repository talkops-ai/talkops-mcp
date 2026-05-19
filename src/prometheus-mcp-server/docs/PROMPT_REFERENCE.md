# Prometheus MCP Server — Natural Language Prompt Reference

**For every tool, resource, and prompt documented in [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md), this guide provides ready-to-use natural language prompts you can give to an AI agent.**

Copy any prompt below exactly or adapt it for your backend, namespace, and service names.

> **Design**: Read-only context uses **resources** (`prom://...`). State-changing actions use **tools**.

---

## Table of Contents

1. [PromQL Querying](#promql-querying)
2. [Application Onboarding](#application-onboarding)
3. [Exporter Management](#exporter-management)
4. [Scrape Configuration](#scrape-configuration)
5. [TSDB FinOps & Optimization](#tsdb-finops--optimization)
6. [Rule Management & Authoring](#rule-management--authoring)
7. [Rule Simulation & Testing](#rule-simulation--testing)
8. [Guided Workflow Prompts](#guided-workflow-prompts)
9. [Resource Reads](#resource-reads)

---

## PromQL Querying

> **Tool**: `prom_validate_promql`

```
Validate the PromQL query: rate(http_requests_total{job="api"}[5m])
```
```
Check if this PromQL is valid before running it: sum by (status_code) (rate(http_requests_total[5m]))
```

> **Tool**: `prom_query_instant`

```
Run an instant query on backend "default": rate(http_requests_total[5m])
```
```
What is the current request rate for the "api-server" job?
```
```
Show me the memory usage of all pods: process_resident_memory_bytes
```

> **Tool**: `prom_query_range`

```
Run a range query for rate(http_requests_total[5m]) from 1715000000 to 1715003600.
```
```
Show me the request rate trend over the last hour for the api-server job.
```

> **Tool**: `prom_explore_labels`

```
Show me all labels and their top values for the metric http_requests_total.
```
```
What label dimensions does the metric container_cpu_usage_seconds_total have?
```

---

## Application Onboarding

> **Tool**: `prom_recommend_instrumentation`

```
What's the best way to monitor my Python web application on Kubernetes?
```
```
Recommend an instrumentation strategy for a custom Go application.
```
```
How should I monitor my Spring Boot app — it already has Actuator.
```
```
What's the recommended monitoring approach for a PostgreSQL database?
```

> **Tool**: `prom_test_endpoint`

```
Test if http://my-app.default:8080/metrics exposes valid Prometheus metrics.
```
```
Validate the metrics endpoint at http://10.0.1.5:9090/metrics.
```

---

## Exporter Management

> **Resource**: `prom://exporters/catalog` (browse catalog)

```
Show me all supported Prometheus exporters in the catalog.
```
```
What exporters are available for deployment?
```

> **Tool**: `prom_recommend_exporter`

```
What exporter should I use for monitoring PostgreSQL?
```
```
Recommend an exporter for Redis monitoring on Kubernetes.
```
```
Which exporter works best for Kafka consumer group lag?
```

> **Tool**: `prom_install_exporter`

```
Deploy the postgres_exporter to the "monitoring" namespace.
```
```
Install redis_exporter in the "default" namespace with custom port 9122.
```
```
Deploy node_exporter as a DaemonSet in the "monitoring" namespace.
```
```
Install kube-state-metrics with RBAC in the "monitoring" namespace.
```

> **Tool**: `prom_uninstall_exporter`

```
Remove the postgres_exporter from the "monitoring" namespace.
```
```
Uninstall the redis_exporter from "default" — we no longer need it.
```

> **Tool**: `prom_verify_exporter`

```
Verify the postgres_exporter is working — check endpoint http://postgres-exporter.monitoring:9187/metrics and up{} series for job "postgres_exporter" on backend "default".
```
```
Run an end-to-end health check on the redis_exporter with a 90-second timeout.
```

---

## Scrape Configuration

> **Tool**: `prom_apply_servicemonitor`

```
Create a ServiceMonitor for service "api-server" in the "production" namespace.
```
```
Apply a ServiceMonitor named "redis-monitor" for service "redis-exporter" in "monitoring" with scrape interval 15s.
```
```
Wire up the "postgres-exporter" service to Prometheus via ServiceMonitor in "monitoring" namespace.
```

> **Tool**: `prom_manage_file_sd`

```
Add target 10.0.1.5:9100 to the file_sd config at /etc/prometheus/file_sd/targets.json with job label "node".
```
```
Remove target 10.0.1.5:9100 from the file_sd targets file and reload Prometheus.
```
```
Add multiple VM targets [10.0.1.5:8080, 10.0.1.6:8080] with labels job=api-server and env=prod.
```

---

## TSDB FinOps & Optimization

> **Resource**: `prom://tsdb/cardinality` (read cardinality data)

```
Show me the TSDB cardinality overview — total series and top hotspot metrics.
```
```
What are the highest cardinality metrics in my Prometheus instance?
```

> **Resource**: `prom://config/runtime` (read runtime config)

```
Show me the runtime configuration — scrape interval, retention, TSDB stats.
```
```
What is the current retention period and scrape interval for Prometheus?
```

> **Tool**: `prom_plan_relabel`

```
Generate a relabel config to drop the labels "pod_id" and "container_id" from all metrics.
```
```
Create a metric_relabel_config to drop the entire metric "kubelet_runtime_operations_total".
```
```
Generate a labelkeep config that only keeps job, instance, and namespace labels.
```

> **Tool**: `prom_optimize_cardinality`

```
Analyze the top 10 highest-cardinality metrics and recommend optimization strategies.
```
```
What should I do about the high cardinality of metric "http_request_duration_seconds_bucket"?
```

> **Tool**: `prom_create_recording_rule`

```
Create a recording rule "job:http_requests:rate5m" with expression "sum by (job) (rate(http_requests_total[5m]))".
```
```
Generate a recording rule to pre-compute the p99 latency per service.
```

> **Tool**: `prom_configure_remote_write`

```
Configure remote-write to Thanos Receive at http://thanos-receive:19291/api/v1/receive.
```
```
Generate remote-write config for Mimir at https://mimir.example.com/api/v1/push with a write relabel filter to only send metrics matching "http_.*".
```

---



## Guided Workflow Prompts

These invoke MCP prompts that return structured multi-step workflows:

> **Prompt**: `prom-k8s-app-onboarding-guided`

```
Guide me through onboarding my Python app "api-server" in the "production" namespace to Prometheus on backend "default".
```

> **Prompt**: `prom-k8s-exporter-onboarding-guided`

```
Walk me through deploying a postgres exporter in the "monitoring" namespace on backend "default".
```

> **Prompt**: `prom-vm-legacy-onboarding-guided`

```
Help me onboard my legacy Python app on VM host 10.0.1.5:8080 to Prometheus.
```

> **Prompt**: `prom-query-guided`

```
Guide me through safely querying the http_requests_total metric on backend "default".
```

> **Prompt**: `prom-troubleshoot-guided`

```
Help me troubleshoot why the "api-server" job is showing as down in the "production" namespace.
```

---

## Resource Reads

> **Resource**: `prom://system/backends`

```
Show me all Prometheus backends and their health.
```

> **Resource**: `prom://system/backends/{backend_id}`

```
Show detailed info for backend "default".
```

> **Resource**: `prom://config/runtime`

```
What is the current Prometheus runtime configuration?
```

> **Resource**: `prom://topology/services`

```
List all services being monitored by Prometheus.
```

> **Resource**: `prom://topology/failed_targets`

```
Show me all failed scrape targets — which services are down?
```

> **Resource**: `prom://metadata/catalog`

```
Show me the metric catalog — I need to find the right metric name.
```

> **Resource**: `prom://tsdb/cardinality`

```
What is the current TSDB cardinality breakdown?
```

> **Resource**: `prom://rules/groups`

```
Show me all alerting and recording rule groups across all backends.
```

> **Resource**: `prom://exporters/catalog`

```
List the full exporter catalog with ports, images, and supported environments.
```

> **Resource**: `prom://best-practices`

```
Show me Prometheus monitoring best practices.
```

> **Resource**: `prom://onboarding-guide`

```
Show me the step-by-step onboarding guide for Prometheus.
```

---

*Document Version: 1.1 (v4 refactor) | Companion to [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md)*

## Rule Management & Authoring

> **Tool**: `prom_upsert_rule_group`

```
Create a new rule group named "high_error_rates" on the prod backend containing an alert for 5xx errors.
```

> **Tool**: `prom_draft_alert_rule`

```
Draft an alert rule that fires when CPU usage exceeds 90% for 5 minutes.
```

> **Tool**: `prom_tune_alert_rule`

```
Tune the "HighMemoryUsage" alert — it's been firing too often. Look at its history and recommend a better threshold.
```

---

## Rule Simulation & Testing

> **Tool**: `prom_simulate_firing_historical`

```
Check if my new high_error_rate alert would have fired at all over the last 24 hours.
```

> **Tool**: `prom_analyze_firing_history`

```
Analyze the firing frequency of the TraefikHighErrorRate alert over the past 24 hours. Is it too noisy?
```

> **Tool**: `prom_check_rule_group`

```
Check the syntax of the provided YAML string to ensure my new PromQL rules are valid before deploying.
```

> **Tool**: `prom_simulate_firing_synthetic`

```
Run a synthetic firing test on the HighCPUUsage rule. Assume the CPU usage stays at 100% for the entire duration of the test.
```

> **Tool**: `prom_run_rule_tests`

```
Run the promtool unit tests defined in my test.yaml file against the rules.yaml file.
```

