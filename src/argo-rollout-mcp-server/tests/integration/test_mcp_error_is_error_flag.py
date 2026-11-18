"""In-memory MCP integration tests for B5, B6, and B7 bug fixes (T-I7)."""

from unittest.mock import AsyncMock
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from kubernetes.client.rest import ApiException
from tests.conftest import make_test_server


@pytest.mark.asyncio
async def test_b5_bluegreen_create_rollout_creates_active_preview_services_once(
    fake_argo_service, fake_generator_service
):
    mcp = make_test_server(
        allow_write=True,
        toolsets=["all"],
        argo_service=fake_argo_service,
        generator_service=fake_generator_service,
    )
    async with Client(mcp) as client:
        res = await client.call_tool(
            "argo_create_rollout",
            {
                "name": "bg-app",
                "image": "nginx:1.25",
                "strategy": "bluegreen",
                "dry_run": False,
            },
        )
        assert res.data.status == "success"
        # Fix B5: create_stable_canary_services called ONCE (not twice) with strategy="bluegreen"
        assert fake_generator_service.create_stable_canary_services.call_count == 1
        _, kwargs = fake_generator_service.create_stable_canary_services.call_args
        assert kwargs["strategy"] == "bluegreen"
        details = res.structured_content["details"] if res.structured_content else res.data.details
        services_created = details["services_created"] if isinstance(details, dict) else getattr(details, "services_created")
        assert "bg-app-active" in services_created
        assert "bg-app-preview" in services_created


@pytest.mark.asyncio
async def test_b6_configure_rollout_strategy_surfaces_service_creation_errors(
    fake_argo_service, fake_generator_service
):
    fake_generator_service.create_rollout_service = AsyncMock(
        side_effect=ApiException(status=403, reason="Forbidden creating service")
    )
    mcp = make_test_server(
        allow_write=True,
        toolsets=["all"],
        argo_service=fake_argo_service,
        generator_service=fake_generator_service,
    )
    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="RBAC permission denied"):
            await client.call_tool(
                "argo_configure_rollout_strategy",
                {
                    "name": "payments-api",
                    "services": {"canary_service": "payments-custom-canary", "auto_create": True},
                    "dry_run": False,
                },
            )


@pytest.mark.asyncio
async def test_b7_migration_tools_raise_tool_error_instead_of_dict_error(
    fake_argo_service, fake_generator_service
):
    fake_generator_service.fetch_deployment_yaml = AsyncMock(
        side_effect=ApiException(status=404, reason="Deployment 'missing-dep' not found")
    )
    mcp = make_test_server(
        allow_write=True,
        toolsets=["all"],
        argo_service=fake_argo_service,
        generator_service=fake_generator_service,
    )
    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="not found"):
            await client.call_tool(
                "argo_validate_deployment_readiness",
                {"deployment_name": "missing-dep", "namespace": "default"},
            )

        with pytest.raises(ToolError, match="not found"):
            await client.call_tool(
                "argo_convert_deployment_to_rollout",
                {"deployment_name": "missing-dep", "namespace": "default", "dry_run": True},
            )
