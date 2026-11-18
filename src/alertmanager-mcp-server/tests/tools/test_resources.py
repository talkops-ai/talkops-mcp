"""Tests for all 10 backend-scoped and system `am://` MCP resources."""

from __future__ import annotations

import json
import httpx
import pytest
import respx

from alertmanager_mcp_server.server.bootstrap import ServerBootstrap
from alertmanager_mcp_server.utils.audit import add_audit_entry
from tests.conftest import (
    MOCK_ALERTS_RESPONSE,
    MOCK_ALERT_GROUPS_RESPONSE,
    MOCK_RECEIVERS_RESPONSE,
    MOCK_SILENCES_RESPONSE,
    MOCK_STATUS_RESPONSE,
)


class TestResources:
    @respx.mock
    @pytest.mark.asyncio
    async def test_all_resources_read_cleanly_and_redact_secrets(
        self, test_server_config
    ) -> None:
        respx.get("http://localhost:9093/-/healthy").mock(
            return_value=httpx.Response(200, text="OK")
        )
        respx.get("http://localhost:9093/-/ready").mock(
            return_value=httpx.Response(200, text="OK")
        )
        respx.get("http://localhost:9093/api/v2/status").mock(
            return_value=httpx.Response(200, json=MOCK_STATUS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/receivers").mock(
            return_value=httpx.Response(200, json=MOCK_RECEIVERS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/alerts").mock(
            return_value=httpx.Response(200, json=MOCK_ALERTS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/alerts/groups").mock(
            return_value=httpx.Response(200, json=MOCK_ALERT_GROUPS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/silences").mock(
            return_value=httpx.Response(200, json=MOCK_SILENCES_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/silence/silence-001").mock(
            return_value=httpx.Response(200, json=MOCK_SILENCES_RESPONSE[0])
        )

        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)

        # 1. am://backends
        b_res = await mcp.read_resource("am://backends")
        b_data = json.loads(b_res.contents[0].content)
        assert b_data["backends"][0]["id"] == "test-am"
        assert b_data["backends"][0]["health"] == "healthy"

        # 2. am://backends/{backend_id}
        bd_res = await mcp.read_resource("am://backends/test-am")
        bd_data = json.loads(bd_res.contents[0].content)
        assert bd_data["backend"]["version"] == "0.27.0"
        assert bd_data["backend"]["ready"] is True

        # 3. am://backends/{backend_id}/config
        cfg_res = await mcp.read_resource("am://backends/test-am/config")
        cfg_text = str(cfg_res.contents[0].content)
        assert "super-secret-bearer-token" not in cfg_text
        assert "global-smtp-secret-password" not in cfg_text

        # 4. am://backends/{backend_id}/receivers
        rcv_res = await mcp.read_resource("am://backends/test-am/receivers")
        rcv_text = str(rcv_res.contents[0].content)
        assert "super-secret-bearer-token" not in rcv_text
        assert "pd-secret-routing-key-123" not in rcv_text
        assert "custom-header-secret" not in rcv_text
        assert "user:pass123@" not in rcv_text

        # 5. am://backends/{backend_id}/alerts/active (Decision D3: per-backend snapshot)
        aa_res = await mcp.read_resource("am://backends/test-am/alerts/active")
        aa_data = json.loads(aa_res.contents[0].content)
        assert aa_data["backend_id"] == "test-am"
        assert aa_data["total"] == 3

        # 6. am://backends/{backend_id}/alerts/groups
        ag_res = await mcp.read_resource("am://backends/test-am/alerts/groups")
        ag_data = json.loads(ag_res.contents[0].content)
        assert ag_data["backend_id"] == "test-am"
        assert ag_data["total_groups"] == 2

        # 7. am://backends/{backend_id}/alerts/{fingerprint}
        fp_res = await mcp.read_resource("am://backends/test-am/alerts/abc123")
        fp_data = json.loads(fp_res.contents[0].content)
        assert fp_data["alert"]["fingerprint"] == "abc123"

        # 8. am://backends/{backend_id}/silences/active
        sa_res = await mcp.read_resource("am://backends/test-am/silences/active")
        sa_data = json.loads(sa_res.contents[0].content)
        assert sa_data["backend_id"] == "test-am"
        assert sa_data["total"] == 1

        # 9. am://backends/{backend_id}/silences/{silence_id}
        sd_res = await mcp.read_resource("am://backends/test-am/silences/silence-001")
        sd_data = json.loads(sd_res.contents[0].content)
        assert sd_data["silence"]["id"] == "silence-001"

        # 10. am://audit-log
        add_audit_entry("test-am", "create_silence", "sre@example.com", "id=silence-001")
        al_res = await mcp.read_resource("am://audit-log")
        al_data = json.loads(al_res.contents[0].content)
        assert al_data["total"] == 1

        await service.close()
