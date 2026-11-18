"""End-to-End Workflow Test: Cardinality & Noise Reduction Flow.

Matches the `controlling-telemetry-cardinality-and-noise` skill workflow:
  1. Read `otel://spanmetrics/{namespace}/{collector}` and `otel://logs-profile/{namespace}/{collector}`
  2. Configure OTTL processing (`otel_configure_processing`) with `dry_run=True`
  3. Configure bounded connectors (`otel_configure_connectors`) with `dry_run=True`
"""

import json
import pytest
from fastmcp import Client

pytestmark = pytest.mark.asyncio


async def test_cardinality_audit_flow(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        # 1. Inspect spanmetrics and logs profile resources
        sm_res = await client.read_resource("otel://spanmetrics/observability/my-collector")
        sm_data = json.loads(sm_res[0].text)
        assert sm_data["enabled"] is True

        logs_res = await client.read_resource("otel://logs-profile/observability/my-collector")
        logs_data = json.loads(logs_res[0].text)
        assert "enabled" in logs_data

        # 2. Preview OTTL cardinality & noise processing rules
        proc_res = await client.call_tool(
            "otel_configure_processing",
            {
                "namespace": "observability",
                "collector_name": "my-collector",
                "signals": ["logs", "traces"],
                "rules": {
                    "parse_json": True,
                    "mask_pii": True,
                    "drop_attributes": ["http.user_agent", "url.query"],
                    "drop_noise_paths": ["/healthz", "/readyz", "/metrics"],
                },
                "dry_run": True,
            },
        )
        proc_data = json.loads(proc_res.content[0].text)
        assert proc_data["dry_run"] is True

        # 3. Preview bounded spanmetrics + servicegraph connectors
        conn_res = await client.call_tool(
            "otel_configure_connectors",
            {
                "namespace": "observability",
                "collector_name": "my-collector",
                "connectors": ["spanmetrics", "servicegraph"],
                "connector_options": {
                    "dimensions": ["http.request.method", "http.response.status_code"],
                },
                "dry_run": True,
            },
        )
        conn_data = json.loads(conn_res.content[0].text)
        assert conn_data["dry_run"] is True
