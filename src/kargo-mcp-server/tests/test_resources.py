"""Tests for MCP resources registration."""


import json
from typing import Any, Dict
from unittest.mock import AsyncMock

import pytest

from kargo_mcp_server.resources.project_resources import ProjectResources
from kargo_mcp_server.resources.stage_resources import StageResources
from kargo_mcp_server.resources.warehouse_resources import WarehouseResources
from kargo_mcp_server.resources.freight_resources import FreightResources
from kargo_mcp_server.resources.promotion_resources import PromotionResources
from kargo_mcp_server.resources.static_resources import StaticResources


def _extract_resources(resource_cls, service_locator: Dict[str, Any]) -> Dict[str, Any]:
    """Register resources on a fake MCP and collect their callables."""
    instance = resource_cls(service_locator)
    collected: Dict[str, Any] = {}

    class FakeMCP:
        def resource(self, uri: str, **kwargs):
            def decorator(fn):
                collected[uri] = fn
                return fn
            return decorator

    instance.register(FakeMCP())
    return collected


class TestProjectResources:
    @pytest.mark.asyncio
    async def test_list_projects_resource(self, service_locator):
        resources = _extract_resources(ProjectResources, service_locator)
        result = await resources["kargo://projects"]()
        data = json.loads(result)
        assert len(data) == 2
        assert data[0]["name"] == "demo-project"

    @pytest.mark.asyncio
    async def test_get_project_resource(self, service_locator):
        resources = _extract_resources(ProjectResources, service_locator)
        result = await resources["kargo://projects/{project_name}"](project_name="demo-project")
        # Returns Markdown + YAML now
        assert "## Project Details" in result
        assert "demo-project" in result


class TestStageResources:
    @pytest.mark.asyncio
    async def test_list_stages_resource(self, service_locator):
        resources = _extract_resources(StageResources, service_locator)
        result = await resources["kargo://projects/{project}/stages"](project="demo")
        data = json.loads(result)
        assert len(data) == 3


class TestWarehouseResources:
    @pytest.mark.asyncio
    async def test_list_warehouses_resource(self, service_locator):
        resources = _extract_resources(WarehouseResources, service_locator)
        result = await resources["kargo://projects/{project}/warehouses"](project="demo")
        data = json.loads(result)
        assert len(data) == 1


class TestFreightResources:
    @pytest.mark.asyncio
    async def test_list_freight_resource(self, service_locator):
        resources = _extract_resources(FreightResources, service_locator)
        result = await resources["kargo://projects/{project}/freight"](project="demo")
        data = json.loads(result)
        assert len(data) == 1


class TestPromotionResources:
    @pytest.mark.asyncio
    async def test_list_promotions_resource(self, service_locator):
        resources = _extract_resources(PromotionResources, service_locator)
        result = await resources["kargo://projects/{project}/promotions"](project="demo")
        data = json.loads(result)
        assert len(data) == 1

class TestPromotionTaskResources:
    @pytest.mark.asyncio
    async def test_list_promotion_tasks_resource(self, service_locator):
        from kargo_mcp_server.resources.promotion_task_resources import PromotionTaskResources
        resources = _extract_resources(PromotionTaskResources, service_locator)
        result = await resources["kargo://projects/{project}/promotiontasks"](project="demo")
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["metadata"]["name"] == "promote"

    @pytest.mark.asyncio
    async def test_get_promotion_task_resource(self, service_locator):
        from kargo_mcp_server.resources.promotion_task_resources import PromotionTaskResources
        resources = _extract_resources(PromotionTaskResources, service_locator)
        result = await resources["kargo://projects/{project}/promotiontasks/{task_name}"](
            project="demo", task_name="promote"
        )
        assert "## PromotionTask Details: promote" in result
        assert "git-clone" in result
        assert "git-push" in result


class TestCredentialsResources:
    @pytest.mark.asyncio
    async def test_list_credentials_resource(self, service_locator):
        from kargo_mcp_server.resources.credentials_resources import CredentialsResources
        resources = _extract_resources(CredentialsResources, service_locator)
        result = await resources["kargo://projects/{project}/credentials"](project="demo")
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["name"] == "git-creds"
        assert data[0]["hasPassword"] is True
        # Password must NOT be in the response
        assert "secret-token" not in result

    @pytest.mark.asyncio
    async def test_get_credential_resource(self, service_locator):
        from kargo_mcp_server.resources.credentials_resources import CredentialsResources
        resources = _extract_resources(CredentialsResources, service_locator)
        result = await resources["kargo://projects/{project}/credentials/{cred_name}"](
            project="demo", cred_name="git-creds"
        )
        assert "## Credential Details: git-creds" in result
        # Password must be redacted
        assert "***REDACTED***" in result
        assert "secret-token" not in result


class TestStaticResources:
    @pytest.mark.asyncio
    async def test_best_practices_resource(self, service_locator):
        resources = _extract_resources(StaticResources, service_locator)
        result = await resources["kargo://best-practices"]()
        assert "# Kargo Best Practices" in result

    @pytest.mark.asyncio
    async def test_promotion_steps_resource(self, service_locator):
        resources = _extract_resources(StaticResources, service_locator)
        result = await resources["kargo://promotion-steps"]()
        assert "git-clone" in result

