# Cardinality Audit Test Guide — OpenTelemetry MCP Server

**Phase 3 of 5** in the OTel Demo end-to-end journey.
**Previous phase**: [Pipeline Investigation](OTEL_PIPELINE_INVESTIGATION_TEST_GUIDE.md)
**Next phase**: [Sampling Review](OTEL_SAMPLING_TEST_GUIDE.md)

> Telemetry is flowing and pipelines are validated (Phase 2). Now you need to ensure
> metric cardinality is under control — high cardinality can crash Prometheus, explode
> storage costs, and slow dashboards. This phase detects issues, inspects SpanMetrics,
> and generates remediation rules.

---

## Prerequisites (Completed in Phase 2)

| Component | Status |
|-----------|--------|
| ✅ Collectors validated | Processor ordering correct, filelog safe |
| ✅ Telemetry flowing | Traces → Jaeger, Metrics → Prometheus, Logs → OpenSearch |
| ✅ SpanMetrics active | `spanmetrics_enabled: true` on `otel-demo-collector` |

---

## The Starting Point

Your OTel Demo collector has a `spanmetrics` connector that generates RED metrics
(Rate, Errors, Duration) from traces. The connector has 5 dimensions and 16 histogram buckets.
Is this causing cardinality problems? How many metric series is it producing?

---

## Phase 1: Cardinality Detection

### Step 1.1: Detect Cardinality Issues

| Field | Value |
|-------|-------|
| **Prompt** | `Detect metric cardinality issues in collector "otel-demo-collector" in the "otel-demo" namespace.` |
| **Tool** | `otel_detect_cardinality` |
| **Parameters** | `{"namespace": "otel-demo", "name": "otel-demo-collector"}` |
| **Internal action** | (1) Fetches collector CRD and parses config. (2) Finds `spanmetrics` connector → counts dimensions (5) and histogram buckets (16). (3) Estimates series per service: `100 × dimension_count = 500`. (4) Evaluates thresholds: > 5 dims = warning, > 10 = critical, > 20 buckets = warning. (5) Checks if existing `transform` processors already drop attributes (remediation detection). |
| **Expected output** | `spanmetrics_enabled: true`, `total_estimated_series: 500`, `issues: []` (5 dimensions is at the warning threshold but not exceeding), `existing_remediation: false` |

**Why 500 series per service?**
- 5 dimensions × ~100 unique combinations per service = 500 time series
- With 15+ demo services: ~7,500+ total series from SpanMetrics alone
- Each series has 16 histogram buckets: ~120,000 data points per scrape cycle

**Manual validation:**
```bash
kubectl port-forward svc/prometheus 9090:9090 -n otel-demo
# Open http://localhost:9090, query:
#   count(calls_total)                    → active call rate series
#   count(duration_milliseconds_bucket)   → histogram series count
```

---

## Phase 2: SpanMetrics Deep Inspection

### Step 2.1: Inspect SpanMetrics via Tool

| Field | Value |
|-------|-------|
| **Prompt** | `Inspect the SpanMetrics connector configuration for "otel-demo-collector" in "otel-demo".` |
| **Tool** | `otel_inspect_spanmetrics_config` |
| **Parameters** | `{"namespace": "otel-demo", "name": "otel-demo-collector"}` |
| **Internal action** | (1) Parses `connectors.spanmetrics` section. (2) Extracts dimensions with their names and default values. (3) Parses histogram config (explicit or exponential). (4) Traces pipeline wiring: which pipeline uses spanmetrics as an *exporter* (source=traces) vs *receiver* (target=metrics). (5) Estimates cardinality. |
| **Key output** | See table below |

**SpanMetrics profile (OTel Demo):**

| Field | Value |
|-------|-------|
| `enabled` | `true` |
| `dimensions` | `http.method`, `http.status_code`, `rpc.method`, `rpc.service`, `http.target` |
| `histogram.type` | `explicit` |
| `histogram.explicit_buckets` | 16 buckets: 2ms, 4ms, 6ms, 8ms, 10ms, 50ms, 100ms, 200ms, 400ms, 800ms, 1s, 1.4s, 2s, 5s, 10s, 15s |
| `source_pipeline` | `traces` (spanmetrics is an exporter in the traces pipeline) |
| `target_pipeline` | `metrics` (spanmetrics is a receiver in the metrics pipeline) |
| `estimated_series_per_service` | 500 |

**How data flows:**
```
Traces pipeline → [span data] → spanmetrics connector → [RED metrics] → Metrics pipeline → Prometheus
```

### Step 2.2: Inspect SpanMetrics via Resource (Same Data)

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the SpanMetrics connector profile for "otel-demo-collector" in "otel-demo".` |
| **Resource** | `otel://spanmetrics/otel-demo/otel-demo-collector` |
| **Internal action** | Same extraction as tool — resources always return full profile |
| **Expected output** | Identical to Step 2.1 |

**Manual validation:**
```bash
kubectl get opentelemetrycollectors -n otel-demo otel-demo-collector \
  -o jsonpath='{.spec.config.connectors.spanmetrics.dimensions}' | python3 -m json.tool
```

---

## Phase 3: Cardinality Remediation

If cardinality is too high, you can generate `transform` processor rules to drop
high-cardinality attributes before they reach exporters.

### Step 3.1: Generate Drop Rules for Metrics

| Field | Value |
|-------|-------|
| **Prompt** | `Generate a transform processor to drop the attributes "http.user_agent" and "url.full" from metrics.` |
| **Tool** | `otel_gen_drop_attribute_rules` |
| **Parameters** | `{"attributes": ["http.user_agent", "url.full"], "signal": "metrics"}` |
| **Internal action** | This is a **stateless generator** — does NOT connect to the cluster. Generates a YAML snippet with `transform/drop_metrics_attributes` processor using OTTL `delete_key()` statements. Context is `datapoint` for metrics. |
| **Expected output** | YAML snippet + integration instructions |

**Generated YAML:**
```yaml
processors:
  transform/drop_metrics_attributes:
    metric_statements:
      - context: datapoint
        statements:
          - delete_key(attributes, "http.user_agent")
          - delete_key(attributes, "url.full")
```

**Integration instructions (generated by tool):**
1. Add the processor to your collector config under `processors:`
2. Add `transform/drop_metrics_attributes` to your metrics pipeline's processor list
3. Place it **after** `k8sattributes` but **before** `batch`

### Step 3.2: Generate Drop Rules for Traces

| Field | Value |
|-------|-------|
| **Prompt** | `Create a transform rule to drop "http.target" from traces.` |
| **Tool** | `otel_gen_drop_attribute_rules` |
| **Parameters** | `{"attributes": ["http.target"], "signal": "traces"}` |
| **Internal action** | Same generator but for traces: context is `span`, uses `trace_statements`, processor name is `transform/drop_traces_attributes` |

**Generated YAML:**
```yaml
processors:
  transform/drop_traces_attributes:
    trace_statements:
      - context: span
        statements:
          - delete_key(attributes, "http.target")
```

> **Important:** Dropping `http.target` from traces will also reduce SpanMetrics cardinality
> because the connector reads from trace spans before export.

### Step 3.3: Generate Drop Rules for Logs

| Field | Value |
|-------|-------|
| **Prompt** | `Generate a transform rule to drop "log.file.path" from logs.` |
| **Tool** | `otel_gen_drop_attribute_rules` |
| **Parameters** | `{"attributes": ["log.file.path"], "signal": "logs"}` |
| **Internal action** | Context is `log`, uses `log_statements`, processor name is `transform/drop_logs_attributes` |

---

## Phase 4: SpanMetrics Enablement (for Collectors Without It)

If you provisioned a new collector in Phase 1 that doesn't have SpanMetrics, you can enable it:

### Step 4.1: Enable with Default Dimensions

| Field | Value |
|-------|-------|
| **Prompt** | `Enable SpanMetrics for collector "recommendation-collector" in "otel-demo" — dry run.` |
| **Tool** | `otel_enable_spanmetrics_for_service` |
| **Parameters** | `{"namespace": "otel-demo", "collector_name": "recommendation-collector", "dry_run": true}` |
| **Internal action** | Generates a SpanMetrics connector config snippet with default dimensions (`service.name`, `http.method`, `http.status_code`, `rpc.method`) and default histogram buckets (16 buckets). Returns the config snippet, pipeline wiring instructions, and integration steps. |
| **Expected output** | Config snippet with `connectors.spanmetrics`, pipeline wiring showing traces→spanmetrics→metrics |

### Step 4.2: Enable with Custom Dimensions

| Field | Value |
|-------|-------|
| **Prompt** | `Enable SpanMetrics with only http.method and http.status_code dimensions — dry run.` |
| **Tool** | `otel_enable_spanmetrics_for_service` |
| **Parameters** | `{"namespace": "otel-demo", "collector_name": "recommendation-collector", "dimensions": ["http.method", "http.status_code"], "dry_run": true}` |
| **Internal action** | Same but uses only the 2 specified dimensions → lower cardinality (~200 series/service vs ~400) |

### Step 4.3: High Dimension Count Warning

| Field | Value |
|-------|-------|
| **Prompt** | `Enable SpanMetrics with 6 dimensions — dry run.` |
| **Tool** | `otel_enable_spanmetrics_for_service` |
| **Parameters** | `{"namespace": "otel-demo", "collector_name": "recommendation-collector", "dimensions": ["http.method", "http.status_code", "http.target", "rpc.method", "rpc.service", "db.system"], "dry_run": true}` |
| **Internal action** | Generates config but adds warning because dimension count > 5 |
| **Expected output** | `warnings: ["High dimension count (6) may cause cardinality issues."]` |

---

## Phase 5: End-to-End Cardinality Audit Flow

This combines all steps into the recommended workflow:

| Step | Prompt | Tool | What It Answers |
|------|--------|------|-----------------|
| 1 | `Detect cardinality issues in "otel-demo-collector"` | `otel_detect_cardinality` | How many series? Any issues? |
| 2 | `Inspect SpanMetrics for "otel-demo-collector"` | `otel_inspect_spanmetrics_config` | Which dimensions are contributing? |
| 3 | `Show SpanMetrics profile via resource` | `otel://spanmetrics/otel-demo/otel-demo-collector` | Same data, different access pattern |
| 4 | `Generate a rule to drop "http.target" from traces` | `otel_gen_drop_attribute_rules` | Remediation YAML for high-cardinality attrs |
| 5 | `Enable SpanMetrics on new collector with 2 dimensions` | `otel_enable_spanmetrics_for_service` | Low-cardinality SpanMetrics for new collector |

---

## Phase Summary

At the end of this phase, you've verified:

| What | Tool / Resource | Status |
|------|----------------|--------|
| ✅ Cardinality estimated | `otel_detect_cardinality` | ~500 series/service, no critical issues |
| ✅ SpanMetrics dimensions audited | `otel_inspect_spanmetrics_config` | 5 dimensions, 16 buckets — within limits |
| ✅ Remediation rules generated | `otel_gen_drop_attribute_rules` | Drop rules for metrics, traces, and logs ready |
| ✅ SpanMetrics enablement | `otel_enable_spanmetrics_for_service` | Can be added to collectors that lack it |

**Next step →** [Sampling Review](OTEL_SAMPLING_TEST_GUIDE.md): With cardinality under control, now optimize trace volume through head or tail sampling strategies.
