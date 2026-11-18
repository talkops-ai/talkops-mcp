"""Integration tests for Policy Toolset (T7-T9) via FastMCP Client."""

import pytest
from fastmcp.client import Client
from fastmcp.exceptions import ToolError


@pytest.mark.asyncio
async def test_t7_configure_middleware_and_schema_gating(mcp_rw, traefik_service):
    async with Client(mcp_rw) as client:
        res = await client.call_tool(
            "traefik_configure_middleware",
            {
                "name": "sec-headers",
                "type": "headers",
                "spec": {"sts_seconds": 31536000, "frame_deny": True},
                "dry_run": False,
            },
        )
        assert res.structured_content["status"] == "success"

        # Simulate pre-v3.5 CRD schema lacking ipDenyList
        traefik_service.set_installed_crd_fields("Middleware", {"rateLimit", "ipAllowList", "headers"})
        with pytest.raises(ToolError, match="ipDenyList"):
            await client.call_tool(
                "traefik_configure_middleware",
                {
                    "name": "deny-bad-ips",
                    "type": "ip_deny_list",
                    "spec": {"source_range": ["192.0.2.0/24"]},
                    "dry_run": True,
                },
            )


@pytest.mark.asyncio
async def test_t8_configure_tls_policy_and_t9_servers_transport(mcp_rw):
    async with Client(mcp_rw) as client:
        # Mutating default TLSOption with dry_run=False requires confirm=True
        cancelled = await client.call_tool(
            "traefik_configure_tls_policy",
            {
                "kind": "TLSOption",
                "name": "default",
                "spec": {"profile": "intermediate"},
                "dry_run": False,
                "confirm": False,
            },
        )
        assert cancelled.structured_content["status"] == "cancelled"

        applied_tls = await client.call_tool(
            "traefik_configure_tls_policy",
            {
                "kind": "TLSOption",
                "name": "default",
                "spec": {"profile": "intermediate"},
                "dry_run": False,
                "confirm": True,
            },
        )
        assert applied_tls.structured_content["status"] == "success"

        # TLSStore must be named 'default'
        with pytest.raises(ToolError, match="default"):
            await client.call_tool(
                "traefik_configure_tls_policy",
                {
                    "kind": "TLSStore",
                    "name": "custom-store",
                    "spec": {"default_certificate_secret": "prod-wildcard-tls"},
                },
            )

        # T9: ServersTransport
        transport = await client.call_tool(
            "traefik_configure_servers_transport",
            {
                "name": "backend-mtls",
                "protocol": "http",
                "spec": {
                    "server_name": "orders.default.svc.cluster.local",
                    "max_idle_conns_per_host": 64,
                    "forwarding_timeouts": {"dial": "5s", "response_header": "30s"},
                },
                "dry_run": False,
            },
        )
        assert transport.structured_content["status"] == "success"
