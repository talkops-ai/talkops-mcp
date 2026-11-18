---
name: optimizing-loki-cardinality-and-finops
description: Audits Grafana Loki log ingestion byte volume, stream cardinality explosions, tiny-chunk S3 PUT storms, TSDB v13 migrations, per-tenant limits, and Bloom filter FinOps optimizations. Use when investigating high Loki storage/S3 bills, attributing ingestion volume by namespace or service, calculating theoretical max streams, demoting pod/session_id/trace_id/client_ip to Loki 3.x structured metadata, dropping noisy healthcheck/debug logs, or sizing TSDB v13 Bloom filters. Do not use for Prometheus metric TSDB cardinality (use optimizing-tsdb-cardinality-and-finops), live OTel Collector OTTL patching (use controlling-telemetry-cardinality-and-noise), log parser format inference (use discovering-loki-schema-and-log-structure), or Compactor PII deletions (use operating-loki-deployments-and-ingestion).
license: Apache-2.0
metadata:
  author: TalkOps
  version: "0.2.0"
  domain: observability
  service: grafana-loki
---

# Optimizing Loki Cardinality and FinOps

Use this skill to perform a rigorous Grafana Loki 3.x FinOps and stream-cardinality audit—identifying noisy workloads, diagnosing tiny-chunk S3 API spikes, enforcing strict label governance, and designing TSDB `v13` + `structured_metadata` + Bloom filter architectures.

## Golden Rules of Loki 3.x Label & Storage FinOps

Consult [references/label-governance-and-cardinality.md](references/label-governance-and-cardinality.md) and [references/bloom-filters-and-tsdb-finops.md](references/bloom-filters-and-tsdb-finops.md):

1. **Stream Labels Index Streams, Never Log Fields**:
   - Keep `<= 10` bounded labels in `{}` (`cluster`, `namespace`, `service_name`, `env`) and `< 100,000` active streams per tenant.
   - **Unconditionally Forbidden in `{}`** (even if staging count `< 500`!): `pod`, `k8s_pod_name`, `container_id`, `trace_id`, `span_id`, `request_id`, `order_id`, `session_id`, `user_id`, `client_ip`, `pod_ip`, `uuid`—demote them to **Loki 3.x `structured_metadata`**!
2. **Tiny-Chunk Syndrome (`< 256 KB` vs `1.5 MB` `chunk_target_size`)**:
   - High stream churn causes ingesters to flush thousands of tiny `< 6 KB` chunks, spiking S3 `PUT`/`GET` API costs `10x–50x` even when daily GB stays flat. Fix by demoting ephemeral labels to `structured_metadata`.
3. **TSDB `v13` Migrations & Bloom Filters**:
   - Migrate from legacy `boltdb-shipper` (`v11`) by appending a **future-dated** `from:` entry (`store: tsdb`, `schema: v13`, `period: 24h`)—**never modify historical `schema_config` entries** (which makes older logs unreadable). TSDB `v13` cuts `index-gateway` RAM by `~70%`.
   - For needle-in-a-haystack queries (`order_id`, `trace_id`, `request_id`, or SKU/entity IDs) scanning `> 10 GB`, keep IDs in `structured_metadata` and enable Loki 3.x **Bloom filters** (`bloom_build.enabled: true`, `bloom_gateway.enabled: true`, `limits_config.bloom_gateway_enable_filtering: true`, `bloom_creation_enabled: true`) to skip `95%+` of chunks without indexing unbounded labels.
4. **Collection-Edge Noise Dropping**:
   - Drop HTTP `200` `kube-probe` / `/healthz` checks and `DEBUG` logs at the collector edge (`stage.drop` in Grafana Alloy / `filter` in OTel Collector), **always preserving `>= 400` probe failures** so failed readiness/liveness probes remain visible!
5. **Dashboard & Ruler Migration Impact**:
   - Before dropping `pod` from `{}` via `stage.label_drop`, audit `loki://rules/groups` and Grafana variables so `{service_name="x", pod="y"}` selectors (which would return `0` streams) are migrated atomically to `{service_name="x"} | pod="y"`.

## Step-by-Step FinOps Audit Workflow

### Step 1: Inspect Guardrails, References, Labels & Ingestion Volume Attribution
1. Read `loki://config/guardrails` and `loki://schema/labels` (and `loki://rules/groups` when evaluating label-demotion impact).
2. Read [references/label-governance-and-cardinality.md](references/label-governance-and-cardinality.md) for label governance, tiny-chunk syndrome, and Alloy/OTel remediation snippets, and read [references/bloom-filters-and-tsdb-finops.md](references/bloom-filters-and-tsdb-finops.md) when evaluating TSDB `v13` migrations, Bloom filters, or per-tenant `limits_config` overrides.
3. Call `loki_analyze_volume(query='{namespace=~".+"}', target_label="namespace", start="now-6h", org_id=...)` and drill into `{namespace="<namespace>"}` with `target_label="service_name"` to rank top byte producers.

### Step 2: Inspect Stream Multiplication & Scan Cost (`loki_get_series` + `loki_get_query_stats`)
1. Call `loki_get_series` on noisy workloads (`{namespace="<namespace>"}` or `{service_name="<service>", namespace="<namespace>"}`) to measure active stream counts and per-label cardinalities.
2. Always call `loki_get_query_stats` alongside `loki_analyze_volume` (both when diagnosing slow scans AND when auditing noisy `/healthz` or `DEBUG` log volume across top services) to quantify exact uncompressed bytes, chunks, and entries scanned.

### Step 3: Run Deterministic Cardinality Math (`audit_label_cardinality.py`)
Always run [scripts/audit_label_cardinality.py](scripts/audit_label_cardinality.py) on observed or user-supplied label cardinality maps to calculate exact theoretical max streams ($\prod \max(c_i, 1)$) before and after remediation and generate Grafana Alloy `loki.process` (`stage.structured_metadata` + `stage.label_drop`) configs:
```bash
python3 .agents/skills/optimizing-loki-cardinality-and-finops/scripts/audit_label_cardinality.py \
  --cardinality-json '{"cluster": 2, "namespace": 4, "service_name": 18, "pod": 540, "session_id": 50000}' \
  --threshold 500 --json
```

## Key Reference Guides & Scripts

- [references/label-governance-and-cardinality.md](references/label-governance-and-cardinality.md) — Allowed vs. forbidden indexed labels, tiny-chunk diagnosis, and Alloy/Promtail `structured_metadata` migration blocks.
- [references/bloom-filters-and-tsdb-finops.md](references/bloom-filters-and-tsdb-finops.md) — TSDB `v13` schema migration, `1.5 MB` chunk tuning, Loki 3.x Bloom filter setup, and per-tenant `limits_config` overrides.
- [scripts/audit_label_cardinality.py](scripts/audit_label_cardinality.py) — Deterministic stream-product calculator and Alloy remediation generator.
