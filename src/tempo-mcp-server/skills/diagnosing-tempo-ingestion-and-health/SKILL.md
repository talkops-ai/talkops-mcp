---
name: diagnosing-tempo-ingestion-and-health
description: Diagnoses Grafana Tempo 2.x and 3.x ingestion pipelines, backend connectivity, hash rings (`RING_MEMBER_UNHEALTHY`, gossip port `7946`), Kafka `PARTITION_LAG_OBSERVED`, `SPANS_DISCARDED` rate/size drops, `X-Scope-OrgID` multi-tenant mismatches, OTel Collector exporter misconfigurations (`:4317` vs `:4318`), `TRACE_TIME_GAPS`, and degraded `TempoStack` Operator CRs (`OPERATOR_CR_NOT_READY`). Use when traces are missing, spans are discarded, TraceQL metrics/service-graphs go blank, or Tempo components are unhealthy. Do not use for Day-1/Day-2 `TempoStack` sizing (use operating-tempo-deployments-and-tenants), OTel Collector internal OOM/queue crashes (use troubleshooting-telemetry-pipelines), Loki ingestion drops (use operating-loki-deployments-and-ingestion), or microservice 5xx error triage (use triaging-tempo-service-errors).
---

# Diagnosing Tempo Ingestion and Health

## Preconditions

- Read `tempo://server/capabilities`, `tempo://deployment/overview`, `tempo://system/backends`, and `tempo://system/backends/{backend_id}` via MCP resources before running diagnostic checks.
- When Kubernetes Operator CRs exist in the target namespace (for example `observability`), inspect `tempo://operator/crs/{namespace}` and `tempo://operator/manifests/{kind}/{namespace}/{name}` via MCP resources rather than raw `kubectl` (never reading or printing raw Kubernetes `Secret` values).

## Diagnostic Workflow Checklist

- [ ] **Step 1 — Collect Factual Diagnostics**: Call `tempo_get_diagnostics(backend_id=..., tenant=..., include=["health", "components", "rings", "ingestion", "config", "operator"])`.
- [ ] **Step 2 — Map Observation Codes to Severity & Remediation**: Look up every code in `observation_codes` / `findings[].code` in [diagnosis-codes.md](references/diagnosis-codes.md) to assign exact severity (**Critical**: `BACKEND_UNREACHABLE`, `COMPONENT_NOT_RUNNING`, `RING_MEMBER_UNHEALTHY`, `TENANT_HEADER_REQUIRED`, `OPERATOR_CR_NOT_READY`; **Warning**: `RING_CHECK_FAILED`, `SPANS_DISCARDED`, `PARTITION_LAG_OBSERVED`, `METRICS_GENERATOR_PROCESSOR_ABSENT`, `TRACE_TIME_GAPS`, `SPAN_ERRORS_PRESENT`; **Info**: `BUILD_INFO_UNAVAILABLE`, `DEPLOYMENT_MODE_UNKNOWN`, `OVERRIDES_API_DISABLED`, `INGESTION_METRICS_UNREACHABLE`).
- [ ] **Step 3 — Branch by Tempo Major Version (2.x vs 3.x)**:
  - Consult [tempo-3-architecture.md](references/tempo-3-architecture.md) when `tempo_major_version == 3` (`architecture_generation == "3.x"`). In Tempo 3.x distributed mode, stateless `distributor -> ingest -> Kafka -> block-builder -> vParquet4 object storage` replaces stateful ingesters; remediate `PARTITION_LAG_OBSERVED` (`tempo_ingest_group_partition_lag_seconds`) by scaling `block-builder` consumers or ingest partitions.
  - In Tempo 2.x distributed mode, check memberlist gossip port `7946` and preserve stateful ingester WAL volumes before restarting unhealthy pods so in-memory traces are not lost.
- [ ] **Step 4 — Triage Missing Traces, Time Gaps & OTel Exporter Wiring**:
  - Follow [no-traces-decision-tree.md](references/no-traces-decision-tree.md) and [multi-tenancy.md](references/multi-tenancy.md) (`tempo_get_attribute_names`, `tempo_get_attribute_values(attribute="resource.service.name")`).
  - Whenever an OpenTelemetry Collector configuration snippet or file is provided, run `scripts/check_otel_exporter_config.py --yaml '<yaml>'` (or `--file <path>`) to catch `PORT_PROTOCOL_MISMATCH` (`otlp` gRPC targeting `:4318` instead of `:4317`, or `otlphttp` targeting `:4317`), `NO_TENANT_HEADER` (missing `headers.X-Scope-OrgID`), and `NOT_IN_TRACES_PIPELINE` (exporter declared under `exporters:` but omitted from `service.pipelines.traces.exporters`).
  - For incomplete traces (`TRACE_TIME_GAPS`), call `tempo_summarize_trace` and `tempo_get_trace` alongside `tempo_get_diagnostics` to check `max_bytes_per_trace_exceeded`, `otel.enabled=false`, or broken W3C `traceparent` propagation.
- [ ] **Step 5 — Inspect Discarded Spans, Overrides & Operator CRs**:
  - When `SPANS_DISCARDED` or `METRICS_GENERATOR_PROCESSOR_ABSENT` is emitted, read `tempo://overrides/{backend_id}/{tenant}` via MCP resources to capture current limits and `etag`.
  - When `OPERATOR_CR_NOT_READY` is emitted, read `tempo://operator/crs/{namespace}` and `tempo://operator/manifests/{kind}/{namespace}/{name}` to inspect `status.conditions` safely.
- [ ] **Step 6 — Safe 2-Phase Remediation (`dry_run=True` First)**: `[GATE]`
  - Always preview changes first with `tempo_patch_tenant_overrides(..., expected_etag=..., dry_run=True)` or `tempo_apply_operator_cr(..., dry_run=True)`.
  - Pause for operator confirmation unless the user explicitly requested applying the fix live—and only after `dry_run=True` succeeds, execute `dry_run=False, confirm=True` followed by a post-change `tempo_get_diagnostics` verification!

## References & Offline Scripts

- Observation code catalog (`ALL_OBSERVATION_CODES` -> severity & remediation): [diagnosis-codes.md](references/diagnosis-codes.md)
- Decision tree for missing traces and empty search results: [no-traces-decision-tree.md](references/no-traces-decision-tree.md)
- Tempo 2.x vs Tempo 3.x architecture & vParquet4 guide: [tempo-3-architecture.md](references/tempo-3-architecture.md)
- Multi-tenancy (`X-Scope-OrgID`) troubleshooting guide: [multi-tenancy.md](references/multi-tenancy.md)
- Offline OpenTelemetry Collector OTLP exporter validator: `scripts/check_otel_exporter_config.py`
