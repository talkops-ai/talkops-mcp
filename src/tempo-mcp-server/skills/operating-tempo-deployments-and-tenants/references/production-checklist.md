# Tempo Production Readiness Checklist

Verify these operational requirements before promoting a `TempoStack`, `TempoMonolithic`, or `/api/overrides` change to production:

1. **Object Storage Durability**:
   - `spec.storage.secret.name` references a valid Kubernetes Secret (`s3`, `gcs`, or `azure`) and never ephemeral `inMemory` storage in production.
   - `spec.replicationFactor >= 2` (`3` for `large-prod`) on `TempoStack`.
2. **Metrics-Generator Processors**:
   - Enable `service-graphs`, `span-metrics`, and `local-blocks` so `tempo_analyze_service_red`, `tempo_compare_span_cohorts`, and `tempo_get_service_dependencies` operate at full fidelity.
3. **Tenant Rate-Limit Headroom**:
   - Verify `tempo_discarded_spans_total == 0` in `tempo_get_diagnostics` (`SPANS_DISCARDED` absent).
   - Ensure `ingestion_burst_size_bytes >= 1.33 * ingestion_rate_limit_bytes`.
4. **Tempo 3.x Kafka & Parquet Checks**:
   - On Tempo 3.x distributed clusters, ensure `vParquet4` block encoding is active and `tempo_ingest_group_partition_lag_seconds` (`PARTITION_LAG_OBSERVED`) remains `< 5s`.
5. **Server-Side Dry-Run Validation**:
   - Every `tempo_apply_operator_cr` and `tempo_patch_tenant_overrides` mutation MUST be executed with `dry_run=True` first and have its unified `diff` inspected before setting `dry_run=False`.
