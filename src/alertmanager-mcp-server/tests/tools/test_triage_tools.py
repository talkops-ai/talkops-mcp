"""Tests for `triage` toolset (`am_summarize_oncall`, `am_list_alerts`, `am_list_alert_groups`)."""

from __future__ import annotations

import httpx
import pytest
import respx

from alertmanager_mcp_server.server.bootstrap import ServerBootstrap
from tests.conftest import (
    MOCK_ALERTS_RESPONSE,
    MOCK_ALERT_GROUPS_RESPONSE,
    MOCK_SILENCES_RESPONSE,
)


class TestTriageTools:
    @respx.mock
    @pytest.mark.asyncio
    async def test_am_summarize_oncall_reports_watchdog_and_breakdowns(
        self, test_server_config
    ) -> None:
        respx.get("http://localhost:9093/api/v2/alerts").mock(
            return_value=httpx.Response(200, json=MOCK_ALERTS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/silences").mock(
            return_value=httpx.Response(200, json=MOCK_SILENCES_RESPONSE)
        )

        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)
        result = await mcp.call_tool("am_summarize_oncall", {"backend_id": "test-am"})
        data = result.structured_content
        assert data is not None
        assert data["backend_id"] == "test-am"
        assert data["watchdog_status"] == "firing"
        # Watchdog is excluded from active incident count (3 total - 1 Watchdog = 2 active)
        assert data["total_active_alerts"] == 2
        assert data["active_silences_count"] == 1
        assert data["by_service"]["checkout"] == 1
        await service.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_am_list_alerts_with_label_filters_and_states(
        self, test_server_config
    ) -> None:
        alerts_route = respx.get("http://localhost:9093/api/v2/alerts").mock(
            return_value=httpx.Response(200, json=MOCK_ALERTS_RESPONSE[1:2])
        )
        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)
        result = await mcp.call_tool(
            "am_list_alerts",
            {
                "backend_id": "test-am",
                "alertname": "=~High.*",
                "severity": "critical",
                "label_filters": '{env="prod", service="checkout"}',
                "state": "active",
                "limit": 10,
                "offset": 0,
            },
        )
        data = result.structured_content
        assert data is not None
        assert data["total"] == 1
        assert data["alerts"][0]["fingerprint"] == "abc123"
        assert alerts_route.called
        await service.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_am_list_alert_groups(self, test_server_config) -> None:
        respx.get("http://localhost:9093/api/v2/alerts/groups").mock(
            return_value=httpx.Response(200, json=MOCK_ALERT_GROUPS_RESPONSE)
        )
        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)
        result = await mcp.call_tool(
            "am_list_alert_groups",
            {"backend_id": "test-am", "state": "active", "limit": 10},
        )
        data = result.structured_content
        assert data is not None
        assert data["total_groups"] == 2
        assert data["groups"][0]["receiver"]["name"] == "payments-pagerduty"
        await service.close()
