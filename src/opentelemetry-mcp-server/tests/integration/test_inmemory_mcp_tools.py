"""Integration tests for MCP Tools using FastMCP in-memory Client.

Covers all 17 registered tools with happy-path, error, and edge-case
tests per §6 and §10 of the testing guide.
"""

import json
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from tests.conftest import get_text

pytestmark = pytest.mark.asyncio


# ──────────────────────────────────────────────
# Tool Registration & Discovery (§10 — P0)
# ──────────────────────────────────────────────


ALL_EXPECTED_TOOLS = [
    # Discovery
    "otel_list_collectors",
    "otel_get_collector",
    "otel_list_instrumented_services",
    # Instrumentation
    "otel_lookup_instrumentation",
    "otel_patch_instrumentation",
    "otel_annotate_deployment",
    # Validation
    "otel_validate_k8sattributes_order",
    "otel_check_filelog_safety",
    "otel_inspect_target_allocator_state",
    "otel_recommend_collector_topology",
    # Governance
    "otel_detect_cardinality",
    "otel_gen_drop_attribute_rules",
    "otel_analyze_ebpf_footprint",
    # Sampling
    "otel_inspect_sampling_configuration",
    "otel_toggle_sampling_strategy",
    # SpanMetrics
    "otel_inspect_spanmetrics_config",
    "otel_enable_spanmetrics_for_service",
]


async def test_all_tools_registered(bootstrapped_mcp):
    """Every tool the server defines must be discoverable via list_tools."""
    async with Client(bootstrapped_mcp) as client:
        tools = await client.list_tools()
        registered = [t.name for t in tools]
        for expected in ALL_EXPECTED_TOOLS:
            assert expected in registered, f"Tool '{expected}' not registered"


# ──────────────────────────────────────────────
# Discovery Tools
# ──────────────────────────────────────────────


async def test_otel_list_collectors_happy_path(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool("otel_list_collectors", {})
        text = result.content[0].text
        data = json.loads(text)
        assert data["total_count"] >= 1
        assert "my-collector" in [i["name"] for i in data["items"]]


async def test_otel_list_collectors_with_namespace(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_list_collectors", {"namespace": "observability"}
        )
        data = json.loads(result.content[0].text)
        assert data["total_count"] >= 1


async def test_otel_list_collectors_with_pagination(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_list_collectors", {"page_size": 1}
        )
        data = json.loads(result.content[0].text)
        assert data["page_size"] == 1


async def test_otel_get_collector_summary(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_get_collector",
            {"name": "my-collector", "namespace": "observability"},
        )
        data = json.loads(result.content[0].text)
        assert data["name"] == "my-collector"
        assert data["namespace"] == "observability"
        assert data["mode"] == "daemonset"


async def test_otel_get_collector_full_detail(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_get_collector",
            {
                "name": "my-collector",
                "namespace": "observability",
                "detail_level": "full",
            },
        )
        data = json.loads(result.content[0].text)
        assert data["raw_config_yaml"] is not None
        assert "receivers" in data["raw_config_yaml"]


async def test_otel_list_instrumented_services(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_list_instrumented_services", {"namespace": "default"}
        )
        data = json.loads(result.content[0].text)
        assert data["total_count"] > 0
        names = [item["name"] for item in data["items"]]
        assert "frontend-service" in names


# ──────────────────────────────────────────────
# Instrumentation Tools
# ──────────────────────────────────────────────


async def test_otel_lookup_instrumentation_known_language(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_lookup_instrumentation", {"language": "java"}
        )
        data = json.loads(result.content[0].text)
        assert data["found"] is True
        assert data["language"] == "java"
        assert "auto_instrumentation_available" in data


async def test_otel_lookup_instrumentation_unknown_language(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_lookup_instrumentation", {"language": "cobol"}
        )
        data = json.loads(result.content[0].text)
        assert data["found"] is False
        assert "supported_languages" in data


async def test_otel_lookup_instrumentation_with_framework(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_lookup_instrumentation",
            {"language": "java", "framework": "Spring"},
        )
        data = json.loads(result.content[0].text)
        assert data["found"] is True
        assert "frameworks" in data


async def test_otel_patch_instrumentation_dry_run(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_patch_instrumentation",
            {
                "namespace": "default",
                "name": "test-instr",
                "endpoint": "http://otel-collector:4317",
                "dry_run": True,
            },
        )
        data = json.loads(result.content[0].text)
        assert data["action"] == "dry_run"
        assert data["dry_run"] is True
        assert data["namespace"] == "default"
        assert "spec_yaml" in data


async def test_otel_create_or_patch_instrumentation_with_sampler(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_patch_instrumentation",
            {
                "namespace": "default",
                "name": "test-instr",
                "sampler_type": "parentbased_traceidratio",
                "sampler_argument": "0.5",
                "dry_run": True,
            },
        )
        data = json.loads(result.content[0].text)
        assert data["spec"]["sampler"]["type"] == "parentbased_traceidratio"
        assert data["spec"]["sampler"]["argument"] == "0.5"


async def test_otel_annotate_deployment_dry_run(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_annotate_deployment",
            {
                "namespace": "default",
                "name": "my-service",
                "language": "java",
                "dry_run": True,
            },
        )
        data = json.loads(result.content[0].text)
        assert data["action"] == "dry_run"
        assert data["dry_run"] is True
        assert "inject-java" in data["annotation"]["key"]
        assert data["annotation"]["value"] == "true"


async def test_otel_annotate_deployment_with_cr_name(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_annotate_deployment",
            {
                "namespace": "default",
                "name": "my-service",
                "language": "python",
                "instrumentation_cr_name": "custom-instr",
                "dry_run": True,
            },
        )
        data = json.loads(result.content[0].text)
        assert data["annotation"]["value"] == "custom-instr"
        assert "inject-python" in data["annotation"]["key"]


async def test_otel_annotate_deployment_unsupported_language(bootstrapped_mcp):
    """Unsupported language should raise ToolError via MCP."""
    async with Client(bootstrapped_mcp) as client:
        with pytest.raises(ToolError, match="Unsupported language"):
            await client.call_tool(
                "otel_annotate_deployment",
                {
                    "namespace": "default",
                    "name": "my-service",
                    "language": "cobol",
                    "dry_run": True,
                },
            )


# ──────────────────────────────────────────────
# Validation Tools
# ──────────────────────────────────────────────


async def test_otel_validate_k8sattributes_order(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_validate_k8sattributes_order",
            {"name": "my-collector", "namespace": "observability"},
        )
        data = json.loads(result.content[0].text)
        assert "all_valid" in data
        assert "validations" in data
        assert "recommended_order" in data


async def test_otel_check_filelog_safety(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_check_filelog_safety",
            {"name": "my-collector", "namespace": "observability"},
        )
        data = json.loads(result.content[0].text)
        assert "safe" in data
        assert "profile" in data
        assert data["collector"] == "observability/my-collector"


async def test_otel_inspect_target_allocator_state_enabled(bootstrapped_mcp, mock_kubernetes_service):
    """Use the collector_cr_with_ta fixture which has TA enabled."""
    import json as json_mod
    import os

    fixture_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "fixtures", "otel", "collector_cr_with_ta.json"
    )
    with open(fixture_path, "r", encoding="utf-8") as f:
        ta_cr = json_mod.load(f)

    mock_kubernetes_service.get_otel_collector.return_value = ta_cr

    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_inspect_target_allocator_state",
            {"name": "my-collector", "namespace": "observability"},
        )
        data = json.loads(result.content[0].text)
        assert data["target_allocator"]["enabled"] is True
        assert data["target_allocator"]["allocation_strategy"] == "consistent-hashing"


async def test_otel_inspect_target_allocator_state_disabled(bootstrapped_mcp):
    """Default fixture has no TA — should return enabled=False."""
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_inspect_target_allocator_state",
            {"name": "my-collector", "namespace": "observability"},
        )
        data = json.loads(result.content[0].text)
        assert data["target_allocator"]["enabled"] is False


async def test_otel_recommend_collector_topology_traces_only(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_recommend_collector_topology",
            {"signals": ["traces"]},
        )
        data = json.loads(result.content[0].text)
        rec = data["recommendation"]
        assert rec["mode"] == "deployment"
        assert len(rec["pipelines"]) == 1
        assert rec["pipelines"][0]["signal"] == "traces"


async def test_otel_recommend_collector_topology_logs_forces_daemonset(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_recommend_collector_topology",
            {"signals": ["logs", "traces"]},
        )
        data = json.loads(result.content[0].text)
        assert data["recommendation"]["mode"] == "daemonset"


async def test_otel_recommend_collector_topology_large_cluster(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_recommend_collector_topology",
            {
                "signals": ["traces", "metrics"],
                "cluster_size": "large",
                "workload_count": 100,
            },
        )
        data = json.loads(result.content[0].text)
        assert data["recommendation"]["gateway_recommended"] is True


async def test_otel_recommend_collector_topology_with_prometheus(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_recommend_collector_topology",
            {"signals": ["metrics"], "has_prometheus_targets": True},
        )
        data = json.loads(result.content[0].text)
        assert data["recommendation"]["target_allocator_recommended"] is True
        assert data["recommendation"]["mode"] == "daemonset"


# ──────────────────────────────────────────────
# Governance Tools
# ──────────────────────────────────────────────


async def test_otel_detect_cardinality(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_detect_cardinality",
            {"name": "my-collector", "namespace": "observability"},
        )
        data = json.loads(result.content[0].text)
        assert "issues" in data
        assert "total_estimated_series" in data
        assert data["spanmetrics_enabled"] is True
        assert data["collector"] == "observability/my-collector"


async def test_otel_gen_drop_attribute_rules(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_gen_drop_attribute_rules",
            {"attributes": ["http.user_agent", "url.full"]},
        )
        data = json.loads(result.content[0].text)
        assert "yaml_snippet" in data
        assert "http.user_agent" in data["yaml_snippet"]
        assert "url.full" in data["yaml_snippet"]
        assert data["signal"] == "metrics"
        assert "instructions" in data


async def test_otel_generate_transform_rules_traces_signal(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_gen_drop_attribute_rules",
            {"attributes": ["db.statement"], "signal": "traces"},
        )
        data = json.loads(result.content[0].text)
        assert data["signal"] == "traces"
        assert "db.statement" in data["yaml_snippet"]


async def test_otel_analyze_ebpf_footprint(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_analyze_ebpf_footprint",
            {"namespace": "default"},
        )
        data = json.loads(result.content[0].text)
        assert "risk_level" in data
        assert "total_ebpf_pods" in data
        assert "recommendations" in data


async def test_otel_analyze_ebpf_all_namespaces(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_analyze_ebpf_footprint", {}
        )
        data = json.loads(result.content[0].text)
        assert data["namespace"] == "all"


# ──────────────────────────────────────────────
# Sampling Tools
# ──────────────────────────────────────────────


async def test_otel_inspect_sampling_configuration(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_inspect_sampling_configuration",
            {"namespace": "observability", "collector_name": "my-collector"},
        )
        data = json.loads(result.content[0].text)
        assert "mode" in data
        assert data["mode"] == "tail"


async def test_otel_inspect_sampling_with_instrumentation_cr(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_inspect_sampling_configuration",
            {
                "namespace": "observability",
                "collector_name": "my-collector",
                "instrumentation_cr_name": "default",
            },
        )
        data = json.loads(result.content[0].text)
        assert "mode" in data


async def test_otel_toggle_sampling_strategy_head(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_toggle_sampling_strategy",
            {
                "namespace": "observability",
                "collector_name": "my-collector",
                "target_mode": "head",
                "sample_rate": 0.5,
                "dry_run": True,
            },
        )
        data = json.loads(result.content[0].text)
        assert data["target_mode"] == "head"
        assert data["dry_run"] is True
        assert "parentbased_traceidratio" in data["config_patch"]


async def test_otel_toggle_sampling_strategy_tail(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_toggle_sampling_strategy",
            {
                "namespace": "observability",
                "collector_name": "my-collector",
                "target_mode": "tail",
                "dry_run": True,
            },
        )
        data = json.loads(result.content[0].text)
        assert data["target_mode"] == "tail"
        assert "tail_sampling" in data["instructions"]


async def test_otel_toggle_sampling_strategy_none(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_toggle_sampling_strategy",
            {
                "namespace": "observability",
                "collector_name": "my-collector",
                "target_mode": "none",
                "dry_run": True,
            },
        )
        data = json.loads(result.content[0].text)
        assert data["target_mode"] == "none"


async def test_otel_toggle_sampling_strategy_invalid_mode(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_toggle_sampling_strategy",
            {
                "namespace": "observability",
                "collector_name": "my-collector",
                "target_mode": "invalid_mode",
                "dry_run": True,
            },
        )
        data = json.loads(result.content[0].text)
        assert "error" in data


# ──────────────────────────────────────────────
# SpanMetrics Tools
# ──────────────────────────────────────────────


async def test_otel_inspect_spanmetrics_config(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_inspect_spanmetrics_config",
            {"name": "my-collector", "namespace": "observability"},
        )
        data = json.loads(result.content[0].text)
        assert data["collector"] == "observability/my-collector"
        profile = data["profile"]
        assert profile["enabled"] is True
        assert len(profile["dimensions"]) >= 1


async def test_otel_enable_spanmetrics_for_service_dry_run(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_enable_spanmetrics_for_service",
            {
                "namespace": "observability",
                "collector_name": "my-collector",
                "dry_run": True,
            },
        )
        data = json.loads(result.content[0].text)
        assert data["dry_run"] is True
        assert "config_snippet" in data
        assert "dimensions" in data
        assert "histogram_buckets" in data


async def test_otel_enable_spanmetrics_custom_dimensions(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_enable_spanmetrics_for_service",
            {
                "namespace": "observability",
                "collector_name": "my-collector",
                "dimensions": ["http.method", "http.status_code"],
                "dry_run": True,
            },
        )
        data = json.loads(result.content[0].text)
        assert data["dimensions"] == ["http.method", "http.status_code"]
        assert data["estimated_series_per_service"] == 200  # 100 * 2 dims


async def test_otel_enable_spanmetrics_high_cardinality_warning(bootstrapped_mcp):
    """More than 5 dimensions should produce a cardinality warning."""
    async with Client(bootstrapped_mcp) as client:
        result = await client.call_tool(
            "otel_enable_spanmetrics_for_service",
            {
                "namespace": "observability",
                "collector_name": "my-collector",
                "dimensions": [
                    "http.method", "http.status_code", "http.url",
                    "rpc.method", "rpc.service", "db.system",
                ],
                "dry_run": True,
            },
        )
        data = json.loads(result.content[0].text)
        assert len(data["warnings"]) > 0
        assert "cardinality" in data["warnings"][0].lower()


# ──────────────────────────────────────────────
# Error & Edge Case Tests (§10 — P1)
# ──────────────────────────────────────────────


async def test_call_nonexistent_tool(bootstrapped_mcp):
    """Calling a tool that doesn't exist must raise ToolError."""
    async with Client(bootstrapped_mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("nonexistent_tool", {})
