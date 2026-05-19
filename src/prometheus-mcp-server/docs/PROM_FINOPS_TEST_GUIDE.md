# FinOps Test Guide — Prometheus MCP Server

**Target workflow**: TSDB FinOps & Cardinality Optimization
**Tools tested**: `prom_optimize_cardinality`, `prom_explore_labels`, `prom_plan_relabel`
**Output**: YAML configs (does NOT apply changes)

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Prometheus instance | Running with TSDB stats API enabled |
| Prometheus MCP Server | Running |

---

## 2. Test Scenarios

### Scenario A: Cardinality Analysis

| Step | Action | Resource |
|------|--------|----------|
| 1 | Get cardinality overview | **Resource**: `prom://tsdb/cardinality` |
| 2 | Get runtime config | **Resource**: `prom://config/runtime` |

**Expected**:
- Step 1: `{overview: {total_series: int}, top_cardinality_metrics: [{metric_name, series_count}, ...]}`
- Step 2: `{scrape_interval, retention, tsdb: {...}}`

### Scenario B: High Cardinality Optimization

| Step | Action | Tool |
|------|--------|------|
| 1 | Analyze top 10 | `prom_optimize_cardinality(backend_id="default", top_n=10)` |
| 2 | Target specific metric | `prom_optimize_cardinality(backend_id="default", metric_name="http_request_duration_seconds_bucket")` |

**Expected**:
- Step 1: Returns recommendations with severity (critical/high/medium) and actionable strategies
- Step 2: Returns focused advice for the specific metric, including series count

### Scenario C: Relabel Config Generation

| Step | Action | Tool | Expected YAML |
|------|--------|------|---------------|
| 1 | Drop labels | `prom_plan_relabel(backend_id="default", labels_to_drop=["pod_id", "container_id"])` | `action: labeldrop` rules |
| 2 | Keep labels only | `prom_plan_relabel(backend_id="default", labels_to_keep=["job", "namespace"])` | `action: labelkeep` rule with `__name__|job|instance|namespace` |
| 3 | Drop entire metric | `prom_plan_relabel(backend_id="default", metric_name="kubelet_runtime_operations_total")` | `action: drop` with `source_labels: [__name__]` |
| 4 | Metric + label drop | `prom_plan_relabel(backend_id="default", metric_name="http_requests_total", labels_to_drop=["user_id"])` | Scoped `labeldrop` for specific metric |

### Scenario D: Recording Rules

| Step | Action | Tool |
|------|--------|------|
| 1 | Create recording rule | `prom_create_recording_rule(backend_id="default", rule_name="job:http_requests:rate5m", rule_expr="sum by (job) (rate(http_requests_total[5m]))")` |
| 2 | With extra labels | `prom_create_recording_rule(backend_id="default", rule_name="env:cpu:avg", rule_expr="avg by (env) (process_cpu_seconds_total)", rule_labels={"aggregation": "env"}, rule_interval="5m")` |

**Expected**: Valid Prometheus rule group YAML with `groups:` structure.

### Scenario E: Remote-Write Configuration

| Step | Action | Tool |
|------|--------|------|
| 1 | Basic remote-write | `prom_configure_remote_write(backend_id="default", remote_url="http://thanos-receive:19291/api/v1/receive")` |
| 2 | With name and filters | `prom_configure_remote_write(backend_id="default", remote_url="https://mimir.example.com/api/v1/push", remote_name="mimir-prod", write_relabel_configs=[{"source_labels": ["__name__"], "regex": "http_.*", "action": "keep"}])` |
| 3 | Custom queue config | `prom_configure_remote_write(backend_id="default", remote_url="http://cortex:9009/api/v1/push", queue_config={"capacity": 20000, "max_shards": 50})` |

**Expected**: Valid `remote_write:` YAML with sensible queue_config defaults when not overridden.

---

## 3. Natural Language Prompts

**Scenario A: Cardinality Analysis**
```text
Show me the TSDB cardinality overview and top hotspot metrics.
```
```text
What is the current Prometheus runtime configuration?
```

**Scenario B: High Cardinality Optimization**
```text
Analyze my top 10 highest-cardinality metrics and tell me what to do about them.
```
```text
What should I do about the high cardinality of the metric "apiserver_request_duration_seconds_bucket"?
```

**Scenario C: Relabel Config Generation**
```text
Generate a relabel config to drop the labels "pod_id" and "container_id".
```
```text
Generate a labelkeep config that only keeps the "job" and "namespace" labels.
```
```text
Create a metric_relabel_config to drop the entire metric "kubelet_runtime_operations_total".
```
```text
Create a relabel config to drop the "user_id" label specifically for the "http_requests_total" metric.
```

**Scenario D: Recording Rules**
```text
Create a recording rule "job:http_requests:rate5m" that pre-computes the request rate per job over 5 minutes: sum by (job) (rate(http_requests_total[5m]))
```
```text
Create a recording rule "env:cpu:avg" for "avg by (env) (process_cpu_seconds_total)" with an interval of 5m and an extra label "aggregation: env".
```

**Scenario E: Remote-Write Configuration**
```text
Configure remote-write to Thanos Receive at http://thanos-receive:19291/api/v1/receive.
```
```text
Generate remote-write config for Mimir at https://mimir.example.com/api/v1/push with the name "mimir-prod" and a write relabel filter to keep only "http_.*".
```
```text
Configure remote-write to Cortex at http://cortex:9009/api/v1/push with a custom queue config: capacity 20000 and max shards 50.
```
