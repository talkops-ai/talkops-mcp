"""End-to-end workflow journey tests verifying the Five-Tool Test (< 5 sequential tool calls)."""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import patch

import pytest

from tests.unit.test_tools_and_resources import _capture_tools, mocked_locator  # noqa: F401


class TestEndToEndJourneys:
    @pytest.mark.asyncio
    async def test_journey_1_incident_red_slo_and_exemplar_pivot_under_5_calls(
        self, mocked_locator: Dict[str, Any]
    ) -> None:
        """Verify an operator can triage an incident and extract Tempo trace IDs in 4 tool calls."""
        tools = _capture_tools(mocked_locator)
        call_count = 0

        # Call 1: Backend & target diagnostics
        diag = await tools["prom_get_diagnostics"](backend_id="default", include="overview")
        call_count += 1
        assert diag["health"] == "healthy"

        # Call 2: Service RED + exemplar extraction
        red = await tools["prom_analyze_service_red"](
            backend_id="default", service_selector='job="api"', lookback="15m"
        )
        call_count += 1
        assert red["exemplars"][0]["trace_id"] == "trace-abc-123"

        # Call 3: Multi-window SLO burn evaluation
        slo = await tools["prom_evaluate_slo_burn"](
            backend_id="default",
            error_query='sum(rate(http_requests_total{job="api",status=~"5.."}[5m]))',
            total_query='sum(rate(http_requests_total{job="api"}[5m]))',
            slo_target=0.999,
        )
        call_count += 1
        assert slo["burn_rate_multiplier"] >= 0

        # Call 4: Period-over-period comparison
        cmp_res = await tools["prom_compare_periods"](
            backend_id="default",
            query='sum(rate(http_requests_total{job="api"}[5m]))',
            current_start="-15m",
            current_end="now",
            baseline_offset="1h",
        )
        call_count += 1
        assert len(cmp_res["comparisons"]) == 1
        assert call_count < 5

    @pytest.mark.asyncio
    async def test_journey_2_cardinality_finops_to_recording_rule_under_5_calls(
        self, mocked_locator: Dict[str, Any]
    ) -> None:
        """Verify TSDB cardinality diagnosis -> rule validation -> dry-run upsert completes in 3 calls."""
        tools = _capture_tools(mocked_locator)
        call_count = 0

        # Call 1: Analyze TSDB cardinality
        card = await tools["prom_analyze_cardinality"](backend_id="default")
        call_count += 1
        assert len(card["top_metrics"]) == 2

        new_group = {
            "name": "finops-recording-rules",
            "interval": "30s",
            "rules": [
                {
                    "record": "job:http_request_duration_seconds:p99_5m",
                    "expr": "histogram_quantile(0.99, sum by (le, job) (rate(http_request_duration_seconds_bucket[5m])))",
                }
            ],
        }

        with patch(
            "prometheus_mcp_server.tools.rules.rules_tools.is_promtool_available",
            return_value=False,
        ):
            # Call 2: Validate rule group
            val = await tools["prom_validate_rules"](rule_group=new_group)
            call_count += 1
            assert val["valid"] is True

            # Call 3: Dry-run upsert rule group
            up = await tools["prom_upsert_rule_group"](
                backend_id="default",
                group=new_group,
                namespace="monitoring",
                dry_run=True,
            )
            call_count += 1
            assert up["status"] == "dry_run_preview"

        assert call_count < 5
