# Tempo Observation Codes Catalog

## Table of Contents

1. [Overview](#1-overview)
2. [Connectivity & Version Observation Codes](#2-connectivity--version-observation-codes)
3. [Component & Ring Observation Codes](#3-component--ring-observation-codes)
4. [Ingestion, Overrides & Metrics-Generator Codes](#4-ingestion-overrides--metrics-generator-codes)
5. [Trace & Kubernetes Operator Observation Codes](#5-trace--kubernetes-operator-observation-codes)

## 1. Overview

`tempo_get_diagnostics` and `tempo_summarize_trace` return purely factual observation codes. Use the tables below to assign operational severity (**Critical**, **Warning**, **Info**) and execute the corresponding remediation workflow.

## 2. Connectivity & Version Observation Codes

| Observation Code | Severity | Meaning & Evidence | Remediation Steps |
| :--- | :--- | :--- | :--- |
| `BACKEND_UNREACHABLE` | **Critical** | `/ready` probe failed or timed out for the Tempo backend. | Verify the configured Tempo base URL, Kubernetes Service DNS, network policies, and gateway pod readiness. |
| `BUILD_INFO_UNAVAILABLE` | **Info** | `/api/status/buildinfo` could not be read; version defaulted to 2.x heuristics. | Check whether the Tempo HTTP gateway blocks `/api/status/buildinfo` or requires authentication headers. |
| `DEPLOYMENT_MODE_UNKNOWN` | **Info** | Neither `/status/services` nor `/api/status/buildinfo` exposed the deployment topology. | Inspect `tempo://operator/crs/{namespace}` or Kubernetes pod labels to determine monolithic vs microservices mode. |

## 3. Component & Ring Observation Codes

| Observation Code | Severity | Meaning & Evidence | Remediation Steps |
| :--- | :--- | :--- | :--- |
| `COMPONENT_NOT_RUNNING` | **Critical** | A Tempo service in `/status/services` reported a non-running state (`starting`, `stopping`, `failed`). | Inspect pod logs and events for the failing module (`distributor`, `ingester`, `ingest`, `block-builder`, `querier`, `compactor`). |
| `RING_CHECK_FAILED` | **Warning** | A hash ring status endpoint (`/distributor/ring`, `/ingester/ring`, `/compactor/ring`, `/metrics-generator/ring`) failed to respond. | Verify that the admin HTTP port routes ring endpoints or check memberlist gossip connectivity (`port 7946`). |
| `RING_MEMBER_UNHEALTHY` | **Critical** | One or more hash ring members reported non-active state or stale heartbeat timestamps. | Check for crashed or OOMKilled ingester/compactor pods and verify headless service DNS resolution for memberlist gossip. |

## 4. Ingestion, Overrides & Metrics-Generator Codes

| Observation Code | Severity | Meaning & Evidence | Remediation Steps |
| :--- | :--- | :--- | :--- |
| `SPANS_DISCARDED` | **Warning** | `tempo_discarded_spans_total` is greater than zero in `/metrics`. Inspect `evidence.reason` (`rate_limited`, `max_bytes_per_trace_exceeded`, `max_live_traces_per_tenant_exceeded`). | Read `tempo://overrides/{backend_id}/{tenant}` and raise `ingestion_rate_limit_bytes`, `ingestion_burst_size_bytes`, or `max_bytes_per_trace` via `tempo_patch_tenant_overrides`. |
| `PARTITION_LAG_OBSERVED` | **Warning** | Tempo 3.x `tempo_ingest_group_partition_lag_seconds` is positive in `/metrics`, indicating `block-builder` consumers are lagging behind Kafka `ingest` partitions. | Scale `block-builder` replicas or increase object storage upload concurrency. |
| `METRICS_GENERATOR_PROCESSOR_ABSENT` | **Warning** | `metrics_generator.processors` in `/status/config` is missing `service-graphs`, `span-metrics`, or `local-blocks`. | Enable `service-graphs`, `span-metrics`, and `local-blocks` in the Tempo configuration or `TempoStack` CR (`template.metricsGenerator`). |
| `OVERRIDES_API_DISABLED` | **Info** | `/api/overrides` returned 404/405 because the runtime `user_configurable_overrides` module is not enabled. | Enable the `user_configurable_overrides` module in Tempo config if dynamic per-tenant API overrides are required. |
| `INGESTION_METRICS_UNREACHABLE` | **Info** | `/metrics` endpoint could not be scraped from the Tempo backend URL. | Check whether the query-frontend/gateway proxies `/metrics` or whether Prometheus scrapes pods directly. |
| `TENANT_HEADER_REQUIRED` | **Critical** | Tempo returned HTTP 401/400 indicating multi-tenancy (`multitenancy_enabled: true`) requires an `x-scope-orgid` header. | Pass `tenant="<tenant_id>"` to MCP tools or configure `default_tenant` on the backend. |

## 5. Trace & Kubernetes Operator Observation Codes

| Observation Code | Severity | Meaning & Evidence | Remediation Steps |
| :--- | :--- | :--- | :--- |
| `TRACE_TIME_GAPS` | **Warning** | Sum of critical-path span durations is `< 50%` of total trace duration in `tempo_summarize_trace`. | Check for uninstrumented middleware, async queue delays, thread-pool starvation, or dropped spans (`SPANS_DISCARDED`). |
| `SPAN_ERRORS_PRESENT` | **Warning** | One or more spans in `tempo_summarize_trace` have `status = error`. | Inspect `deepest_error_span` and `error_origin_service` using `triaging-tempo-service-errors`. |
| `OPERATOR_CR_NOT_READY` | **Critical** | A Kubernetes `TempoStack` or `TempoMonolithic` resource has `Ready=False` or non-empty `status.conditions` failures. | Read `tempo://operator/manifests/{kind}/{namespace}/{name}` and inspect operator controller logs, storage secret keys, and PVC/S3 permissions. |
