"""Integration tests for Traffic Toolset (T1-T6) via FastMCP Client."""

import pytest
from fastmcp.client import Client
from fastmcp.exceptions import ToolError


@pytest.mark.asyncio
async def test_t1_configure_http_route_preview_and_apply(mcp_rw):
    async with Client(mcp_rw) as client:
        preview = await client.call_tool(
            "traefik_configure_http_route",
            {
                "name": "orders-route",
                "namespace": "default",
                "entry_points": ["websecure"],
                "rules": [
                    {
                        "match": {"host": "orders.example.com", "path_prefix": "/v1"},
                        "services": [{"name": "orders-svc", "port": 8080}],
                        "middlewares": [{"name": "api-ratelimit"}],
                    }
                ],
                "tls": {"secret_name": "prod-wildcard-tls"},
                "dry_run": True,
            },
        )
        p_data = preview.structured_content
        assert p_data["status"] == "preview"
        assert "Host(`orders.example.com`)" in p_data["manifest"]

        applied = await client.call_tool(
            "traefik_configure_http_route",
            {
                "name": "orders-route",
                "namespace": "default",
                "entry_points": ["websecure"],
                "rules": [
                    {
                        "match": {"host": "orders.example.com", "path_prefix": "/v1"},
                        "services": [{"name": "orders-svc", "port": 8080}],
                    }
                ],
                "dry_run": False,
            },
        )
        assert applied.structured_content["status"] == "success"


@pytest.mark.asyncio
async def test_t2_and_t3_weighted_service_and_preview_first_weight_shifts(mcp_rw):
    async with Client(mcp_rw) as client:
        # T2: Create weighted service with expose IngressRoute
        wrr = await client.call_tool(
            "traefik_configure_weighted_service",
            {
                "name": "checkout-wrr",
                "namespace": "default",
                "backends": [
                    {"name": "payments-stable", "port": 80, "weight": 95},
                    {"name": "payments-canary", "port": 80, "weight": 5},
                ],
                "expose": {"route_name": "checkout-route", "match": "Host(`checkout.example.com`)"},
                "dry_run": False,
            },
        )
        assert wrr.structured_content["status"] == "success"

        # T3: Default dry_run=True preview returns resource_version
        shift_preview = await client.call_tool(
            "traefik_set_traffic_weights",
            {
                "name": "payments-wrr",
                "namespace": "default",
                "weights": {"payments-stable": 75, "payments-canary": 25},
            },
        )
        sp_data = shift_preview.structured_content
        assert sp_data["status"] == "preview"
        assert sp_data["dry_run"] is True
        rv = sp_data["details"]["resource_version"]
        assert rv == "4001"

        # T3: Apply with expected_resource_version
        shift_apply = await client.call_tool(
            "traefik_set_traffic_weights",
            {
                "name": "payments-wrr",
                "namespace": "default",
                "weights": {"payments-stable": 75, "payments-canary": 25},
                "expected_resource_version": rv,
                "dry_run": False,
            },
        )
        assert shift_apply.structured_content["status"] == "success"

        # Stale resourceVersion triggers conflict error
        with pytest.raises(ToolError, match="conflict"):
            await client.call_tool(
                "traefik_set_traffic_weights",
                {
                    "name": "payments-wrr",
                    "namespace": "default",
                    "weights": {"payments-stable": 50, "payments-canary": 50},
                    "expected_resource_version": "stale-999",
                    "dry_run": False,
                },
            )


@pytest.mark.asyncio
async def test_t4_traffic_mirroring_and_t5_update_route_and_t6_tcp_udp(mcp_rw):
    async with Client(mcp_rw) as client:
        # T4: Traffic mirroring requires confirm when dry_run=False
        cancelled = await client.call_tool(
            "traefik_configure_traffic_mirroring",
            {
                "name": "payments-mirror",
                "namespace": "default",
                "action": "enable",
                "spec": {
                    "main": {"name": "payments-stable", "port": 80},
                    "mirrors": [{"name": "payments-canary", "port": 80, "percent": 10}],
                },
                "dry_run": False,
                "confirm": False,
            },
        )
        assert cancelled.structured_content["status"] == "cancelled"

        enabled = await client.call_tool(
            "traefik_configure_traffic_mirroring",
            {
                "name": "payments-mirror",
                "namespace": "default",
                "action": "enable",
                "spec": {
                    "main": {"name": "payments-stable", "port": 80},
                    "mirrors": [{"name": "payments-canary", "port": 80, "percent": 10}],
                },
                "dry_run": False,
                "confirm": True,
            },
        )
        assert enabled.structured_content["status"] == "success"

        # T5: Update route
        updated = await client.call_tool(
            "traefik_update_route",
            {
                "name": "payments-route",
                "namespace": "default",
                "changes": {"priority": 300},
                "dry_run": False,
            },
        )
        assert updated.structured_content["status"] == "success"

        # T6: TCP route requires TLS when HostSNI is specific
        with pytest.raises(ToolError, match="HostSNI"):
            await client.call_tool(
                "traefik_configure_tcp_udp_route",
                {
                    "name": "pg-tcp",
                    "protocol": "tcp",
                    "routes": [{"match": "HostSNI(`db.example.com`)", "services": [{"name": "orders-svc", "port": 5432}]}],
                },
            )

        tcp_ok = await client.call_tool(
            "traefik_configure_tcp_udp_route",
            {
                "name": "pg-tcp",
                "protocol": "tcp",
                "routes": [{"match": "HostSNI(`db.example.com`)", "services": [{"name": "orders-svc", "port": 5432}]}],
                "tls": {"passthrough": True},
                "dry_run": False,
            },
        )
        assert tcp_ok.structured_content["status"] == "success"
