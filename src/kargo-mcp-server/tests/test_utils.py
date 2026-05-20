"""Tests for DAG utility functions."""

from typing import List

import pytest

from kargo_mcp_server.models.common import ObjectMeta
from kargo_mcp_server.models.stage import (
    FreightSources,
    RequestedFreight,
    RequestedFreightOrigin,
    Stage,
    StageSpec,
    StageStatus,
)
from kargo_mcp_server.utils.kargo_helpers import (
    build_stage_dag,
    format_topology_summary,
    stages_to_summaries,
    validate_no_self_reference,
)


def _make_stage(
    name: str,
    upstream_stage_names: list[str] | None = None,
    warehouse: str = "default",
) -> Stage:
    """Helper to create a Stage with optional upstream stage references.

    Mirrors real Kargo structure:
    - ``origin`` always points to a Warehouse.
    - ``sources.stages`` lists upstream stage names (DAG edges).
    - ``sources.direct`` is True for root stages (no upstreams).
    """
    if upstream_stage_names:
        sources = FreightSources(direct=False, stages=upstream_stage_names)
    else:
        sources = FreightSources(direct=True, stages=[])

    freight = [
        RequestedFreight(
            origin=RequestedFreightOrigin(kind="Warehouse", name=warehouse),
            sources=sources,
        )
    ]

    return Stage(
        metadata=ObjectMeta(name=name, namespace="test"),
        spec=StageSpec(requestedFreight=freight),
        status=StageStatus(currentFreightId=f"freight-{name}"),
    )


class TestValidateNoSelfReference:
    def test_valid_spec(self):
        """A stage referencing a different upstream stage should not raise."""
        spec = StageSpec(
            requestedFreight=[
                RequestedFreight(
                    origin=RequestedFreightOrigin(kind="Warehouse", name="wh"),
                    sources=FreightSources(stages=["dev"]),
                )
            ]
        )
        validate_no_self_reference("staging", spec.model_dump(by_alias=True))  # should not raise

    def test_self_reference_raises(self):
        """A stage listing itself in sources.stages should raise ValueError."""
        spec = StageSpec(
            requestedFreight=[
                RequestedFreight(
                    origin=RequestedFreightOrigin(kind="Warehouse", name="wh"),
                    sources=FreightSources(stages=["dev"]),
                )
            ]
        )
        with pytest.raises(ValueError, match="cannot list itself"):
            validate_no_self_reference("dev", spec.model_dump(by_alias=True))


class TestBuildStageDAG:
    def test_linear_pipeline(self):
        stages = [
            _make_stage("dev"),
            _make_stage("staging", ["dev"]),
            _make_stage("production", ["staging"]),
        ]
        upstream, downstream = build_stage_dag(stages)

        assert upstream["dev"] == set()
        assert upstream["staging"] == {"dev"}
        assert upstream["production"] == {"staging"}

        assert downstream["dev"] == {"staging"}
        assert downstream["staging"] == {"production"}
        assert downstream["production"] == set()

    def test_fan_out_pipeline(self):
        stages = [
            _make_stage("staging"),
            _make_stage("us-east", ["staging"]),
            _make_stage("eu-west", ["staging"]),
        ]
        upstream, downstream = build_stage_dag(stages)

        assert downstream["staging"] == {"us-east", "eu-west"}
        assert upstream["us-east"] == {"staging"}
        assert upstream["eu-west"] == {"staging"}

    def test_diamond_pipeline(self):
        stages = [
            _make_stage("dev"),
            _make_stage("qa", ["dev"]),
            _make_stage("perf", ["dev"]),
            _make_stage("prod", ["qa", "perf"]),
        ]
        upstream, downstream = build_stage_dag(stages)

        assert upstream["prod"] == {"qa", "perf"}
        assert downstream["dev"] == {"qa", "perf"}


class TestStagesToSummaries:
    def test_summaries_include_topology(self):
        stages = [
            _make_stage("dev"),
            _make_stage("staging", ["dev"]),
        ]
        upstream, downstream = build_stage_dag(stages)
        summaries = stages_to_summaries(stages, upstream, downstream)

        assert len(summaries) == 2
        dev = next(s for s in summaries if s.name == "dev")
        assert dev.upstream_stages == []
        assert dev.downstream_stages == ["staging"]
        assert dev.current_freight_id == "freight-dev"


class TestFormatTopologySummary:
    def test_summary_structure(self):
        stages = [
            _make_stage("dev"),
            _make_stage("staging", ["dev"]),
            _make_stage("production", ["staging"]),
        ]
        upstream, downstream = build_stage_dag(stages)
        summary = format_topology_summary(stages, upstream, downstream)

        assert summary["stage_count"] == 3
        assert summary["roots"] == ["dev"]
        assert summary["leaves"] == ["production"]
        edges: List[object] = summary["edges"]  # type: ignore[assignment]
        assert len(edges) == 2
