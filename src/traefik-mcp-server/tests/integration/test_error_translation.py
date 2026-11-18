"""Integration tests for model-directed ToolError messages with actionable next-step URIs/tools."""

import pytest
from fastmcp.client import Client
from fastmcp.exceptions import ToolError
from kubernetes.client.rest import ApiException
from traefik_mcp_server.tools.base import translate_error


@pytest.mark.parametrize(
    "status,reason,expected_hint",
    [
        (404, "Not Found", "traefik://routes/default"),
        (403, "Forbidden", "RBAC permission denied"),
        (409, "Conflict", "traefik://manifests/IngressRoute/default/payments-route"),
        (422, "Unprocessable Entity", "traefik://schema/IngressRoute"),
    ],
)
def test_translate_k8s_api_exceptions_into_actionable_tool_errors(status, reason, expected_hint):
    exc = ApiException(status=status, reason=reason)
    err = translate_error(exc, "traefik_update_route", namespace="default", resource_name="payments-route")
    assert isinstance(err, ToolError)
    assert expected_hint in str(err)


@pytest.mark.asyncio
async def test_missing_route_error_contains_discovery_uri_hint(mcp_rw):
    async with Client(mcp_rw) as client:
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool(
                "traefik_set_traffic_weights",
                {
                    "name": "does-not-exist",
                    "namespace": "default",
                    "weights": {"a": 100},
                },
            )
        assert "traefik://routes/default" in str(exc_info.value)
