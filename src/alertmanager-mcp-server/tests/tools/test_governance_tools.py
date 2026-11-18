"""Tests for `governance` toolset (`am_audit_alert_hygiene`, `am_audit_silences`)."""

from __future__ import annotations

import httpx
import pytest
import respx

from alertmanager_mcp_server.server.bootstrap import ServerBootstrap
from tests.conftest import (
    MOCK_ALERTS_RESPONSE,
    MOCK_SILENCES_RESPONSE,
    MOCK_STATUS_RESPONSE,
)


class TestGovernanceTools:
    @respx.mock
    @pytest.mark.asyncio
    async def test_am_audit_alert_hygiene_detects_default_route_and_missing_annotations(
        self, test_server_config
    ) -> None:
        respx.get("http://localhost:9093/api/v2/status").mock(
            return_value=httpx.Response(200, json=MOCK_STATUS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/alerts").mock(
            return_value=httpx.Response(200, json=MOCK_ALERTS_RESPONSE)
        )

        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)
        res = await mcp.call_tool(
            "am_audit_alert_hygiene",
            {"backend_id": "test-am", "check_long_firing_hours": 24},
        )
        data = res.structured_content
        assert data is not None
        assert data["watchdog_status"] == "firing"
        assert data["default_route_count"] == 1
        assert data["default_route_alerts"][0]["fingerprint"] == "def456"
        assert data["missing_annotations_count"] == 1
        assert data["invalid_severity_count"] == 1
        assert data["long_firing_count"] == 1
        await service.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_am_audit_silences_detects_violations_and_expiring_soon(
        self, test_server_config
    ) -> None:
        bad_silence = {
            **MOCK_SILENCES_RESPONSE[0],
            "id": "silence-bad",
            "matchers": [{"name": "env", "value": "prod", "isRegex": False, "isEqual": True}],
            "createdBy": "mcp",
            "comment": "no ticket",
        }
        respx.get("http://localhost:9093/api/v2/silences").mock(
            return_value=httpx.Response(
                200, json=[MOCK_SILENCES_RESPONSE[0], bad_silence]
            )
        )
        respx.get("http://localhost:9093/api/v2/alerts").mock(
            return_value=httpx.Response(200, json=MOCK_ALERTS_RESPONSE)
        )

        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)
        res = await mcp.call_tool(
            "am_audit_silences",
            {
                "backend_id": "test-am",
                "since_minutes": 1440,
                "expiring_within_minutes": 120,
            },
        )
        data = res.structured_content
        assert data is not None
        assert data["active_silences_count"] == 2
        assert data["policy_violations_count"] == 1
        assert data["non_compliant_silences"][0]["id"] == "silence-bad"
        assert len(data["expiring_soon_silences"]) == 2
        await service.close()
