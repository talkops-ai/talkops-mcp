"""GitOps ownership detection utility.

Detects whether a Kubernetes resource is managed by Argo CD, Flux CD, or Helm
so that mutating tools can warn or block in-place cluster drift (`GITOPS_MANAGED`)
and return a clean manifest for pull-request workflows.
"""

from typing import Any, Dict, List, Optional

from opentelemetry_mcp_server.models.findings import Finding, FindingCode

_ARGOCD_ANNOTATIONS = (
    "argocd.argoproj.io/tracking-id",
    "argocd.argoproj.io/compare-options",
)
_ARGOCD_LABELS = ("argocd.argoproj.io/instance",)

_FLUX_LABELS = (
    "kustomize.toolkit.fluxcd.io/name",
    "kustomize.toolkit.fluxcd.io/namespace",
    "helm.toolkit.fluxcd.io/name",
    "helm.toolkit.fluxcd.io/namespace",
)


def detect_gitops_ownership(
    resource_or_meta: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Inspect a Kubernetes resource or metadata dict for GitOps controller ownership."""
    if not isinstance(resource_or_meta, dict):
        return {
            "managed": False,
            "controller": None,
            "manager": None,
            "tracking_id": None,
            "markers": [],
        }

    metadata = (
        resource_or_meta.get("metadata")
        if "metadata" in resource_or_meta
        and isinstance(resource_or_meta.get("metadata"), dict)
        else resource_or_meta
    )
    labels: Dict[str, Any] = metadata.get("labels") or {}
    annotations: Dict[str, Any] = metadata.get("annotations") or {}

    markers: List[str] = []
    controller: Optional[str] = None
    tracking_id: Optional[str] = None

    for key in _ARGOCD_ANNOTATIONS:
        if key in annotations:
            controller = "argocd"
            tracking_id = str(annotations[key])
            markers.append(f"annotation:{key}={annotations[key]}")

    for key in _ARGOCD_LABELS:
        if key in labels:
            controller = controller or "argocd"
            tracking_id = tracking_id or str(labels[key])
            markers.append(f"label:{key}={labels[key]}")

    for key in _FLUX_LABELS:
        if key in labels or key in annotations:
            controller = controller or "flux"
            val = labels.get(key) or annotations.get(key)
            tracking_id = tracking_id or str(val)
            markers.append(f"{key}={val}")

    managed_by = str(labels.get("app.kubernetes.io/managed-by", "")).strip()
    if (
        managed_by.lower() in ("argocd", "flux", "helm")
        and managed_by.lower() != "talkops-mcp"
    ):
        controller = controller or managed_by.lower()
        markers.append(f"label:app.kubernetes.io/managed-by={managed_by}")

    return {
        "managed": bool(controller),
        "controller": controller,
        "manager": controller,
        "tracking_id": tracking_id,
        "markers": markers,
    }


def build_gitops_finding(
    resource_or_name: Any,
    resource_ref_or_ns: str = "",
    gitops_info: Optional[Dict[str, Any]] = None,
) -> Optional[Finding]:
    """Return a GITOPS_MANAGED Finding if the resource is owned by Argo CD, Flux, or Helm."""
    if gitops_info is not None:
        info = gitops_info
        ref = (
            f"{resource_ref_or_ns}/{resource_or_name}"
            if resource_ref_or_ns
            else str(resource_or_name)
        )
    else:
        info = detect_gitops_ownership(resource_or_name)
        ref = resource_ref_or_ns or "target"

    if not info.get("managed"):
        return None
    controller = info.get("controller") or info.get("manager")
    markers = info.get("markers") or []
    return Finding.create(
        FindingCode.GITOPS_MANAGED,
        message=(
            f"Resource '{ref}' is managed by GitOps controller "
            f"'{controller}' ({', '.join(markers)}). Direct cluster mutation "
            "will cause GitOps drift unless committed to the source repository."
        ),
        component=ref,
        evidence=info,
        next_tool_hint=(
            "Use the dry_run=True manifest output to commit changes to your GitOps repository, "
            "or pass confirm=True to force an in-place override."
        ),
    )
