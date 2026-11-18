"""End-to-end workflow journey tests verifying the Five-Tool Test (< 5 sequential tool calls)."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest
from fastmcp import Client

from loki_mcp_server.server.bootstrap import ServerBootstrap
from tests.conftest import LOKI_BASE_URL, get_text


@pytest.fixture
async def journey_client(mock_loki_http):
    env = {
        "LOKI_URL": LOKI_BASE_URL,
        "MCP_ALLOW_WRITE": "true",
    }
    with patch.dict(os.environ, env, clear=False):
        mcp, _, _ = ServerBootstrap.initialize(["--allow-write"])
        async with Client(transport=mcp) as client:
            yield client


class TestEndToEndJourneys:
    """Verifies multi-step SRE and FinOps workflows complete in < 5 sequential tool calls."""

    @pytest.mark.asyncio
    async def test_journey_1_incident_triage_and_trace_pivot_under_5_calls(
        self, journey_client
    ) -> None:
        call_count = 0

        # Call 1: Backend & ingestion diagnostics
        diag_res = await journey_client.call_tool("loki_get_diagnostics", {})
        call_count += 1
        diag = json.loads(get_text(diag_res))
        assert diag["health"]["reachable"] is True

        # Call 2: One-shot service log health & error digest
        sum_res = await journey_client.call_tool(
            "loki_summarize_service_logs",
            {"selector": '{app="checkout"}', "start": "now-30m"},
        )
        call_count += 1
        summary = json.loads(get_text(sum_res))
        assert "error_summary" in summary

        # Call 3: Period-over-period regression comparison
        cmp_res = await journey_client.call_tool(
            "loki_compare_periods",
            {
                "selector": '{app="checkout"}',
                "start": "now-15m",
                "baseline_offset": "1h",
            },
        )
        call_count += 1
        cmp_data = json.loads(get_text(cmp_res))
        assert "new_error_signatures" in cmp_data

        # Call 4: Cross-service trace log correlation
        corr_res = await journey_client.call_tool(
            "loki_correlate_trace_logs",
            {"correlation_id": "4bf92f3577b34da6a3ce929d0e0e4736", "start": "now-1h"},
        )
        call_count += 1
        corr = json.loads(get_text(corr_res))
        assert corr["correlation_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert call_count < 5

    @pytest.mark.asyncio
    async def test_journey_2_finops_volume_to_recording_rule_under_5_calls(
        self, journey_client
    ) -> None:
        call_count = 0

        # Call 1: Analyze log ingestion volume
        vol_res = await journey_client.call_tool(
            "loki_analyze_volume",
            {"query": '{namespace="prod"}', "target_label": "service_name"},
        )
        call_count += 1
        vol = json.loads(get_text(vol_res))
        assert vol["total_attributed_bytes"] > 0

        # Call 2: Check active series cardinality
        ser_res = await journey_client.call_tool(
            "loki_get_series",
            {"match": '{app="checkout"}'},
        )
        call_count += 1
        ser = json.loads(get_text(ser_res))
        assert ser["total_series"] > 0

        recording_rule_yaml = (
            "name: checkout-finops-recording\n"
            "interval: 1m\n"
            "rules:\n"
            "  - record: service_name:loki_http_requests:rate5m\n"
            '    expr: sum by (service_name) (rate({service_name="checkout"}[5m]))\n'
        )

        # Call 3: Dry-run upsert recording rule
        preview_res = await journey_client.call_tool(
            "loki_upsert_rule_group",
            {
                "namespace": "prod",
                "group_name": "checkout-finops-recording",
                "rules_yaml": recording_rule_yaml,
                "dry_run": True,
            },
        )
        call_count += 1
        preview = json.loads(get_text(preview_res))
        assert preview["status"] == "dry_run_preview"

        # Call 4: Confirmed upsert recording rule
        apply_res = await journey_client.call_tool(
            "loki_upsert_rule_group",
            {
                "namespace": "prod",
                "group_name": "checkout-finops-recording",
                "rules_yaml": recording_rule_yaml,
                "dry_run": False,
                "confirm": True,
            },
        )
        call_count += 1
        applied = json.loads(get_text(apply_res))
        assert applied["dry_run"] is False
        assert call_count < 5

    @pytest.mark.asyncio
    async def test_journey_3_compactor_pii_scrubbing_under_5_calls(
        self, journey_client
    ) -> None:
        call_count = 0

        # Call 1: Verify matching lines with read-only range query
        q_res = await journey_client.call_tool(
            "loki_query_range",
            {"query": '{app="checkout"} |= "secret"', "start": "now-1h", "max_log_lines": 5},
        )
        call_count += 1
        assert json.loads(get_text(q_res))["result_type"] == "streams"

        # Call 2: Preview Compactor deletion blast radius (dry_run=True)
        del_preview_res = await journey_client.call_tool(
            "loki_manage_delete_requests",
            {
                "action": "create",
                "query": '{app="checkout"} |= "secret"',
                "start": "now-1h",
                "dry_run": True,
            },
        )
        call_count += 1
        assert json.loads(get_text(del_preview_res))["dry_run"] is True

        # Call 3: Submit confirmed Compactor deletion request
        del_apply_res = await journey_client.call_tool(
            "loki_manage_delete_requests",
            {
                "action": "create",
                "query": '{app="checkout"} |= "secret"',
                "start": "now-1h",
                "dry_run": False,
                "confirm": True,
            },
        )
        call_count += 1
        assert json.loads(get_text(del_apply_res))["dry_run"] is False
        assert call_count < 5
