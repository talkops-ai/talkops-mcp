# Per-Tenant `/api/overrides` Tuning Cookbook

## 1. Supported Per-Tenant Override Fields

Read `tempo://overrides/{backend_id}/{tenant}` before patching via `tempo_patch_tenant_overrides`.

| Field | Type | Typical Production Range | Purpose & Symptoms When Exceeded |
| :--- | :--- | :--- | :--- |
| `ingestion_rate_limit_bytes` | `int` | `15000000` (15 MB/s) – `100000000` (100 MB/s) | Sustained per-tenant byte ingestion limit (`rate_limited` in `discarded_spans`). |
| `ingestion_burst_size_bytes` | `int` | `1.3x–2.0x` of `ingestion_rate_limit_bytes` | Token bucket burst allowance for traffic spikes. Always set `>= ingestion_rate_limit_bytes`. |
| `max_bytes_per_trace` | `int` | `5000000` (5 MB) – `50000000` (50 MB) | Maximum byte size of a single trace (`max_bytes_per_trace_exceeded` in `discarded_spans`). |
| `max_traces_per_user` | `int` | `10000` – `100000` | Maximum concurrent active live traces in ingester memory (`max_live_traces_per_tenant_exceeded`). |
| `block_retention` | `str` | `"168h"` (7d) – `"720h"` (30d) | Per-tenant trace block retention window in object storage. |
| `metrics_generator.processors` | `list[str]` | `["service-graphs", "span-metrics", "local-blocks"]` | Active `metrics-generator` processors for the tenant. |

## 2. Safe Tuning Rules

1. **Burst Ratio Rule**: Whenever raising `ingestion_rate_limit_bytes`, set `ingestion_burst_size_bytes` to at least `int(ingestion_rate_limit_bytes * 1.5)` so micro-bursts from batching OTel Collectors are not dropped.
2. **Optimistic Concurrency (`etag`)**: Always pass the `etag` from `tempo://overrides/{backend_id}/{tenant}` to `tempo_patch_tenant_overrides` when updating an existing tenant config. If HTTP 412 (`Precondition Failed`) occurs, re-read `tempo://overrides/{backend_id}/{tenant}` and re-apply.
