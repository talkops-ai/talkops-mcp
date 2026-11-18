"""Tests for `routing` toolset (`am_check_notification_health`, `am_explain_routing`, `am_push_test_alert`)."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from alertmanager_mcp_server.server.bootstrap import ServerBootstrap
from tests.conftest import (
    MOCK_ALERTS_RESPONSE,
    MOCK_RECEIVERS_RESPONSE,
    MOCK_SILENCES_RESPONSE,
    MOCK_STATUS_RESPONSE,
    SAMPLE_METRICS_TEXT,
)


class TestRoutingTools:
    @respx.mock
    @pytest.mark.asyncio
    async def test_am_check_notification_health(self, test_server_config) -> None:
        respx.get("http://localhost:9093/-/healthy").mock(
            return_value=httpx.Response(200, text="OK")
        )
        respx.get("http://localhost:9093/-/ready").mock(
            return_value=httpx.Response(200, text="OK")
        )
        respx.get("http://localhost:9093/api/v2/status").mock(
            return_value=httpx.Response(200, json=MOCK_STATUS_RESPONSE)
        )
        respx.get("http://localhost:9093/metrics").mock(
            return_value=httpx.Response(200, text=SAMPLE_METRICS_TEXT)
        )
        respx.get("http://localhost:9093/api/v2/receivers").mock(
            return_value=httpx.Response(200, json=MOCK_RECEIVERS_RESPONSE)
        )

        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)
        res = await mcp.call_tool(
            "am_check_notification_health",
            {"backend_id": "test-am", "integration": "pagerduty"},
        )
        data = res.structured_content
        assert data is not None
        assert data["status"] == "degraded"
        assert "pagerduty" in data["degraded_integrations"]
        assert "pagerduty" in data["integrations"]
        assert "slack" not in data["integrations"]
        await service.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_am_explain_routing_by_labels_and_fingerprint(
        self, test_server_config
    ) -> None:
        respx.get("http://localhost:9093/api/v2/status").mock(
            return_value=httpx.Response(200, json=MOCK_STATUS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/alerts").mock(
            return_value=httpx.Response(200, json=MOCK_ALERTS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/silences").mock(
            return_value=httpx.Response(200, json=MOCK_SILENCES_RESPONSE)
        )

        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)
        res = await mcp.call_tool(
            "am_explain_routing",
            {
                "backend_id": "test-am",
                "fingerprint": "abc123",
                "at_time": "2026-03-25T12:00:00Z",
            },
        )
        data = res.structured_content
        assert data is not None
        assert data["receivers"] == ["payments-pagerduty", "payments-audit-webhook"]
        assert data["fell_back_to_default"] is False
        assert len(data["matching_silences"]) == 1
        assert data["matching_silences"][0]["id"] == "silence-001"
        await service.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_am_push_test_alert_requires_confirm_and_sets_auto_resolve(
        self, test_server_config
    ) -> None:
        respx.get("http://localhost:9093/api/v2/status").mock(
            return_value=httpx.Response(200, json=MOCK_STATUS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/alerts").mock(
            return_value=httpx.Response(200, json=MOCK_ALERTS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/silences").mock(
            return_value=httpx.Response(200, json=MOCK_SILENCES_RESPONSE)
        )
        post_route = respx.post("http://localhost:9093/api/v2/alerts").mock(
            return_value=httpx.Response(200, json={})
        )

        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)

        # Without confirm=True, raises ToolError (ConfirmationRequiredError)
        with pytest.raises(ToolError, match="confirm=True"):
            await mcp.call_tool(
                "am_push_test_alert",
                {
                    "backend_id": "test-am",
                    "labels": {"alertname": "SyntheticTest", "team": "platform"},
                    "confirm": False,
                },
            )
        assert post_route.call_count == 0

        # With confirm=True, pushes synthetic alert with mcp_test="true" and endsAt
        res = await mcp.call_tool(
            "am_push_test_alert",
            {
                "backend_id": "test-am",
                "labels": {"alertname": "SyntheticTest", "team": "platform"},
                "resolve_after_minutes": 5,
                "confirm": True,
            },
        )
        data = res.structured_content
        assert data is not None
        assert data["status"] == "sent"
        assert data["labels"]["mcp_test"] == "true"
        assert data["starts_at"].endswith("Z")
        assert data["ends_at"].endswith("Z")
        assert post_route.call_count == 1
        await service.close()
