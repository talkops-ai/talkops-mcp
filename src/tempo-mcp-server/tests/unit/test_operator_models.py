"""Unit tests for Tempo Operator CRD models.

Covers Pydantic validation for TempoOperatorCRSummary, TempoStackSpec,
and TempoOperatorCRDetail.
"""

import pytest
from pydantic import ValidationError

from tempo_mcp_server.models.operator import (
    TempoOperatorCRSummary,
    TempoStackSpec,
    TempoOperatorCRDetail,
)


class TestTempoOperatorCRSummary:
    """Validate TempoOperatorCRSummary model."""

    def test_minimal_valid_summary(self):
        summary = TempoOperatorCRSummary(
            name="my-tempo",
            namespace="tracing",
            kind="TempoStack",
        )
        assert summary.name == "my-tempo"
        assert summary.namespace == "tracing"
        assert summary.kind == "TempoStack"
        assert summary.storage_type is None
        assert summary.ready is None

    def test_full_summary(self):
        summary = TempoOperatorCRSummary(
            name="prod-tempo",
            namespace="monitoring",
            kind="TempoMonolithic",
            storage_type="s3",
            retention="48h",
            size="small",
            status_phase="Ready",
            ready=True,
            age="3d",
        )
        assert summary.storage_type == "s3"
        assert summary.retention == "48h"
        assert summary.ready is True
        assert summary.age == "3d"

    def test_roundtrip_model_dump(self):
        summary = TempoOperatorCRSummary(
            name="test",
            namespace="default",
            kind="TempoStack",
            storage_type="gcs",
        )
        dumped = summary.model_dump()
        assert dumped["name"] == "test"
        assert dumped["storage_type"] == "gcs"
        # Verify roundtrip
        restored = TempoOperatorCRSummary(**dumped)
        assert restored == summary

    def test_missing_required_name_raises(self):
        with pytest.raises(ValidationError):
            TempoOperatorCRSummary(  # type: ignore[call-arg]
                namespace="default",
                kind="TempoStack",
            )

    def test_missing_required_kind_raises(self):
        with pytest.raises(ValidationError):
            TempoOperatorCRSummary(  # type: ignore[call-arg]
                name="test",
                namespace="default",
            )


class TestTempoStackSpec:
    """Validate TempoStackSpec model."""

    def test_minimal_spec_with_storage(self):
        spec = TempoStackSpec(
            storage={"secret": {"name": "s3-creds", "type": "s3"}}
        )
        assert spec.storage["secret"]["type"] == "s3"
        assert spec.retention is None

    def test_full_spec(self):
        spec = TempoStackSpec(
            storage={"secret": {"name": "s3-creds", "type": "s3"}},
            retention={"global": {"traces": "48h"}},
            resources={"total": {"limits": {"memory": "2Gi"}}},
            search={"defaultResultLimit": 20},
            template={"queryFrontend": {"jaegerQuery": {"enabled": True}}},
        )
        assert spec.retention is not None
        assert spec.resources is not None
        assert spec.template is not None
        assert spec.retention["global"]["traces"] == "48h"
        assert spec.resources["total"]["limits"]["memory"] == "2Gi"
        assert spec.template["queryFrontend"]["jaegerQuery"]["enabled"] is True

    def test_missing_storage_raises(self):
        with pytest.raises(ValidationError):
            TempoStackSpec()  # type: ignore[call-arg]


class TestTempoOperatorCRDetail:
    """Validate TempoOperatorCRDetail model."""

    def test_minimal_detail(self):
        detail = TempoOperatorCRDetail(
            name="my-tempo",
            namespace="tracing",
            kind="TempoStack",
            api_version="tempo.grafana.com/v1alpha1",
        )
        assert detail.labels == {}
        assert detail.spec == {}
        assert detail.conditions == []

    def test_detail_with_conditions(self):
        detail = TempoOperatorCRDetail(
            name="prod",
            namespace="monitoring",
            kind="TempoStack",
            api_version="tempo.grafana.com/v1alpha1",
            conditions=[
                {"type": "Ready", "status": "True", "reason": "ComponentsReady"},
            ],
        )
        assert len(detail.conditions) == 1
        assert detail.conditions[0]["type"] == "Ready"

    def test_roundtrip_model_dump(self):
        detail = TempoOperatorCRDetail(
            name="test",
            namespace="default",
            kind="TempoMonolithic",
            api_version="tempo.grafana.com/v1alpha1",
            storage_type="pv",
            retention="72h",
        )
        dumped = detail.model_dump()
        restored = TempoOperatorCRDetail(**dumped)
        assert restored == detail
