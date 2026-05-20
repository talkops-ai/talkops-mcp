"""Tests for Pydantic models."""

from datetime import datetime

import pytest

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
    ProjectSummary,
    PromotionPolicy,
)
from kargo_mcp_server.models.promotion import (
    Promotion,
    PromotionSpec,
    PromotionStatus,
    PromotionStepStatus,
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


class TestObjectMeta:
    def test_minimal(self):
        meta = ObjectMeta(name="test")
        assert meta.name == "test"
        assert meta.namespace is None
        assert meta.labels == {}

    def test_full(self):
        meta = ObjectMeta(name="test", namespace="ns", labels={"env": "dev"})
        assert meta.namespace == "ns"
        assert meta.labels == {"env": "dev"}


class TestProjectModels:
    def test_project_from_api_response(self):
        """Model should parse a Kargo API-style JSON response."""
        data = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Project",
            "metadata": {"name": "my-project", "namespace": "my-project"},
            "spec": {"promotionPolicy": {"autoPromotionEnabled": False}},
        }
        project = Project.model_validate(data)
        assert project.metadata.name == "my-project"
        assert project.spec.promotion_policy is not None
        assert project.spec.promotion_policy.auto_promotion_enabled is False

    def test_project_summary(self):
        s = ProjectSummary(name="p1", namespace="p1", stage_count=3, auto_promotion_enabled=True)
        d = s.model_dump()
        assert d["name"] == "p1"
        assert d["stage_count"] == 3


class TestStageModels:
    def test_stage_with_freight_origins(self):
        data = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Stage",
            "metadata": {"name": "staging", "namespace": "demo"},
            "spec": {
                "requestedFreight": [
                    {
                        "origin": {"kind": "Warehouse", "name": "wh1"},
                        "sources": {"stages": ["dev"]}
                    }
                ]
            },
        }
        stage = Stage.model_validate(data)
        assert stage.metadata.name == "staging"
        assert len(stage.spec.requestedFreight) == 1
        assert stage.spec.requestedFreight[0].origin.kind == "Warehouse"
        assert stage.spec.requestedFreight[0].origin.name == "wh1"
        assert stage.spec.requestedFreight[0].sources.stages == ["dev"]

    def test_stage_summary_roundtrip(self):
        s = StageSummary(name="dev", upstream_stages=[], downstream_stages=["staging"])
        d = s.model_dump()
        s2 = StageSummary.model_validate(d)
        assert s2.name == "dev"
        assert s2.downstream_stages == ["staging"]


class TestWarehouseModels:
    def test_warehouse_with_sources(self):
        data = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Warehouse",
            "metadata": {"name": "wh1", "namespace": "demo"},
            "spec": {"sources": [{"type": "image", "url": "docker.io/nginx"}]},
        }
        wh = Warehouse.model_validate(data)
        assert wh.spec.sources[0].type == "image"
        assert wh.spec.sources[0].url == "docker.io/nginx"


class TestFreightModels:
    def test_freight_stage_state(self):
        state = FreightStageState(stage="dev", available=True, promoted=True, verified=False)
        assert state.verified is False

    def test_freight_summary(self):
        s = FreightSummary(
            id="abc", artifacts=[ArtifactReference(type="image", ref="nginx:1.25")]
        )
        assert len(s.artifacts) == 1


class TestPromotionModels:
    def test_promotion_from_api_response_with_freight_field(self):
        """Model should parse a Kargo API response using the canonical 'freight' field."""
        data = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Promotion",
            "metadata": {"name": "promo-001", "namespace": "demo"},
            "spec": {"stage": "dev", "freight": "freight-abc"},
            "status": {
                "state": "Succeeded",
                "steps": [
                    {"name": "git-clone", "type": "git-clone", "status": "Succeeded"}
                ],
            },
        }
        p = Promotion.model_validate(data)
        assert p.spec.stage == "dev"
        assert p.spec.freight == "freight-abc"
        assert p.status is not None
        assert p.status.state == "Succeeded"
        assert len(p.status.steps) == 1
        assert p.status.steps[0].name == "git-clone"

    def test_promotion_from_legacy_freightId_field(self):
        """Model should also accept the legacy 'freightId' alias for backward compat."""
        data = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Promotion",
            "metadata": {"name": "promo-002", "namespace": "demo"},
            "spec": {"stage": "staging", "freightId": "freight-xyz"},
        }
        p = Promotion.model_validate(data)
        assert p.spec.freight == "freight-xyz"

    def test_promotion_spec_with_optional_project(self):
        """PromotionSpec should accept an optional project field."""
        data = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Promotion",
            "metadata": {"name": "promo-003", "namespace": "demo"},
            "spec": {"stage": "dev", "freight": "freight-abc", "project": "demo"},
        }
        p = Promotion.model_validate(data)
        assert p.spec.project == "demo"

        # Without project
        data2 = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Promotion",
            "metadata": {"name": "promo-004", "namespace": "demo"},
            "spec": {"stage": "dev", "freight": "freight-abc"},
        }
        p2 = Promotion.model_validate(data2)
        assert p2.spec.project is None

    def test_promotion_summary(self):
        s = PromotionSummary(name="p1", stage="dev", freight="f1", state="Running")
        assert s.state == "Running"
        assert s.freight == "f1"
