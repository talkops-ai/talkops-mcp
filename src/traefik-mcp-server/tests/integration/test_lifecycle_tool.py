"""Integration tests for T10 traefik_delete_resource: referential integrity, confirmation gate, and safe cascade."""

import pytest
from fastmcp.client import Client
from fastmcp.exceptions import ToolError


@pytest.mark.asyncio
async def test_t10_delete_resource_referential_integrity_and_cascade(mcp_rw):
    async with Client(mcp_rw) as client:
        # Without confirm=True, returns status="cancelled"
        cancelled = await client.call_tool(
            "traefik_delete_resource",
            {"kind": "Middleware", "name": "api-ratelimit", "namespace": "default", "confirm": False},
        )
        assert cancelled.structured_content["status"] == "cancelled"

        # Referenced Middleware cannot be deleted without force=True
        with pytest.raises(ToolError, match="referenced by"):
            await client.call_tool(
                "traefik_delete_resource",
                {"kind": "Middleware", "name": "api-ratelimit", "namespace": "default", "confirm": True},
            )

        # Deleting parent IngressRoute with cascade=True deletes MCP-managed child Middleware and TraefikService
        del_res = await client.call_tool(
            "traefik_delete_resource",
            {
                "kind": "IngressRoute",
                "name": "payments-route",
                "namespace": "default",
                "cascade": True,
                "confirm": True,
            },
        )
        deleted = del_res.structured_content["details"]["deleted"]
        assert "IngressRoute/default/payments-route" in deleted
        assert "Middleware/default/api-ratelimit" in deleted
        assert "TraefikService/default/payments-wrr" in deleted
