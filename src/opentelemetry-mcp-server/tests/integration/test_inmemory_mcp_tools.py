"""T-I1 through T-I9: Integration tests for the 17 MCP Tools via FastMCP Client."""

import json
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from opentelemetry_mcp_server.config import KubernetesConfig, ServerConfig
from opentelemetry_mcp_server.exceptions import OtelResourceNotFoundError
from opentelemetry_mcp_server.resources import initialize_resources
from opentelemetry_mcp_server.server.core import create_mcp_server
from opentelemetry_mcp_server.services.collector_config_service import (
    CollectorConfigService,
)
from opentelemetry_mcp_server.tools import initialize_tools

pytestmark = pytest.mark.asyncio

ALL_EXPECTED_17_TOOLS = {
    # Discovery & UI (3)
    "otel_survey_cluster",
    "otel_list_workloads",
    "otel_query_a2ui",
    # Collector Lifecycle (4)
    "otel_provision_collector",
    "otel_patch_collector",
    "otel_revert_collector_config",
    "otel_delete_resource",
    # Instrumentation (3)
    "otel_patch_instrumentation",
    "otel_manage_workload_instrumentation",
    "otel_verify_instrumentation",
    # Pipeline (4)
    "otel_configure_receivers",
    "otel_configure_processing",
    "otel_configure_sampling",
    "otel_configure_connectors",
    # Diagnostics & Governance (3)
    "otel_diagnose_collector",
    "otel_validate_collector_config",
    "otel_audit_security_posture",
}

EXPECTED_READ_ONLY_7_TOOLS = {
    "otel_survey_cluster",
    "otel_list_workloads",
    "otel_query_a2ui",
    "otel_verify_instrumentation",
    "otel_diagnose_collector",
    "otel_validate_collector_config",
    "otel_audit_security_posture",
}

REMOVED_LEGACY_TOOLS = {
    "otel_lookup_instrumentation",
    "otel_recommend_collector_topology",
    "otel_gen_drop_attribute_rules",
    "otel_list_collectors",
    "otel_get_collector",
    "otel_annotate_deployment",
}


async def test_tool_surface_parameter_cap_and_annotations(bootstrapped_mcp):
    """T-I1: Verify exact 17 tools, <= 8 parameters per tool, and removed static tools."""
    async with Client(bootstrapped_mcp) as client:
        tools = await client.list_tools()
        registered = {t.name for t in tools}
        assert registered == ALL_EXPECTED_17_TOOLS
        assert registered.isdisjoint(REMOVED_LEGACY_TOOLS)

        for tool in tools:
            props = (tool.inputSchema or {}).get("properties", {})
            assert len(props) <= 8, (
                f"Tool '{tool.name}' has {len(props)} parameters (> 8 max): {list(props.keys())}"
            )
            assert tool.annotations is not None, f"Tool '{tool.name}' missing ToolAnnotations"


async def test_read_only_and_toolset_gating(mock_kubernetes_service):
    """T-I3: Verify --read-only exposes only 7 read-only tools and --toolsets filters accurately."""
    ro_cfg = ServerConfig(
        allow_write=False,
        read_only=True,
        toolsets=["all"],
        kubernetes=KubernetesConfig(enabled=False),
    )
    ro_mcp = create_mcp_server(ro_cfg)
    locator = {
        "kubernetes_service": mock_kubernetes_service,
        "collector_config_service": CollectorConfigService(),
        "config": ro_cfg,
    }
    initialize_tools(locator).register_all_tools(ro_mcp)
    initialize_resources(locator).register_all_resources(ro_mcp)

    async with Client(ro_mcp) as client:
        ro_tools = {t.name for t in await client.list_tools()}
        assert ro_tools == EXPECTED_READ_ONLY_7_TOOLS

    # Toolset filtering: only discovery + diagnostics
    sub_cfg = ServerConfig(
        allow_write=True,
        read_only=False,
        toolsets=["discovery", "diagnostics"],
        kubernetes=KubernetesConfig(enabled=False),
    )
    sub_mcp = create_mcp_server(sub_cfg)
    sub_locator = {
        "kubernetes_service": mock_kubernetes_service,
        "collector_config_service": CollectorConfigService(),
        "config": sub_cfg,
    }
    initialize_tools(sub_locator).register_all_tools(sub_mcp)
    async with Client(sub_mcp) as client:
        sub_tools = {t.name for t in await client.list_tools()}
        assert sub_tools == {
            "otel_survey_cluster",
            "otel_list_workloads",
            "otel_diagnose_collector",
            "otel_validate_collector_config",
        }


async def test_discovery_and_consolidated_diagnostic_tools(bootstrapped_mcp):
    """T-I8: Verify otel_survey_cluster, otel_list_workloads, otel_diagnose_collector, otel_verify_instrumentation."""
    async with Client(bootstrapped_mcp) as client:
        survey_res = await client.call_tool("otel_survey_cluster", {"namespaces": ["observability"]})
        survey_data = json.loads(survey_res.content[0].text)
        assert "operator" in survey_data
        assert "collectors" in survey_data
        assert "instrumentations" in survey_data

        wl_res = await client.call_tool("otel_list_workloads", {"namespace": "default"})
        wl_data = json.loads(wl_res.content[0].text)
        assert "items" in wl_data

        diag_res = await client.call_tool(
            "otel_diagnose_collector",
            {"namespace": "observability", "name": "my-collector", "include": ["status", "pods", "config_lint"]},
        )
        diag_data = json.loads(diag_res.content[0].text)
        assert diag_data["collector"] == "observability/my-collector"
        assert "findings" in diag_data

        ver_res = await client.call_tool(
            "otel_verify_instrumentation",
            {"namespace": "default", "workload_name": "frontend-service", "workload_kind": "Deployment"},
        )
        ver_data = json.loads(ver_res.content[0].text)
        assert "findings" in ver_data


async def test_two_phase_dry_run_and_pre_apply_linter_blocking(
    bootstrapped_mcp, mock_kubernetes_service
):
    """T-I4: Verify dry_run=True preview vs dry_run=False apply, and pre-apply linter blocking."""
    async with Client(bootstrapped_mcp) as client:
        # 1. Provision collector in dry_run=True
        prov_res = await client.call_tool(
            "otel_provision_collector",
            {
                "namespace": "observability",
                "name": "otel-agent",
                "role": "agent",
                "signals": ["traces", "metrics"],
                "dry_run": True,
            },
        )
        prov_data = json.loads(prov_res.content[0].text)
        assert prov_data["dry_run"] is True

        # 2. Pre-apply linter must block invalid config_yaml with CFG_UNDEFINED_COMPONENT_REF
        bad_yaml = """
receivers:
  otlp: {}
processors:
  memory_limiter: {}
  batch: {}
exporters:
  otlp: {}
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [nonexistent_exporter]
"""
        try:
            patch_bad = await client.call_tool(
                "otel_patch_collector",
                {
                    "namespace": "observability",
                    "name": "my-collector",
                    "config_yaml": bad_yaml,
                    "dry_run": False,
                },
            )
            patch_bad_data = json.loads(patch_bad.content[0].text)
            assert patch_bad_data.get("blocked") is True or patch_bad_data.get("action") == "blocked_by_linter"
        except ToolError as exc:
            assert "nonexistent_exporter" in str(exc) or "CFG_UNDECLARED_COMPONENT" in str(exc)


async def test_destructive_action_confirmation_gate(bootstrapped_mcp, mock_kubernetes_service):
    """T-I5: Verify otel_delete_resource and otel_revert_collector_config require confirm=True when dry_run=False."""
    async with Client(bootstrapped_mcp) as client:
        # Without confirm=True, dry_run=False must not execute a real deletion (dry_run=False)
        del_unconfirmed = await client.call_tool(
            "otel_delete_resource",
            {
                "namespace": "observability",
                "name": "my-collector",
                "kind": "OpenTelemetryCollector",
                "dry_run": False,
                "confirm": False,
            },
        )
        del_unconfirmed_data = json.loads(del_unconfirmed.content[0].text)
        assert del_unconfirmed_data.get("action") in ("confirmation_required", "aborted", "dry_run")
        for call in mock_kubernetes_service.delete_custom_resource.call_args_list:
            assert call.kwargs.get("dry_run") is True

        mock_kubernetes_service.delete_custom_resource.reset_mock()

        # With confirm=True and dry_run=False, deletion proceeds with dry_run=False
        del_confirmed = await client.call_tool(
            "otel_delete_resource",
            {
                "namespace": "observability",
                "name": "my-collector",
                "kind": "OpenTelemetryCollector",
                "dry_run": False,
                "confirm": True,
            },
        )
        del_confirmed_data = json.loads(del_confirmed.content[0].text)
        assert del_confirmed_data.get("deleted") is True or del_confirmed_data.get("action") == "deleted"
        assert mock_kubernetes_service.delete_custom_resource.called
        assert mock_kubernetes_service.delete_custom_resource.call_args.kwargs.get("dry_run") is False


async def test_json_coercion_middleware_end_to_end(bootstrapped_mcp):
    """T-I6: Verify stringified JSON lists, dicts, and booleans are coerced transparently by JsonCoercionMiddleware."""
    async with Client(bootstrapped_mcp) as client:
        res = await client.call_tool(
            "otel_configure_processing",
            {
                "namespace": "observability",
                "collector_name": "my-collector",
                "signals": '["logs", "traces"]',
                "rules": '{"parse_json": true, "mask_pii": true, "drop_attributes": ["http.user_agent", "url.query"]}',
                "dry_run": "true",
            },
        )
        data = json.loads(res.content[0].text)
        assert data["dry_run"] is True


async def test_tool_error_is_error_true_with_recovery_hint(
    bootstrapped_mcp, mock_kubernetes_service
):
    """T-I9: Verify missing K8s resource raises ToolError with recovery hints."""
    mock_kubernetes_service.get_otel_collector.side_effect = OtelResourceNotFoundError(
        "OpenTelemetryCollector 'missing-col' not found in namespace 'observability'"
    )
    async with Client(bootstrapped_mcp) as client:
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool(
                "otel_diagnose_collector",
                {"namespace": "observability", "name": "missing-col"},
            )
        assert "missing-col" in str(exc_info.value)
        assert "otel://collectors/observability" in str(exc_info.value)
