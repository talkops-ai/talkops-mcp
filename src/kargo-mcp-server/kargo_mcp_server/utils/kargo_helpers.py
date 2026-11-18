"""Kargo utility functions for DAG validation, step validation, and pipeline formatting."""

from typing import Any, Dict, List, Optional, Set, Tuple

from kargo_mcp_server.exceptions import KargoValidationError
from kargo_mcp_server.models.stage import (
    AutoPromotionOptions,
    FreightSources,
    RequestedFreight,
    RequestedFreightOrigin,
    Stage,
    StageSummary,
)

# All Kargo v1.12 open-source built-in promotion steps
VALID_OSS_PROMOTION_STEPS = frozenset({
    "argocd-update",
    "argocd-wait",
    "compose-output",
    "copy",
    "delete",
    "fail",
    "file-write",
    "git-clear",
    "git-clone",
    "git-commit",
    "git-merge-pr",
    "git-open-pr",
    "git-push",
    "git-tag",
    "git-wait-for-pr",
    "github-push",
    "helm-template",
    "helm-update-chart",
    "http",
    "http-download",
    "json-parse",
    "json-update",
    "kustomize-build",
    "kustomize-set-image",
    "oci-download",
    "oci-push",
    "set-freight-alias",
    "set-metadata",
    "tar",
    "toml-parse",
    "toml-update",
    "untar",
    "yaml-merge",
    "yaml-parse",
    "yaml-update",
})

REMOVED_PROMOTION_STEPS = {
    "helm-update-image": (
        "Step 'helm-update-image' was removed in Kargo v1.3.0. "
        "Use 'yaml-update' to update image tags in Helm values files."
    ),
    "helm-chart-update": (
        "Step 'helm-chart-update' is not a registered Kargo v1.12 step runner. "
        "Use 'helm-update-chart' instead."
    ),
}

REMOVED_STEP_CONFIG_FIELDS = {
    "fromOrigin": "Removed in Kargo v1.3.0; use expressions like imageFrom() / commitFrom() / chartFrom().",
    "fromFreight": "Removed in Kargo v1.3.0; use expressions like imageFrom() / commitFrom() / chartFrom().",
    "prNumberFromStep": "Removed in Kargo v1.3.0; use '${{ outputs.<step-alias>.pr.id }}'.",
    "commitFromStep": "Removed in Kargo v1.3.0; use '${{ outputs.<step-alias>.commit }}'.",
    "messageFromSteps": "Removed in Kargo v1.5.0; use 'message' with expressions.",
}


def validate_promotion_steps(
    steps: List[Dict[str, Any]],
) -> Tuple[List[str], List[str]]:
    """Validate promotion steps against Kargo v1.12 specification.

    Returns:
        Tuple of (errors, warnings). Raises KargoValidationError if steps is empty or invalid type.
    """
    if not isinstance(steps, list) or not steps:
        raise KargoValidationError(
            "Promotion steps must be a non-empty list of step dicts (each with 'uses' or 'task')."
        )

    errors: List[str] = []
    warnings: List[str] = []

    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"Step [{idx}] must be a dict, got {type(step).__name__}.")
            continue

        uses = step.get("uses")
        task = step.get("task")
        if not uses and not task:
            errors.append(
                f"Step [{idx}] must specify either 'uses' (built-in runner) or 'task' (PromotionTask reference)."
            )
            continue

        if uses:
            if uses in REMOVED_PROMOTION_STEPS:
                errors.append(f"Step [{idx}]: {REMOVED_PROMOTION_STEPS[uses]}")
            elif uses not in VALID_OSS_PROMOTION_STEPS:
                warnings.append(
                    f"Step [{idx}] uses '{uses}' which is not a standard Kargo v1.12 OSS runner "
                    "(may require Kargo Enterprise or CustomPromotionStep)."
                )

        cfg = step.get("config")
        if isinstance(cfg, dict):
            for bad_field, reason in REMOVED_STEP_CONFIG_FIELDS.items():
                if bad_field in cfg:
                    errors.append(
                        f"Step [{idx}] ({uses or 'task'}) uses removed config field '{bad_field}': {reason}"
                    )
            if uses == "git-commit" and "author" in cfg:
                errors.append(
                    f"Step [{idx}] (git-commit) uses 'config.author' which was removed in Kargo v1.12.0. "
                    "Configure author on 'git-clone' or ClusterConfig.spec.gitClient."
                )
            if uses == "git-open-pr" and "createTargetBranch" in cfg:
                errors.append(
                    f"Step [{idx}] (git-open-pr) uses 'config.createTargetBranch' which was removed from git-open-pr in Kargo v1.12.0. "
                    "Configure 'createTargetBranch' on 'git-push' instead."
                )
            if uses == "git-push" and "maxRetries" in cfg:
                errors.append(
                    f"Step [{idx}] (git-push) uses invalid 'config.maxRetries'; Kargo v1.12 git-push uses 'config.maxAttempts'."
                )

    return errors, warnings


def validate_no_self_reference(stage_name: str, spec: Dict[str, Any]) -> None:
    """Validate that a stage spec does not reference itself as an upstream source."""
    for rf in spec.get("requestedFreight", []):
        if not isinstance(rf, dict):
            continue
        sources = rf.get("sources") or {}
        upstream_stages: List[str] = sources.get("stages") or []
        if stage_name in upstream_stages:
            raise ValueError(
                f"Stage {stage_name!r} cannot list itself as an upstream source"
            )


def validate_no_dag_cycles(
    existing_stages: List[Stage],
    target_stage_name: str,
    target_spec: Dict[str, Any],
) -> None:
    """Validate that applying target_spec to target_stage_name does not create a cycle in the Stage DAG."""
    validate_no_self_reference(target_stage_name, target_spec)

    # Build adjacency: stage -> set of upstream stages
    upstreams: Dict[str, Set[str]] = {}
    for s in existing_stages:
        if s.metadata.name == target_stage_name:
            continue
        ups: Set[str] = set()
        for rf in s.spec.requested_freight:
            ups.update(rf.sources.stages)
        upstreams[s.metadata.name] = ups

    new_ups: Set[str] = set()
    for rf in target_spec.get("requestedFreight", []):
        if isinstance(rf, dict):
            sources = rf.get("sources") or {}
            new_ups.update(sources.get("stages") or [])
    upstreams[target_stage_name] = new_ups

    # DFS cycle detection
    visiting: Set[str] = set()
    visited: Set[str] = set()

    def dfs(node: str, path: List[str]) -> None:
        if node in visiting:
            cycle_str = " -> ".join(path + [node])
            raise ValueError(f"Stage DAG cycle detected: {cycle_str}")
        if node in visited:
            return
        visiting.add(node)
        for parent in upstreams.get(node, set()):
            dfs(parent, path + [node])
        visiting.remove(node)
        visited.add(node)

    for stg in list(upstreams.keys()):
        dfs(stg, [])


def build_requested_freight(
    origins: List[Dict[str, Any]],
) -> List[RequestedFreight]:
    """Convert user-friendly or canonical requestedFreight dicts into RequestedFreight models."""
    freight_list: List[RequestedFreight] = []

    for rf in origins:
        if not isinstance(rf, dict):
            raise KargoValidationError("Each requested_freight item must be a dict.")

        # Support canonical {"origin": {"kind": "Warehouse", "name": "..."}, "sources": {...}}
        if "origin" in rf and isinstance(rf["origin"], dict):
            origin_dict = rf["origin"]
            kind = origin_dict.get("kind", "Warehouse")
            name = origin_dict.get("name", "")
            sources_dict = rf.get("sources") or {}
            upstream_stages = sources_dict.get("stages") or []
            direct = sources_dict.get("direct", len(upstream_stages) == 0)
            availability = sources_dict.get("availabilityStrategy") or sources_dict.get("availability_strategy")
            soak = sources_dict.get("requiredSoakTime") or sources_dict.get("required_soak_time")
            auto_opts_dict = sources_dict.get("autoPromotionOptions") or sources_dict.get("auto_promotion_options")
            selection_policy = (
                auto_opts_dict.get("selectionPolicy") or auto_opts_dict.get("selection_policy")
                if isinstance(auto_opts_dict, dict)
                else None
            )
        else:
            kind = rf.get("kind", "Warehouse")
            name = rf.get("name") or rf.get("warehouse") or ""
            upstream_stages = rf.get("stages") or []
            direct = rf.get("direct", len(upstream_stages) == 0)
            availability = rf.get("availability_strategy") or rf.get("availabilityStrategy")
            soak = rf.get("required_soak_time") or rf.get("requiredSoakTime")
            selection_policy = rf.get("selection_policy") or rf.get("selectionPolicy")

        if not name:
            raise KargoValidationError(
                "Each requested_freight entry must specify a Warehouse 'name' "
                "(e.g. {'kind': 'Warehouse', 'name': 'my-warehouse'})."
            )

        if kind == "Stage":
            raise KargoValidationError(
                f"Cannot use kind='Stage' for origin '{name}'. "
                "In Kargo, origins must always be Warehouses. "
                "To specify upstream stages, use: "
                "{'kind': 'Warehouse', 'name': '<warehouse>', 'stages': ['<upstream-stage>']}"
            )

        if kind != "Warehouse":
            raise KargoValidationError(
                f"Invalid origin kind '{kind}'. Origin kind must be 'Warehouse'."
            )

        auto_opts = (
            AutoPromotionOptions(selectionPolicy=selection_policy)
            if selection_policy
            else None
        )

        sources = FreightSources(
            direct=bool(direct),
            stages=list(upstream_stages),
            availabilityStrategy=availability,
            requiredSoakTime=soak,
            autoPromotionOptions=auto_opts,
        )

        freight_list.append(
            RequestedFreight(
                origin=RequestedFreightOrigin(kind="Warehouse", name=name),
                sources=sources,
            )
        )

    return freight_list


def build_stage_dag(
    stages: List[Stage],
) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    """Build upstream and downstream maps from a list of stages."""
    upstream_map: Dict[str, Set[str]] = {s.metadata.name: set() for s in stages}
    downstream_map: Dict[str, Set[str]] = {s.metadata.name: set() for s in stages}

    for stage in stages:
        for rf in stage.spec.requested_freight:
            for upstream_name in rf.sources.stages:
                upstream_map[stage.metadata.name].add(upstream_name)
                if upstream_name in downstream_map:
                    downstream_map[upstream_name].add(stage.metadata.name)

    return upstream_map, downstream_map


def stages_to_summaries(
    stages: List[Stage],
    upstream_map: Dict[str, Set[str]],
    downstream_map: Dict[str, Set[str]],
    auto_promo_stages: Optional[Set[str]] = None,
) -> List[StageSummary]:
    """Convert Stage resources to StageSummary objects with DAG topology and v1.12 status."""
    summaries: List[StageSummary] = []
    for s in stages:
        warehouses = sorted({rf.origin.name for rf in s.spec.requested_freight if rf.origin and rf.origin.name})
        auto_enabled = False
        if s.status and s.status.auto_promotion_enabled is not None:
            auto_enabled = bool(s.status.auto_promotion_enabled)
        elif auto_promo_stages is not None:
            auto_enabled = s.metadata.name in auto_promo_stages

        has_hold = bool(
            s.status
            and (s.status.auto_promotion_holds or s.status.effective_auto_promotion_holds)
        )

        summaries.append(
            StageSummary(
                name=s.metadata.name,
                namespace=s.metadata.namespace or "",
                phase=s.get_phase(),
                health_status=s.get_health_status(),
                warehouses=warehouses,
                upstream_stages=sorted(upstream_map.get(s.metadata.name, set())),
                downstream_stages=sorted(downstream_map.get(s.metadata.name, set())),
                current_freight_id=s.get_current_freight_id(),
                auto_promotion_enabled=auto_enabled,
                has_auto_promotion_hold=has_hold,
            )
        )
    return summaries


def format_topology_summary(
    stages: List[Stage],
    upstream_map: Dict[str, Set[str]],
    downstream_map: Dict[str, Set[str]],
    warehouses: Optional[List[str]] = None,
    auto_promo_stages: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Format a complete pipeline topology summary as a dictionary."""
    roots = [s.metadata.name for s in stages if not upstream_map.get(s.metadata.name)]
    leaves = [s.metadata.name for s in stages if not downstream_map.get(s.metadata.name)]

    edges: List[Dict[str, str]] = []
    warehouse_edges: List[Dict[str, str]] = []

    for s in stages:
        for rf in s.spec.requested_freight:
            if rf.sources.direct and rf.origin.name:
                warehouse_edges.append(
                    {"from_warehouse": rf.origin.name, "to_stage": s.metadata.name}
                )
        for upstream in sorted(upstream_map.get(s.metadata.name, set())):
            edges.append({"from": upstream, "to": s.metadata.name})

    summaries = stages_to_summaries(
        stages, upstream_map, downstream_map, auto_promo_stages=auto_promo_stages
    )

    return {
        "stage_count": len(stages),
        "warehouses": warehouses or sorted(
            {rf.origin.name for s in stages for rf in s.spec.requested_freight if rf.origin.name}
        ),
        "roots": roots,
        "leaves": leaves,
        "warehouse_edges": warehouse_edges,
        "edges": edges,
        "stages": [
            {
                "name": sm.name,
                "phase": sm.phase,
                "health_status": sm.health_status,
                "warehouses": sm.warehouses,
                "upstream": sm.upstream_stages,
                "downstream": sm.downstream_stages,
                "current_freight_id": sm.current_freight_id,
                "auto_promotion_enabled": sm.auto_promotion_enabled,
                "has_auto_promotion_hold": sm.has_auto_promotion_hold,
            }
            for sm in summaries
        ],
    }
