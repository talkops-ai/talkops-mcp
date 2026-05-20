"""Tests for granular v4 tools — 6 tool groups, 14 tools total.

v4 refactor: DiscoveryTools (am_list_backends, am_get_backend_status),
RoutingTools (am_get_routing_tree, am_list_receivers), and
GovernanceTools (am_export_config) have been moved to resources.
"""
from typing import Any, Dict
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
from httpx import Response

from alertmanager_mcp_server.tools import initialize_tools
from alertmanager_mcp_server.tools.alert_tools import AlertTools
from alertmanager_mcp_server.tools.silence_tools import SilenceTools
from alertmanager_mcp_server.tools.helper_tools import HelperTools
from alertmanager_mcp_server.tools.routing_tools import RoutingTools
from alertmanager_mcp_server.tools.governance_tools import GovernanceTools
from alertmanager_mcp_server.tools.triage_tools import TriageTools
from alertmanager_mcp_server.utils.audit import clear_audit_log, get_audit_entries
from tests.conftest import (
    MOCK_ALERTS_RESPONSE, MOCK_ALERT_GROUPS_RESPONSE,
    MOCK_SILENCES_RESPONSE, MOCK_STATUS_RESPONSE,
)


def _capture_tools(tool_instance) -> Dict[str, Any]:
    """Register a tool module on a mock MCP and return captured tool functions by name."""
    mcp = MagicMock()
    captured: Dict[str, Any] = {}

    def capture_tool(**kwargs):
        def decorator(f):
            captured[f.__name__] = f
            return f
        return decorator

    mcp.tool = capture_tool
    tool_instance.register(mcp)
    return captured


class TestToolRegistration:
    def test_initialize_tools_creates_registry(self, service_locator):
        registry = initialize_tools(service_locator)
        assert len(registry.tools) == 6

    def test_registry_registers_all_tools(self, service_locator):
        registry = initialize_tools(service_locator)
        mcp = MagicMock()
        mcp.tool = MagicMock(return_value=lambda f: f)
        registry.register_all_tools(mcp)
        # 3 alert + 4 silence + 2 helper + 2 routing + 2 governance + 1 triage = 14
        assert mcp.tool.call_count == 14


class TestAlertTools:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_alerts(self, service_locator, mock_context):
        respx.get("http://localhost:9093/api/v2/alerts").mock(return_value=Response(200, json=MOCK_ALERTS_RESPONSE))
        fns = _capture_tools(AlertTools(service_locator))
        result = await fns["am_list_alerts"](backend_id="test-am", ctx=mock_context)
        assert len(result["alerts"]) == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_alerts_with_severity(self, service_locator, mock_context):
        respx.get("http://localhost:9093/api/v2/alerts").mock(return_value=Response(200, json=MOCK_ALERTS_RESPONSE))
        fns = _capture_tools(AlertTools(service_locator))
        result = await fns["am_list_alerts"](backend_id="test-am", severity="critical", ctx=mock_context)
        assert "alerts" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_alert_groups(self, service_locator, mock_context):
        respx.get("http://localhost:9093/api/v2/alerts/groups").mock(return_value=Response(200, json=MOCK_ALERT_GROUPS_RESPONSE))
        fns = _capture_tools(AlertTools(service_locator))
        result = await fns["am_list_alert_groups"](backend_id="test-am", ctx=mock_context)
        assert isinstance(result, list)
        assert len(result) == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_push_test_alert(self, service_locator, mock_context):
        clear_audit_log()
        respx.post("http://localhost:9093/api/v2/alerts").mock(return_value=Response(200, json={}))
        fns = _capture_tools(AlertTools(service_locator))
        result = await fns["am_push_test_alert"](
            backend_id="test-am", alert_labels={"alertname": "MCPTest"}, ctx=mock_context,
        )
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_push_test_missing_alertname(self, service_locator, mock_context):
        fns = _capture_tools(AlertTools(service_locator))
        result = await fns["am_push_test_alert"](
            backend_id="test-am", alert_labels={"team": "sre"}, ctx=mock_context,
        )
        assert result["isError"] is True


class TestSilenceTools:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_silences(self, service_locator, mock_context):
        respx.get("http://localhost:9093/api/v2/silences").mock(return_value=Response(200, json=MOCK_SILENCES_RESPONSE))
        fns = _capture_tools(SilenceTools(service_locator))
        result = await fns["am_list_silences"](backend_id="test-am", ctx=mock_context)
        assert "silences" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_silence(self, service_locator, mock_context):
        clear_audit_log()
        respx.get("http://localhost:9093/api/v2/silences").mock(return_value=Response(200, json=[]))
        respx.post("http://localhost:9093/api/v2/silences").mock(return_value=Response(200, json={"id": "silence-new"}))
        respx.get("http://localhost:9093/api/v2/silence/silence-new").mock(
            return_value=Response(200, json={**MOCK_SILENCES_RESPONSE[0], "id": "silence-new"})
        )
        fns = _capture_tools(SilenceTools(service_locator))
        result = await fns["am_create_silence"](
            backend_id="test-am",
            matchers=[{"name": "service", "value": "api", "isRegex": False, "isEqual": True}],
            duration_minutes=60, ctx=mock_context,
        )
        assert "silence_id" in result

    @pytest.mark.asyncio
    async def test_create_silence_exceeds_cap(self, service_locator, mock_context):
        fns = _capture_tools(SilenceTools(service_locator))
        result = await fns["am_create_silence"](
            backend_id="test-am",
            matchers=[{"name": "alertname", "value": "Test", "isRegex": False, "isEqual": True}],
            duration_minutes=2000, ctx=mock_context,
        )
        assert result["isError"] is True
        assert "cap" in result["error"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_expire_silence(self, service_locator, mock_context):
        clear_audit_log()
        respx.delete("http://localhost:9093/api/v2/silence/silence-001").mock(return_value=Response(200))
        fns = _capture_tools(SilenceTools(service_locator))
        result = await fns["am_expire_silence"](backend_id="test-am", silence_id="silence-001", ctx=mock_context)
        assert result["success"] is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_silence(self, service_locator, mock_context):
        clear_audit_log()
        respx.get("http://localhost:9093/api/v2/silence/silence-001").mock(
            return_value=Response(200, json=MOCK_SILENCES_RESPONSE[0])
        )
        respx.post("http://localhost:9093/api/v2/silences").mock(return_value=Response(200, json={"id": "silence-ext"}))
        respx.get("http://localhost:9093/api/v2/silence/silence-ext").mock(
            return_value=Response(200, json={**MOCK_SILENCES_RESPONSE[0], "id": "silence-ext"})
        )
        respx.delete("http://localhost:9093/api/v2/silence/silence-001").mock(return_value=Response(200))
        fns = _capture_tools(SilenceTools(service_locator))
        result = await fns["am_update_silence"](
            backend_id="test-am", silence_id="silence-001", add_minutes=30, ctx=mock_context,
        )
        assert "new_silence_id" in result


class TestHelperTools:
    @respx.mock
    @pytest.mark.asyncio
    async def test_preview_silence(self, service_locator, mock_context):
        respx.get("http://localhost:9093/api/v2/alerts").mock(return_value=Response(200, json=MOCK_ALERTS_RESPONSE))
        respx.get("http://localhost:9093/api/v2/status").mock(return_value=Response(200, json=MOCK_STATUS_RESPONSE))
        fns = _capture_tools(HelperTools(service_locator))
        result = await fns["am_preview_silence"](
            backend_id="test-am",
            matchers=[{"name": "env", "value": "prod", "isRegex": False, "isEqual": True}],
            ctx=mock_context,
        )
        assert result["affected_alert_count"] == 2
        assert "summary_text" in result
        assert "would_affect_receivers" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_silence_alert_by_labels(self, service_locator, mock_context):
        clear_audit_log()
        respx.get("http://localhost:9093/api/v2/silences").mock(return_value=Response(200, json=[]))
        respx.post("http://localhost:9093/api/v2/silences").mock(return_value=Response(200, json={"id": "silence-helper"}))
        respx.get("http://localhost:9093/api/v2/silence/silence-helper").mock(
            return_value=Response(200, json={**MOCK_SILENCES_RESPONSE[0], "id": "silence-helper"})
        )
        fns = _capture_tools(HelperTools(service_locator))
        result = await fns["am_silence_alert"](
            backend_id="test-am",
            alert_labels={"alertname": "HighCPU", "service": "api", "env": "prod"},
            duration_minutes=60, ctx=mock_context,
        )
        assert "silence_id" in result
        assert "derived_matchers" in result

    @pytest.mark.asyncio
    async def test_silence_alert_exceeds_cap(self, service_locator, mock_context):
        fns = _capture_tools(HelperTools(service_locator))
        result = await fns["am_silence_alert"](
            backend_id="test-am", alert_labels={"alertname": "Test"}, duration_minutes=2000, ctx=mock_context,
        )
        assert result["isError"] is True

    @pytest.mark.asyncio
    async def test_silence_alert_no_inputs(self, service_locator, mock_context):
        fns = _capture_tools(HelperTools(service_locator))
        result = await fns["am_silence_alert"](backend_id="test-am", ctx=mock_context)
        assert result["isError"] is True


class TestRoutingTools:
    @respx.mock
    @pytest.mark.asyncio
    async def test_explain_routing(self, service_locator, mock_context):
        respx.get("http://localhost:9093/api/v2/status").mock(return_value=Response(200, json=MOCK_STATUS_RESPONSE))
        fns = _capture_tools(RoutingTools(service_locator))
        result = await fns["am_explain_routing"](
            backend_id="test-am", labels={"alertname": "HighCPU", "service": "api"}, ctx=mock_context,
        )
        assert "receivers" in result
        assert "explanation" in result
        assert "matched_route" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_audit_default_route(self, service_locator, mock_context):
        respx.get("http://localhost:9093/api/v2/status").mock(return_value=Response(200, json=MOCK_STATUS_RESPONSE))
        respx.get("http://localhost:9093/api/v2/alerts").mock(return_value=Response(200, json=MOCK_ALERTS_RESPONSE))
        fns = _capture_tools(RoutingTools(service_locator))
        result = await fns["am_audit_default_route"](backend_id="test-am", ctx=mock_context)
        assert "alert_count" in result
        assert "summary_text" in result


class TestGovernanceTools:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_recent_changes(self, service_locator, mock_context):
        respx.get("http://localhost:9093/api/v2/silences").mock(return_value=Response(200, json=MOCK_SILENCES_RESPONSE))
        fns = _capture_tools(GovernanceTools(service_locator))
        result = await fns["am_list_recent_changes"](backend_id="test-am", ctx=mock_context)
        assert "changes" in result
        assert "summary_text" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_validate_silence_policy_pass(self, service_locator, mock_context):
        respx.get("http://localhost:9093/api/v2/alerts").mock(return_value=Response(200, json=[]))
        fns = _capture_tools(GovernanceTools(service_locator))
        result = await fns["am_validate_silence_policy"](
            backend_id="test-am",
            matchers=[{"name": "alertname", "value": "HighCPU", "isRegex": False, "isEqual": True}],
            duration_minutes=60, comment="Maintenance", created_by="admin",
            ctx=mock_context,
        )
        assert result["allowed"] is True
        assert len(result["violations"]) == 0

    @pytest.mark.asyncio
    async def test_validate_silence_policy_violations(self, service_locator, mock_context):
        fns = _capture_tools(GovernanceTools(service_locator))
        result = await fns["am_validate_silence_policy"](
            backend_id="test-am",
            matchers=[{"name": "severity", "value": "critical", "isRegex": False, "isEqual": True}],
            duration_minutes=2000, comment="", created_by="",
            ctx=mock_context,
        )
        assert result["allowed"] is False
        assert len(result["violations"]) >= 3  # duration, comment, created_by, broad matcher


class TestTriageTools:
    @respx.mock
    @pytest.mark.asyncio
    async def test_summarize_oncall(self, service_locator, mock_context):
        respx.get("http://localhost:9093/api/v2/alerts").mock(return_value=Response(200, json=MOCK_ALERTS_RESPONSE))
        fns = _capture_tools(TriageTools(service_locator))
        result = await fns["am_summarize_oncall"](backend_id="test-am", ctx=mock_context)
        assert result["total_alerts"] == 2
        assert "summary_text" in result
        assert "by_severity" in result
        assert "by_service" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_summarize_oncall_empty(self, service_locator, mock_context):
        respx.get("http://localhost:9093/api/v2/alerts").mock(return_value=Response(200, json=[]))
        fns = _capture_tools(TriageTools(service_locator))
        result = await fns["am_summarize_oncall"](backend_id="test-am", ctx=mock_context)
        assert result["total_alerts"] == 0
        assert "All clear" in result["summary_text"]
