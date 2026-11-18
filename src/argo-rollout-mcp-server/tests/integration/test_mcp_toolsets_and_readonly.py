"""In-memory MCP integration tests for toolsets and read-only default gating (T-I1)."""

import pytest
from fastmcp import Client
from tests.conftest import make_test_server

READ_ONLY_TOOLS = {
    "argo_validate_deployment_readiness",
    "argo_compare_canary_metrics",
    "argo_diagnose_rollout",
}

ALL_15_TOOLS = {
    "argo_create_rollout",
    "argo_set_rollout_image",
    "argo_configure_rollout_strategy",
    "argo_manage_rollout_lifecycle",
    "argo_delete_rollout",
    "argo_validate_deployment_readiness",
    "argo_convert_deployment_to_rollout",
    "argo_convert_rollout_to_deployment",
    "argo_manage_legacy_deployment",
    "argo_configure_analysis_template",
    "argo_delete_analysis_template",
    "argo_create_experiment",
    "argo_delete_experiment",
    "argo_compare_canary_metrics",
    "argo_diagnose_rollout",
}


@pytest.mark.asyncio
async def test_readonly_default_exposes_only_readonly_tools(fake_argo_service, fake_generator_service):
    mcp = make_test_server(
        allow_write=False,
        toolsets=["all"],
        argo_service=fake_argo_service,
        generator_service=fake_generator_service,
    )
    async with Client(mcp) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools}
        assert names == READ_ONLY_TOOLS


@pytest.mark.asyncio
async def test_allow_write_exposes_all_15_tools(fake_argo_service, fake_generator_service):
    mcp = make_test_server(
        allow_write=True,
        toolsets=["all"],
        argo_service=fake_argo_service,
        generator_service=fake_generator_service,
    )
    async with Client(mcp) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools}
        assert len(names) == 15
        assert names == ALL_15_TOOLS


@pytest.mark.asyncio
async def test_specific_toolsets_filter_tools(fake_argo_service, fake_generator_service):
    mcp = make_test_server(
        allow_write=True,
        toolsets=["diagnostics"],
        argo_service=fake_argo_service,
        generator_service=fake_generator_service,
    )
    async with Client(mcp) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools}
        assert names == {"argo_diagnose_rollout"}
