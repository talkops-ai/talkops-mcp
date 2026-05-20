"""Kargo utility functions for DAG validation and formatting."""


from typing import Any, Dict, List, Set, Tuple

from kargo_mcp_server.models.stage import Stage, StageSummary


def validate_no_self_reference(stage_name: str, spec: Dict[str, Any]) -> None:
    """Validate that a stage spec does not reference itself as an upstream source.

    Args:
        stage_name: Name of the stage being validated
        spec: Stage spec dict to validate

    Raises:
        ValueError: If the stage references itself
    """
    for rf in spec.get("requestedFreight", []):
        sources = rf.get("sources", {})
        upstream_stages: List[str] = sources.get("stages", [])
        if stage_name in upstream_stages:
            raise ValueError(
                f"Stage {stage_name!r} cannot list itself as an upstream source"
            )


def build_stage_dag(
    stages: List[Stage],
) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    """Build upstream and downstream maps from a list of stages.

    Inspects each stage's ``requestedFreight[].sources.stages`` to
    determine which stages feed into which.  The ``origin`` field
    always points to a Warehouse and is not relevant for the
    stage-to-stage DAG.

    Args:
        stages: List of Stage resources

    Returns:
        Tuple of (upstream_map, downstream_map) where each is a dict
        mapping stage name to set of related stage names
    """
    upstream_map: Dict[str, Set[str]] = {s.metadata.name: set() for s in stages}
    downstream_map: Dict[str, Set[str]] = {s.metadata.name: set() for s in stages}

    for stage in stages:
        for rf in stage.spec.requestedFreight:
            # Sources.stages lists upstream stage names
            for upstream_name in rf.sources.stages:
                upstream_map[stage.metadata.name].add(upstream_name)
                if upstream_name in downstream_map:
                    downstream_map[upstream_name].add(stage.metadata.name)

    return upstream_map, downstream_map


def stages_to_summaries(
    stages: List[Stage],
    upstream_map: Dict[str, Set[str]],
    downstream_map: Dict[str, Set[str]],
) -> List[StageSummary]:
    """Convert Stage resources to StageSummary objects with DAG topology.

    Args:
        stages: List of Stage resources
        upstream_map: Map of stage name to upstream stage names
        downstream_map: Map of stage name to downstream stage names

    Returns:
        List of StageSummary objects
    """
    summaries: List[StageSummary] = []
    for s in stages:
        summaries.append(
            StageSummary(
                name=s.metadata.name,
                upstream_stages=sorted(upstream_map.get(s.metadata.name, set())),
                downstream_stages=sorted(downstream_map.get(s.metadata.name, set())),
                current_freight_id=(
                    s.status.current_freight_id if s.status else None
                ),
                auto_promotion_enabled=True,
            )
        )
    return summaries


def format_topology_summary(
    stages: List[Stage],
    upstream_map: Dict[str, Set[str]],
    downstream_map: Dict[str, Set[str]],
) -> Dict[str, object]:
    """Format a topology summary as a dictionary for API responses.

    Args:
        stages: List of Stage resources
        upstream_map: Map of stage name to upstream stage names
        downstream_map: Map of stage name to downstream stage names

    Returns:
        Dictionary with topology information
    """
    # Identify roots (stages with no upstream) and leaves (stages with no downstream)
    roots = [s.metadata.name for s in stages if not upstream_map.get(s.metadata.name)]
    leaves = [s.metadata.name for s in stages if not downstream_map.get(s.metadata.name)]

    edges: List[Dict[str, str]] = []
    for stage_name, upstreams in upstream_map.items():
        for upstream in upstreams:
            edges.append({"from": upstream, "to": stage_name})

    return {
        "stage_count": len(stages),
        "roots": roots,
        "leaves": leaves,
        "edges": edges,
        "stages": [
            {
                "name": s.metadata.name,
                "upstream": sorted(upstream_map.get(s.metadata.name, set())),
                "downstream": sorted(downstream_map.get(s.metadata.name, set())),
                "current_freight_id": (
                    s.status.current_freight_id if s.status else None
                ),
            }
            for s in stages
        ],
    }
