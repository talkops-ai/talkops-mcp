"""Tests for MCP tools registration and invocation."""


from typing import Any, Dict
from unittest.mock import AsyncMock

import pytest

from kargo_mcp_server.exceptions import KargoOperationError, KargoValidationError
from kargo_mcp_server.models.common import ObjectMeta
from kargo_mcp_server.models.promotion import Promotion, PromotionSpec, PromotionStatus
from kargo_mcp_server.tools.project.project_tools import ProjectTools
from kargo_mcp_server.tools.stage.stage_tools import StageTools
from kargo_mcp_server.tools.warehouse.warehouse_tools import WarehouseTools
from kargo_mcp_server.tools.freight.freight_tools import FreightTools
from kargo_mcp_server.tools.promotion.promotion_tools import PromotionTools
from kargo_mcp_server.tools.promotion_task.promotion_task_tools import PromotionTaskTools
from kargo_mcp_server.tools.credentials.credentials_tools import CredentialsTools
from kargo_mcp_server.tools.diagnostics.diagnostics_tools import DiagnosticsTools


# ---- Helper: extract tool closures from a tools class ----

def _extract_tools(tool_cls, service_locator: Dict[str, Any]) -> Dict[str, Any]:
    """Register tools on a mock MCP and collect their callables."""
    instance = tool_cls(service_locator)
    collected: Dict[str, Any] = {}

    class FakeMCP:
        def tool(self):
            def decorator(fn):
                collected[fn.__name__] = fn
                return fn
            return decorator

    instance.register(FakeMCP())
    return collected


class TestProjectTools:
    @pytest.mark.asyncio
    async def test_project_mgmt_list(self, service_locator, mock_ctx):
        tools = _extract_tools(ProjectTools, service_locator)
        result = await tools["kargo_project_mgmt"](action="list", ctx=mock_ctx)
        assert len(result) == 2
        assert result[0]["name"] == "demo-project"

    @pytest.mark.asyncio
    async def test_project_mgmt_get(self, service_locator, mock_ctx):
        tools = _extract_tools(ProjectTools, service_locator)
        result = await tools["kargo_project_mgmt"](action="get", name="demo-project", ctx=mock_ctx)
        assert result["metadata"]["name"] == "demo-project"

    @pytest.mark.asyncio
    async def test_project_mgmt_create(self, service_locator, mock_ctx):
        tools = _extract_tools(ProjectTools, service_locator)
        service_locator["kargo_service"].create_project = AsyncMock(
            return_value=AsyncMock(model_dump=lambda **kwargs: {"metadata": {"name": "new-project"}})
        )
        result = await tools["kargo_project_mgmt"](action="create", name="new-project", auto_promotion=True, ctx=mock_ctx)
        assert result["metadata"]["name"] == "new-project"
        service_locator["kargo_service"].create_project.assert_called_once()


class TestStageTools:
    @pytest.mark.asyncio
    async def test_stage_mgmt_list(self, service_locator, mock_ctx):
        tools = _extract_tools(StageTools, service_locator)
        result = await tools["kargo_stage_mgmt"](action="list", project="demo-project", ctx=mock_ctx)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_stage_mgmt_upsert_write_gate(self, readonly_service_locator, mock_ctx):
        tools = _extract_tools(StageTools, readonly_service_locator)
        with pytest.raises(KargoOperationError, match="Write operations are disabled"):
            await tools["kargo_stage_mgmt"](
                action="upsert", project="demo", stage_name="new", ctx=mock_ctx
            )

    @pytest.mark.asyncio
    async def test_stage_mgmt_reverify_write_gate(self, readonly_service_locator, mock_ctx):
        tools = _extract_tools(StageTools, readonly_service_locator)
        with pytest.raises(KargoOperationError, match="Write operations are disabled"):
            await tools["kargo_stage_mgmt"](
                action="reverify", project="demo", stage_name="dev", ctx=mock_ctx
            )


class TestWarehouseTools:
    @pytest.mark.asyncio
    async def test_warehouse_mgmt_list(self, service_locator, mock_ctx):
        tools = _extract_tools(WarehouseTools, service_locator)
        result = await tools["kargo_warehouse_mgmt"](action="list", project="demo-project", ctx=mock_ctx)
        assert len(result) == 1
        assert result[0]["name"] == "my-warehouse"

    @pytest.mark.asyncio
    async def test_warehouse_mgmt_refresh_write_gate(self, readonly_service_locator, mock_ctx):
        tools = _extract_tools(WarehouseTools, readonly_service_locator)
        with pytest.raises(KargoOperationError, match="Write operations are disabled"):
            await tools["kargo_warehouse_mgmt"](
                action="refresh", project="demo", warehouse_name="wh1", ctx=mock_ctx
            )

    @pytest.mark.asyncio
    async def test_warehouse_mgmt_upsert_write_gate(self, readonly_service_locator, mock_ctx):
        tools = _extract_tools(WarehouseTools, readonly_service_locator)
        with pytest.raises(KargoOperationError, match="Write operations are disabled"):
            await tools["kargo_warehouse_mgmt"](
                action="upsert", project="demo", warehouse_name="wh1",
                subscriptions=[{"type": "image", "repo_url": "docker.io/nginx"}],
                ctx=mock_ctx,
            )

    @pytest.mark.asyncio
    async def test_warehouse_mgmt_upsert(self, service_locator, mock_ctx):
        tools = _extract_tools(WarehouseTools, service_locator)
        wh_mock = AsyncMock()
        wh_mock.metadata.name = "wh1"
        wh_mock.metadata.namespace = "demo"
        service_locator["kargo_service"].upsert_warehouse = AsyncMock(return_value=wh_mock)
        result = await tools["kargo_warehouse_mgmt"](
            action="upsert", project="demo", warehouse_name="wh1",
            subscriptions=[
                {"type": "image", "repo_url": "ghcr.io/org/app", "semver_constraint": "^1.0.0"},
                {"type": "git", "repo_url": "https://github.com/org/repo.git", "branch": "main"},
            ],
            ctx=mock_ctx,
        )
        assert result["name"] == "wh1"
        service_locator["kargo_service"].upsert_warehouse.assert_called_once()
        # Verify the spec passed to the service has the correct structure
        call_args = service_locator["kargo_service"].upsert_warehouse.call_args
        spec = call_args[0][2]  # third positional arg is the spec
        assert "subscriptions" in spec
        assert len(spec["subscriptions"]) == 2
        assert "image" in spec["subscriptions"][0]
        assert "git" in spec["subscriptions"][1]

    @pytest.mark.asyncio
    async def test_warehouse_mgmt_upsert_missing_subscriptions(self, service_locator, mock_ctx):
        """Upsert without subscriptions should raise validation error."""
        from kargo_mcp_server.exceptions import KargoValidationError
        tools = _extract_tools(WarehouseTools, service_locator)
        with pytest.raises(KargoValidationError, match="subscriptions.*required"):
            await tools["kargo_warehouse_mgmt"](
                action="upsert", project="demo", warehouse_name="wh1",
                ctx=mock_ctx,
            )


class TestFreightTools:
    @pytest.mark.asyncio
    async def test_freight_mgmt_list(self, service_locator, mock_ctx):
        tools = _extract_tools(FreightTools, service_locator)
        result = await tools["kargo_freight_mgmt"](action="list", project="demo-project", ctx=mock_ctx)
        assert len(result) == 1
        assert result[0]["id"] == "freight-abc"

    @pytest.mark.asyncio
    async def test_freight_mgmt_approve_write_gate(self, readonly_service_locator, mock_ctx):
        tools = _extract_tools(FreightTools, readonly_service_locator)
        with pytest.raises(KargoOperationError, match="Write operations are disabled"):
            await tools["kargo_freight_mgmt"](
                action="approve", project="demo", freight_id="f1", stage="dev", ctx=mock_ctx
            )


class TestPromotionTools:
    @pytest.mark.asyncio
    async def test_promotion_mgmt_list(self, service_locator, mock_ctx):
        tools = _extract_tools(PromotionTools, service_locator)
        result = await tools["kargo_promotion_mgmt"](action="list", project="demo-project", ctx=mock_ctx)
        assert len(result) == 1
        assert result[0]["state"] == "Succeeded"

    @pytest.mark.asyncio
    async def test_promotion_mgmt_create_single(self, service_locator, mock_ctx):
        """Create with a single freight_id returns a single result dict."""
        tools = _extract_tools(PromotionTools, service_locator)
        result = await tools["kargo_promotion_mgmt"](
            action="create", project="demo-project", stage="dev", freight_id="freight-abc", ctx=mock_ctx
        )
        assert result["name"] == "promo-002"
        assert result["state"] == "Pending"
        assert result["freight"] == "freight-abc"
        service_locator["kargo_service"].create_promotion.assert_called_once_with(
            project="demo-project", stage="dev", freight="freight-abc"
        )

    @pytest.mark.asyncio
    async def test_promotion_mgmt_create_multi_freight(self, service_locator, mock_ctx):
        """Create with multiple freight_ids returns a list of results."""
        tools = _extract_tools(PromotionTools, service_locator)

        # Set up distinct return values for each call
        promo_a = Promotion(
            metadata=ObjectMeta(name="promo-a", namespace="demo-project"),
            spec=PromotionSpec(stage="dev", freight="freight-guestbook"),
            status=PromotionStatus(state="Pending"),
        )
        promo_b = Promotion(
            metadata=ObjectMeta(name="promo-b", namespace="demo-project"),
            spec=PromotionSpec(stage="dev", freight="freight-features"),
            status=PromotionStatus(state="Pending"),
        )
        service_locator["kargo_service"].create_promotion = AsyncMock(
            side_effect=[promo_a, promo_b]
        )

        result = await tools["kargo_promotion_mgmt"](
            action="create",
            project="demo-project",
            stage="dev",
            freight_id=["freight-guestbook", "freight-features"],
            ctx=mock_ctx,
        )
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "promo-a"
        assert result[0]["freight"] == "freight-guestbook"
        assert result[1]["name"] == "promo-b"
        assert result[1]["freight"] == "freight-features"
        assert service_locator["kargo_service"].create_promotion.call_count == 2

    @pytest.mark.asyncio
    async def test_promotion_mgmt_create_missing_freight_id(self, service_locator, mock_ctx):
        """Create without freight_id should raise validation error."""
        tools = _extract_tools(PromotionTools, service_locator)
        with pytest.raises(KargoValidationError, match="freight_id.*required"):
            await tools["kargo_promotion_mgmt"](
                action="create", project="demo-project", stage="dev", freight_id=None, ctx=mock_ctx
            )

    @pytest.mark.asyncio
    async def test_promotion_mgmt_create_missing_stage(self, service_locator, mock_ctx):
        """Create without stage should raise validation error."""
        tools = _extract_tools(PromotionTools, service_locator)
        with pytest.raises(KargoValidationError, match="stage.*required"):
            await tools["kargo_promotion_mgmt"](
                action="create", project="demo-project", stage=None, freight_id="f1", ctx=mock_ctx
            )

    @pytest.mark.asyncio
    async def test_promotion_mgmt_abort_write_gate(self, readonly_service_locator, mock_ctx):
        tools = _extract_tools(PromotionTools, readonly_service_locator)
        with pytest.raises(KargoOperationError, match="Write operations are disabled"):
            await tools["kargo_promotion_mgmt"](
                action="abort", project="demo", promotion_name="p1", ctx=mock_ctx
            )


class TestPromotionTaskTools:
    @pytest.mark.asyncio
    async def test_promotion_task_mgmt_list(self, service_locator, mock_ctx):
        tools = _extract_tools(PromotionTaskTools, service_locator)
        service_locator["kargo_service"].list_promotion_tasks = AsyncMock(
            return_value=[{"metadata": {"name": "task1"}}]
        )
        result = await tools["kargo_promotion_task_mgmt"](action="list", project="demo-project", ctx=mock_ctx)
        assert len(result) == 1
        assert result[0]["metadata"]["name"] == "task1"

    @pytest.mark.asyncio
    async def test_promotion_task_mgmt_upsert_write_gate(self, readonly_service_locator, mock_ctx):
        tools = _extract_tools(PromotionTaskTools, readonly_service_locator)
        with pytest.raises(KargoOperationError, match="Write operations are disabled"):
            await tools["kargo_promotion_task_mgmt"](
                action="upsert", project="demo", task_name="task1",
                preset="gitops-image-update",
                git_repo_url="https://github.com/org/repo.git",
                image_repo_url="ghcr.io/org/app",
                ctx=mock_ctx,
            )

    @pytest.mark.asyncio
    async def test_promotion_task_mgmt_upsert_with_preset(self, service_locator, mock_ctx):
        """Upsert with a preset should build the spec and call the service."""
        tools = _extract_tools(PromotionTaskTools, service_locator)
        task_mock = AsyncMock()
        task_mock.metadata.name = "promote"
        task_mock.metadata.namespace = "demo"
        service_locator["kargo_service"].upsert_promotion_task = AsyncMock(return_value=task_mock)
        result = await tools["kargo_promotion_task_mgmt"](
            action="upsert", project="demo", task_name="promote",
            preset="gitops-image-update",
            git_repo_url="https://github.com/org/repo.git",
            image_repo_url="ghcr.io/org/app",
            argocd_app_name_pattern="myapp-${{ ctx.stage }}",
            ctx=mock_ctx,
        )
        assert result["name"] == "promote"
        service_locator["kargo_service"].upsert_promotion_task.assert_called_once()
        # Verify the spec has steps and vars
        call_args = service_locator["kargo_service"].upsert_promotion_task.call_args
        spec = call_args[0][2]  # third positional arg is the spec
        assert "steps" in spec
        assert "vars" in spec
        step_uses = [s["uses"] for s in spec["steps"]]
        assert "git-clone" in step_uses
        assert "argocd-update" in step_uses

    @pytest.mark.asyncio
    async def test_promotion_task_mgmt_upsert_with_custom_steps(self, service_locator, mock_ctx):
        """Upsert with custom_steps should pass them through."""
        tools = _extract_tools(PromotionTaskTools, service_locator)
        task_mock = AsyncMock()
        task_mock.metadata.name = "custom-task"
        task_mock.metadata.namespace = "demo"
        service_locator["kargo_service"].upsert_promotion_task = AsyncMock(return_value=task_mock)
        custom = [{"uses": "git-clone", "config": {"repoURL": "https://example.com"}}]
        result = await tools["kargo_promotion_task_mgmt"](
            action="upsert", project="demo", task_name="custom-task",
            custom_steps=custom,
            ctx=mock_ctx,
        )
        assert result["name"] == "custom-task"
        call_args = service_locator["kargo_service"].upsert_promotion_task.call_args
        spec = call_args[0][2]
        assert spec["steps"] == custom


class TestDiagnosticsTools:
    @pytest.mark.asyncio
    async def test_describe_topology(self, service_locator, mock_ctx):
        tools = _extract_tools(DiagnosticsTools, service_locator)
        result = await tools["kargo_describe_topology"](project="demo-project", ctx=mock_ctx)
        assert result["stage_count"] == 3
        assert result["roots"] == ["dev"]

class TestCredentialsTools:
    @pytest.mark.asyncio
    async def test_credentials_mgmt_list(self, service_locator, mock_ctx):
        tools = _extract_tools(CredentialsTools, service_locator)
        service_locator["kargo_service"].list_repo_credentials = AsyncMock(
            return_value=[{"metadata": {"name": "git-creds"}}]
        )
        result = await tools["kargo_credentials_mgmt"](action="list", project="demo-project", ctx=mock_ctx)
        assert len(result) == 1
        assert result[0]["metadata"]["name"] == "git-creds"

    @pytest.mark.asyncio
    async def test_credentials_mgmt_create_write_gate(self, readonly_service_locator, mock_ctx):
        tools = _extract_tools(CredentialsTools, readonly_service_locator)
        with pytest.raises(KargoOperationError, match="Write operations are disabled"):
            await tools["kargo_credentials_mgmt"](
                action="create", project="demo", name="git-creds", repo_url="url", type="git", ctx=mock_ctx
            )

    @pytest.mark.asyncio
    async def test_credentials_mgmt_create(self, service_locator, mock_ctx):
        tools = _extract_tools(CredentialsTools, service_locator)
        service_locator["kargo_service"].create_repo_credentials = AsyncMock(
            return_value={"metadata": {"name": "git-creds"}}
        )
        result = await tools["kargo_credentials_mgmt"](
            action="create", 
            project="demo", 
            name="git-creds", 
            repo_url="url", 
            type="git",
            username=None,
            password=None,
            description=None,
            repo_url_is_regex=False,
            ctx=mock_ctx
        )
        assert result["metadata"]["name"] == "git-creds"
        service_locator["kargo_service"].create_repo_credentials.assert_called_once()
