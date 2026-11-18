"""Integration tests for FastMCP wire protocol, toolset matrix, <=8 parameter budget, zero prompts, and Gateway API write-exclusion."""

import json
import pytest
from fastmcp.client import Client
from traefik_mcp_server.config import ServerConfig
from traefik_mcp_server.server.bootstrap import ServerBootstrap


EXPECTED_ALL_15_TOOLS = {
    "traefik_configure_http_route",
    "traefik_configure_weighted_service",
    "traefik_set_traffic_weights",
    "traefik_configure_traffic_mirroring",
    "traefik_update_route",
    "traefik_configure_tcp_udp_route",
    "traefik_configure_middleware",
    "traefik_configure_tls_policy",
    "traefik_configure_servers_transport",
    "traefik_delete_resource",
    "traefik_diagnose_route",
    "traefik_trace_request",
    "traefik_compare_traffic_metrics",
    "traefik_analyze_logs",
    "traefik_audit_configuration",
}

EXPECTED_READONLY_5_TOOLS = {
    "traefik_diagnose_route",
    "traefik_trace_request",
    "traefik_compare_traffic_metrics",
    "traefik_analyze_logs",
    "traefik_audit_configuration",
}

GATEWAY_API_KINDS = {"Gateway", "GatewayClass", "HTTPRoute", "GRPCRoute", "TLSRoute", "TCPRoute", "ReferenceGrant"}


@pytest.mark.asyncio
async def test_readonly_mode_exposes_5_tools_12_resources_and_zero_prompts(mcp_ro):
    async with Client(mcp_ro) as client:
        tools = await client.list_tools()
        assert {t.name for t in tools} == EXPECTED_READONLY_5_TOOLS

        static_res = await client.list_resources()
        tpl_res = await client.list_resource_templates()
        assert len(static_res) == 4
        assert len(tpl_res) == 8

        prompts = await client.list_prompts()
        assert prompts == []


@pytest.mark.asyncio
async def test_readwrite_mode_exposes_all_15_tools_with_max_8_params_and_annotations(mcp_rw):
    async with Client(mcp_rw) as client:
        tools = await client.list_tools()
        assert {t.name for t in tools} == EXPECTED_ALL_15_TOOLS

        for t in tools:
            props = (t.inputSchema or {}).get("properties", {})
            assert len(props) <= 8, f"Tool '{t.name}' exceeds <= 8 parameter budget ({len(props)} params)"
            assert t.outputSchema is not None, f"Tool '{t.name}' is missing outputSchema"
            assert t.annotations is not None, f"Tool '{t.name}' is missing ToolAnnotations"


@pytest.mark.asyncio
async def test_write_tools_do_not_accept_gateway_api_kinds(mcp_rw):
    async with Client(mcp_rw) as client:
        tools = {t.name: t for t in await client.list_tools()}

        update_schema_str = json.dumps(tools["traefik_update_route"].inputSchema)
        delete_schema_str = json.dumps(tools["traefik_delete_resource"].inputSchema)
        for gw_kind in GATEWAY_API_KINDS:
            assert f'"{gw_kind}"' not in update_schema_str
            assert f'"{gw_kind}"' not in delete_schema_str

        # Confirm diagnostic tool DOES accept Gateway API kinds
        diag_schema_str = json.dumps(tools["traefik_diagnose_route"].inputSchema)
        assert '"HTTPRoute"' in diag_schema_str
        assert '"Gateway"' in diag_schema_str


@pytest.mark.asyncio
async def test_toolset_filtering_traffic_and_policies():
    mcp_traffic, _ = ServerBootstrap.build(config=ServerConfig(allow_write=True, toolsets=("traffic",)))
    async with Client(mcp_traffic) as client:
        t_names = {t.name for t in await client.list_tools()}
        assert t_names == {
            "traefik_configure_http_route",
            "traefik_configure_weighted_service",
            "traefik_set_traffic_weights",
            "traefik_configure_traffic_mirroring",
            "traefik_update_route",
            "traefik_configure_tcp_udp_route",
            "traefik_delete_resource",
        }

    mcp_policies, _ = ServerBootstrap.build(config=ServerConfig(allow_write=True, toolsets=("policies",)))
    async with Client(mcp_policies) as client:
        p_names = {t.name for t in await client.list_tools()}
        assert p_names == {
            "traefik_configure_middleware",
            "traefik_configure_tls_policy",
            "traefik_configure_servers_transport",
            "traefik_delete_resource",
        }


@pytest.mark.asyncio
async def test_json_coercion_middleware_coerces_stringified_dicts(mcp_rw):
    async with Client(mcp_rw) as client:
        res = await client.call_tool(
            "traefik_set_traffic_weights",
            {
                "name": "payments-wrr",
                "namespace": "default",
                "weights": '{"payments-stable": 80, "payments-canary": 20}',
                "dry_run": "true",
            },
        )
        data = res.structured_content
        assert data["status"] == "preview"
        assert data["dry_run"] is True
