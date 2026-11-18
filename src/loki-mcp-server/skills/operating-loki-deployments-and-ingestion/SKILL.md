---
name: operating-loki-deployments-and-ingestion
description: Operates Grafana Loki 3.x clusters, diagnoses loki_discarded_samples_total ingestion drops, manages Compactor GDPR/PII log deletion requests, tunes Grafana Alloy/OTel Collector OTLP ingestion pipelines, and sizes/applies LokiStack Kubernetes Operator CRDs. Use when troubleshooting Loki readiness or 429/too-old/line-too-long ingestion drops, creating or cancelling Compactor delete requests, choosing Monolithic vs Simple Scalable vs Microservices sizing, or deploying/scaling LokiStack CRs. Do not use for stream cardinality FinOps audits (use optimizing-loki-cardinality-and-finops), AlertingRule/RecordingRule authoring (use authoring-loki-alerting-and-recording-rules), TempoStack operations (use operating-tempo-deployments-and-tenants), or OTel Collector OTTL redaction processors (use controlling-telemetry-cardinality-and-noise).
license: Apache-2.0
metadata:
  author: TalkOps
  version: "0.2.0"
  domain: observability
  service: grafana-loki
---

# Operating Loki Deployments and Ingestion

Use this skill to operate, diagnose, size, and govern Grafana Loki 3.x deployments—covering ingestion drop remediation, Compactor GDPR/PII log deletion lifecycles, OTel/Alloy collector pipelines, and Kubernetes `LokiStack` (`loki.grafana.com/v1`) Custom Resources.

## Operational Workflows

### Workflow 1: Diagnose Cluster Health & Discarded Samples
1. Read `loki://system/health`, `loki://server/capabilities` (checking `allow_write` before any mutation!), and [references/alloy-promtail-otel-ingestion.md](references/alloy-promtail-otel-ingestion.md).
2. Call `loki_get_diagnostics(include_metrics=True, org_id=...)` to inspect `/ready`, `/config` (`runtime_config`: `compactor`, `limits_config`, `schema`), and `/metrics` `loki_discarded_samples_total` by `reason` (cross-checking `loki_analyze_volume` when rate limits fire):
   - `per_stream_rate_limit`: Split monolithic `{job="..."}` streams by bounded `service_name` + `namespace` while keeping `pod`/`container`/`node` in `structured_metadata`.
   - `rate_limited`: Raise `ingestion_rate_mb` / `ingestion_burst_size_mb` or drop noisy logs at the collector.
   - `max_global_streams_per_user`: Move dynamic labels (`pod`, `trace_id`, `ip`) out of `{}` into `structured_metadata`.
   - `line_too_long`: Enable `limits_config.max_line_size_truncate: true` or collector truncation.
   - `greater_than_max_sample_age` / `timestamp_too_old`: Caused by `reject_old_samples_max_age` (`168h` default)—fix NTP skew, rewrite archival replay timestamps to ingestion time in OTel Collector (`otlphttp` `/otlp`) / Alloy while keeping original event time in payload/structured metadata, or raise `reject_old_samples_max_age` per tenant (`unordered_writes: true` handles out-of-order writes within max-age).

### Workflow 2: Safe Compactor GDPR/PII Log Deletion
1. **Verify Compactor Prerequisites First**: Read [references/compactor-retention-and-deletion.md](references/compactor-retention-and-deletion.md), call `loki_get_diagnostics`, and read `loki://compactor/delete-requests` to confirm `compactor.retention_enabled: true` and `compactor.delete_request_store` (`s3`/`gcs`/`azure`/`filesystem`) are configured! If disabled, explain why `/loki/api/v1/delete` requires durable request tracking and render the required `compactor:` YAML via `render_loki_architecture_config.py`.
2. **Block Unbounded Deletions**: **Never** submit whole-namespace or filterless delete requests (`{namespace="<namespace>"}` over 7–30 days)—Compactor `/loki/api/v1/delete` rewrites every matching chunk in object storage (massive I/O amplification and audit-log loss). Direct storage reclamation to `limits_config.retention_period` / `retention_stream`.
3. **4-Step Scoped PII Scrub (`action="create"`)**:
   - Scope exact blast radius first with read-only `loki_query_range` (`{service_name="<service>", namespace="<namespace>"} |= "<pii_field>="`).
   - Preview via `loki_manage_delete_requests(action="create", query=..., start=..., end=..., dry_run=True, org_id=...)`.
   - Execute `loki_manage_delete_requests(action="create", ..., dry_run=False, confirm=True, org_id=...)` and verify `loki://compactor/delete-requests` (noting `retention_delete_delay`, typically `2h`).
4. **Cancel Pending Mistaken Requests (`action="cancel"`)**:
   - Read `loki://compactor/delete-requests` to verify `status: "received"`, call `loki_manage_delete_requests(action="cancel", request_id="...", dry_run=True, org_id=...)` **first**, then execute `dry_run=False, confirm=True` and re-read `loki://compactor/delete-requests`.

### Workflow 3: Architecture Sizing, `LokiStack` CRDs & Zero-Secret Hygiene
1. **Read Sizing Guide & Inspect Existing Operator CRs via MCP Resources**: Read [references/loki-3-architecture-and-sizing.md](references/loki-3-architecture-and-sizing.md), and always read `loki://operator/crs/{namespace}` and `loki://operator/manifests/{kind}/{namespace}/{name}` (substituting `{kind}`, `{namespace}`, and `{name}`) rather than raw `kubectl` before scaling or updating `LokiStack`—**preserve historical `storage.schemas` `effectiveDate` entries** to prevent TSDB index corruption!
2. **Render Validated Configs Locally (`render_loki_architecture_config.py`)**:
   - Sizing tiers: **Monolithic** (`< 20 GB/day`, `1x.demo`/`1x.extra-small`), **Simple Scalable** (`20 GB – 1 TB/day`, `1x.small` `<= 500 GB/day`), **Microservices** (`> 1 TB/day` + Bloom filters, `1x.medium` `<= 2 TB/day`, `replication_factor: 3`, `zone_awareness_enabled: true`, SSD WAL, TSDB `v13`).
   ```bash
   python3 .agents/skills/operating-loki-deployments-and-ingestion/scripts/render_loki_architecture_config.py \
     --mode lokistack --size 1x.small --storage s3 --retention-days 30 --namespace <namespace> --name <lokistack-name> --json
   ```
3. **Zero-Secret Hygiene & Read-Only Gate**:
   - **Never** inline S3 `access_key_id`/`secret_access_key`, bearer tokens, or Basic-Auth URLs in manifests or commands, and **never** dump Kubernetes `Secret` data—always reference `spec.storage.secret.name`!
   - When `allow_write: true`, always run `loki_apply_operator_cr(..., dry_run=True)` **before** `dry_run=False, confirm=True` (stopping at `dry_run=True` if only previewing; when `allow_write: false`, output the complete manifest without calling write tools).

## Key Reference Guides & Scripts

- [references/loki-3-architecture-and-sizing.md](references/loki-3-architecture-and-sizing.md) — Monolithic vs. Simple Scalable vs. Microservices sizing, `LokiStack` tiers, RF=3, zone awareness, and SSD WAL.
- [references/alloy-promtail-otel-ingestion.md](references/alloy-promtail-otel-ingestion.md) — `loki_discarded_samples_total` remediation matrix plus Alloy and OTel Collector `otlphttp` `/otlp` pipelines.
- [references/compactor-retention-and-deletion.md](references/compactor-retention-and-deletion.md) — Compactor `retention_enabled` + `delete_request_store` prerequisites, per-stream retention, and 4-step PII deletion runbook.
- [scripts/render_loki_architecture_config.py](scripts/render_loki_architecture_config.py) — Deterministic generator for Loki 3.x `loki.yaml` (with Bloom filters & zone awareness) and `LokiStack` CRDs.
