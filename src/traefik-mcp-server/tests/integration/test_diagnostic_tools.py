"""Integration tests for Diagnostic Toolset (T11-T15) via FastMCP Client."""

import pytest
from fastmcp.client import Client
from fastmcp.exceptions import ToolError


@pytest.mark.asyncio
async def test_t11_diagnose_route_healthy_and_gateway_api(mcp_ro):
    async with Client(mcp_ro) as client:
        report = await client.call_tool(
            "traefik_diagnose_route",
            {"name": "payments-route", "kind": "IngressRoute", "namespace": "default", "detail": "full"},
        )
        data = report.structured_content
        assert data["healthy"] is True
        assert "HEALTHY" in data["diagnosis_codes"]

        gw_report = await client.call_tool(
            "traefik_diagnose_route",
            {"name": "orders-httproute", "kind": "HTTPRoute", "namespace": "default"},
        )
        assert gw_report.structured_content["healthy"] is True

        missing = await client.call_tool(
            "traefik_diagnose_route",
            {"name": "nonexistent-route", "kind": "IngressRoute", "namespace": "default"},
        )
        assert missing.structured_content["healthy"] is False
        assert "ROUTE_NOT_FOUND" in missing.structured_content["diagnosis_codes"]


@pytest.mark.asyncio
async def test_t12_trace_request_and_ssrf_probe_guard(mcp_ro):
    async with Client(mcp_ro) as client:
        trace = await client.call_tool(
            "traefik_trace_request",
            {
                "request": {"url": "https://api.example.com/payments/checkout", "method": "GET"},
                "entry_point": "websecure",
            },
        )
        t_data = trace.structured_content
        assert t_data["matched"] is True
        assert t_data["matched_router"]["name"] == "default-payments-route-0@kubernetescrd"
        assert len(t_data["shadowed_routers"]) == 1

        # SSRF guard blocks probing arbitrary external hostnames not in cluster routes
        with pytest.raises(ToolError, match="SSRF guard blocked"):
            await client.call_tool(
                "traefik_trace_request",
                {
                    "request": {"url": "http://169.254.169.254/latest/meta-data/"},
                    "probe": {"enabled": True},
                },
            )


@pytest.mark.asyncio
async def test_t13_compare_metrics_t14_analyze_logs_and_t15_audit(mcp_ro):
    async with Client(mcp_ro) as client:
        metrics = await client.call_tool(
            "traefik_compare_traffic_metrics",
            {
                "name": "payments-wrr",
                "scope": "service",
                "namespace": "default",
                "baseline_window": "1h",
                "comparison_window": "15m",
            },
        )
        m_data = metrics.structured_content
        assert m_data["prometheus_available"] is True
        assert len(m_data["backend_split"]) == 2

        logs = await client.call_tool(
            "traefik_analyze_logs",
            {"source": "access", "since": "15m", "group_by": "status"},
        )
        l_data = logs.structured_content
        assert l_data["total_lines_scanned"] == 4
        assert "topsecret123" not in str(l_data["samples"])

        audit = await client.call_tool(
            "traefik_audit_configuration",
            {"min_severity": "low", "max_findings": 50},
        )
        a_data = audit.structured_content
        assert 0 <= a_data["score"] <= 100
        assert "counts_by_severity" in a_data
