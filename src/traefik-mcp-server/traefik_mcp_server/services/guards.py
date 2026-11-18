"""Write-guard pipeline for Traefik MCP Server mutations."""

from __future__ import annotations

import copy
import difflib
from typing import Any, Dict, List, Optional, Set, Tuple
import yaml as pyyaml

from traefik_mcp_server.exceptions.custom import (
    KubernetesNamespaceError,
    TraefikEmptyBackendError,
    TraefikOwnershipError,
    TraefikReferentialIntegrityError,
    TraefikSchemaGatingError,
    TraefikWeightError,
)
from traefik_mcp_server.models.schemas import GuardResult
from traefik_mcp_server.utils.redaction import sanitize_manifest

MANAGED_BY_LABEL_KEY = "app.kubernetes.io/managed-by"
MANAGED_BY_LABEL_VALUE = "talkops-traefik-mcp"

# Default Traefik v3.6+ native Middleware spec keys (note: ipDenyList is NOT native in Traefik v3)
DEFAULT_V3_MIDDLEWARE_SPEC_KEYS: Set[str] = {
    "addPrefix",
    "basicAuth",
    "buffering",
    "chain",
    "circuitBreaker",
    "compress",
    "contentType",
    "digestAuth",
    "encodedCharacters",
    "errors",
    "forwardAuth",
    "grpcWeb",
    "headers",
    "inFlightReq",
    "ipAllowList",
    "passTLSClientCert",
    "plugin",
    "rateLimit",
    "redirectRegex",
    "redirectScheme",
    "replacePath",
    "replacePathRegex",
    "retry",
    "stripPrefix",
    "stripPrefixRegex",
    "tap",
}

DEFAULT_V3_MIDDLEWARE_TCP_SPEC_KEYS: Set[str] = {
    "inFlightConn",
    "ipAllowList",
}

DEFAULT_V3_LB_STRATEGIES: Set[str] = {"wrr", "p2c", "hrw", "leasttime", "RoundRobin"}


def check_namespace_policy(
    namespace: str,
    allowed_namespaces: Optional[Any] = None,
    protected_namespaces: Optional[List[str]] = None,
) -> Any:
    """Validate target namespace against allowed_namespaces and protected_namespaces.

    Returns:
        GuardResult when called with a ServerConfig object, or (GuardResult, is_protected_namespace)
    """
    direct_config_call = hasattr(allowed_namespaces, "allowed_namespaces")
    if direct_config_call:
        cfg = allowed_namespaces
        allowed_namespaces = cfg.allowed_namespaces
        protected_namespaces = list(cfg.protected_namespaces)
    ns = (namespace or "default").strip()
    protected = set(protected_namespaces or ["kube-system", "traefik"])
    if direct_config_call and ns in protected:
        raise KubernetesNamespaceError(
            f"Namespace '{ns}' is a protected infrastructure namespace."
        )
    if allowed_namespaces and ns not in allowed_namespaces:
        if ns in protected:
            raise KubernetesNamespaceError(
                f"Namespace '{ns}' is a protected namespace and not in allowed_namespaces ({', '.join(allowed_namespaces)})."
            )
        raise KubernetesNamespaceError(
            f"Namespace '{ns}' is not in allowed_namespaces ({', '.join(allowed_namespaces)})."
        )
    if ns in protected:
        res = GuardResult(
            guard="namespace_policy",
            passed=True,
            severity="warning",
            message=f"Namespace '{ns}' is a protected infrastructure namespace; operator confirmation is required.",
        )
        return res if direct_config_call else (res, True)
    res = GuardResult(
        guard="namespace_policy",
        passed=True,
        severity="info",
        message=f"Namespace '{ns}' permitted by namespace policy.",
    )
    return res if direct_config_call else (res, False)


def check_ownership(
    target_kind: str,
    target_name: str,
    namespace: str,
    existing_obj: Optional[Dict[str, Any]] = None,
    argo_rollouts: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[GuardResult, Optional[str]]:
    """Check whether a resource is owned by Argo Rollouts, GitOps (ArgoCD/Flux), or NGINX Ingress provider.

    Returns:
        (GuardResult, owner_type) where owner_type is 'argo_rollouts', 'nginx_provider', 'gitops', or None.
    """
    meta = (existing_obj or {}).get("metadata") or {}
    labels = meta.get("labels") or {}
    annotations = meta.get("annotations") or {}
    spec = (existing_obj or {}).get("spec") or {}

    # 1. Check Argo Rollouts ownership on TraefikService
    if target_kind == "TraefikService":
        for oref in meta.get("ownerReferences") or []:
            if isinstance(oref, dict) and (
                oref.get("kind") == "Rollout" or str(oref.get("apiVersion", "")).startswith("argoproj.io/")
            ):
                ro_name = oref.get("name", "<rollout>")
                msg = (
                    f"TraefikService '{target_name}' in namespace '{namespace}' is owned via ownerReferences by Argo Rollout '{ro_name}'. "
                    "Direct weight mutations would be overwritten by the Rollouts controller. "
                    "Use 'argo_manage_rollout_lifecycle' or 'argo_configure_rollout_strategy' on the Argo Rollouts MCP server."
                )
                return GuardResult(guard="ownership", passed=False, severity="error", message=msg), "argo_rollouts"

        if annotations.get("argoproj.io/rollout-name") or labels.get("argoproj.io/rollout-name"):
            ro_name = annotations.get("argoproj.io/rollout-name") or labels.get("argoproj.io/rollout-name")
            msg = (
                f"TraefikService '{target_name}' in namespace '{namespace}' is managed by Argo Rollout '{ro_name}'. "
                "Direct weight mutations would be overwritten by the Rollouts controller. "
                "Use 'argo_manage_rollout_lifecycle' or 'argo_configure_rollout_strategy' on the Argo Rollouts MCP server."
            )
            return GuardResult(guard="ownership", passed=False, severity="error", message=msg), "argo_rollouts"

        for ro in argo_rollouts or []:
            ro_meta = (ro.get("metadata") or {}).get("name", "<rollout>")
            tr = (
                (((ro.get("spec") or {}).get("strategy") or {}).get("canary") or {})
                .get("trafficRouting", {})
                .get("traefik", {})
            )
            if tr.get("weightedTraefikServiceName") == target_name:
                msg = (
                    f"TraefikService '{target_name}' in namespace '{namespace}' is referenced via "
                    f"weightedTraefikServiceName by Argo Rollout '{ro_meta}'. "
                    "Use 'argo_manage_rollout_lifecycle' on the Argo Rollouts MCP server instead."
                )
                return GuardResult(guard="ownership", passed=False, severity="error", message=msg), "argo_rollouts"

    # 2. Check Kubernetes Ingress claimed by kubernetesIngressNGINX provider
    if target_kind == "Ingress" and existing_obj:
        ing_class = spec.get("ingressClassName") or annotations.get("kubernetes.io/ingress.class") or ""
        has_nginx_ann = any(k.startswith("nginx.ingress.kubernetes.io/") for k in annotations)
        if ing_class == "nginx" or has_nginx_ann:
            msg = (
                f"Ingress '{target_name}' in namespace '{namespace}' is claimed by the NGINX Ingress provider "
                f"(ingressClass='{ing_class or 'nginx'}', nginx annotations present). "
                "Do not mix 'traefik.ingress.kubernetes.io/router.*' annotations onto an NGINX-claimed Ingress; "
                "follow the 'adopting-traefik-nginx-ingress-provider' skill or create a dedicated IngressRoute."
            )
            return GuardResult(guard="ownership", passed=False, severity="error", message=msg), "nginx_provider"

    # 3. Check GitOps (ArgoCD / Flux) ownership
    gitops_keys = (
        "argocd.argoproj.io/tracking-id",
        "argocd.argoproj.io/instance",
        "kustomize.toolkit.fluxcd.io/name",
        "helm.toolkit.fluxcd.io/name",
    )
    found_gitops = [k for k in gitops_keys if k in annotations or k in labels]
    if found_gitops:
        return (
            GuardResult(
                guard="ownership",
                passed=True,
                severity="warning",
                message=(
                    f"{target_kind} '{target_name}' has GitOps tracking metadata ({', '.join(found_gitops)}). "
                    "Live cluster edits may cause GitOps drift and be reverted on the next sync."
                ),
            ),
            "gitops",
        )

    return (
        GuardResult(
            guard="ownership",
            passed=True,
            severity="info",
            message=f"No conflicting controller ownership detected on {target_kind} '{target_name}'.",
        ),
        None,
    )


def validate_against_crd_schema(
    kind: str,
    spec_dict: Dict[str, Any],
    crd_spec_properties: Optional[Dict[str, Any]] = None,
    supported_strategies: Optional[Set[str]] = None,
) -> GuardResult:
    """Capability-gate a proposed CRD spec against the cluster's installed CRD OpenAPI schema."""
    if kind == "Middleware":
        allowed_keys = set(crd_spec_properties.keys()) if crd_spec_properties else DEFAULT_V3_MIDDLEWARE_SPEC_KEYS
        for key in spec_dict:
            if key not in allowed_keys:
                if key == "ipDenyList":
                    raise TraefikSchemaGatingError(
                        "Middleware field 'ipDenyList' is not a native Traefik v3 CRD field. "
                        "Use 'ip_allow_list' (ipAllowList) or configure a community denyip plugin via type='plugin'."
                    )
                raise TraefikSchemaGatingError(
                    f"Middleware spec field '{key}' is not supported by the installed Traefik Middleware CRD schema. "
                    f"Supported fields: {', '.join(sorted(allowed_keys))}."
                )

    elif kind == "MiddlewareTCP":
        allowed_keys = set(crd_spec_properties.keys()) if crd_spec_properties else DEFAULT_V3_MIDDLEWARE_TCP_SPEC_KEYS
        for key in spec_dict:
            if key not in allowed_keys:
                raise TraefikSchemaGatingError(
                    f"MiddlewareTCP spec field '{key}' is not supported by the installed CRD schema. "
                    f"Supported fields: {', '.join(sorted(allowed_keys))}."
                )

    # Check load-balancing strategy gating on IngressRoute / TraefikService
    allowed_strats = supported_strategies if supported_strategies is not None else DEFAULT_V3_LB_STRATEGIES
    if kind in ("IngressRoute", "TraefikService"):
        services_to_check: List[Dict[str, Any]] = []
        if kind == "IngressRoute":
            for r in spec_dict.get("routes") or []:
                services_to_check.extend(r.get("services") or [])
        else:
            services_to_check.extend((spec_dict.get("weighted") or {}).get("services") or [])
        for svc in services_to_check:
            strat = svc.get("strategy")
            if strat and strat not in allowed_strats:
                raise TraefikSchemaGatingError(
                    f"Load-balancing strategy '{strat}' is not supported by this cluster's Traefik CRD schema "
                    f"(supported: {', '.join(sorted(allowed_strats))})."
                )

    return GuardResult(
        guard="crd_schema",
        passed=True,
        severity="info",
        message=f"{kind} spec validated against Traefik v3 CRD schema.",
    )


def detect_middleware_chain_cycles(
    middleware_name: str,
    namespace: str,
    chain_refs: List[Dict[str, str]],
    existing_middlewares: Dict[Tuple[str, str], Dict[str, Any]],
) -> GuardResult:
    """Detect direct or transitive cycles in Middleware chain references."""
    start = (namespace, middleware_name)

    adj: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
    for (mw_ns, mw_n), mw_obj in existing_middlewares.items():
        spec = (mw_obj.get("spec") or {}).get("chain") or {}
        refs: List[Tuple[str, str]] = []
        for r in spec.get("middlewares") or []:
            if isinstance(r, dict) and r.get("name"):
                refs.append((r.get("namespace") or mw_ns, r["name"]))
        adj[(mw_ns, mw_n)] = refs

    adj[start] = [
        (r.get("namespace") or namespace, r["name"])
        for r in chain_refs
        if isinstance(r, dict) and r.get("name")
    ]

    visited: Set[Tuple[str, str]] = set()
    stack: List[Tuple[str, str]] = [start]

    def _dfs(node: Tuple[str, str], path: List[Tuple[str, str]]) -> None:
        for nxt in adj.get(node, []):
            if nxt == start or nxt in path:
                cycle_str = " -> ".join(f"{ns}/{n}" for ns, n in [*path, nxt])
                raise TraefikReferentialIntegrityError(
                    f"Circular middleware chain cycle detected: {cycle_str}. "
                    "Traefik rejects circular chain references."
                )
            if nxt not in visited:
                visited.add(nxt)
                _dfs(nxt, [*path, nxt])

    _dfs(start, [start])
    return GuardResult(
        guard="chain_cycle_check",
        passed=True,
        severity="info",
        message="No circular references detected in middleware chain.",
    )


def check_empty_backend_weights(
    weights: Dict[str, int],
    ready_endpoints_by_service: Dict[str, Optional[int]],
) -> GuardResult:
    """Block setting all weights to 0 or routing positive weight to a Service with 0 ready endpoints."""
    if not weights:
        raise TraefikWeightError("weights dictionary cannot be empty.")
    for svc_name, w in weights.items():
        if int(w) < 0:
            raise TraefikWeightError(f"Negative weight ({w}) is invalid for service '{svc_name}'.")
    total = sum(int(w) for w in weights.values())
    if total <= 0:
        raise TraefikWeightError(
            "ALL_WEIGHTS_ZERO: Total traffic weight across all backends cannot be 0. "
            "At least one backend must have weight > 0."
        )
    for svc_name, w in weights.items():
        if int(w) > 0:
            ready = ready_endpoints_by_service.get(svc_name)
            if ready is not None and ready <= 0:
                raise TraefikEmptyBackendError(
                    f"WEIGHT_TO_EMPTY_BACKEND: Cannot assign positive traffic weight ({w}) to backend "
                    f"Service '{svc_name}' because it has 0 ready endpoints."
                )
    return GuardResult(
        guard="empty_backend_weight",
        passed=True,
        severity="info",
        message="All positive-weight backends have ready endpoints and total weight > 0.",
    )


def compute_unified_diff(
    old_obj: Optional[Dict[str, Any]],
    new_obj: Dict[str, Any],
    resource_label: str = "manifest.yaml",
) -> Optional[str]:
    """Generate a unified diff between sanitized live object YAML and proposed YAML."""
    new_clean = sanitize_manifest(copy.deepcopy(new_obj))
    new_clean.get("metadata", {}).pop("resourceVersion", None)
    new_clean.get("metadata", {}).pop("uid", None)
    new_clean.get("metadata", {}).pop("creationTimestamp", None)
    new_clean.get("metadata", {}).pop("generation", None)
    new_yaml = pyyaml.dump(new_clean, default_flow_style=False, sort_keys=False)

    if not old_obj:
        old_lines: List[str] = []
    else:
        old_clean = sanitize_manifest(copy.deepcopy(old_obj))
        old_clean.get("metadata", {}).pop("resourceVersion", None)
        old_clean.get("metadata", {}).pop("uid", None)
        old_clean.get("metadata", {}).pop("creationTimestamp", None)
        old_clean.get("metadata", {}).pop("generation", None)
        old_yaml = pyyaml.dump(old_clean, default_flow_style=False, sort_keys=False)
        old_lines = old_yaml.splitlines(keepends=True)

    new_lines = new_yaml.splitlines(keepends=True)
    diff = "".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"live/{resource_label}" if old_obj else "/dev/null",
            tofile=f"proposed/{resource_label}",
        )
    )
    return diff or None


def stamp_managed_by_label(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure app.kubernetes.io/managed-by=talkops-traefik-mcp label is present."""
    meta = manifest.setdefault("metadata", {})
    labels = meta.setdefault("labels", {})
    labels.setdefault(MANAGED_BY_LABEL_KEY, MANAGED_BY_LABEL_VALUE)
    return manifest


def is_managed_by_mcp(obj: Optional[Dict[str, Any]]) -> bool:
    """Return True if the Kubernetes object carries app.kubernetes.io/managed-by=talkops-traefik-mcp."""
    if not isinstance(obj, dict):
        return False
    labels = (obj.get("metadata") or {}).get("labels") or {}
    return labels.get(MANAGED_BY_LABEL_KEY) == MANAGED_BY_LABEL_VALUE


def lint_middleware_ordering(chain_with_types: List[Tuple[str, str]]) -> List[str]:
    """Check middleware execution order and return advisory warnings when ordering is suboptimal."""
    warnings: List[str] = []
    types = [t.lower() for _, t in chain_with_types]

    # 1. redirectScheme / redirectRegex should be first
    for idx, (m_name, m_type) in enumerate(chain_with_types):
        if m_type in ("redirectscheme", "redirect_scheme", "redirectregex", "redirect_regex") and idx > 0:
            warnings.append(
                f"Middleware '{m_name}' ({m_type}) is at position {idx}; redirects should usually be placed first (position 0)."
            )

    # 2. ipAllowList should precede auth middlewares
    auth_indices = [
        i
        for i, t in enumerate(types)
        if t in ("basicauth", "basic_auth", "digestauth", "digest_auth", "forwardauth", "forward_auth")
    ]
    ip_indices = [i for i, t in enumerate(types) if t in ("ipallowlist", "ip_allow_list")]
    if auth_indices and ip_indices and min(ip_indices) > min(auth_indices):
        warnings.append(
            "ipAllowList appears after authentication middleware in the chain; place ipAllowList before auth to drop unauthorized IPs early."
        )

    # 3. rateLimit / inFlightReq should precede auth middlewares
    rl_indices = [
        i
        for i, t in enumerate(types)
        if t in ("ratelimit", "rate_limit", "inflightreq", "in_flight_req")
    ]
    if auth_indices and rl_indices and min(rl_indices) > min(auth_indices):
        warnings.append(
            "rateLimit/inFlightReq appears after authentication middleware; place rate limiting before auth to protect against unauthenticated traffic spikes."
        )

    return warnings


def check_crd_schema_gating(
    kind: str,
    spec: Dict[str, Any],
    installed_fields: Optional[Set[str]] = None,
    supported_strategies: Optional[Set[str]] = None,
) -> GuardResult:
    """Validate spec against installed CRD field set."""
    props = {k: {} for k in installed_fields} if installed_fields is not None else None
    return validate_against_crd_schema(
        kind=kind,
        spec_dict=spec,
        crd_spec_properties=props,
        supported_strategies=supported_strategies,
    )


check_traffic_weights_safety = check_empty_backend_weights
stamp_managed_metadata = stamp_managed_by_label

