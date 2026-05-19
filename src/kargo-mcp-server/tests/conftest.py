"""Shared test fixtures and mock factories."""


from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from kargo_mcp_server.config import AuthMode, Config, KargoConfig, ServerConfig
from kargo_mcp_server.models.common import ObjectMeta
from kargo_mcp_server.models.freight import (
    ArtifactReference,
    Freight,
    FreightSpec,
    FreightStageState,
    FreightStatus,
    FreightSummary,
)
from kargo_mcp_server.models.project import (
    Project,
    ProjectSpec,
    ProjectStatus,
    ProjectSummary,
    PromotionPolicy,
)
from kargo_mcp_server.models.promotion import (
    Promotion,
    PromotionSpec,
    PromotionStatus,
    PromotionSummary,
)
from kargo_mcp_server.models.stage import (
    RequestedFreight,
    RequestedFreightOrigin,
    Stage,
    StageSpec,
    StageStatus,
    StageSummary,
)
from kargo_mcp_server.models.warehouse import (
    Warehouse,
    WarehouseSource,
    WarehouseSpec,
    WarehouseStatus,
    WarehouseSummary,
)
from kargo_mcp_server.services.kargo_service import KargoService


# ---- Config Fixtures ----

@pytest.fixture
def test_config() -> ServerConfig:
    """Create a test ServerConfig."""
    return ServerConfig(
        name="test-kargo-mcp",
        version="0.1.0-test",
        transport="stdio",
        host="127.0.0.1",
        port=9999,
        allow_write=True,
        kargo=KargoConfig(
            base_url="http://kargo-test:8080",
            auth_mode=AuthMode.ADMIN,
            admin_password="test-password",
            timeout=5,
        ),
    )


@pytest.fixture
def readonly_config(test_config: ServerConfig) -> ServerConfig:
    """Create a test config with write disabled."""
    test_config.allow_write = False
    return test_config


# ---- Mock Service Fixtures ----

@pytest.fixture
def mock_kargo_service() -> AsyncMock:
    """Create a mock KargoService with all methods."""
    service = AsyncMock(spec=KargoService)

    # Default return values for read operations
    service.list_projects.return_value = [
        ProjectSummary(name="demo-project", namespace="demo-project", stage_count=3, auto_promotion_enabled=True),
        ProjectSummary(name="prod-project", namespace="prod-project", stage_count=2, auto_promotion_enabled=False),
    ]

    service.get_project.return_value = {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "Project",
        "metadata": {"name": "demo-project", "namespace": "demo-project"},
        "spec": {"promotionPolicy": {"autoPromotionEnabled": True}},
    }

    service.list_stages.return_value = [
        StageSummary(name="dev", upstream_stages=[], downstream_stages=["staging"], current_freight_id="abc123"),
        StageSummary(name="staging", upstream_stages=["dev"], downstream_stages=["production"]),
        StageSummary(name="production", upstream_stages=["staging"], downstream_stages=[]),
    ]

    service.get_stage.return_value = {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "Stage",
        "metadata": {"name": "dev", "namespace": "demo-project"},
        "spec": {
            "requestedFreight": [
                {
                    "origin": {"kind": "Warehouse", "name": "my-warehouse"},
                    "sources": {"direct": True}
                }
            ]
        },
        "status": {"currentFreightId": "abc123"},
    }

    service.list_warehouses.return_value = [
        WarehouseSummary(name="my-warehouse", source_types=["image", "git"]),
    ]

    service.get_warehouse.return_value = {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "Warehouse",
        "metadata": {"name": "my-warehouse", "namespace": "demo-project"},
        "spec": {"sources": [{"type": "image", "url": "docker.io/library/nginx"}]},
    }

    service.list_freight.return_value = [
        FreightSummary(
            id="freight-abc",
            artifacts=[ArtifactReference(type="image", ref="nginx:1.25")],
            per_stage=[FreightStageState(stage="dev", available=True, promoted=True, verified=True)],
        ),
    ]

    service.get_freight.return_value = {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "Freight",
        "metadata": {"name": "freight-abc", "namespace": "demo-project"},
    }

    service.list_promotions.return_value = [
        PromotionSummary(name="promo-001", stage="dev", freight="freight-abc", state="Succeeded"),
    ]

    service.get_promotion.return_value = {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "Promotion",
        "metadata": {"name": "promo-001", "namespace": "demo-project"},
        "spec": {"stage": "dev", "freight": "freight-abc"},
        "status": {"state": "Succeeded"},
    }

    service.describe_topology.return_value = {
        "stage_count": 3,
        "roots": ["dev"],
        "leaves": ["production"],
        "edges": [{"from": "dev", "to": "staging"}, {"from": "staging", "to": "production"}],
        "stages": [
            {"name": "dev", "upstream": [], "downstream": ["staging"]},
            {"name": "staging", "upstream": ["dev"], "downstream": ["production"]},
            {"name": "production", "upstream": ["staging"], "downstream": []},
        ],
    }

    # Mutating operations
    service.create_promotion.return_value = Promotion(
        metadata=ObjectMeta(name="promo-002", namespace="demo-project"),
        spec=PromotionSpec(stage="dev", freight="freight-abc"),
        status=PromotionStatus(state="Pending"),
    )

    service.abort_promotion.return_value = Promotion(
        metadata=ObjectMeta(name="promo-002", namespace="demo-project"),
        spec=PromotionSpec(stage="dev", freight="freight-abc"),
        status=PromotionStatus(state="Aborted"),
    )

    service.approve_freight.return_value = Freight(
        metadata=ObjectMeta(name="freight-abc", namespace="demo-project"),
        spec=FreightSpec(artifacts=[ArtifactReference(type="image", ref="nginx:1.25")]),
        status=FreightStatus(stageStates=[FreightStageState(stage="dev", available=True, promoted=False, verified=False)]),
    )

    service.upsert_stage.return_value = Stage(
        metadata=ObjectMeta(name="new-stage", namespace="demo-project"),
        spec=StageSpec(),
        status=StageStatus(currentFreightId=None),
    )

    service.reverify_stage.return_value = Stage(
        metadata=ObjectMeta(name="dev", namespace="demo-project"),
        spec=StageSpec(),
        status=StageStatus(currentFreightId="abc123"),
    )

    service.refresh_warehouse.return_value = None

    service.list_promotion_tasks.return_value = [
        {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "PromotionTask",
            "metadata": {"name": "promote", "namespace": "demo-project"},
            "spec": {
                "steps": [
                    {"uses": "git-clone", "config": {"repoURL": "https://github.com/org/repo.git"}},
                    {"uses": "git-push", "config": {"path": "./out"}},
                ],
                "vars": [{"name": "repoURL", "value": "https://github.com/org/repo.git"}],
            },
        }
    ]

    service.get_promotion_task.return_value = {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "PromotionTask",
        "metadata": {"name": "promote", "namespace": "demo-project"},
        "spec": {
            "steps": [
                {"uses": "git-clone", "config": {"repoURL": "https://github.com/org/repo.git"}},
                {"uses": "git-push", "config": {"path": "./out"}},
            ],
            "vars": [{"name": "repoURL", "value": "https://github.com/org/repo.git"}],
        },
    }

    service.list_repo_credentials.return_value = [
        {
            "metadata": {"name": "git-creds", "namespace": "demo-project"},
            "type": "git",
            "repoURL": "https://github.com/org/repo.git",
            "username": "deploy-bot",
            "password": "secret-token",
        }
    ]

    service.get_repo_credentials.return_value = {
        "metadata": {"name": "git-creds", "namespace": "demo-project"},
        "type": "git",
        "repoURL": "https://github.com/org/repo.git",
        "username": "deploy-bot",
        "password": "secret-token",
    }

    return service


@pytest.fixture
def service_locator(mock_kargo_service: AsyncMock, test_config: ServerConfig) -> Dict[str, Any]:
    """Create a service locator with mock services."""
    return {
        "kargo_service": mock_kargo_service,
        "config": test_config,
    }


@pytest.fixture
def readonly_service_locator(mock_kargo_service: AsyncMock, readonly_config: ServerConfig) -> Dict[str, Any]:
    """Create a service locator with write disabled."""
    return {
        "kargo_service": mock_kargo_service,
        "config": readonly_config,
    }


# ---- Mock Context Fixture ----

@pytest.fixture
def mock_ctx() -> AsyncMock:
    """Create a mock FastMCP Context."""
    ctx = AsyncMock()
    ctx.info = AsyncMock()
    ctx.debug = AsyncMock()
    ctx.warning = AsyncMock()
    ctx.error = AsyncMock()
    return ctx
