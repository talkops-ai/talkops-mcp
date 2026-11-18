# "No Traces Found" Decision Tree

When `tempo_traceql_search` or `tempo_get_trace` returns zero traces, execute these checks in order:

## Branch 1: Verify Backend Readiness & Tenant Isolation

1. Call `tempo_get_diagnostics` and check for `BACKEND_UNREACHABLE` or `TENANT_HEADER_REQUIRED`.
2. If multi-tenancy is enabled (`multitenancy_enabled: true` in `tempo://deployment/overview`), verify the exact `X-Scope-OrgID` value emitted by the OpenTelemetry Collector and pass `tenant="<org_id>"` to `tempo_traceql_search` and `tempo_get_attribute_names`.

## Branch 2: Check Schema Population (`tempo_get_attribute_names`)

1. Call `tempo_get_attribute_names` (`scope="resource"`).
2. **If `attribute_names` is completely empty**:
   - No spans have been ingested for this tenant in the retention window, OR ingester live traces have not flushed and querier cannot reach ingesters.
   - Check `SPANS_DISCARDED` in `tempo_get_diagnostics` (`discarded_spans`).
   - Run `scripts/check_otel_exporter_config.py` against the OpenTelemetry Collector config to verify the OTLP gRPC (`4317`) or HTTP (`4318`) endpoint and tenant headers.
3. **If `attribute_names` is non-empty**:
   - Call `tempo_get_attribute_values` with `attribute_name="resource.service.name"` to check for service name typos or environment prefixes.

## Branch 3: Check Time Window & Ingestion Lag

1. Broaden `start` and `end` (for example `start="now-6h"`, `end="now"`) and set `most_recent=True` on `tempo_traceql_search`.
2. On Tempo 3.x, check `PARTITION_LAG_OBSERVED` in `tempo_get_diagnostics`; high Kafka partition lag delays trace visibility in object storage blocks.
