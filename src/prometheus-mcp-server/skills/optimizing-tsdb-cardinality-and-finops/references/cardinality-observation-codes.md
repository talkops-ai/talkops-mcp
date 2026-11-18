# TSDB Cardinality Observation Codes & Remediation Matrix

`prom_analyze_cardinality` and `prom_get_diagnostics` emit deterministic `observations[]` codes. Use this matrix to select the appropriate remediation strategy:

| Observation Code | Trigger Condition | Primary Root Cause | Recommended FinOps Strategy |
| :--- | :--- | :--- | :--- |
| `HIGH_HEAD_SERIES` | Active head series $\ge 1,000,000$ | Fleet-wide cardinality growth or pod churn | Audit top 15 metrics via `prom_analyze_cardinality`; shard scrape jobs or enable `write_relabel_configs`. |
| `HIGH_CARDINALITY_METRIC` | Single metric $\ge 10,000$ series or $\ge 15\%$ of TSDB | Multiplicative label cross-product (`path` $\times$ `status` $\times$ `pod`) | Create a recording rule aggregating away `pod`/`instance`, then `labeldrop` high-fanout labels. |
| `UNBOUNDED_LABEL_FANOUT` | Label has $\ge 1,000$ unique values | Ephemeral IDs (`user_id`, `request_id`, `ip`, `email`, raw URL path) in labels | Apply `action: labeldrop` in `metric_relabel_configs` and fix application instrumentation. |
| `HISTOGRAM_BUCKET_EXPLOSION` | `*_bucket` metric $\ge 5,000$ series | Classic histogram with 15–30 `le` buckets $\times$ many pods/routes | Drop unused intermediate `le` buckets (`source_labels: [__name__, le]`, `action: drop`), pre-aggregate by `le, service` in recording rules, or migrate to Prometheus 3.0 native histograms. |
| `UNREFERENCED_HIGH_COST_METRIC` | Metric $\ge 5,000$ series and referenced in $0$ rules | Default exporter / cAdvisor metrics (`container_tasks_state`, `go_gc_*`) never queried | Drop the metric at scrape ingestion via `metric_relabel_configs` (`source_labels: [__name__]`, `action: drop`). |
