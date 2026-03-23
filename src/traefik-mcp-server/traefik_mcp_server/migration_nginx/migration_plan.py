"""Agent-supplied overrides for NGINX→Traefik migration (hybrid model).

Lets an agent drop known-breaking annotations and append pre-created Middleware refs
after deterministic generation. See docs/TICKET_MIGRATION_AGENT_INTELLIGENCE.md.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Mapping, Optional, Set

from pydantic import BaseModel, Field

from traefik_mcp_server.migration_nginx.analyzer import (
    AnalysisReport,
    IngressReport,
    Summary,
)
from traefik_mcp_server.migration_nginx.scanner import IngressInfo, NGINX_ANNOTATION_PREFIX


class IngressMigrationPlanEntry(BaseModel):
    """Per-Ingress overrides from the agent."""

    ignore_annotations: List[str] = Field(
        default_factory=list,
        description="Short nginx annotation keys (or full nginx.ingress.kubernetes.io/...) to exclude from analysis and from middleware / strip logic.",
    )
    inject_middlewares: List[str] = Field(
        default_factory=list,
        description=(
            "Extra Traefik middleware references appended to "
            "traefik.ingress.kubernetes.io/router.middlewares. "
            "Use bare Middleware name (same namespace) or a full ref like ns-name@kubernetescrd."
        ),
    )
    shadow_mode: bool = Field(
        default=False,
        description=(
            "If true, generate a Traefik TraefikService of kind 'mirroring' alongside "
            "the migration artifacts. This mirrors a percentage of live traffic to a "
            "shadow service for validation without affecting real users."
        ),
    )
    shadow_mirror_percent: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Percentage of traffic to mirror when shadow_mode is enabled (1-100).",
    )


def normalize_ignore_key(key: str) -> str:
    """Normalize user/agent keys to short nginx annotation form."""
    k = (key or "").strip()
    if k.startswith(NGINX_ANNOTATION_PREFIX):
        k = k[len(NGINX_ANNOTATION_PREFIX) :]
    return k


def parse_migration_plan(
    raw: Optional[Mapping[str, Any]],
) -> Dict[str, IngressMigrationPlanEntry]:
    """Parse tool JSON into a map keyed by ``namespace/name`` and/or ``ingressName``."""
    if not raw:
        return {}
    out: Dict[str, IngressMigrationPlanEntry] = {}
    for key, val in raw.items():
        if not isinstance(val, Mapping):
            continue
        try:
            out[str(key)] = IngressMigrationPlanEntry.model_validate(val)
        except Exception:
            continue
    return out


def plan_entry_for_ingress(
    plan: Mapping[str, IngressMigrationPlanEntry],
    namespace: str,
    name: str,
) -> IngressMigrationPlanEntry:
    """Resolve plan: prefer ``namespace/name``, then ``name``, then ``*`` wildcard."""
    composite = f"{namespace}/{name}"
    if composite in plan:
        return plan[composite]
    if name in plan:
        return plan[name]
    # Cluster-level defaults via wildcard key
    if "*" in plan:
        return plan["*"]
    return IngressMigrationPlanEntry()


def filter_ingress_for_plan(ing: IngressInfo, ignore_keys: List[str]) -> IngressInfo:
    """Copy ingress with listed nginx annotations removed (short + full metadata keys)."""
    if not ignore_keys:
        return ing
    norm: Set[str] = {normalize_ignore_key(k) for k in ignore_keys}
    new_nginx = {k: v for k, v in ing.nginx_annotations.items() if k not in norm}
    new_ann: Dict[str, str] = {}
    for k, v in ing.annotations.items():
        if k.startswith(NGINX_ANNOTATION_PREFIX):
            short = k[len(NGINX_ANNOTATION_PREFIX) :]
            if short in norm:
                continue
        new_ann[k] = v
    return replace(ing, annotations=new_ann, nginx_annotations=new_nginx)


def _recompute_ingress_status(ir: IngressReport) -> None:
    has_unsupported = any(m.status == "unsupported" for m in ir.mappings)
    has_partial = any(m.status == "partial" for m in ir.mappings)
    if has_unsupported:
        ir.overall_status = "breaking"
    elif has_partial:
        ir.overall_status = "workaround"
    else:
        ir.overall_status = "ready"


def apply_plan_to_analysis(
    report: AnalysisReport,
    plan: Mapping[str, IngressMigrationPlanEntry],
) -> AnalysisReport:
    """Drop mappings for ignored annotations and recompute per-ingress + summary status."""
    if not plan:
        return report

    new_reports: List[IngressReport] = []
    for ir in report.ingress_reports:
        entry = plan_entry_for_ingress(plan, ir.namespace, ir.name)
        mappings = list(ir.mappings)
        if entry.ignore_annotations:
            norm = {normalize_ignore_key(k) for k in entry.ignore_annotations}
            mappings = [m for m in mappings if m.original_key not in norm]
        updated = IngressReport(
            namespace=ir.namespace,
            name=ir.name,
            mappings=mappings,
            overall_status=ir.overall_status,
        )
        _recompute_ingress_status(updated)
        new_reports.append(updated)

    summary = Summary()
    for ir in new_reports:
        summary.total += 1
        if ir.overall_status == "ready":
            summary.fully_compatible += 1
        elif ir.overall_status == "workaround":
            summary.needs_workaround += 1
        else:
            summary.has_unsupported += 1

    return AnalysisReport(
        target=report.target,
        ingress_reports=new_reports,
        summary=summary,
    )


def format_inject_middleware_ref(raw: str, ingress_namespace: str) -> str:
    """Normalize agent middleware name to Traefik Ingress NGINX provider ref."""
    s = (raw or "").strip()
    if not s:
        return s
    if "@kubernetescrd" in s:
        return s
    # Allow "namespace-mwname@kubernetescrd" already without duplicate
    return f"{ingress_namespace}-{s}@kubernetescrd"
