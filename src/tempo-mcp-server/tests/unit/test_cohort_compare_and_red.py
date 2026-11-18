"""Unit tests for tempo_analyze_service_red and tempo_compare_span_cohorts."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from tempo_mcp_server.config import ServerConfig
from tempo_mcp_server.tools.metrics.metrics_tools import MetricsTools


def _register_metrics_tools(tempo_svc):
    locator = {
        "tempo_service": tempo_svc,
        "kubernetes_service": MagicMock(),
        "config": ServerConfig(),
    }
    mcp = MagicMock()
    captured = {}

    def capture_tool(**kwargs):
        def decorator(fn):
            captured[fn.__name__] = fn
            return fn

        return decorator

    mcp.tool = capture_tool
    MetricsTools(locator).register(mcp)
    return captured


class TestServiceRedAndCohorts:
    """Verify RED metrics calculation and compare() cohort query construction."""

    @pytest.mark.asyncio
    async def test_analyze_service_red_returns_rates_and_quantiles_without_verdict(self):
        tempo = MagicMock()

        async def fake_range(backend_id, q, start=None, end=None, step=None, tenant=None, exemplars=False, sample=None):
            if "status = error" in q:
                return {"data": {"result": [{"metric": {}, "values": [[1000, "2.0"]]}]}}
            if "0.5" in q:
                return {"data": {"result": [{"metric": {}, "values": [[1000, "0.05"]]}]}}
            if "0.95" in q:
                return {"data": {"result": [{"metric": {}, "values": [[1000, "0.25"]]}]}}
            if "0.99" in q:
                return {"data": {"result": [{"metric": {}, "values": [[1000, "0.85"]]}]}}
            return {"data": {"result": [{"metric": {}, "values": [[1000, "40.0"]]}]}}

        tempo.metrics_query_range = AsyncMock(side_effect=fake_range)
        tools = _register_metrics_tools(tempo)

        res = await tools["tempo_analyze_service_red"](
            backend_id="default",
            service="checkout",
            since="15m",
            ctx=AsyncMock(),
        )
        assert res["service"] == "checkout"
        assert res["current"]["rate_rps"] == 40.0
        assert res["current"]["error_rate_rps"] == 2.0
        assert res["current"]["error_ratio"] == 0.05
        assert res["current"]["p50_duration"] == 0.05
        assert res["current"]["p99_duration"] == 0.85
        assert "severity" not in res
        assert "verdict" not in res

    @pytest.mark.asyncio
    async def test_compare_span_cohorts_builds_compare_pipeline(self):
        tempo = MagicMock()
        tempo.metrics_query_instant = AsyncMock(
            return_value={
                "data": {
                    "result": [
                        {
                            "metric": {
                                "__meta_type": "selection",
                                "span.http.route": "/checkout",
                            },
                            "value": [1000, "82"],
                        },
                        {
                            "metric": {
                                "__meta_type": "baseline",
                                "span.http.route": "/checkout",
                            },
                            "value": [1000, "18"],
                        },
                    ]
                }
            }
        )
        tools = _register_metrics_tools(tempo)

        res = await tools["tempo_compare_span_cohorts"](
            backend_id="default",
            base_query='{ resource.service.name = "checkout" }',
            selection="status = error",
            top_n=10,
            ctx=AsyncMock(),
        )
        assert (
            res["effective_query"]
            == '{ resource.service.name = "checkout" } | compare({ status = error }, 10)'
        )
        assert len(res["divergent_attributes"]) == 1
        assert res["divergent_attributes"][0]["attribute"] == "span.http.route"
        assert res["divergent_attributes"][0]["value"] == "/checkout"
