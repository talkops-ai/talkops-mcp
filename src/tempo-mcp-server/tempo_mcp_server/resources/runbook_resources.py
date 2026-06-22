"""Runbook resources — operational troubleshooting guides."""

from tempo_mcp_server.resources.base import BaseResource


class RunbookResources(BaseResource):
    """Static runbook resources for common operational scenarios."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "tempo://runbooks/latency-spike",
            name="tempo_runbook_latency_spike",
            description="Runbook: Investigating latency spikes using Tempo traces",
            mime_type="text/markdown",
        )
        async def runbook_latency_spike() -> str:
            return """# Runbook: Latency Spike Investigation

## Workflow
1. **Detect** — Use `tempo_traceql_metrics_range` to confirm the spike:
   ```
   { resource.service.name = "<service>" } | quantile_over_time(duration, 0.99)
   ```
2. **Locate** — Search for slow traces during the window:
   ```
   tempo_traceql_search(service="<service>", min_duration_ms=<threshold>, since="1h")
   ```
3. **Analyze** — Summarize the slowest trace:
   ```
   tempo_summarize_trace(trace_id="<id>")
   ```
4. **Correlate** — Find related traces:
   ```
   tempo_find_related_traces(trace_id="<id>", strategy="same_endpoint")
   ```
5. **Root Cause** — Check the critical path and error summaries in the trace summary.
"""

        @mcp_instance.resource(
            "tempo://runbooks/error-burst",
            name="tempo_runbook_error_burst",
            description="Runbook: Investigating error bursts using Tempo traces",
            mime_type="text/markdown",
        )
        async def runbook_error_burst() -> str:
            return """# Runbook: Error Burst Investigation

## Workflow
1. **Quantify** — Measure error rate:
   ```
   { status = error } | rate() | by(resource.service.name)
   ```
2. **Search** — Find error traces:
   ```
   tempo_traceql_search(service="<service>", status="error", since="30m")
   ```
3. **Triage** — Summarize an error trace to identify the root cause:
   ```
   tempo_summarize_trace(trace_id="<id>")
   ```
4. **Correlate** — Find traces with the same error pattern:
   ```
   tempo_find_related_traces(trace_id="<id>", strategy="same_service_errors")
   ```
"""

        @mcp_instance.resource(
            "tempo://runbooks/no-traces-found",
            name="tempo_runbook_no_traces",
            description="Runbook: Troubleshooting 'no traces found' scenarios",
            mime_type="text/markdown",
        )
        async def runbook_no_traces() -> str:
            return """# Runbook: No Traces Found

## Diagnostic Steps
1. **Check Backend Health**: `tempo_get_diagnostics(backend_id="<id>")`
2. **Verify Attributes Exist**: `tempo_get_attribute_names(backend_id="<id>", since="1h")`
3. **Broaden Time Range**: Try `since="24h"` or `since="7d"`
4. **Relax Filters**: Start with `{ }` (match everything) to confirm traces exist
5. **Check Tenant**: For multi-tenant backends, ensure correct tenant ID
6. **Check Ingestion**: Verify data pipeline (OTel Collector → Tempo)
7. **Retention**: Traces beyond the retention window are evicted

## Common Causes
- Wrong tenant ID
- Time range outside retention window
- Service not yet instrumented
- OTel Collector misconfiguration
"""

        @mcp_instance.resource(
            "tempo://runbooks/cross-tenant-access",
            name="tempo_runbook_cross_tenant",
            description="Runbook: Cross-tenant query configuration and usage",
            mime_type="text/markdown",
        )
        async def runbook_cross_tenant() -> str:
            return """# Runbook: Cross-Tenant Access

## Prerequisites
- `multi_tenant_queries_enabled: true` in Tempo config
- Requester must have permission for all target tenants

## Usage
Provide pipe-separated tenant IDs:
```
tenant="team-a|team-b"
```

## Tenant ID Constraints
- Max 150 bytes
- Allowed characters: alphanumeric + `!-_.*'()`
- Each segment in a pipe-separated list must be valid individually

## Example
```python
tempo_traceql_search(
    backend_id="prod",
    service="api-gateway",
    tenant="team-a|team-b",
    since="1h",
)
```
"""
