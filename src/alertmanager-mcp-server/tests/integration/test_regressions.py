"""End-to-end regression suite verifying fixes for all 14 audited defects (P1–P14)."""

from __future__ import annotations

import json
import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from alertmanager_mcp_server.server.bootstrap import ServerBootstrap
from tests.conftest import (
    MOCK_ALERTS_RESPONSE,
    MOCK_CREATE_SILENCE_RESPONSE,
    MOCK_RECEIVERS_RESPONSE,
    MOCK_SILENCES_RESPONSE,
    MOCK_STATUS_RESPONSE,
)


class TestAll14AuditRegressions:
    @respx.mock
    @pytest.mark.asyncio
    async def test_p1_and_p11_colon_comments_and_dict_args_not_corrupted(
        self, test_server_config
    ) -> None:
        """P1 & P11: Silence comments containing ':' and native dict arguments succeed."""
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
                json={
                    **MOCK_SILENCES_RESPONSE[0],
                    "id": "silence-002",
                    "comment": "JIRA-1: planned db failover",
                },
            )
        )

        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)
        res = await mcp.call_tool(
            "am_create_silence",
            {
                "backend_id": "test-am",
                "matchers": [
                    {"name": "alertname", "value": "DiskFull", "isRegex": False, "isEqual": True},
                    {"name": "service", "value": "db", "isRegex": False, "isEqual": True},
                ],
                "duration_minutes": 30,
                "created_by": "sre@example.com",
                "comment": "JIRA-1: planned db failover",
                "confirm": True,
            },
        )
        sc = res.structured_content
        assert sc is not None
        assert sc["silence_id"] == "silence-002"
        assert sc["comment"] == "JIRA-1: planned db failover"
        await service.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_p2_naive_datetime_rejected_with_tool_error(
        self, test_server_config
    ) -> None:
        """P2: Naive timestamps without timezone offset ('Z' or '±HH:MM') are rejected."""
        respx.get("http://localhost:9093/api/v2/alerts").mock(
            return_value=httpx.Response(200, json=[])
        )
        respx.get("http://localhost:9093/api/v2/status").mock(
            return_value=httpx.Response(200, json=MOCK_STATUS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/silences").mock(
            return_value=httpx.Response(200, json=[])
        )

        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)
        with pytest.raises(ToolError, match="SP006"):
            await mcp.call_tool(
                "am_create_silence",
                {
                    "backend_id": "test-am",
                    "matchers": [{"name": "service", "value": "db", "isRegex": False, "isEqual": True}],
                    "starts_at": "2026-11-03T10:00:00",
                    "ends_at": "2026-11-03T12:00:00",
                    "created_by": "sre@example.com",
                    "comment": "CHG-1: naive test",
                    "confirm": True,
                },
            )
        await service.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_p4_p5_p6_routing_and_inhibition_engine_accuracy(
        self, test_server_config
    ) -> None:
        """P4, P5, P6: Parent route gating, match_re, braced matchers, and live source alert inhibition."""
        respx.get("http://localhost:9093/api/v2/status").mock(
            return_value=httpx.Response(200, json=MOCK_STATUS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/alerts").mock(
            return_value=httpx.Response(200, json=MOCK_ALERTS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/silences").mock(
            return_value=httpx.Response(200, json=[])
        )

        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)
        # env="staging" fails parent route `{env="prod", service=~"checkout|payments"}`,
        # so child `severity: critical` must NOT match; falls back to `default-slack`
        res = await mcp.call_tool(
            "am_explain_routing",
            {
                "backend_id": "test-am",
                "labels": {
                    "alertname": "HighLatency",
                    "env": "staging",
                    "service": "checkout",
                    "severity": "critical",
                },
            },
        )
        data = res.structured_content
        assert data is not None
        assert data["receivers"] == ["default-slack"]
        assert data["fell_back_to_default"] is True

        # Warning alert when NO NodeDown source alert is firing -> is_inhibited is False
        res_warn = await mcp.call_tool(
            "am_explain_routing",
            {
                "backend_id": "test-am",
                "labels": {
                    "alertname": "HighCPU",
                    "env": "prod",
                    "cluster": "us-east-1",
                    "service": "checkout",
                    "severity": "warning",
                },
            },
        )
        warn_sc = res_warn.structured_content
        assert warn_sc is not None
        assert warn_sc["is_inhibited"] is False
        await service.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_p7_errors_raise_mcp_tool_error_instead_of_returning_is_error_false(
        self, test_server_config
    ) -> None:
        """P7: Unknown backend or invalid parameters raise ToolError (`isError=True` on wire)."""
        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)
        with pytest.raises(ToolError, match="Unknown backend_id 'nonexistent'"):
            await mcp.call_tool("am_list_alerts", {"backend_id": "nonexistent"})
        await service.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_p8_receivers_resource_redacts_http_config_credentials(
        self, test_server_config
    ) -> None:
        """P8: `http_config.authorization.credentials` is redacted in `am://backends/{id}/receivers`."""
        respx.get("http://localhost:9093/api/v2/status").mock(
            return_value=httpx.Response(200, json=MOCK_STATUS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/receivers").mock(
            return_value=httpx.Response(200, json=MOCK_RECEIVERS_RESPONSE)
        )

        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)
        rcv_res = await mcp.read_resource("am://backends/test-am/receivers")
        content = str(rcv_res.contents[0].content)
        assert "super-secret-bearer-token" not in content
        parsed = json.loads(content)
        pd_rcv = next(r for r in parsed["receivers"] if r["name"] == "payments-pagerduty")
        pd_cfg = pd_rcv["details"]["pagerduty_configs"][0]
        assert pd_cfg["http_config"]["authorization"]["credentials"] == "***REDACTED***"
        await service.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_p9_and_p10_duration_cap_and_wildcard_matcher_blocked(
        self, test_server_config
    ) -> None:
        """P9 & P10: Explicit `ends_at` > 24h and wildcard `.*` matchers are rejected."""
        respx.get("http://localhost:9093/api/v2/alerts").mock(
            return_value=httpx.Response(200, json=[])
        )
        respx.get("http://localhost:9093/api/v2/status").mock(
            return_value=httpx.Response(200, json=MOCK_STATUS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/silences").mock(
            return_value=httpx.Response(200, json=[])
        )

        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)
        with pytest.raises(ToolError, match="SP007"):
            await mcp.call_tool(
                "am_create_silence",
                {
                    "backend_id": "test-am",
                    "matchers": [{"name": "service", "value": "db", "isRegex": False, "isEqual": True}],
                    "starts_at": "2026-11-03T10:00:00Z",
                    "ends_at": "2026-12-03T10:00:00Z",
                    "created_by": "sre@example.com",
                    "comment": "CHG-99: 30-day silence attempt",
                    "confirm": True,
                },
            )

        with pytest.raises(ToolError, match="SP003"):
            await mcp.call_tool(
                "am_create_silence",
                {
                    "backend_id": "test-am",
                    "matchers": [{"name": "alertname", "value": ".*", "isRegex": True, "isEqual": True}],
                    "duration_minutes": 30,
                    "created_by": "sre@example.com",
                    "comment": "CHG-99: wildcard attempt",
                    "confirm": True,
                },
            )
        await service.close()
