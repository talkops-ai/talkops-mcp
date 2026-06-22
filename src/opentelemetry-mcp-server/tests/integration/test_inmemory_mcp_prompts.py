"""Integration tests for MCP Prompts using FastMCP in-memory Client.

Covers all 5 prompts with registration, content, argument substitution,
and tool-reference validation per §6 and §10 of the testing guide.
"""

import pytest
from fastmcp import Client

pytestmark = pytest.mark.asyncio


# ──────────────────────────────────────────────
# Prompt Registration & Discovery (§10 — P0)
# ──────────────────────────────────────────────

ALL_EXPECTED_PROMPTS = [
    "otel_onboard_service",
    "otel_investigate_pipeline",
    "otel_cardinality_audit",
    "otel_sampling_review",
    "otel_security_audit",
]


async def test_all_prompts_registered(bootstrapped_mcp):
    """Every prompt the server defines must be discoverable."""
    async with Client(bootstrapped_mcp) as client:
        prompts = await client.list_prompts()
        names = [p.name for p in prompts]
        for expected in ALL_EXPECTED_PROMPTS:
            assert expected in names, f"Prompt '{expected}' not registered"


# ──────────────────────────────────────────────
# Content & Argument Substitution
# ──────────────────────────────────────────────


async def test_get_onboard_service_prompt(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.get_prompt(
            "otel_onboard_service",
            arguments={
                "service_name": "my-service",
                "namespace": "default",
                "language": "java",
            },
        )
        assert len(result.messages) > 0
        text = result.messages[0].content.text
        assert "my-service" in text
        assert "java" in text
        assert "default" in text


async def test_get_investigate_pipeline_prompt(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.get_prompt(
            "otel_investigate_pipeline",
            arguments={
                "collector_name": "my-collector",
                "namespace": "observability",
            },
        )
        assert len(result.messages) > 0
        text = result.messages[0].content.text
        assert "my-collector" in text
        assert "observability" in text


async def test_get_cardinality_audit_prompt(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.get_prompt(
            "otel_cardinality_audit",
            arguments={
                "collector_name": "my-coll",
                "namespace": "default",
            },
        )
        assert len(result.messages) > 0
        text = result.messages[0].content.text
        assert "cardinality" in text.lower()


async def test_get_sampling_review_prompt(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.get_prompt(
            "otel_sampling_review",
            arguments={
                "collector_name": "my-coll",
                "namespace": "default",
            },
        )
        assert len(result.messages) > 0
        text = result.messages[0].content.text
        assert "sampling" in text.lower()


async def test_get_security_audit_prompt(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.get_prompt(
            "otel_security_audit",
            arguments={"namespace": "default"},
        )
        assert len(result.messages) > 0
        text = result.messages[0].content.text
        assert "security" in text.lower()


# ──────────────────────────────────────────────
# Tool-Reference Validation (§10 — P1)
# ──────────────────────────────────────────────


async def test_onboard_prompt_references_correct_tools(bootstrapped_mcp):
    """The onboarding prompt must reference the tools it depends on."""
    async with Client(bootstrapped_mcp) as client:
        result = await client.get_prompt(
            "otel_onboard_service",
            arguments={
                "service_name": "svc",
                "namespace": "ns",
                "language": "python",
            },
        )
        text = result.messages[0].content.text
        assert "otel_lookup_instrumentation" in text
        assert "otel_patch_instrumentation" in text
        assert "otel_annotate_deployment" in text
        assert "otel_list_instrumented_services" in text


async def test_investigate_prompt_references_correct_tools(bootstrapped_mcp):
    """The investigation prompt must reference the tools it depends on."""
    async with Client(bootstrapped_mcp) as client:
        result = await client.get_prompt(
            "otel_investigate_pipeline",
            arguments={"collector_name": "c", "namespace": "n"},
        )
        text = result.messages[0].content.text
        assert "otel_get_collector" in text
        assert "otel_validate_k8sattributes_order" in text
        assert "otel_check_filelog_safety" in text
        assert "otel_inspect_sampling_configuration" in text


async def test_cardinality_prompt_references_correct_tools(bootstrapped_mcp):
    """The cardinality audit prompt must reference the tools it depends on."""
    async with Client(bootstrapped_mcp) as client:
        result = await client.get_prompt(
            "otel_cardinality_audit",
            arguments={"collector_name": "c", "namespace": "n"},
        )
        text = result.messages[0].content.text
        assert "otel_detect_cardinality" in text
        assert "otel_gen_drop_attribute_rules" in text
        assert "otel_inspect_spanmetrics_config" in text


async def test_sampling_prompt_references_correct_tools(bootstrapped_mcp):
    """The sampling review prompt must reference the tools it depends on."""
    async with Client(bootstrapped_mcp) as client:
        result = await client.get_prompt(
            "otel_sampling_review",
            arguments={"collector_name": "c", "namespace": "n"},
        )
        text = result.messages[0].content.text
        assert "otel_inspect_sampling_configuration" in text
        assert "otel_get_collector" in text
        assert "otel_toggle_sampling_strategy" in text


async def test_security_prompt_references_correct_tools(bootstrapped_mcp):
    """The security audit prompt must reference the tools it depends on."""
    async with Client(bootstrapped_mcp) as client:
        result = await client.get_prompt(
            "otel_security_audit",
            arguments={"namespace": "n"},
        )
        text = result.messages[0].content.text
        assert "otel_analyze_ebpf_footprint" in text
        assert "otel_list_instrumented_services" in text
        assert "otel_list_collectors" in text
