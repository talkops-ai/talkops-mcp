# Multi-Tenancy (`X-Scope-OrgID`) Troubleshooting

## 1. How Tempo Enforces Multi-Tenancy

When `multitenancy_enabled: true` is active in `/status/config` (visible via `tempo://deployment/overview`):
- Every ingestion request (OTLP gRPC/HTTP) and every query request (`/api/search`, `/api/traces`, `/api/metrics`, `/api/overrides`) MUST include the `X-Scope-OrgID` header.
- Missing headers trigger HTTP 400/401 and produce `TENANT_HEADER_REQUIRED` in `tempo_get_diagnostics`.

## 2. Common Multi-Tenant Failure Modes

1. **Tenant Header Mismatch ("Silent Empty Results")**:
   - The OTel Collector writes traces under `X-Scope-OrgID: prod`, while queries use `X-Scope-OrgID: default`.
   - **Check**: Compare the `headers.X-Scope-OrgID` in the OTel Collector exporter config (`scripts/check_otel_exporter_config.py`) against the `tenant` parameter passed to `tempo_traceql_search`.
2. **Per-Tenant Rate Limit Exhaustion**:
   - One noisy tenant exceeds `ingestion_rate_limit_bytes` or `max_live_traces_per_tenant`.
   - **Check**: Inspect `discarded_spans` in `tempo_get_diagnostics` (filtered by `tenant` label) and read `tempo://overrides/{backend_id}/{tenant}`.
