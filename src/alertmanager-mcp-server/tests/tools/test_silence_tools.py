"""Tests for `silences` toolset (`am_list_silences`, `am_preview_silence`, `am_create_silence`, `am_silence_alert`, `am_update_silence`, `am_expire_silence`)."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from alertmanager_mcp_server.server.bootstrap import ServerBootstrap
from tests.conftest import (
    MOCK_ALERTS_RESPONSE,
    MOCK_CREATE_SILENCE_RESPONSE,
    MOCK_SILENCES_RESPONSE,
    MOCK_STATUS_RESPONSE,
)


class TestSilenceTools:
    @respx.mock
    @pytest.mark.asyncio
    async def test_am_list_and_preview_silence(self, test_server_config) -> None:
        respx.get("http://localhost:9093/api/v2/silences").mock(
            return_value=httpx.Response(200, json=MOCK_SILENCES_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/alerts").mock(
            return_value=httpx.Response(200, json=MOCK_ALERTS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/status").mock(
            return_value=httpx.Response(200, json=MOCK_STATUS_RESPONSE)
        )

        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)
        list_res = await mcp.call_tool(
            "am_list_silences",
            {"backend_id": "test-am", "state": "active", "created_by": "sre"},
        )
        list_sc = list_res.structured_content
        assert list_sc is not None
        assert list_sc["total"] == 1

        prev_res = await mcp.call_tool(
            "am_preview_silence",
            {
                "backend_id": "test-am",
                "matchers": ['alertname="HighLatency"', 'service="checkout"'],
                "duration_minutes": 60,
                "created_by": "sre@example.com",
                "comment": "CHG-101: preview",
            },
        )
        pdata = prev_res.structured_content
        assert pdata is not None
        assert pdata["valid"] is True
        assert pdata["affected_alert_count"] == 1
        assert len(pdata["overlapping_silences"]) == 1
        await service.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_am_create_silence_with_colon_comment_and_deduplication(
        self, test_server_config
    ) -> None:
        respx.get("http://localhost:9093/api/v2/alerts").mock(
            return_value=httpx.Response(200, json=MOCK_ALERTS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/status").mock(
            return_value=httpx.Response(200, json=MOCK_STATUS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/silences").mock(
            return_value=httpx.Response(200, json=MOCK_SILENCES_RESPONSE)
        )
        respx.post("http://localhost:9093/api/v2/silences").mock(
            return_value=httpx.Response(200, json=MOCK_CREATE_SILENCE_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/silence/silence-002").mock(
            return_value=httpx.Response(
                200,
                json={
                    **MOCK_SILENCES_RESPONSE[0],
                    "id": "silence-002",
                    "comment": "JIRA-101: database failover window",
                },
            )
        )

        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)

        # 1. Exact duplicate of silence-001 returns deduped=True
        dup_res = await mcp.call_tool(
            "am_create_silence",
            {
                "backend_id": "test-am",
                "matchers": [
                    {"name": "alertname", "value": "HighLatency", "isRegex": False, "isEqual": True},
                    {"name": "service", "value": "checkout", "isRegex": False, "isEqual": True},
                ],
                "duration_minutes": 60,
                "created_by": "sre@example.com",
                "comment": "JIRA-101: database failover window",
                "confirm": True,
            },
        )
        dup_sc = dup_res.structured_content
        assert dup_sc is not None
        assert dup_sc["deduped"] is True
        assert dup_sc["silence_id"] == "silence-001"

        # 2. New matcher set creates silence-002 cleanly even with colons in comment
        new_res = await mcp.call_tool(
            "am_create_silence",
            {
                "backend_id": "test-am",
                "matchers": [
                    {"name": "alertname", "value": "HighLatency", "isRegex": False, "isEqual": True},
                    {"name": "instance", "value": "checkout-01:8080", "isRegex": False, "isEqual": True},
                ],
                "duration_minutes": 60,
                "created_by": "sre@example.com",
                "comment": "JIRA-101: database failover window",
                "confirm": True,
            },
        )
        new_sc = new_res.structured_content
        assert new_sc is not None
        assert new_sc["deduped"] is False
        assert new_sc["silence_id"] == "silence-002"
        await service.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_am_silence_alert_and_expire_silence(
        self, test_server_config
    ) -> None:
        respx.get("http://localhost:9093/api/v2/alerts").mock(
            return_value=httpx.Response(200, json=MOCK_ALERTS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/status").mock(
            return_value=httpx.Response(200, json=MOCK_STATUS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/silences").mock(
            return_value=httpx.Response(200, json=[])
        )
        respx.post("http://localhost:9093/api/v2/silences").mock(
            return_value=httpx.Response(200, json=MOCK_CREATE_SILENCE_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/silence/silence-002").mock(
            return_value=httpx.Response(
                200,
                json={**MOCK_SILENCES_RESPONSE[0], "id": "silence-002"},
            )
        )
        respx.get("http://localhost:9093/api/v2/silence/silence-001").mock(
            return_value=httpx.Response(200, json=MOCK_SILENCES_RESPONSE[0])
        )
        del_route = respx.delete("http://localhost:9093/api/v2/silence/silence-001").mock(
            return_value=httpx.Response(200)
        )

        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)

        sil_res = await mcp.call_tool(
            "am_silence_alert",
            {
                "backend_id": "test-am",
                "fingerprint": "abc123",
                "scope": "instance",
                "duration_minutes": 30,
                "created_by": "sre@example.com",
                "comment": "INC-900: investigating checkout-01",
                "confirm": True,
            },
        )
        sil_sc = sil_res.structured_content
        assert sil_sc is not None
        assert sil_sc["silence_id"] == "silence-002"

        # Expire silence requires confirm=True
        with pytest.raises(ToolError, match="confirm=True"):
            await mcp.call_tool(
                "am_expire_silence",
                {
                    "backend_id": "test-am",
                    "silence_id": "silence-001",
                    "expired_by": "sre@example.com",
                    "reason": "CHG-101 completed early",
                    "confirm": False,
                },
            )
        assert del_route.call_count == 0

        exp_res = await mcp.call_tool(
            "am_expire_silence",
            {
                "backend_id": "test-am",
                "silence_id": "silence-001",
                "expired_by": "sre@example.com",
                "reason": "CHG-101 completed early",
                "confirm": True,
            },
        )
        exp_sc = exp_res.structured_content
        assert exp_sc is not None
        assert exp_sc["status"] == "expired"
        assert del_route.call_count == 1
        await service.close()
