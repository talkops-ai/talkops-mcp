---
name: optimizing-tsdb-cardinality-and-finops
description: Audits Prometheus TSDB series cardinality, label value fan-out, CronJob pod churn, histogram bucket bloat, and unreferenced high-cost metrics; sizes TSDB RAM/SSD/sharding capacity; and generates safe metricRelabelings, recording rules, hashmod sharding, and remote_write FinOps configurations. Use when reducing Prometheus memory or Mimir/Thanos cloud bills, investigating high series counts or label fanout, pruning histogram buckets, or sizing/sharding Prometheus. Do not use for general PromQL query writing (use authoring-promql-and-analyzing-metrics), Grafana Loki log stream cardinality (use optimizing-loki-cardinality-and-finops), OTel Collector OTTL attribute filtering (use controlling-telemetry-cardinality-and-noise), or basic ServiceMonitor onboarding (use configuring-prometheus-scraping-and-discovery).
license: Apache-2.0
metadata:
  author: talkops
  version: "0.2.0"
  domain: observability
  component: prometheus
---

# Optimizing TSDB Cardinality and FinOps

Diagnoses Prometheus TSDB series explosions, label fan-out, pod churn, and cloud `remote_write` cost drivers using `/api/v1/status/tsdb` statistics and active rule cross-referencing, then synthesizes safe recording rules, `metricRelabelings`, `write_relabel_configs`, and capacity/sharding plans. Never shell out to `kubectl` when MCP resources and tools are available.

## MCP Execution Primitives Used

- **Resources**:
  - `prom://tsdb/cardinality` — live TSDB head block stats (`total_series`, `num_label_pairs`, `memory_bytes`) and top high-cardinality metrics.
  - `prom://config/runtime` — inspect global `scrape_interval`, `evaluation_interval`, and TSDB status.
  - `prom://rules/groups` and `prom://rules/{backend_id}/groups/{group_name}` — verify which metrics are referenced by active alerting and recording rules before dropping anything!
  - `prom://kubernetes/scrape-crds` & `prom://kubernetes/manifests/{kind}/{namespace}/{name}` — inspect existing `ServiceMonitor` / `PodMonitor` specs before adding `metricRelabelings`.
  - `prom://audit/recent` — verify rule and scrape-config FinOps mutation audit records.
- **Tools (`diagnostics`, `query`, `rules`, `scrape` toolsets)**:
  - `prom_get_diagnostics` — inspect TSDB head/WAL health (`include="tsdb"`).
  - `prom_analyze_cardinality` — compute series share (`pct_of_total`), label value fan-out (`focus_label`), rule usage (`check_unused_rules=True`), and deterministic observation codes (`HIGH_HEAD_SERIES`, `HIGH_CARDINALITY_METRIC`, `UNBOUNDED_LABEL_FANOUT`, `HISTOGRAM_BUCKET_EXPLOSION`, `UNREFERENCED_HIGH_COST_METRIC`).
  - `prom_explore_metrics` — inspect label cardinality (`label_name`) on offending metrics.
  - `prom_validate_rules` & `prom_upsert_rule_group` — validate and deploy pre-aggregated `level:metric:operations` recording rules (`dry_run=True` default).
  - `prom_apply_scrape_config` — preview and apply `metricRelabelings` onto `ServiceMonitor` / `PodMonitor` CRDs (`dry_run=True` default).

## Step-by-Step FinOps Workflow

### 1. Audit TSDB Cardinality & Rule Dependencies `[HIGH FREEDOM]`
1. Read `prom://tsdb/cardinality` and `prom://rules/groups`, and call `prom_analyze_cardinality(backend_id="default", top_n=20, focus_label=..., check_unused_rules=True)` + `prom_get_diagnostics(backend_id="default", include="tsdb")`.
2. **Alert-Blinding Refusal Guardrail**: Strictly **refuse** to `action: drop` `up` or core SLO/liveness metrics (`traces_spanmetrics_calls_total`, `http_requests_total`, etc.) that are referenced in active `prom://rules/groups` (`referenced_in_rules: true`), because dropping them silently blinds paging alerts during outages! Instead, keep `up` + pre-aggregated recording rules in `write_relabel_configs` while dropping only genuinely `UNREFERENCED_HIGH_COST_METRIC` series.
3. Consult [references/cardinality-observation-codes.md](references/cardinality-observation-codes.md) and [references/relabel-and-remote-write-patterns.md](references/relabel-and-remote-write-patterns.md) for critical traps:
   - **Intra-Scrape `labeldrop` Collision Trap**: Never blindly `action: labeldrop` an application-emitted per-request/per-user label (`session_id`, `user_id`, `request_id`) on a counter/gauge in `metric_relabel_configs` if multiple series in the **same scrape** share all remaining labels — Prometheus will reject colliding series with `duplicate sample for timestamp`! Safe 2-step remediation: (1) create a pre-aggregated recording rule (`sum by (...) (rate(...[5m]))`) and drop the raw metric from `remote_write.write_relabel_configs` to stop remote cost immediately, and (2) remove the attribute at the source SDK or OpenTelemetry Collector `transform` processor. (Note: `labeldrop` IS safe on target-unique metadata labels like `container_id` or `pod_uid` where each series remains unique per `pod`/`container`, and `action: labeldrop` / `labelkeep` MUST omit `source_labels` / `sourceLabels`!)
   - **Histogram Bucket Pruning vs. Native Histograms**: Always present and contrast **both** complete architectures:
     1. **Classic Histograms = Pre-aggregated Recording Rules (`sum by (le, service_name) (rate(..._bucket[5m]))` / `level:metric:operations`) + `metricRelabelings` Bucket Pruning** (`sourceLabels: [__name__, le]`, `action: drop` on unused intermediate buckets while **strictly retaining `le="+Inf"`** required by `histogram_quantile()`).
     2. **Prometheus 3.0 Native Histograms** (`scrapeNativeHistograms: true`, `nativeHistogramBucketLimit`, `send_native_histograms: true` — single dynamic sparse series per label set with zero `_bucket` fan-out).
   - **CronJob / Ephemeral Pod Churn**: Always prescribe all **3 layers**: (1) Kubernetes `Job`/`CronJob` cleanup (`ttlSecondsAfterFinished` and `successfulJobsHistoryLimit` so `kube-state-metrics` stops exporting completed Pod series), (2) pre-aggregated recording rules stripping `pod` + `remote_write.write_relabel_configs` keep-allowlist, and (3) **short local TSDB retention (`--storage.tsdb.retention.time=24h` / `spec.retention: 24h`)** so churned Pod series age out of local TSDB blocks within 24 hours.

### 2. Run Deterministic FinOps Generator & Capacity Sizing `[MEDIUM FREEDOM]`
1. Run [scripts/generate_finops_config.py](scripts/generate_finops_config.py) to emit validated `prometheus.yml` (`metric_relabel_configs`, `remote_write` with `http://` or `https://` URL validation and `queue_config`) and Operator CRD (`metricRelabelings`) blocks:
   ```bash
   python3 .agents/skills/optimizing-tsdb-cardinality-and-finops/scripts/generate_finops_config.py \
     --mode relabel --action drop --source-labels __name__ --regex 'envoy_cluster_upstream_cx_debug_.*'
   ```
   ```bash
   python3 .agents/skills/optimizing-tsdb-cardinality-and-finops/scripts/generate_finops_config.py \
     --mode remote_write --remote-url https://mimir-distributor.observability.svc:8080/api/v1/push \
     --keep-regex '(^.*:.*:.*$|up|kube_pod_status_phase)'
   ```
   *(If running outside `.agents/skills`, invoke `./scripts/generate_finops_config.py` relative to this skill directory.)*
2. **Capacity & Sharding Math** (from [references/relabel-and-remote-write-patterns.md](references/relabel-and-remote-write-patterns.md)):
   - **RAM**: $\text{Active Series} \times 8\,\text{KB} \times 1.5$ (e.g. $2\text{M} \rightarrow 24\text{ GB} \rightarrow 24\text{–}32\text{ GiB}$ pod limit).
   - **SSD Disk**: $\text{Active Series} \times \frac{\text{Retention Seconds}}{\text{Scrape Interval}} \times 1.8\,\text{B} \times 1.25$ (e.g. $2\text{M}$ @ `30s` for `15d` $= 2\text{M} \times 43{,}200 \times 2.25\,\text{B} \approx 194.4\text{ GB} \rightarrow 200\text{–}250\text{ GiB}$ PVC).
   - **Scale-Out Architecture (`> 1.5M` series)**: Whenever active series exceed `1.5M` (e.g. `2.0M`), ALWAYS recommend all **3 components**: (1) `hashmod` horizontal target sharding (`action: hashmod`, `modulus: N`, `Prometheus.spec.shards: 2+`), (2) **`remote_write` to Mimir/Thanos paired with short `24h–48h` local Prometheus TSDB retention** (offloading long-term 15d+ retention from local SSDs), and (3) centralized **ThanosRuler / Mimir Ruler** because each shard holds only $1/N$ of global series!

### 3. Preview & Apply Recording Rules / Relabeling `[LOW FREEDOM — GATE]`
1. Validate any pre-aggregated recording rules via `prom_validate_rules` first, then preview with `prom_upsert_rule_group(..., dry_run=True)` and `prom_apply_scrape_config(..., dry_run=True)`.
2. If the operator asked for advisory analysis/YAML or if write mode is disabled (`MCP_ALLOW_WRITE=false`), **stop** after `dry_run=True` / script generation. When live remediation was explicitly requested and all safety checks pass, **proceed immediately in the same turn** to `dry_run=False, confirm=True` and verify `prom://audit/recent`.

## Reference Documentation

- [TSDB Cardinality Observation Codes & Remediation Matrix](references/cardinality-observation-codes.md)
- [Relabeling, Remote-Write, and TSDB Capacity Architecture](references/relabel-and-remote-write-patterns.md)
