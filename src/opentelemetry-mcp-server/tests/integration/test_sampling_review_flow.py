"""End-to-End Workflow Test: Sampling & Trace-Derived Metrics Flow.

Matches the `tuning-sampling-and-trace-derived-metrics` skill workflow:
  1. Read `otel://sampling/{namespace}/{collector}`
  2. Verify `otel_configure_sampling` blocks `tail` sampling on a DaemonSet collector (`CFG_TAIL_SAMPLING_NO_TRACE_AFFINITY`)
  3. Configure `probabilistic` head sampling in `dry_run=True`
"""

import json
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

pytestmark = pytest.mark.asyncio


async def test_sampling_review_flow(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        # 1. Read current sampling resource
        samp_res = await client.read_resource("otel://sampling/observability/my-collector")
        samp_data = json.loads(samp_res[0].text)
        assert "mode" in samp_data

        # 2. Verify tail sampling is blocked on a daemonset collector without trace affinity
        try:
            tail_res = await client.call_tool(
                "otel_configure_sampling",
                {
                    "namespace": "observability",
                    "collector_name": "my-collector",
                    "strategy": "tail",
                    "sampling_options": {"sample_rate": 0.10},
                    "dry_run": True,
                },
            )
            tail_data = json.loads(tail_res.content[0].text)
            assert (
                tail_data.get("blocked") is True
                or tail_data.get("action") == "blocked_by_topology"
                or any(
                    "TAIL_SAMPLING" in str(f.get("code", ""))
                    for f in tail_data.get("findings", [])
                )
            )
        except ToolError as exc:
            assert "tail" in str(exc).lower() or "daemonset" in str(exc).lower()

        # 3. Configure probabilistic head sampling in dry_run=True
        head_res = await client.call_tool(
            "otel_configure_sampling",
            {
                "namespace": "observability",
                "collector_name": "my-collector",
                "strategy": "probabilistic",
                "sampling_options": {"sample_rate": 0.25},
                "dry_run": True,
            },
        )
        head_data = json.loads(head_res.content[0].text)
        assert head_data["dry_run"] is True
