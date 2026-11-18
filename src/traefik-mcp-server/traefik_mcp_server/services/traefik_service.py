"""Traefik v3 Kubernetes & Runtime execution service."""

from __future__ import annotations

import copy
import json
import socket
import ssl
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import parse_qsl, urlsplit
import httpx
import yaml as pyyaml
from kubernetes import client, config as k8s_config
from kubernetes.client.rest import ApiException

from traefik_mcp_server.config import ServerConfig
from traefik_mcp_server.exceptions.custom import (
    KubernetesNamespaceError,
    KubernetesOperationError,
    KubernetesResourceError,
    TraefikEmptyBackendError,
    TraefikMiddlewareError,
    TraefikMirroringError,
    TraefikOperationError,
    TraefikOwnershipError,
    TraefikReferentialIntegrityError,
    TraefikRouteConfigError,
    TraefikRouteNotFoundError,
    TraefikSchemaGatingError,
    TraefikServiceError,
    TraefikSSRFBlockedError,
    TraefikTLSError,
    TraefikWeightError,
)
from traefik_mcp_server.models.schemas import (
    ALL_DIAGNOSIS_CODES,
    BackendRef,
    DiagnosisCodeItem,
    ExecutionResult,
    GuardResult,
    HealthCheck,
    HttpRouteRule,
    MiddlewareRef,
    MirroringSpec,
    ProbeOptions,
    RequestTrace,
    RouteChanges,
    RouteDiagnosisReport,
    RouteMatch,
    RouteTLS,
    StickyCookie,
    TcpUdpRouteRule,
    TraceRequestSpec,
    WeightedExposeConfig,
)
from traefik_mcp_server.services.audit_checks import run_configuration_audit
from traefik_mcp_server.services.guards import (
    DEFAULT_V3_LB_STRATEGIES,
    DEFAULT_V3_MIDDLEWARE_SPEC_KEYS,
    DEFAULT_V3_MIDDLEWARE_TCP_SPEC_KEYS,
    check_empty_backend_weights,
    check_namespace_policy,
    check_ownership,
    compute_unified_diff,
    detect_middleware_chain_cycles,
    is_managed_by_mcp,
    lint_middleware_ordering,
    stamp_managed_by_label,
    validate_against_crd_schema,
)
from traefik_mcp_server.services.log_parser import analyze_log_lines
from traefik_mcp_server.services.prometheus_client import PrometheusClient
from traefik_mcp_server.services.rule_engine import (
    compile_route_match,
    compute_default_priority,
    evaluate_rule_against_request,
    extract_hosts_from_rule,
    lint_v3_rule,
)
from traefik_mcp_server.services.traefik_runtime_client import TraefikRuntimeClient
from traefik_mcp_server.services.x509_utils import check_host_coverage, parse_pem_certificate
from traefik_mcp_server.traefik_middleware_builders import (
    build_middleware_crd,
    build_middleware_spec_from_type,
    middleware_dict_to_yaml,
)
from traefik_mcp_server.utils.redaction import (
    redact_headers,
    redact_static_config,
    sanitize_manifest,
)

TRAEFIK_GROUP = "traefik.io"
TRAEFIK_VERSION = "v1alpha1"
TRAEFIK_API_VERSION = f"{TRAEFIK_GROUP}/{TRAEFIK_VERSION}"
TRAEFIK_INGRESS_ANNOTATION_PREFIX = "traefik.ingress.kubernetes.io/"

KIND_TO_CRD_META: Dict[str, Tuple[str, str, str]] = {
    "IngressRoute": (TRAEFIK_GROUP, TRAEFIK_VERSION, "ingressroutes"),
    "IngressRouteTCP": (TRAEFIK_GROUP, TRAEFIK_VERSION, "ingressroutetcps"),
    "IngressRouteUDP": (TRAEFIK_GROUP, TRAEFIK_VERSION, "ingressrouteudps"),
    "TraefikService": (TRAEFIK_GROUP, TRAEFIK_VERSION, "traefikservices"),
    "Middleware": (TRAEFIK_GROUP, TRAEFIK_VERSION, "middlewares"),
    "MiddlewareTCP": (TRAEFIK_GROUP, TRAEFIK_VERSION, "middlewaretcps"),
    "TLSOption": (TRAEFIK_GROUP, TRAEFIK_VERSION, "tlsoptions"),
    "TLSStore": (TRAEFIK_GROUP, TRAEFIK_VERSION, "tlsstores"),
    "ServersTransport": (TRAEFIK_GROUP, TRAEFIK_VERSION, "serverstransports"),
    "ServersTransportTCP": (TRAEFIK_GROUP, TRAEFIK_VERSION, "serverstransporttcps"),
    # Gateway API (read-only)
    "GatewayClass": ("gateway.networking.k8s.io", "v1", "gatewayclasses"),
    "Gateway": ("gateway.networking.k8s.io", "v1", "gateways"),
    "HTTPRoute": ("gateway.networking.k8s.io", "v1", "httproutes"),
    "GRPCRoute": ("gateway.networking.k8s.io", "v1", "grpcroutes"),
    "TLSRoute": ("gateway.networking.k8s.io", "v1alpha2", "tlsroutes"),
    "TCPRoute": ("gateway.networking.k8s.io", "v1alpha2", "tcproutes"),
    "ReferenceGrant": ("gateway.networking.k8s.io", "v1beta1", "referencegrants"),
    # Ownership & Certificate CRDs (read-only)
    "Rollout": ("argoproj.io", "v1alpha1", "rollouts"),
    "Certificate": ("cert-manager.io", "v1", "certificates"),
}

DELETABLE_TRAEFIK_KINDS: Tuple[str, ...] = (
    "IngressRoute",
    "IngressRouteTCP",
    "IngressRouteUDP",
    "TraefikService",
    "Middleware",
    "MiddlewareTCP",
    "TLSOption",
    "TLSStore",
    "ServersTransport",
    "ServersTransportTCP",
)

TLS_PROFILES: Dict[str, Dict[str, Any]] = {
    "intermediate": {
        "minVersion": "VersionTLS12",
        "cipherSuites": [
            "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",
            "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
            "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384",
            "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
            "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256",
            "TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256",
        ],
        "curvePreferences": ["X25519", "CurveP256", "CurveP384"],
        "sniStrict": True,
    },
    "modern": {
        "minVersion": "VersionTLS13",
        "curvePreferences": ["X25519", "CurveP256", "CurveP384"],
        "sniStrict": True,
    },
}


def yaml_dump(obj: Dict[str, Any]) -> str:
    """Serialize a manifest dictionary to clean YAML."""
    return pyyaml.dump(
        sanitize_manifest(obj),
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    ).rstrip() + "\n"


def _backend_ref_to_dict(b: Union[BackendRef, Dict[str, Any]]) -> Dict[str, Any]:
    obj = b if isinstance(b, BackendRef) else BackendRef.model_validate(b)
    out: Dict[str, Any] = {"name": obj.name}
    if obj.kind == "TraefikService":
        out["kind"] = "TraefikService"
    else:
        if obj.port is not None:
            out["port"] = obj.port
    if obj.namespace:
        out["namespace"] = obj.namespace
    if obj.weight is not None:
        out["weight"] = int(obj.weight)
    if obj.scheme:
        out["scheme"] = obj.scheme
    if obj.strategy:
        out["strategy"] = obj.strategy
    if obj.pass_host_header is not None:
        out["passHostHeader"] = bool(obj.pass_host_header)
    if obj.servers_transport:
        out["serversTransport"] = obj.servers_transport
    if obj.native_lb is not None:
        out["nativeLB"] = bool(obj.native_lb)
    if obj.sticky:
        cookie: Dict[str, Any] = {
            "secure": bool(obj.sticky.secure),
            "httpOnly": bool(obj.sticky.http_only),
        }
        if obj.sticky.name:
            cookie["name"] = obj.sticky.name
        if obj.sticky.same_site:
            cookie["sameSite"] = obj.sticky.same_site
        if obj.sticky.max_age is not None:
            cookie["maxAge"] = int(obj.sticky.max_age)
        if obj.sticky.path:
            cookie["path"] = obj.sticky.path
        out["sticky"] = {"cookie": cookie}
    if obj.health_check:
        # Traefik v3 defaults nativeLBByDefault=true on Kubernetes Services and rejects healthCheck
        # unless nativeLB=false (Pod EndpointSlice load-balancing).
        if obj.kind == "Service" and obj.native_lb is None:
            out["nativeLB"] = False
        hc: Dict[str, Any] = {
            "path": obj.health_check.path,
            "interval": obj.health_check.interval,
            "timeout": obj.health_check.timeout,
        }
        if obj.health_check.scheme:
            hc["scheme"] = obj.health_check.scheme
        if obj.health_check.port is not None:
            hc["port"] = int(obj.health_check.port)
        if obj.health_check.hostname:
            hc["hostname"] = obj.health_check.hostname
        if obj.health_check.headers:
            hc["headers"] = dict(obj.health_check.headers)
        if obj.health_check.mode:
            hc["mode"] = obj.health_check.mode
        if obj.health_check.follow_redirects is not None:
            hc["followRedirects"] = bool(obj.health_check.follow_redirects)
        out["healthCheck"] = hc
    if obj.flush_interval:
        out["responseForwarding"] = {"flushInterval": obj.flush_interval}
    return out


def _tls_to_dict(tls: Union[RouteTLS, Dict[str, Any], None], protocol: str = "http") -> Optional[Dict[str, Any]]:
    if not tls:
        return None
    obj = tls if isinstance(tls, RouteTLS) else RouteTLS.model_validate(tls)
    if obj.passthrough and protocol.lower() != "tcp":
        raise TraefikTLSError("TLS passthrough=True is only supported on TCP routes (IngressRouteTCP).")
    out: Dict[str, Any] = {}
    if obj.secret_name:
        out["secretName"] = obj.secret_name
    if obj.cert_resolver:
        out["certResolver"] = obj.cert_resolver
    if obj.domains:
        out["domains"] = list(obj.domains)
    if obj.options:
        out["options"] = dict(obj.options)
    if obj.store:
        out["store"] = dict(obj.store)
    if protocol.lower() == "tcp" and obj.passthrough:
        out["passthrough"] = True
    return out or None


class TraefikService:
    """Primary execution service for Traefik v3 Kubernetes CRDs, Runtime API, and Prometheus telemetry."""

    def __init__(
        self,
        config_obj: Optional[ServerConfig] = None,
        *,
        config: Optional[ServerConfig] = None,
        seed_objects: Optional[List[Dict[str, Any]]] = None,
        runtime_fixture: Optional[Dict[str, Any]] = None,
        prometheus_fixture: Optional[Dict[str, Any]] = None,
    ):
        self.config = config or config_obj or ServerConfig()
        self.k8s_core_v1: Optional[client.CoreV1Api] = None
        self.k8s_custom_api: Optional[client.CustomObjectsApi] = None
        self.k8s_networking_v1: Optional[client.NetworkingV1Api] = None
        self.k8s_apps_v1: Optional[client.AppsV1Api] = None
        self.k8s_apiext_v1: Optional[client.ApiextensionsV1Api] = None
        self._initialized = False
        self._lazy_init = False

        self.prometheus = PrometheusClient(
            prometheus_url=self.config.prometheus_url,
            fixture_data=prometheus_fixture,
        )
        self.runtime = TraefikRuntimeClient(
            traefik_api_url=self.config.traefik_api_url,
            traefik_namespace=self.config.traefik_namespace,
        )
        if runtime_fixture is not None:
            self.runtime.set_mock_runtime_data(rawdata=runtime_fixture)

        # In-memory store for offline dry-run and unit/integration testing
        self._memory_store: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        self._crd_schemas: Dict[str, Dict[str, Any]] = {}
        self._supported_strategies: Set[str] = set(DEFAULT_V3_LB_STRATEGIES)
        self._static_config_override: Optional[Dict[str, Any]] = None
        self._mock_logs: Dict[str, List[str]] = {"access": [], "controller": []}
        self._has_legacy_containo_crds: bool = False
        self._offline_seeded: bool = seed_objects is not None
        if seed_objects:
            self._seed(seed_objects)

    def _seed(self, objs: List[Dict[str, Any]]) -> None:
        """Seed a list of objects into the in-memory store."""
        for obj in objs:
            self.seed_object(obj)

    def set_installed_crd_fields(self, kind: str, fields: Set[str]) -> None:
        """Override the installed CRD OpenAPI spec properties for schema-gating tests."""
        self._crd_schemas[kind] = {f: {"type": "object"} for f in fields}

    def enable_lazy_init(self) -> None:
        """Enable lazy Kubernetes client initialization so startup never crashes without a cluster."""
        self._lazy_init = True

    def _try_init_k8s(self) -> bool:
        if self._offline_seeded:
            return False
        if self._initialized:
            return True
        try:
            kcfg = self.config.kubernetes
            if kcfg and kcfg.in_cluster:
                k8s_config.load_incluster_config()
            elif kcfg and (kcfg.kubeconfig or kcfg.context_name):
                k8s_config.load_kube_config(
                    config_file=kcfg.kubeconfig,
                    context=kcfg.context_name,
                )
            else:
                k8s_config.load_kube_config()

            self.k8s_core_v1 = client.CoreV1Api()
            self.k8s_custom_api = client.CustomObjectsApi()
            self.k8s_networking_v1 = client.NetworkingV1Api()
            self.k8s_apps_v1 = client.AppsV1Api()
            self.k8s_apiext_v1 = client.ApiextensionsV1Api()
            self.runtime.k8s_core_v1 = self.k8s_core_v1
            self._initialized = True
            return True
        except Exception:
            return False

    # ── In-Memory & Cluster Storage Helpers ────────────────────────────────────

    def seed_object(self, obj: Dict[str, Any]) -> None:
        """Seed an object into the in-memory store for testing and offline inspection."""
        kind = obj.get("kind", "")
        meta = obj.get("metadata") or {}
        name = meta.get("name", "")
        ns = meta.get("namespace") or "default"
        meta.setdefault("resourceVersion", "1")
        self._memory_store[(kind, ns, name)] = copy.deepcopy(obj)

    def get_object(self, kind: str, namespace: str, name: str) -> Optional[Dict[str, Any]]:
        """Fetch an object from the in-memory store or live Kubernetes API."""
        ns = namespace or "default"
        if (kind, ns, name) in self._memory_store:
            return copy.deepcopy(self._memory_store[(kind, ns, name)])

        if not self._try_init_k8s():
            return None

        try:
            if kind in KIND_TO_CRD_META and self.k8s_custom_api:
                grp, ver, plural = KIND_TO_CRD_META[kind]
                if kind == "GatewayClass":
                    return self.k8s_custom_api.get_cluster_custom_object(grp, ver, plural, name)
                return self.k8s_custom_api.get_namespaced_custom_object(grp, ver, ns, plural, name)
            if kind == "Ingress" and self.k8s_networking_v1:
                ing = self.k8s_networking_v1.read_namespaced_ingress(name=name, namespace=ns)
                return client.ApiClient().sanitize_for_serialization(ing)
            if kind == "Service" and self.k8s_core_v1:
                svc = self.k8s_core_v1.read_namespaced_service(name=name, namespace=ns)
                return client.ApiClient().sanitize_for_serialization(svc)
            if kind == "Secret" and self.k8s_core_v1:
                sec = self.k8s_core_v1.read_namespaced_secret(name=name, namespace=ns)
                return client.ApiClient().sanitize_for_serialization(sec)
        except Exception:
            return None
        return None

    def list_objects(self, kind: str, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List objects of a given kind from the in-memory store and/or cluster."""
        ns = None if namespace in (None, "", "_all", "*") else namespace
        results_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for (k, obj_ns, obj_name), obj in self._memory_store.items():
            if k == kind and (ns is None or obj_ns == ns):
                results_by_key[(obj_ns, obj_name)] = copy.deepcopy(obj)

        if self._try_init_k8s():
            try:
                if kind in KIND_TO_CRD_META and self.k8s_custom_api:
                    grp, ver, plural = KIND_TO_CRD_META[kind]
                    if kind == "GatewayClass":
                        resp = self.k8s_custom_api.list_cluster_custom_object(grp, ver, plural)
                    elif ns:
                        resp = self.k8s_custom_api.list_namespaced_custom_object(grp, ver, ns, plural)
                    else:
                        resp = self.k8s_custom_api.list_cluster_custom_object(grp, ver, plural)
                    for item in (resp or {}).get("items") or []:
                        m = item.get("metadata") or {}
                        item.setdefault("kind", kind)
                        results_by_key[(m.get("namespace") or "default", m.get("name", ""))] = item
                elif kind == "Ingress" and self.k8s_networking_v1:
                    resp = (
                        self.k8s_networking_v1.list_namespaced_ingress(namespace=ns)
                        if ns
                        else self.k8s_networking_v1.list_ingress_for_all_namespaces()
                    )
                    api_c = client.ApiClient()
                    for item in getattr(resp, "items", []) or []:
                        d = api_c.sanitize_for_serialization(item)
                        d["kind"] = "Ingress"
                        m = d.get("metadata") or {}
                        results_by_key[(m.get("namespace") or "default", m.get("name", ""))] = d
                elif kind == "Service" and self.k8s_core_v1:
                    resp = (
                        self.k8s_core_v1.list_namespaced_service(namespace=ns)
                        if ns
                        else self.k8s_core_v1.list_service_for_all_namespaces()
                    )
                    api_c = client.ApiClient()
                    for item in getattr(resp, "items", []) or []:
                        d = api_c.sanitize_for_serialization(item)
                        d["kind"] = "Service"
                        m = d.get("metadata") or {}
                        results_by_key[(m.get("namespace") or "default", m.get("name", ""))] = d
                elif kind == "Secret" and self.k8s_core_v1:
                    resp = (
                        self.k8s_core_v1.list_namespaced_secret(namespace=ns)
                        if ns
                        else self.k8s_core_v1.list_secret_for_all_namespaces()
                    )
                    api_c = client.ApiClient()
                    for item in getattr(resp, "items", []) or []:
                        d = api_c.sanitize_for_serialization(item)
                        d["kind"] = "Secret"
                        m = d.get("metadata") or {}
                        results_by_key[(m.get("namespace") or "default", m.get("name", ""))] = d
            except Exception:
                pass

        return list(results_by_key.values())

    def _get_ready_endpoint_count(self, namespace: str, service_name: str) -> Optional[int]:
        """Return count of ready endpoints for a Service if Endpoint/Service object is known."""
        ep_obj = self._memory_store.get(("Endpoints", namespace, service_name))
        if ep_obj is not None:
            ready = 0
            for subset in ep_obj.get("subsets") or []:
                ready += len(subset.get("addresses") or [])
            return ready
        if self._try_init_k8s() and self.k8s_core_v1:
            try:
                ep = self.k8s_core_v1.read_namespaced_endpoints(name=service_name, namespace=namespace)
                ready = 0
                for sub in getattr(ep, "subsets", None) or []:
                    ready += len(getattr(sub, "addresses", None) or [])
                return ready
            except Exception:
                return None
        return None

    def _apply_or_preview_object(
        self,
        body: Dict[str, Any],
        dry_run: bool = True,
        extra_guards: Optional[List[GuardResult]] = None,
        extra_warnings: Optional[List[str]] = None,
        summary_action: str = "Configured",
        extra_details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run the write-guard pipeline, compute unified diff, and execute server-side dry-run or SSA."""
        kind = body.get("kind", "IngressRoute")
        meta = body.setdefault("metadata", {})
        name = meta.get("name", "")
        namespace = meta.get("namespace", "default")

        guards: List[GuardResult] = [
            GuardResult(
                guard="write_access",
                passed=True,
                severity="info",
                message="Write access permitted.",
            )
        ]
        warnings: List[str] = list(extra_warnings or [])

        # 1. Namespace policy check
        ns_guard, is_protected_ns = check_namespace_policy(
            namespace=namespace,
            allowed_namespaces=self.config.allowed_namespaces,
            protected_namespaces=self.config.protected_namespaces,
        )
        guards.append(ns_guard)
        if is_protected_ns:
            warnings.append(ns_guard.message)

        # 2. Existing object & ownership check
        existing = self.get_object(kind, namespace, name)
        rollouts = self.list_objects("Rollout", namespace)
        own_guard, owner_type = check_ownership(
            target_kind=kind,
            target_name=name,
            namespace=namespace,
            existing_obj=existing,
            argo_rollouts=rollouts,
        )
        guards.append(own_guard)
        if not own_guard.passed:
            return ExecutionResult(
                status="refused",
                summary=own_guard.message,
                dry_run=dry_run,
                resource_uri=f"traefik://manifests/{kind}/{namespace}/{name}",
                warnings=warnings,
                guards=guards,
                details={"owner_type": owner_type, **(extra_details or {})},
            ).model_dump()
        if owner_type == "gitops":
            warnings.append(own_guard.message)

        # 3. CRD OpenAPI schema gating
        crd_props = self._crd_schemas.get(kind)
        schema_guard = validate_against_crd_schema(
            kind=kind,
            spec_dict=body.get("spec") or {},
            crd_spec_properties=crd_props,
            supported_strategies=self._supported_strategies,
        )
        guards.append(schema_guard)

        if extra_guards:
            guards.extend(extra_guards)

        # 4. Stamp managed-by label & clean explicit None annotation tombstones before diffing
        if kind in KIND_TO_CRD_META:
            stamp_managed_by_label(body)

        explicitly_removed_anns: List[str] = []
        raw_body_anns = (body.get("metadata") or {}).get("annotations")
        if isinstance(raw_body_anns, dict):
            explicitly_removed_anns = [k for k, v in raw_body_anns.items() if v is None]
            for ak in explicitly_removed_anns:
                raw_body_anns.pop(ak, None)
            if not raw_body_anns:
                (body.get("metadata") or {}).pop("annotations", None)

        diff_text = compute_unified_diff(existing, body, resource_label=f"{kind}/{namespace}/{name}.yaml")

        # 5. Server-side dry-run / SSA apply
        existing_rv_raw = str((existing or {}).get("metadata", {}).get("resourceVersion", "0"))
        new_rv = str(int(existing_rv_raw) + 1) if existing_rv_raw.isdigit() else "1"
        k8s_payload = copy.deepcopy(body)
        k8s_meta = k8s_payload.setdefault("metadata", {})
        for ro_field in ("managedFields", "uid", "creationTimestamp", "generation", "resourceVersion", "selfLink"):
            k8s_meta.pop(ro_field, None)

        # Ensure RFC 7396 JSON Merge Patch removes deleted top-level spec keys (e.g. ipWhiteList -> ipAllowList, tls.remove)
        # and explicit annotation removals.
        if existing:
            old_spec = existing.get("spec") or {}
            new_spec = k8s_payload.get("spec")
            if isinstance(old_spec, dict) and isinstance(new_spec, dict):
                for old_k in old_spec:
                    if old_k not in new_spec:
                        new_spec[old_k] = None
            old_anns = (existing.get("metadata") or {}).get("annotations") or {}
            body_anns = (body.get("metadata") or {}).get("annotations")
            if isinstance(old_anns, dict):
                k8s_anns = k8s_meta.get("annotations")
                if body_anns is not None and isinstance(body_anns, dict):
                    k8s_anns = k8s_meta.setdefault("annotations", {})
                    for old_ak in old_anns:
                        if not old_ak.startswith(("kubectl.kubernetes.io/", "argocd.argoproj.io/")) and old_ak not in body_anns:
                            k8s_anns[old_ak] = None
                elif kind == "IngressRoute" and "kubernetes.io/ingress.class" in old_anns and k8s_anns is None:
                    k8s_meta["annotations"] = {"kubernetes.io/ingress.class": None}
            if explicitly_removed_anns:
                k8s_anns = k8s_meta.setdefault("annotations", {})
                for rem_ak in explicitly_removed_anns:
                    k8s_anns[rem_ak] = None

        if self._try_init_k8s():
            dry_run_param = "All" if dry_run else None
            if kind in KIND_TO_CRD_META and self.k8s_custom_api:
                grp, ver, plural = KIND_TO_CRD_META[kind]
                try:
                    if existing:
                        k8s_resp = self.k8s_custom_api.patch_namespaced_custom_object(
                            group=grp,
                            version=ver,
                            namespace=namespace,
                            plural=plural,
                            name=name,
                            body=k8s_payload,
                            dry_run=dry_run_param,
                            field_manager=self.config.field_manager,
                        )
                    else:
                        k8s_resp = self.k8s_custom_api.create_namespaced_custom_object(
                            group=grp,
                            version=ver,
                            namespace=namespace,
                            plural=plural,
                            body=k8s_payload,
                            dry_run=dry_run_param,
                            field_manager=self.config.field_manager,
                        )
                    if isinstance(k8s_resp, dict):
                        live_rv = (k8s_resp.get("metadata") or {}).get("resourceVersion")
                        if live_rv:
                            new_rv = str(live_rv)
                except ApiException:
                    raise
                except Exception:
                    pass
            elif kind == "Ingress" and self.k8s_networking_v1 and existing:
                try:
                    self.k8s_networking_v1.patch_namespaced_ingress(
                        name=name,
                        namespace=namespace,
                        body=k8s_payload,
                        dry_run=dry_run_param,
                        field_manager=self.config.field_manager,
                    )
                except ApiException:
                    raise
                except Exception:
                    pass
            elif kind == "Service" and self.k8s_core_v1 and existing:
                try:
                    self.k8s_core_v1.patch_namespaced_service(
                        name=name,
                        namespace=namespace,
                        body=k8s_payload,
                        dry_run=dry_run_param,
                        field_manager=self.config.field_manager,
                    )
                except ApiException:
                    raise
                except Exception:
                    pass

        body_to_store = copy.deepcopy(k8s_payload)
        body_to_store["metadata"]["resourceVersion"] = new_rv

        guards.append(
            GuardResult(
                guard="server_dry_run",
                passed=True,
                severity="info",
                message="Kubernetes server-side dry-run validation succeeded.",
            )
        )

        if not dry_run:
            self._memory_store[(kind, namespace, name)] = body_to_store

        manifest_yaml = yaml_dump(body_to_store if not dry_run else body)
        mode_prefix = "[DRY-RUN PREVIEW]" if dry_run else "[APPLIED]"
        current_rv = (existing or {}).get("metadata", {}).get("resourceVersion", "1")
        result = ExecutionResult(
            status="preview" if dry_run else "success",
            summary=f"{mode_prefix} {summary_action} {kind} '{namespace}/{name}'.",
            dry_run=dry_run,
            manifest=manifest_yaml,
            diff=diff_text,
            resource_uri=f"traefik://manifests/{kind}/{namespace}/{name}",
            warnings=warnings,
            guards=guards,
            details={
                "kind": kind,
                "name": name,
                "namespace": namespace,
                "resource_version": current_rv if dry_run else new_rv,
                **(extra_details or {}),
            },
        )
        return result.model_dump()

    # ── T1: traefik_configure_http_route ───────────────────────────────────────

    async def configure_http_route(
        self,
        name: str,
        namespace: str = "default",
        rules: Optional[List[Union[HttpRouteRule, Dict[str, Any]]]] = None,
        entry_points: Optional[List[str]] = None,
        tls: Optional[Union[RouteTLS, Dict[str, Any]]] = None,
        ingress_class: Optional[str] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        if not rules:
            raise TraefikRouteConfigError("rules must contain at least one HttpRouteRule.")

        eps = [e.strip() for e in (entry_points or ["websecure"]) if e and e.strip()]
        static_cfg = self.get_static_config()
        known_eps = set((static_cfg.get("entryPoints") or {}).keys())
        warnings: List[str] = []
        if known_eps:
            for ep in eps:
                if ep not in known_eps:
                    warnings.append(
                        f"EntryPoint '{ep}' is not declared in Traefik static config ({sorted(known_eps)})."
                    )

        allow_cross_ns = bool(
            ((static_cfg.get("providers") or {}).get("kubernetesCRD") or {}).get("allowCrossNamespace", False)
        )

        compiled_routes: List[Dict[str, Any]] = []
        all_hosts: List[str] = []

        for rule_in in rules:
            rule_obj = rule_in if isinstance(rule_in, HttpRouteRule) else HttpRouteRule.model_validate(rule_in)
            match_expr = compile_route_match(rule_obj.match, protocol="http")
            all_hosts.extend(extract_hosts_from_rule(match_expr))

            route_entry: Dict[str, Any] = {
                "match": match_expr,
                "kind": "Rule",
                "services": [_backend_ref_to_dict(s) for s in rule_obj.services],
            }
            if rule_obj.priority is not None:
                route_entry["priority"] = int(rule_obj.priority)
            if rule_obj.middlewares:
                mw_list: List[Dict[str, str]] = []
                for mw in rule_obj.middlewares:
                    if mw.namespace and mw.namespace != namespace and not allow_cross_ns:
                        raise TraefikReferentialIntegrityError(
                            f"Cross-namespace Middleware reference '{mw.namespace}/{mw.name}' is blocked because "
                            "providers.kubernetesCRD.allowCrossNamespace=false."
                        )
                    mw_dict = {"name": mw.name}
                    if mw.namespace:
                        mw_dict["namespace"] = mw.namespace
                    mw_list.append(mw_dict)
                route_entry["middlewares"] = mw_list
            if rule_obj.observability:
                route_entry["observability"] = dict(rule_obj.observability)

            # Check backend readiness warnings
            for s in rule_obj.services:
                ready = self._get_ready_endpoint_count(s.namespace or namespace, s.name)
                if ready is not None and ready == 0:
                    warnings.append(f"Backend Service '{s.name}' currently has 0 ready endpoints.")

            compiled_routes.append(route_entry)

        metadata: Dict[str, Any] = {"name": name, "namespace": namespace}
        if ingress_class:
            metadata["annotations"] = {"kubernetes.io/ingress.class": ingress_class}

        spec: Dict[str, Any] = {
            "entryPoints": eps,
            "routes": compiled_routes,
        }
        tls_dict = _tls_to_dict(tls, protocol="http")
        if tls_dict:
            spec["tls"] = tls_dict
            # Check TLS secret SAN coverage if secret exists in store
            sec_name = tls_dict.get("secretName")
            if sec_name:
                sec_obj = self.get_object("Secret", namespace, sec_name)
                if sec_obj and (sec_obj.get("data") or {}).get("tls.crt"):
                    try:
                        cert_meta = parse_pem_certificate(sec_obj["data"]["tls.crt"])
                        ok_cov, _, uncovered = check_host_coverage(all_hosts, cert_meta.get("sans") or [])
                        if not ok_cov:
                            warnings.append(
                                f"TLS Secret '{sec_name}' SANs {cert_meta.get('sans')} do not cover route host(s): {uncovered}."
                            )
                        if cert_meta.get("expired"):
                            warnings.append(f"TLS Secret '{sec_name}' certificate has expired ({cert_meta.get('not_after')}).")
                    except Exception:
                        pass

        body = {
            "apiVersion": TRAEFIK_API_VERSION,
            "kind": "IngressRoute",
            "metadata": metadata,
            "spec": spec,
        }
        return self._apply_or_preview_object(
            body=body,
            dry_run=dry_run,
            extra_warnings=warnings,
            summary_action="Configured HTTP",
            extra_details={"hosts": list(dict.fromkeys(all_hosts)), "rule_count": len(compiled_routes)},
        )

    # ── T2: traefik_configure_weighted_service ─────────────────────────────────

    async def configure_weighted_service(
        self,
        name: str,
        namespace: str = "default",
        backends: Optional[List[Union[BackendRef, Dict[str, Any]]]] = None,
        sticky: Optional[Union[StickyCookie, Dict[str, Any]]] = None,
        health_check: Optional[Union[bool, HealthCheck, Dict[str, Any]]] = False,
        expose: Optional[Union[WeightedExposeConfig, Dict[str, Any]]] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        if not backends or len(backends) < 2:
            raise TraefikWeightError("weighted TraefikService requires at least 2 backends with weights.")

        default_hc: Optional[HealthCheck] = None
        if isinstance(health_check, HealthCheck):
            default_hc = health_check
        elif isinstance(health_check, dict):
            default_hc = HealthCheck.model_validate(health_check)
        elif health_check is True:
            default_hc = HealthCheck(path="/", interval="10s", timeout="3s")

        parsed_backends = [b if isinstance(b, BackendRef) else BackendRef.model_validate(b) for b in backends]
        weights_map: Dict[str, int] = {}
        ready_map: Dict[str, Optional[int]] = {}
        svc_items: List[Dict[str, Any]] = []
        ts_annotations: Dict[str, str] = {}
        wrr_warnings: List[str] = []

        for b in parsed_backends:
            if b.weight is None:
                raise TraefikWeightError(f"Backend '{b.name}' is missing required 'weight'.")
            if default_hc is not None and b.health_check is None:
                b = b.model_copy(update={"health_check": default_hc})
            if b.health_check is not None and b.kind == "Service" and self._try_init_k8s():
                svc_obj = self.get_object("Service", b.namespace or namespace, b.name)
                svc_type = ((svc_obj or {}).get("spec") or {}).get("type", "ClusterIP") if svc_obj else None
                if svc_obj is not None and svc_type != "ExternalName":
                    # Traefik v3 kubernetescrd rejects spec.weighted.services[].healthCheck on ClusterIP/NodePort/LB
                    # Services ("healthCheck allowed only for ExternalName services") and enforces pod health via
                    # nativeLB=false + EndpointSlice readiness probes.
                    ts_annotations["talkops.io/health-check"] = json.dumps(
                        b.health_check.model_dump(exclude_none=True), separators=(",", ":")
                    )
                    b = b.model_copy(
                        update={
                            "health_check": None,
                            "native_lb": False if b.native_lb is None else b.native_lb,
                        }
                    )
                    if not wrr_warnings:
                        wrr_warnings.append(
                            "Traefik v3 kubernetesCRD restricts inline service.healthCheck to ExternalName Services; "
                            "set nativeLB=false for per-pod EndpointSlice failover and recorded healthCheck policy in "
                            "metadata.annotations['talkops.io/health-check']."
                        )
            weights_map[b.name] = int(b.weight)
            ready_map[b.name] = self._get_ready_endpoint_count(b.namespace or namespace, b.name)
            svc_items.append(_backend_ref_to_dict(b))

        weight_guard = check_empty_backend_weights(weights_map, ready_map)

        weighted_block: Dict[str, Any] = {"services": svc_items}
        if sticky:
            st_obj = sticky if isinstance(sticky, StickyCookie) else StickyCookie.model_validate(sticky)
            cookie_cfg: Dict[str, Any] = {
                "secure": bool(st_obj.secure),
                "httpOnly": bool(st_obj.http_only),
            }
            if st_obj.name:
                cookie_cfg["name"] = st_obj.name
            if st_obj.same_site:
                cookie_cfg["sameSite"] = st_obj.same_site
            if st_obj.max_age is not None:
                cookie_cfg["maxAge"] = int(st_obj.max_age)
            weighted_block["sticky"] = {"cookie": cookie_cfg}

        ts_meta: Dict[str, Any] = {"name": name, "namespace": namespace}
        if ts_annotations:
            ts_meta["annotations"] = ts_annotations
        ts_body = {
            "apiVersion": TRAEFIK_API_VERSION,
            "kind": "TraefikService",
            "metadata": ts_meta,
            "spec": {"weighted": weighted_block},
        }

        ts_res = self._apply_or_preview_object(
            body=ts_body,
            dry_run=dry_run,
            extra_guards=[weight_guard],
            extra_warnings=wrr_warnings,
            summary_action="Configured weighted",
            extra_details={"weights": weights_map},
        )
        if ts_res["status"] == "refused" or not expose:
            return ts_res

        exp_obj = expose if isinstance(expose, WeightedExposeConfig) else WeightedExposeConfig.model_validate(expose)
        route_name = exp_obj.route_name or (name[:-4] if name.endswith("-wrr") else f"{name}-route")
        ir_res = await self.configure_http_route(
            name=route_name,
            namespace=namespace,
            rules=[
                HttpRouteRule(
                    match=exp_obj.match,
                    middlewares=exp_obj.middlewares,
                    services=[BackendRef(name=name, kind="TraefikService")],
                )
            ],
            entry_points=exp_obj.entry_points,
            tls=exp_obj.tls,
            dry_run=dry_run,
        )

        combined_manifest = f"{ts_res['manifest']}---\n{ir_res['manifest']}"
        ts_res["manifest"] = combined_manifest
        ts_res["summary"] = (
            f"{'[DRY-RUN PREVIEW]' if dry_run else '[APPLIED]'} Configured weighted TraefikService "
            f"'{namespace}/{name}' and exposing IngressRoute '{namespace}/{route_name}'."
        )
        ts_res["details"]["exposed_route"] = route_name
        ts_res["warnings"] = list(dict.fromkeys([*ts_res.get("warnings", []), *ir_res.get("warnings", [])]))
        return ts_res

    # ── T3: traefik_set_traffic_weights ────────────────────────────────────────

    async def set_traffic_weights(
        self,
        name: str,
        namespace: str = "default",
        weights: Optional[Dict[str, int]] = None,
        expected_resource_version: Optional[str] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        if not weights:
            raise TraefikWeightError("weights dictionary cannot be empty.")

        existing = self.get_object("TraefikService", namespace, name)
        if not existing and not name.endswith("-wrr"):
            existing = self.get_object("TraefikService", namespace, f"{name}-wrr")
            if existing:
                name = f"{name}-wrr"
        if not existing:
            raise TraefikRouteNotFoundError(
                f"TraefikService '{name}' not found in namespace '{namespace}'"
            )

        current_rv = str((existing.get("metadata") or {}).get("resourceVersion", "1"))
        if expected_resource_version and str(expected_resource_version) != current_rv:
            raise ApiException(
                status=409,
                reason=(
                    f"Optimistic concurrency conflict: expected resourceVersion='{expected_resource_version}', "
                    f"but live object has resourceVersion='{current_rv}'"
                ),
            )

        wrr_services = ((existing.get("spec") or {}).get("weighted") or {}).get("services") or []
        if not wrr_services:
            raise TraefikServiceError(
                f"TraefikService '{name}' is not a weighted service (no spec.weighted.services found)"
            )

        existing_names = {s.get("name") for s in wrr_services if s.get("name")}
        unknown = set(weights.keys()) - existing_names
        if unknown:
            raise TraefikWeightError(
                f"Unknown backend service(s) {sorted(unknown)} on TraefikService '{name}'. "
                f"Configured backends are: {sorted(existing_names)}"
            )

        before_weights = {s["name"]: int(s.get("weight", 0)) for s in wrr_services if s.get("name")}
        after_weights = dict(before_weights)
        for k, v in weights.items():
            after_weights[k] = int(v)

        ready_map = {
            svc_name: self._get_ready_endpoint_count(namespace, svc_name)
            for svc_name in after_weights
        }
        weight_guard = check_empty_backend_weights(after_weights, ready_map)

        updated_obj = copy.deepcopy(existing)
        for s in updated_obj["spec"]["weighted"]["services"]:
            s_name = s.get("name")
            if s_name in after_weights:
                s["weight"] = after_weights[s_name]

        return self._apply_or_preview_object(
            body=updated_obj,
            dry_run=dry_run,
            extra_guards=[weight_guard],
            summary_action=f"Shifted weights on ({before_weights} -> {after_weights})",
            extra_details={
                "before_weights": before_weights,
                "after_weights": after_weights,
            },
        )

    # ── T4: traefik_configure_traffic_mirroring ────────────────────────────────

    async def configure_traffic_mirroring(
        self,
        name: str,
        namespace: str = "default",
        action: str = "enable",
        spec: Optional[Union[MirroringSpec, Dict[str, Any]]] = None,
        route_name: Optional[str] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        act = action.strip().lower()
        mirror_ts_name = name if name.endswith("-mirror") else name

        if act == "disable":
            existing = self.get_object("TraefikService", namespace, mirror_ts_name)
            if not existing and not mirror_ts_name.endswith("-mirror"):
                existing = self.get_object("TraefikService", namespace, f"{name}-mirror")
                if existing:
                    mirror_ts_name = f"{name}-mirror"
            if not existing:
                raise TraefikRouteNotFoundError(
                    f"Mirroring TraefikService '{mirror_ts_name}' not found in namespace '{namespace}'"
                )
            mir_block_existing = (existing.get("spec") or {}).get("mirroring") or {}
            main_svc = mir_block_existing.get("name") or mir_block_existing.get("service")
            main_port = mir_block_existing.get("port", 80)

            if not dry_run:
                if route_name and main_svc:
                    ir = self.get_object("IngressRoute", namespace, route_name)
                    if ir:
                        ir_copy = copy.deepcopy(ir)
                        for r in (ir_copy.get("spec") or {}).get("routes") or []:
                            r["services"] = [{"name": main_svc, "port": main_port}]
                        self._apply_or_preview_object(body=ir_copy, dry_run=False, summary_action="Restored primary backend on")
                self._memory_store.pop(("TraefikService", namespace, mirror_ts_name), None)
                if self._try_init_k8s() and self.k8s_custom_api:
                    grp, ver, plural = KIND_TO_CRD_META["TraefikService"]
                    try:
                        self.k8s_custom_api.delete_namespaced_custom_object(grp, ver, namespace, plural, mirror_ts_name)
                    except Exception:
                        pass

            return ExecutionResult(
                status="preview" if dry_run else "success",
                summary=f"{'[DRY-RUN PREVIEW]' if dry_run else '[APPLIED]'} Disabled traffic mirroring on '{namespace}/{mirror_ts_name}'.",
                dry_run=dry_run,
                resource_uri=f"traefik://routes/{namespace}",
                details={"name": mirror_ts_name, "namespace": namespace, "restored_service": main_svc},
            ).model_dump()

        if act not in ("enable", "update"):
            raise TraefikMirroringError(f"Unsupported mirroring action '{action}'. Use 'enable', 'update', or 'disable'.")
        if not spec:
            raise TraefikMirroringError(f"Action '{act}' requires 'spec' with 'main' and 'mirrors'.")

        spec_obj = spec if isinstance(spec, MirroringSpec) else MirroringSpec.model_validate(spec)
        mirrors_list: List[Dict[str, Any]] = []
        for m in spec_obj.mirrors:
            entry: Dict[str, Any] = {
                "name": m.name,
                "port": m.port,
                "percent": int(m.percent),
            }
            if m.namespace:
                entry["namespace"] = m.namespace
            mirrors_list.append(entry)

        mirror_block: Dict[str, Any] = {
            "name": spec_obj.main.name,
            "port": spec_obj.main.port or 80,
            "mirrorBody": bool(spec_obj.mirror_body),
            "mirrors": mirrors_list,
        }
        if spec_obj.max_body_size is not None:
            mirror_block["maxBodySize"] = int(spec_obj.max_body_size)

        warnings = [
            "Traffic mirroring duplicates incoming requests to shadow backend(s). Verify shadow backends are idempotent or isolated from production databases."
        ]

        ts_body = {
            "apiVersion": TRAEFIK_API_VERSION,
            "kind": "TraefikService",
            "metadata": {"name": mirror_ts_name, "namespace": namespace},
            "spec": {"mirroring": mirror_block},
        }

        res = self._apply_or_preview_object(
            body=ts_body,
            dry_run=dry_run,
            extra_warnings=warnings,
            summary_action=f"{act.capitalize()}d traffic mirroring",
            extra_details={"main": spec_obj.main.name, "mirrors": mirrors_list},
        )
        if route_name and res["status"] != "refused":
            ir = self.get_object("IngressRoute", namespace, route_name)
            if ir:
                ir_copy = copy.deepcopy(ir)
                for r in (ir_copy.get("spec") or {}).get("routes") or []:
                    r["services"] = [{"name": mirror_ts_name, "kind": "TraefikService"}]
                ir_res = self._apply_or_preview_object(
                    body=ir_copy,
                    dry_run=dry_run,
                    summary_action="Repointed IngressRoute to mirroring service",
                )
                res["manifest"] = f"{res['manifest']}---\n{ir_res['manifest']}"
                res["details"]["repointed_route"] = route_name
        return res

    # ── T5: traefik_update_route ───────────────────────────────────────────────

    async def update_route(
        self,
        route_kind: str,
        name: str,
        namespace: str = "default",
        changes: Optional[Union[RouteChanges, Dict[str, Any]]] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        if not changes:
            raise TraefikRouteConfigError("changes must specify at least one modification.")
        chg = changes if isinstance(changes, RouteChanges) else RouteChanges.model_validate(changes)
        has_any = any(
            getattr(chg, f) is not None
            for f in ("middlewares", "tls", "entry_points", "priority", "match", "ingress_class", "annotations", "backend")
        )
        if not has_any:
            raise TraefikRouteConfigError("RouteChanges must specify at least one field to update.")

        existing = self.get_object(route_kind, namespace, name)
        if not existing:
            raise TraefikRouteNotFoundError(
                f"{route_kind} '{name}' not found in namespace '{namespace}'"
            )

        updated = copy.deepcopy(existing)
        warnings: List[str] = []
        ordered_chain: List[Dict[str, str]] = []
        extra_manifests: List[str] = []

        upd_meta = updated.setdefault("metadata", {})
        upd_anns = upd_meta.setdefault("annotations", {})
        if chg.annotations:
            for ak, av in chg.annotations.items():
                if av is None:
                    upd_anns[ak] = None
                else:
                    upd_anns[ak] = str(av)
        if chg.ingress_class is not None:
            ic_val = chg.ingress_class.strip()
            if route_kind == "Ingress":
                if ic_val:
                    updated.setdefault("spec", {})["ingressClassName"] = ic_val
                else:
                    (updated.get("spec") or {}).pop("ingressClassName", None)
                    upd_anns["kubernetes.io/ingress.class"] = None
            else:
                if ic_val:
                    upd_anns["kubernetes.io/ingress.class"] = ic_val
                else:
                    upd_anns["kubernetes.io/ingress.class"] = None

        # Case 1: Standard Kubernetes Ingress (Traefik router annotations + backing Service annotations)
        if route_kind == "Ingress":
            own_guard, owner_type = check_ownership("Ingress", name, namespace, existing_obj=existing)
            if not own_guard.passed:
                return ExecutionResult(
                    status="refused",
                    summary=own_guard.message,
                    dry_run=dry_run,
                    resource_uri=f"traefik://manifests/Ingress/{namespace}/{name}",
                    guards=[own_guard],
                    details={"owner_type": owner_type},
                ).model_dump()

            meta = updated.setdefault("metadata", {})
            anns = meta.setdefault("annotations", {})

            if chg.entry_points is not None:
                anns[f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}router.entrypoints"] = ",".join(chg.entry_points)
            if chg.priority is not None:
                anns[f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}router.priority"] = str(chg.priority)
            if chg.tls is not None:
                if chg.tls.get("remove"):
                    anns.pop(f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}router.tls", None)
                    anns.pop(f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}router.tls.certresolver", None)
                    anns.pop(f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}router.tls.options", None)
                else:
                    tls_set = chg.tls.get("set") or chg.tls
                    anns[f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}router.tls"] = "true"
                    if tls_set.get("cert_resolver"):
                        anns[f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}router.tls.certresolver"] = str(tls_set["cert_resolver"])
                    if tls_set.get("options") and isinstance(tls_set["options"], dict):
                        opt_ns = tls_set["options"].get("namespace") or namespace
                        opt_n = tls_set["options"].get("name")
                        anns[f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}router.tls.options"] = f"{opt_ns}-{opt_n}@kubernetescrd"

            if chg.middlewares is not None:
                raw_existing = anns.get(f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}router.middlewares", "")
                cur_tokens = [t.strip() for t in raw_existing.split(",") if t.strip()]
                new_tokens = [
                    f"{(r.namespace or namespace)}-{r.name}@kubernetescrd"
                    for r in chg.middlewares.refs
                ]
                if chg.middlewares.action == "replace":
                    cur_tokens = new_tokens
                elif chg.middlewares.action == "detach":
                    remove_set = set(new_tokens)
                    cur_tokens = [t for t in cur_tokens if t not in remove_set]
                else:  # attach
                    pos = chg.middlewares.position
                    to_add = [t for t in new_tokens if t not in cur_tokens]
                    if pos == "prepend":
                        cur_tokens = to_add + cur_tokens
                    elif isinstance(pos, int):
                        cur_tokens = cur_tokens[:pos] + to_add + cur_tokens[pos:]
                    else:
                        cur_tokens = cur_tokens + to_add
                if cur_tokens:
                    anns[f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}router.middlewares"] = ",".join(cur_tokens)
                else:
                    anns.pop(f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}router.middlewares", None)
                ordered_chain = [{"ref": t} for t in cur_tokens]

            # Backend options on Ingress -> written to backing Kubernetes Service annotations
            if chg.backend is not None:
                svc_name = chg.backend.service_name
                if not svc_name:
                    rules_list = (updated.get("spec") or {}).get("rules") or []
                    for rl in rules_list:
                        paths = ((rl.get("http") or {}).get("paths")) or []
                        if paths:
                            svc_name = (((paths[0].get("backend") or {}).get("service")) or {}).get("name")
                            break
                if svc_name:
                    svc_obj = self.get_object("Service", namespace, svc_name) or {
                        "apiVersion": "v1",
                        "kind": "Service",
                        "metadata": {"name": svc_name, "namespace": namespace},
                        "spec": {"ports": [{"port": 80}]},
                    }
                    svc_anns = svc_obj.setdefault("metadata", {}).setdefault("annotations", {})
                    if chg.backend.sticky:
                        svc_anns[f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}service.sticky.cookie"] = "true"
                        if chg.backend.sticky.name:
                            svc_anns[f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}service.sticky.cookie.name"] = chg.backend.sticky.name
                        svc_anns[f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}service.sticky.cookie.secure"] = str(chg.backend.sticky.secure).lower()
                        svc_anns[f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}service.sticky.cookie.httponly"] = str(chg.backend.sticky.http_only).lower()
                        if chg.backend.sticky.same_site:
                            svc_anns[f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}service.sticky.cookie.samesite"] = chg.backend.sticky.same_site
                    if chg.backend.servers_transport:
                        svc_anns[f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}service.serverstransport"] = (
                            f"{namespace}-{chg.backend.servers_transport}@kubernetescrd"
                        )
                    if chg.backend.pass_host_header is not None:
                        svc_anns[f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}service.passhostheader"] = str(chg.backend.pass_host_header).lower()
                    if chg.backend.native_lb is not None:
                        svc_anns[f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}service.nativelb"] = str(chg.backend.native_lb).lower()
                    if not dry_run:
                        self._apply_or_preview_object(body=svc_obj, dry_run=False, summary_action="Updated Service")
                    extra_manifests.append(yaml_dump(svc_obj))

            res = self._apply_or_preview_object(
                body=updated,
                dry_run=dry_run,
                extra_warnings=warnings,
                summary_action="Updated Ingress",
                extra_details={"middleware_chain": ordered_chain},
            )
            if extra_manifests:
                res["manifest"] = "\n---\n".join([res["manifest"].rstrip(), *[m.rstrip() for m in extra_manifests]]) + "\n"
            return res

        # Case 2: IngressRoute / IngressRouteTCP
        spec = updated.setdefault("spec", {})
        if chg.entry_points is not None:
            spec["entryPoints"] = list(chg.entry_points)

        if chg.tls is not None:
            if chg.tls.get("remove"):
                spec.pop("tls", None)
            else:
                tls_payload = chg.tls.get("set") or chg.tls
                tls_dict = _tls_to_dict(
                    tls_payload,
                    protocol="tcp" if route_kind == "IngressRouteTCP" else "http",
                )
                if tls_dict:
                    if chg.tls.get("replace"):
                        spec["tls"] = tls_dict
                    else:
                        spec["tls"] = {**(spec.get("tls") or {}), **tls_dict}

        routes_list = spec.get("routes") or []
        target_indices = (
            [chg.rule_index]
            if chg.rule_index is not None and 0 <= chg.rule_index < len(routes_list)
            else list(range(len(routes_list)))
        )

        for idx in target_indices:
            rule_dict = routes_list[idx]
            if chg.priority is not None:
                rule_dict["priority"] = int(chg.priority)
            if chg.match is not None:
                v_match = validate_rule_syntax(chg.match, protocol="tcp" if route_kind == "IngressRouteTCP" else "http")
                if not v_match.get("valid"):
                    raise TraefikRouteConfigError(
                        f"Invalid Traefik v3 match rule '{chg.match}': {'; '.join(v_match.get('errors') or [])}"
                    )
                rule_dict["match"] = chg.match

            if chg.middlewares is not None:
                current_mws: List[Dict[str, str]] = [
                    dict(m) for m in (rule_dict.get("middlewares") or []) if isinstance(m, dict)
                ]
                incoming: List[Dict[str, str]] = []
                for r in chg.middlewares.refs:
                    d = {"name": r.name}
                    if r.namespace:
                        d["namespace"] = r.namespace
                    incoming.append(d)

                if chg.middlewares.action == "replace":
                    current_mws = incoming
                elif chg.middlewares.action == "detach":
                    detach_names = {(m.get("namespace") or namespace, m["name"]) for m in incoming}
                    current_mws = [
                        m
                        for m in current_mws
                        if (m.get("namespace") or namespace, m.get("name")) not in detach_names
                    ]
                else:  # attach (idempotent)
                    existing_keys = {(m.get("namespace") or namespace, m.get("name")) for m in current_mws}
                    to_insert = [
                        m for m in incoming if (m.get("namespace") or namespace, m["name"]) not in existing_keys
                    ]
                    pos = chg.middlewares.position
                    if pos == "prepend":
                        current_mws = to_insert + current_mws
                    elif isinstance(pos, int):
                        current_mws = current_mws[:pos] + to_insert + current_mws[pos:]
                    else:
                        current_mws = current_mws + to_insert

                if current_mws:
                    rule_dict["middlewares"] = current_mws
                else:
                    rule_dict.pop("middlewares", None)
                ordered_chain = current_mws

            if chg.backend is not None:
                svcs = rule_dict.get("services") or []
                for s in svcs:
                    if chg.backend.service_name and s.get("name") != chg.backend.service_name:
                        continue
                    if chg.backend.sticky:
                        cookie_d: Dict[str, Any] = {
                            "secure": bool(chg.backend.sticky.secure),
                            "httpOnly": bool(chg.backend.sticky.http_only),
                        }
                        if chg.backend.sticky.name:
                            cookie_d["name"] = chg.backend.sticky.name
                        if chg.backend.sticky.same_site:
                            cookie_d["sameSite"] = chg.backend.sticky.same_site
                        if chg.backend.sticky.max_age is not None:
                            cookie_d["maxAge"] = int(chg.backend.sticky.max_age)
                        s["sticky"] = {"cookie": cookie_d}
                    if chg.backend.health_check:
                        if chg.backend.native_lb is None and s.get("kind", "Service") == "Service" and "nativeLB" not in s:
                            s["nativeLB"] = False
                        s["healthCheck"] = {
                            "path": chg.backend.health_check.path,
                            "interval": chg.backend.health_check.interval,
                            "timeout": chg.backend.health_check.timeout,
                        }
                    if chg.backend.strategy:
                        s["strategy"] = chg.backend.strategy
                    if chg.backend.pass_host_header is not None:
                        s["passHostHeader"] = bool(chg.backend.pass_host_header)
                    if chg.backend.servers_transport:
                        s["serversTransport"] = chg.backend.servers_transport
                    if chg.backend.native_lb is not None:
                        s["nativeLB"] = bool(chg.backend.native_lb)
                    if chg.backend.scheme:
                        s["scheme"] = chg.backend.scheme
                    if chg.backend.port is not None:
                        s["port"] = chg.backend.port

        # Lint middleware ordering
        if ordered_chain:
            chain_with_types: List[Tuple[str, str]] = []
            for m in ordered_chain:
                m_ns = m.get("namespace") or namespace
                m_n = m.get("name", "")
                mw_obj = self.get_object("Middleware", m_ns, m_n)
                m_type = next(iter((mw_obj.get("spec") or {}).keys()), "") if mw_obj else ""
                chain_with_types.append((m_n, m_type))
            warnings.extend(lint_middleware_ordering(chain_with_types))

        return self._apply_or_preview_object(
            body=updated,
            dry_run=dry_run,
            extra_warnings=warnings,
            summary_action=f"Updated {route_kind}",
            extra_details={"middleware_chain": ordered_chain},
        )

    # ── T6: traefik_configure_tcp_udp_route ────────────────────────────────────

    async def configure_tcp_udp_route(
        self,
        name: str,
        namespace: str = "default",
        protocol: str = "tcp",
        entry_points: Optional[List[str]] = None,
        routes: Optional[List[Union[TcpUdpRouteRule, Dict[str, Any]]]] = None,
        tls: Optional[Union[RouteTLS, Dict[str, Any]]] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        proto = protocol.strip().lower()
        if proto not in ("tcp", "udp"):
            raise TraefikRouteConfigError("protocol must be 'tcp' or 'udp'.")
        if not routes:
            raise TraefikRouteConfigError("routes list cannot be empty.")

        kind = "IngressRouteUDP" if proto == "udp" else "IngressRouteTCP"
        eps = [e.strip() for e in (entry_points or ([f"{proto}"] if proto == "udp" else ["tcp"])) if e and e.strip()]
        warnings: List[str] = []
        static_cfg = self.get_static_config()
        known_eps = set((static_cfg.get("entryPoints") or {}).keys())
        if known_eps:
            for ep in eps:
                if ep not in known_eps:
                    warnings.append(
                        f"EntryPoint '{ep}' is not declared in Traefik static config ({sorted(known_eps)})."
                    )

        if proto == "udp" and tls:
            raise TraefikRouteConfigError("TLS is not supported on UDP routes (IngressRouteUDP).")

        tls_dict = _tls_to_dict(tls, protocol="tcp") if proto == "tcp" else None

        compiled_routes: List[Dict[str, Any]] = []
        for r_in in routes:
            r_obj = r_in if isinstance(r_in, TcpUdpRouteRule) else TcpUdpRouteRule.model_validate(r_in)
            svc_list: List[Dict[str, Any]] = []
            for s in r_obj.services:
                sd: Dict[str, Any] = {"name": s.name, "port": s.port}
                if s.weight is not None:
                    sd["weight"] = int(s.weight)
                if s.native_lb is not None:
                    sd["nativeLB"] = bool(s.native_lb)
                if proto == "tcp":
                    if s.proxy_protocol_version is not None:
                        sd["proxyProtocol"] = {"version": int(s.proxy_protocol_version)}
                    if s.servers_transport:
                        sd["serversTransport"] = s.servers_transport
                svc_list.append(sd)

            if proto == "udp":
                if r_obj.match or r_obj.middlewares:
                    raise TraefikRouteConfigError("IngressRouteUDP rules only support 'services' (no match or middlewares).")
                compiled_routes.append({"services": svc_list})
            else:
                match_str = compile_route_match(r_obj.match or "HostSNI(`*`)", protocol="tcp")
                snis = extract_hosts_from_rule(match_str)
                if any(s != "*" for s in snis) and not tls_dict:
                    raise TraefikRouteConfigError(
                        f"TCP match rule '{match_str}' specifies a non-wildcard HostSNI, which requires a 'tls' block (termination or passthrough=True)."
                    )
                r_dict: Dict[str, Any] = {"match": match_str, "services": svc_list}
                if r_obj.priority is not None:
                    r_dict["priority"] = int(r_obj.priority)
                if r_obj.middlewares:
                    r_dict["middlewares"] = [
                        {"name": m.name, **({"namespace": m.namespace} if m.namespace else {})}
                        for m in r_obj.middlewares
                    ]
                compiled_routes.append(r_dict)

        spec: Dict[str, Any] = {
            "entryPoints": eps,
            "routes": compiled_routes,
        }
        if tls_dict:
            spec["tls"] = tls_dict

        body = {
            "apiVersion": TRAEFIK_API_VERSION,
            "kind": kind,
            "metadata": {"name": name, "namespace": namespace},
            "spec": spec,
        }
        return self._apply_or_preview_object(
            body=body,
            dry_run=dry_run,
            extra_warnings=warnings,
            summary_action=f"Configured {proto.upper()}",
            extra_details={"protocol": proto, "rule_count": len(compiled_routes)},
        )

    # ── T7: traefik_configure_middleware ───────────────────────────────────────

    async def configure_middleware(
        self,
        name: str,
        namespace: str = "default",
        protocol: str = "http",
        middleware_type: str = "rate_limit",
        spec: Optional[Dict[str, Any]] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        spec_dict, warnings = build_middleware_spec_from_type(
            protocol=protocol,
            middleware_type=middleware_type,
            raw_spec=spec or {},
        )

        # Check IP strategy warning when behind load balancer
        static_cfg = self.get_static_config()
        has_trusted_ips = any(
            bool((ep_cfg.get("forwardedHeaders") or {}).get("trustedIPs"))
            for ep_cfg in (static_cfg.get("entryPoints") or {}).values()
            if isinstance(ep_cfg, dict)
        )
        if middleware_type in ("ip_allow_list", "rate_limit") and has_trusted_ips:
            inner = next(iter(spec_dict.values()), {})
            if "ipStrategy" not in inner and "sourceCriterion" not in inner:
                warnings.append(
                    f"Traefik entryPoints use forwardedHeaders.trustedIPs; consider setting ipStrategy/sourceCriterion on '{name}' so client IPs are extracted accurately behind your load balancer."
                )

        # Check plugin registration in static config
        if middleware_type == "plugin":
            plugin_name = next(iter((spec_dict.get("plugin") or {}).keys()), "")
            declared_plugins = set((static_cfg.get("plugins") or {}).keys())
            if declared_plugins and plugin_name not in declared_plugins:
                raise TraefikMiddlewareError(
                    f"Plugin '{plugin_name}' is not declared in Traefik static configuration (declared plugins: {sorted(declared_plugins)})."
                )

        # Check chain cycles
        extra_guards: List[GuardResult] = []
        if middleware_type == "chain":
            existing_mws = {
                ((m.get("metadata") or {}).get("namespace", "default"), (m.get("metadata") or {}).get("name", "")): m
                for m in self.list_objects("Middleware", namespace)
            }
            chain_refs = (spec_dict.get("chain") or {}).get("middlewares") or []
            cycle_guard = detect_middleware_chain_cycles(name, namespace, chain_refs, existing_mws)
            extra_guards.append(cycle_guard)

        body = build_middleware_crd(
            name=name,
            namespace=namespace,
            spec=spec_dict,
            protocol=protocol,
        )
        return self._apply_or_preview_object(
            body=body,
            dry_run=dry_run,
            extra_guards=extra_guards,
            extra_warnings=warnings,
            summary_action=f"Configured {protocol.upper()} Middleware ({middleware_type})",
            extra_details={"middleware_type": middleware_type, "protocol": protocol},
        )

    # ── T8: traefik_configure_tls_policy ───────────────────────────────────────

    async def configure_tls_policy(
        self,
        kind: str,
        name: str,
        namespace: str = "default",
        spec: Optional[Dict[str, Any]] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        if kind not in ("TLSOption", "TLSStore"):
            raise TraefikTLSError("kind must be 'TLSOption' or 'TLSStore'.")
        raw = dict(spec or {})
        warnings: List[str] = []

        if kind == "TLSStore":
            if name != "default":
                raise TraefikTLSError("Traefik only supports a single TLSStore named 'default' per namespace.")
            store_spec: Dict[str, Any] = {}
            def_cert_block = raw.get("default_certificate") or raw.get("defaultCertificate") or {}
            def_sec = (
                raw.get("default_certificate_secret")
                or raw.get("defaultCertificateSecret")
                or (def_cert_block.get("secret_name") if isinstance(def_cert_block, dict) else None)
                or (def_cert_block.get("secretName") if isinstance(def_cert_block, dict) else None)
                or (def_cert_block if isinstance(def_cert_block, str) else None)
            )
            if def_sec:
                store_spec["defaultCertificate"] = {"secretName": str(def_sec)}
            def_gen = raw.get("default_generated_cert") or raw.get("defaultGeneratedCert")
            if def_gen and isinstance(def_gen, dict):
                store_spec["defaultGeneratedCert"] = dict(def_gen)
            certs = raw.get("certificates") or []
            if certs:
                store_spec["certificates"] = [
                    {"secretName": c if isinstance(c, str) else c.get("secretName")}
                    for c in certs
                ]
            if not store_spec:
                raise TraefikTLSError("TLSStore requires 'default_certificate_secret', 'default_generated_cert', or 'certificates'.")
            body = {
                "apiVersion": TRAEFIK_API_VERSION,
                "kind": "TLSStore",
                "metadata": {"name": name, "namespace": namespace},
                "spec": store_spec,
            }
            return self._apply_or_preview_object(
                body=body,
                dry_run=dry_run,
                extra_warnings=warnings,
                summary_action="Configured default TLSStore",
            )

        # TLSOption
        profile = str(raw.get("profile", "custom")).lower()
        opt_spec: Dict[str, Any] = {}
        if profile in TLS_PROFILES:
            opt_spec.update(copy.deepcopy(TLS_PROFILES[profile]))

        min_v = raw.get("min_version") or raw.get("minVersion") or opt_spec.get("minVersion")
        if min_v:
            opt_spec["minVersion"] = str(min_v)
            if str(min_v) in ("VersionTLS10", "VersionTLS11"):
                warnings.append(f"minVersion='{min_v}' is deprecated and insecure; use VersionTLS12 or VersionTLS13.")
        max_v = raw.get("max_version") or raw.get("maxVersion")
        if max_v:
            opt_spec["maxVersion"] = str(max_v)
        ciphers = raw.get("cipher_suites") or raw.get("cipherSuites")
        if ciphers:
            opt_spec["cipherSuites"] = list(ciphers)
        curves = raw.get("curve_preferences") or raw.get("curvePreferences")
        if curves:
            opt_spec["curvePreferences"] = list(curves)
        if "sni_strict" in raw or "sniStrict" in raw:
            opt_spec["sniStrict"] = bool(raw.get("sni_strict", raw.get("sniStrict")))
        alpn = raw.get("alpn_protocols") or raw.get("alpnProtocols")
        if alpn:
            opt_spec["alpnProtocols"] = list(alpn)
        if "disable_session_tickets" in raw or "disableSessionTickets" in raw:
            opt_spec["disableSessionTickets"] = bool(raw.get("disable_session_tickets", raw.get("disableSessionTickets")))
        client_auth = raw.get("client_auth") or raw.get("clientAuth")
        if client_auth and isinstance(client_auth, dict):
            ca_block: Dict[str, Any] = {
                "clientAuthType": client_auth.get("client_auth_type")
                or client_auth.get("clientAuthType")
                or "RequireAndVerifyClientCert"
            }
            sec_names = client_auth.get("secret_names") or client_auth.get("secretNames") or []
            if sec_names:
                ca_block["secretNames"] = list(sec_names)
            opt_spec["clientAuth"] = ca_block

        if not opt_spec:
            opt_spec = copy.deepcopy(TLS_PROFILES["intermediate"])

        body = {
            "apiVersion": TRAEFIK_API_VERSION,
            "kind": "TLSOption",
            "metadata": {"name": name, "namespace": namespace},
            "spec": opt_spec,
        }
        return self._apply_or_preview_object(
            body=body,
            dry_run=dry_run,
            extra_warnings=warnings,
            summary_action=f"Configured TLSOption (profile={profile})",
            extra_details={"profile": profile},
        )

    # ── T9: traefik_configure_servers_transport ────────────────────────────────

    async def configure_servers_transport(
        self,
        protocol: str = "http",
        name: str = "",
        namespace: str = "default",
        spec: Optional[Dict[str, Any]] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        proto = protocol.strip().lower()
        if proto not in ("http", "tcp"):
            raise TraefikOperationError("protocol must be 'http' or 'tcp'.")
        if not name:
            raise TraefikOperationError("ServersTransport name is required.")

        raw = dict(spec or {})
        warnings: List[str] = []
        kind = "ServersTransportTCP" if proto == "tcp" else "ServersTransport"
        st_spec: Dict[str, Any] = {}

        if proto == "tcp":
            if raw.get("dial_timeout") or raw.get("dialTimeout"):
                st_spec["dialTimeout"] = str(raw.get("dial_timeout") or raw.get("dialTimeout"))
            if raw.get("dial_keep_alive") or raw.get("dialKeepAlive"):
                st_spec["dialKeepAlive"] = str(raw.get("dial_keep_alive") or raw.get("dialKeepAlive"))
            if raw.get("termination_delay") or raw.get("terminationDelay"):
                st_spec["terminationDelay"] = str(raw.get("termination_delay") or raw.get("terminationDelay"))
            tls_in = raw.get("tls")
            if isinstance(tls_in, dict):
                tls_out: Dict[str, Any] = {}
                if "insecure_skip_verify" in tls_in or "insecureSkipVerify" in tls_in:
                    insec = bool(tls_in.get("insecure_skip_verify", tls_in.get("insecureSkipVerify")))
                    tls_out["insecureSkipVerify"] = insec
                    if insec:
                        warnings.append("insecureSkipVerify=True disables backend TLS certificate validation.")
                if tls_in.get("server_name") or tls_in.get("serverName"):
                    tls_out["serverName"] = str(tls_in.get("server_name") or tls_in.get("serverName"))
                if tls_in.get("root_cas") or tls_in.get("rootCAs"):
                    tls_out["rootCAs"] = list(tls_in.get("root_cas") or tls_in.get("rootCAs"))
                if tls_in.get("certificates") or tls_in.get("certificatesSecrets"):
                    tls_out["certificatesSecrets"] = list(tls_in.get("certificates") or tls_in.get("certificatesSecrets"))
                st_spec["tls"] = tls_out
        else:
            if raw.get("server_name") or raw.get("serverName"):
                st_spec["serverName"] = str(raw.get("server_name") or raw.get("serverName"))
            if "insecure_skip_verify" in raw or "insecureSkipVerify" in raw:
                insec = bool(raw.get("insecure_skip_verify", raw.get("insecureSkipVerify")))
                st_spec["insecureSkipVerify"] = insec
                if insec:
                    warnings.append("insecureSkipVerify=True disables backend TLS certificate validation.")
            if raw.get("root_cas") or raw.get("rootCAsSecrets") or raw.get("rootCAs"):
                st_spec["rootCAsSecrets"] = list(raw.get("root_cas") or raw.get("rootCAsSecrets") or raw.get("rootCAs"))
            if raw.get("certificates") or raw.get("certificatesSecrets"):
                st_spec["certificatesSecrets"] = list(raw.get("certificates") or raw.get("certificatesSecrets"))
            if raw.get("max_idle_conns_per_host") is not None or raw.get("maxIdleConnsPerHost") is not None:
                st_spec["maxIdleConnsPerHost"] = int(raw.get("max_idle_conns_per_host", raw.get("maxIdleConnsPerHost")))
            if "disable_http2" in raw or "disableHTTP2" in raw:
                st_spec["disableHTTP2"] = bool(raw.get("disable_http2", raw.get("disableHTTP2")))
            if raw.get("peer_cert_uri") or raw.get("peerCertURI"):
                st_spec["peerCertURI"] = str(raw.get("peer_cert_uri") or raw.get("peerCertURI"))
            ft = raw.get("forwarding_timeouts") or raw.get("forwardingTimeouts")
            if isinstance(ft, dict):
                ft_out: Dict[str, Any] = {}
                if ft.get("dial") or ft.get("dialTimeout"):
                    ft_out["dialTimeout"] = str(ft.get("dial") or ft.get("dialTimeout"))
                if ft.get("response_header") or ft.get("responseHeaderTimeout"):
                    ft_out["responseHeaderTimeout"] = str(ft.get("response_header") or ft.get("responseHeaderTimeout"))
                if ft.get("idle_conn") or ft.get("idleConnTimeout"):
                    ft_out["idleConnTimeout"] = str(ft.get("idle_conn") or ft.get("idleConnTimeout"))
                if ft.get("read_idle") or ft.get("readIdleTimeout"):
                    ft_out["readIdleTimeout"] = str(ft.get("read_idle") or ft.get("readIdleTimeout"))
                if ft.get("ping") or ft.get("pingTimeout"):
                    ft_out["pingTimeout"] = str(ft.get("ping") or ft.get("pingTimeout"))
                if ft_out:
                    st_spec["forwardingTimeouts"] = ft_out
            if raw.get("spiffe") and isinstance(raw["spiffe"], dict):
                st_spec["spiffe"] = dict(raw["spiffe"])

        if not st_spec:
            raise TraefikOperationError(f"{kind} requires at least one transport setting in 'spec'.")

        body = {
            "apiVersion": TRAEFIK_API_VERSION,
            "kind": kind,
            "metadata": {"name": name, "namespace": namespace},
            "spec": st_spec,
        }
        return self._apply_or_preview_object(
            body=body,
            dry_run=dry_run,
            extra_warnings=warnings,
            summary_action=f"Configured {kind}",
            extra_details={"protocol": proto},
        )

    # ── T10: traefik_delete_resource ───────────────────────────────────────────

    def find_references_to_object(self, kind: str, namespace: str, name: str) -> List[str]:
        """Return list of routes or chains referencing a policy or TraefikService object."""
        refs: List[str] = []
        for r_kind in ("IngressRoute", "IngressRouteTCP", "Ingress"):
            for obj in self.list_objects(r_kind, None):
                m = obj.get("metadata") or {}
                r_ns = m.get("namespace") or "default"
                r_name = m.get("name") or ""
                spec = obj.get("spec") or {}
                if r_kind == "Ingress":
                    anns = m.get("annotations") or {}
                    if kind == "Middleware":
                        mw_csv = anns.get(f"{TRAEFIK_INGRESS_ANNOTATION_PREFIX}router.middlewares", "")
                        if f"{namespace}-{name}@kubernetescrd" in mw_csv or name in mw_csv:
                            refs.append(f"Ingress/{r_ns}/{r_name}")
                    continue

                if kind == "TLSOption":
                    opt = (spec.get("tls") or {}).get("options") or {}
                    if opt.get("name") == name and (opt.get("namespace") or r_ns) == namespace:
                        refs.append(f"{r_kind}/{r_ns}/{r_name}")

                for rule in spec.get("routes") or []:
                    if kind in ("Middleware", "MiddlewareTCP"):
                        for mw in rule.get("middlewares") or []:
                            if mw.get("name") == name and (mw.get("namespace") or r_ns) == namespace:
                                refs.append(f"{r_kind}/{r_ns}/{r_name}")
                    if kind == "TraefikService":
                        for svc in rule.get("services") or []:
                            if svc.get("kind") == "TraefikService" and svc.get("name") == name and (svc.get("namespace") or r_ns) == namespace:
                                refs.append(f"{r_kind}/{r_ns}/{r_name}")
                    if kind in ("ServersTransport", "ServersTransportTCP"):
                        for svc in rule.get("services") or []:
                            if svc.get("serversTransport") == name and r_ns == namespace:
                                refs.append(f"{r_kind}/{r_ns}/{r_name}")

        if kind == "Middleware":
            for mw_obj in self.list_objects("Middleware", namespace):
                mw_name = (mw_obj.get("metadata") or {}).get("name", "")
                if mw_name == name:
                    continue
                chain_mws = ((mw_obj.get("spec") or {}).get("chain") or {}).get("middlewares") or []
                for cm in chain_mws:
                    if isinstance(cm, dict) and cm.get("name") == name and (cm.get("namespace") or namespace) == namespace:
                        refs.append(f"Middleware/{namespace}/{mw_name}")

        return list(dict.fromkeys(refs))

    async def delete_resource(
        self,
        kind: str,
        name: str,
        namespace: str = "default",
        cascade: bool = False,
        force: bool = False,
    ) -> Dict[str, Any]:
        if kind not in DELETABLE_TRAEFIK_KINDS:
            raise TraefikOperationError(
                f"Deletion of kind '{kind}' is forbidden by the 0->1 safety boundary. "
                f"Deletable Traefik kinds: {', '.join(DELETABLE_TRAEFIK_KINDS)}."
            )

        existing = self.get_object(kind, namespace, name)
        if not existing:
            raise TraefikRouteNotFoundError(f"{kind} '{name}' not found in namespace '{namespace}'")

        own_guard, owner_type = check_ownership(
            kind, name, namespace, existing_obj=existing, argo_rollouts=self.list_objects("Rollout", namespace)
        )
        if not own_guard.passed:
            return ExecutionResult(
                status="refused",
                summary=own_guard.message,
                resource_uri=f"traefik://manifests/{kind}/{namespace}/{name}",
                guards=[own_guard],
                details={"owner_type": owner_type},
            ).model_dump()

        refs = self.find_references_to_object(kind, namespace, name)
        if refs and not force:
            raise TraefikReferentialIntegrityError(
                f"Cannot delete {kind} '{namespace}/{name}' because it is still referenced by {len(refs)} resource(s): "
                f"{', '.join(refs)}. Detach it first via traefik_update_route or pass force=True."
            )

        deleted_items = [f"{kind}/{namespace}/{name}"]

        # Optional safe cascade: ONLY delete child TraefikServices/Middlewares that are
        # (a) referenced solely by this route and (b) carry app.kubernetes.io/managed-by=talkops-traefik-mcp
        # NEVER delete Kubernetes Services, Secrets, or workloads.
        if cascade and kind in ("IngressRoute", "IngressRouteTCP"):
            spec = existing.get("spec") or {}
            candidate_children: List[Tuple[str, str, str]] = []
            for r in spec.get("routes") or []:
                for mw in r.get("middlewares") or []:
                    mw_kind = "MiddlewareTCP" if kind == "IngressRouteTCP" else "Middleware"
                    candidate_children.append((mw_kind, mw.get("namespace") or namespace, mw.get("name", "")))
                for svc in r.get("services") or []:
                    if svc.get("kind") == "TraefikService":
                        candidate_children.append(("TraefikService", svc.get("namespace") or namespace, svc.get("name", "")))

            # Remove the parent first so reference counts reflect remaining routes
            self._memory_store.pop((kind, namespace, name), None)
            for c_kind, c_ns, c_name in candidate_children:
                c_obj = self.get_object(c_kind, c_ns, c_name)
                if not c_obj or not is_managed_by_mcp(c_obj):
                    continue
                remaining_refs = self.find_references_to_object(c_kind, c_ns, c_name)
                if not remaining_refs:
                    self._memory_store.pop((c_kind, c_ns, c_name), None)
                    deleted_items.append(f"{c_kind}/{c_ns}/{c_name}")
        else:
            self._memory_store.pop((kind, namespace, name), None)

        if self._try_init_k8s() and self.k8s_custom_api:
            for item_ref in deleted_items:
                parts = item_ref.split("/", 2)
                if len(parts) == 3 and parts[0] in KIND_TO_CRD_META:
                    d_grp, d_ver, d_plural = KIND_TO_CRD_META[parts[0]]
                    try:
                        self.k8s_custom_api.delete_namespaced_custom_object(d_grp, d_ver, parts[1], d_plural, parts[2])
                    except Exception:
                        pass

        return ExecutionResult(
            status="success",
            summary=f"Deleted {', '.join(deleted_items)}.",
            dry_run=False,
            resource_uri=f"traefik://routes/{namespace}",
            details={"deleted": deleted_items, "forced": force, "referenced_by": refs},
        ).model_dump()

    # ── T11: traefik_diagnose_route ────────────────────────────────────────────

    async def diagnose_route(
        self,
        kind: str = "IngressRoute",
        name: str = "",
        namespace: str = "default",
        include: Optional[List[str]] = None,
        detail: str = "summary",
    ) -> Dict[str, Any]:
        inc = set(include or ["runtime", "endpoints", "tls", "events"])
        items: List[DiagnosisCodeItem] = []

        def _add_code(
            code: str,
            severity: str = "error",
            evidence: str = "",
            remediation: str = "",
            resource_uri: Optional[str] = None,
        ) -> None:
            items.append(
                DiagnosisCodeItem(
                    code=code,
                    severity=severity,  # type: ignore[arg-type]
                    evidence=evidence,
                    remediation=remediation,
                    resource_uri=resource_uri,
                )
            )

        obj = self.get_object(kind, namespace, name)
        if not obj:
            _add_code(
                "ROUTE_NOT_FOUND",
                severity="critical",
                evidence=f"{kind} '{name}' was not found in namespace '{namespace}'.",
                remediation=f"Read 'traefik://routes/{namespace}' or 'traefik://gateway/{namespace}' to verify valid names.",
                resource_uri=f"traefik://routes/{namespace}",
            )
            report = RouteDiagnosisReport(
                kind=kind,
                name=name,
                namespace=namespace,
                healthy=False,
                verdict=f"{kind} '{namespace}/{name}' not found (codes: ROUTE_NOT_FOUND).",
                diagnosis_codes=["ROUTE_NOT_FOUND"],
                diagnosis_items=items,
                next_actions=[f"Read traefik://routes/{namespace}"],
            )
            return report.model_dump()

        api_ver = str(obj.get("apiVersion", ""))
        meta = obj.get("metadata") or {}
        anns = meta.get("annotations") or {}
        spec = obj.get("spec") or {}
        status_block = obj.get("status") or {}

        if "containo.us" in api_ver:
            _add_code(
                "LEGACY_API_GROUP",
                severity="error",
                evidence=f"Resource uses deprecated apiVersion '{api_ver}'.",
                remediation="Migrate resource apiVersion to 'traefik.io/v1alpha1'.",
                resource_uri=f"traefik://manifests/{kind}/{namespace}/{name}",
            )

        # Ownership checks
        own_guard, owner_type = check_ownership(
            kind, name, namespace, existing_obj=obj, argo_rollouts=self.list_objects("Rollout", namespace)
        )
        if owner_type == "argo_rollouts":
            _add_code(
                "ARGO_ROLLOUT_MANAGED",
                severity="info",
                evidence=own_guard.message,
                remediation="Use 'argo_manage_rollout_lifecycle' on the Argo Rollouts MCP server for weight progression.",
            )
        elif owner_type == "gitops":
            _add_code(
                "GITOPS_MANAGED",
                severity="info",
                evidence=own_guard.message,
                remediation="Commit permanent routing changes to your GitOps repository after live triage.",
            )

        static_cfg = self.get_static_config()
        known_eps = set((static_cfg.get("entryPoints") or {}).keys())
        prov_crd = (static_cfg.get("providers") or {}).get("kubernetesCRD") or {}
        allow_cross_ns = bool(prov_crd.get("allowCrossNamespace", False))
        allow_ext_name = bool(prov_crd.get("allowExternalNameServices", False))
        allow_empty_svc = bool(prov_crd.get("allowEmptyServices", False))

        # Gateway API route / Gateway checks
        if kind in ("HTTPRoute", "GRPCRoute", "TLSRoute", "TCPRoute", "Gateway"):
            parents = status_block.get("parents") or []
            for p in parents:
                for cond in p.get("conditions") or []:
                    ctype = cond.get("type")
                    cstatus = cond.get("status")
                    creason = cond.get("reason", "")
                    cmsg = cond.get("message", "")
                    if ctype == "Accepted" and cstatus == "False":
                        code = "GATEWAY_LISTENER_REJECTS_ROUTE" if "NotAllowed" in creason or "Listener" in creason else "GATEWAY_ROUTE_NOT_ACCEPTED"
                        _add_code(
                            code,
                            severity="error",
                            evidence=f"Gateway parent condition Accepted=False ({creason}: {cmsg}).",
                            remediation="Inspect Gateway listener allowedRoutes and hostname matching via 'traefik://gateway/" + namespace + "'.",
                            resource_uri=f"traefik://gateway/{namespace}",
                        )
                    if ctype == "ResolvedRefs" and cstatus == "False":
                        code = "REFERENCE_GRANT_MISSING" if "RefNotPermitted" in creason else "GATEWAY_REFS_UNRESOLVED"
                        _add_code(
                            code,
                            severity="error",
                            evidence=f"Gateway parent condition ResolvedRefs=False ({creason}: {cmsg}).",
                            remediation="Create a ReferenceGrant in the target namespace or fix backendRef service/port.",
                            resource_uri=f"traefik://gateway/{namespace}",
                        )
            for cond in status_block.get("conditions") or []:
                if cond.get("type") == "Programmed" and cond.get("status") == "False":
                    _add_code(
                        "GATEWAY_NOT_PROGRAMMED",
                        severity="error",
                        evidence=f"Gateway condition Programmed=False ({cond.get('reason')}: {cond.get('message')}).",
                        remediation="Check Traefik Gateway provider configuration and entryPoint listener bindings.",
                        resource_uri=f"traefik://gateway/{namespace}",
                    )

        # Standard Ingress provider checks
        if kind == "Ingress":
            ing_class = spec.get("ingressClassName") or anns.get("kubernetes.io/ingress.class") or ""
            has_nginx = any(k.startswith("nginx.ingress.kubernetes.io/") for k in anns)
            has_traefik = any(k.startswith(TRAEFIK_INGRESS_ANNOTATION_PREFIX) for k in anns)
            if has_nginx and has_traefik:
                _add_code(
                    "INGRESS_PROVIDER_CONFLICT",
                    severity="error",
                    evidence="Ingress mixes both 'nginx.ingress.kubernetes.io/*' and 'traefik.ingress.kubernetes.io/*' annotations.",
                    remediation="Do not mix NGINX and Traefik annotations on one Ingress; see 'adopting-traefik-nginx-ingress-provider'.",
                )
            provs = static_cfg.get("providers") or {}
            nginx_enabled = bool((provs.get("kubernetesIngressNGINX") or {}).get("enabled", False))
            if ing_class == "nginx" and not nginx_enabled:
                _add_code(
                    "INGRESS_NOT_CLAIMED",
                    severity="error",
                    evidence="Ingress has ingressClassName='nginx', but providers.kubernetesIngressNGINX is not enabled.",
                    remediation="Enable providers.kubernetesIngressNGINX in Traefik Helm values or update ingressClassName.",
                )

        # Provider ingressClass filter check on IngressRoute
        req_class = prov_crd.get("ingressClass") or "traefik"
        route_class = anns.get("kubernetes.io/ingress.class") or spec.get("ingressClassName")
        if route_class and route_class != req_class:
            _add_code(
                "ROUTE_IGNORED_BY_PROVIDER",
                severity="error",
                evidence=f"Route ingress.class='{route_class}' does not match provider ingressClass='{req_class}'.",
                remediation=f"Set ingress_class='{req_class}' via traefik_configure_http_route or traefik_update_route.",
            )

        # EntryPoints check
        route_eps = spec.get("entryPoints") or []
        if known_eps:
            for ep in route_eps:
                if ep not in known_eps:
                    _add_code(
                        "ENTRYPOINT_UNKNOWN",
                        severity="error",
                        evidence=f"EntryPoint '{ep}' is not defined in Traefik static configuration ({sorted(known_eps)}).",
                        remediation="Use a valid entryPoint from 'traefik://instance/static-config'.",
                        resource_uri="traefik://instance/static-config",
                    )

        # Runtime router check
        proto = "tcp" if "TCP" in kind else ("udp" if "UDP" in kind else "http")
        runtime_router_info: Dict[str, Any] = {}
        if "runtime" in inc:
            rt_router = self.runtime.find_runtime_router(namespace, name, protocol=proto)
            if rt_router:
                runtime_router_info = rt_router
                if str(rt_router.get("status", "enabled")).lower() == "disabled" or rt_router.get("error"):
                    _add_code(
                        "ROUTER_DISABLED",
                        severity="critical",
                        evidence=f"Traefik runtime disabled router '{rt_router.get('name')}': {rt_router.get('error')}",
                        remediation="Fix the underlying middleware, TLS, or rule error reported in runtime_router.error.",
                        resource_uri="traefik://runtime/health",
                    )
            elif self.runtime.is_reachable() and kind in ("IngressRoute", "IngressRouteTCP", "IngressRouteUDP", "Ingress"):
                _add_code(
                    "ROUTER_NOT_IN_RUNTIME",
                    severity="warning",
                    evidence=f"{kind} '{namespace}/{name}' is present in Kubernetes but absent from Traefik runtime routers.",
                    remediation="Check Traefik controller logs via traefik_analyze_logs(source='controller') and provider watch namespaces.",
                    resource_uri="traefik://runtime/health",
                )

        # Rules, Middlewares, and Backends inspection
        middlewares_out: List[Dict[str, Any]] = []
        backends_out: List[Dict[str, Any]] = []
        all_route_hosts: List[str] = []

        routes_array = spec.get("routes") or []
        if kind == "TraefikService":
            # Diagnose TraefikService directly
            routes_array = [{"match": "", "services": [{"name": name, "kind": "TraefikService"}]}]

        for r_dict in routes_array:
            m_str = r_dict.get("match", "")
            if m_str:
                all_route_hosts.extend(extract_hosts_from_rule(m_str))
                valid_rule, rule_issues, _ = lint_v3_rule(m_str, protocol=proto)
                if not valid_rule:
                    is_v2 = any("v2" in iss.lower() or "renamed" in iss.lower() or "colon" in iss.lower() for iss in rule_issues)
                    _add_code(
                        "RULE_SYNTAX_V2" if is_v2 else "RULE_INVALID",
                        severity="error",
                        evidence=f"Rule '{m_str}': {'; '.join(rule_issues)}",
                        remediation="Update match rule to Traefik v3 syntax via traefik_configure_http_route.",
                    )
                if proto == "tcp":
                    snis = extract_hosts_from_rule(m_str)
                    if any(s != "*" for s in snis) and not spec.get("tls"):
                        _add_code(
                            "TCP_SNI_WITHOUT_TLS",
                            severity="error",
                            evidence=f"IngressRouteTCP rule '{m_str}' matches specific HostSNI without a spec.tls block.",
                            remediation="Add a TLS block (or passthrough=True) via traefik_configure_tcp_udp_route.",
                        )

                # Priority shadowing check against runtime routers
                if "runtime" in inc:
                    my_prio = compute_default_priority(m_str, r_dict.get("priority"))
                    my_hosts = set(extract_hosts_from_rule(m_str))
                    has_subpath = "PathPrefix(`/" in m_str and "PathPrefix(`/`)" not in m_str
                    for other_r in self.runtime.get_protocol_snapshot(proto).get("routers") or []:
                        if other_r.get("name") == runtime_router_info.get("name"):
                            continue
                        other_rule = str(other_r.get("rule") or "")
                        other_prio = int(other_r.get("priority") or compute_default_priority(other_rule, None))
                        if other_prio <= my_prio:
                            continue
                        other_hosts = set(extract_hosts_from_rule(other_rule))
                        same_or_catchall = (
                            other_rule == m_str
                            or (
                                has_subpath
                                and bool(my_hosts & other_hosts)
                                and "PathPrefix(`/`)" in other_rule
                            )
                        )
                        if same_or_catchall:
                            _add_code(
                                "PRIORITY_SHADOWED",
                                severity="warning",
                                evidence=(
                                    f"Router '{other_r.get('name')}' (rule='{other_rule}', priority={other_prio}) "
                                    f"evaluates ahead of this route (priority={my_prio})."
                                ),
                                remediation="Assign an explicit higher priority via traefik_update_route.",
                            )

            # Middlewares on rule
            for mw_ref in r_dict.get("middlewares") or []:
                mw_n = mw_ref.get("name", "")
                mw_ns = mw_ref.get("namespace") or namespace
                mw_kind = "MiddlewareTCP" if proto == "tcp" else "Middleware"
                if mw_ns != namespace and not allow_cross_ns:
                    _add_code(
                        "MIDDLEWARE_CROSS_NAMESPACE_BLOCKED",
                        severity="error",
                        evidence=f"Cross-namespace middleware '{mw_ns}/{mw_n}' referenced while allowCrossNamespace=false.",
                        remediation="Deploy the Middleware in the same namespace or enable allowCrossNamespace.",
                    )
                mw_obj = self.get_object(mw_kind, mw_ns, mw_n)
                if not mw_obj:
                    _add_code(
                        "MIDDLEWARE_MISSING",
                        severity="critical",
                        evidence=f"{mw_kind} '{mw_ns}/{mw_n}' does not exist.",
                        remediation=f"Create '{mw_n}' with traefik_configure_middleware or detach it with traefik_update_route.",
                        resource_uri=f"traefik://policies/{mw_ns}",
                    )
                    middlewares_out.append({"name": mw_n, "namespace": mw_ns, "exists": False, "runtime_status": "missing"})
                else:
                    # Check chain cycle or runtime middleware error
                    chain_refs = ((mw_obj.get("spec") or {}).get("chain") or {}).get("middlewares") or []
                    if chain_refs:
                        all_mws = {
                            ((m.get("metadata") or {}).get("namespace", "default"), (m.get("metadata") or {}).get("name", "")): m
                            for m in self.list_objects("Middleware", mw_ns)
                        }
                        try:
                            detect_middleware_chain_cycles(mw_n, mw_ns, chain_refs, all_mws)
                        except TraefikReferentialIntegrityError as cyc_exc:
                            _add_code(
                                "MIDDLEWARE_CHAIN_CYCLE",
                                severity="error",
                                evidence=str(cyc_exc),
                                remediation="Break the circular chain reference via traefik_configure_middleware.",
                            )
                    rt_mw_err = None
                    for rtm in self.runtime.get_protocol_snapshot(proto).get("middlewares") or []:
                        if f"{mw_ns}-{mw_n}".lower() in str(rtm.get("name", "")).lower() and rtm.get("error"):
                            rt_mw_err = rtm.get("error")
                            _add_code(
                                "MIDDLEWARE_RUNTIME_ERROR",
                                severity="error",
                                evidence=f"Runtime middleware '{rtm.get('name')}' error: {rt_mw_err}",
                                remediation="Inspect middleware spec via traefik://policies/" + mw_ns,
                            )
                    middlewares_out.append({
                        "name": mw_n,
                        "namespace": mw_ns,
                        "exists": True,
                        "runtime_status": "error" if rt_mw_err else "enabled",
                    })

            # Backends on rule
            for svc_ref in r_dict.get("services") or []:
                s_kind = svc_ref.get("kind", "Service")
                s_name = svc_ref.get("name", "")
                s_ns = svc_ref.get("namespace") or namespace
                s_port = svc_ref.get("port")
                st_name = svc_ref.get("serversTransport")

                if st_name:
                    st_kind = "ServersTransportTCP" if proto == "tcp" else "ServersTransport"
                    if not self.get_object(st_kind, s_ns, st_name):
                        _add_code(
                            "SERVERS_TRANSPORT_MISSING",
                            severity="error",
                            evidence=f"{st_kind} '{s_ns}/{st_name}' referenced by backend '{s_name}' does not exist.",
                            remediation="Create the transport via traefik_configure_servers_transport.",
                        )

                if s_kind == "TraefikService":
                    ts_obj = self.get_object("TraefikService", s_ns, s_name)
                    if not ts_obj:
                        _add_code(
                            "TRAEFIK_SERVICE_MISSING",
                            severity="critical",
                            evidence=f"TraefikService '{s_ns}/{s_name}' does not exist.",
                            remediation="Create the TraefikService via traefik_configure_weighted_service.",
                        )
                        backends_out.append({"name": s_name, "kind": "TraefikService", "exists": False})
                        continue

                    ts_spec = ts_obj.get("spec") or {}
                    wrr_svcs = (ts_spec.get("weighted") or {}).get("services") or []
                    if wrr_svcs:
                        total_w = sum(int(ws.get("weight", 0)) for ws in wrr_svcs)
                        if total_w <= 0:
                            _add_code(
                                "ALL_WEIGHTS_ZERO",
                                severity="critical",
                                evidence=f"TraefikService '{s_name}' has total weight 0 across all backends.",
                                remediation="Set positive traffic weights via traefik_set_traffic_weights.",
                            )
                        for ws in wrr_svcs:
                            self._diagnose_single_k8s_service(
                                ws.get("namespace") or s_ns,
                                ws.get("name", ""),
                                ws.get("port"),
                                weight=ws.get("weight"),
                                allow_ext_name=allow_ext_name,
                                allow_empty_svc=allow_empty_svc,
                                add_code_fn=_add_code,
                                backends_out=backends_out,
                            )
                    mir_spec = ts_spec.get("mirroring") or {}
                    if mir_spec:
                        self._diagnose_single_k8s_service(
                            s_ns,
                            mir_spec.get("name", ""),
                            mir_spec.get("port"),
                            weight=100,
                            allow_ext_name=allow_ext_name,
                            allow_empty_svc=allow_empty_svc,
                            add_code_fn=_add_code,
                            backends_out=backends_out,
                        )
                        for m_item in mir_spec.get("mirrors") or []:
                            m_name = m_item.get("name", "")
                            m_ns = m_item.get("namespace") or s_ns
                            if not self.get_object("Service", m_ns, m_name):
                                _add_code(
                                    "MIRROR_TARGET_MISSING",
                                    severity="warning",
                                    evidence=f"Mirror target Service '{m_ns}/{m_name}' on '{s_name}' does not exist.",
                                    remediation="Update or disable mirroring via traefik_configure_traffic_mirroring.",
                                )
                else:
                    self._diagnose_single_k8s_service(
                        s_ns,
                        s_name,
                        s_port,
                        weight=svc_ref.get("weight"),
                        allow_ext_name=allow_ext_name,
                        allow_empty_svc=allow_empty_svc,
                        add_code_fn=_add_code,
                        backends_out=backends_out,
                    )

        # TLS diagnosis
        tls_out: Dict[str, Any] = {}
        tls_block = spec.get("tls")
        if "tls" in inc and isinstance(tls_block, dict):
            sec_name = tls_block.get("secretName")
            resolver = tls_block.get("certResolver")
            opt_ref = tls_block.get("options")

            if resolver:
                known_resolvers = set((static_cfg.get("certificatesResolvers") or {}).keys())
                if known_resolvers and resolver not in known_resolvers:
                    _add_code(
                        "CERT_RESOLVER_UNKNOWN",
                        severity="error",
                        evidence=f"certResolver '{resolver}' is not defined in static config ({sorted(known_resolvers)}).",
                        remediation="Use a valid certResolver from 'traefik://instance/static-config'.",
                    )

            if isinstance(opt_ref, dict) and opt_ref.get("name"):
                opt_n = opt_ref["name"]
                opt_ns = opt_ref.get("namespace") or namespace
                if not self.get_object("TLSOption", opt_ns, opt_n):
                    _add_code(
                        "TLS_OPTION_MISSING",
                        severity="error",
                        evidence=f"TLSOption '{opt_ns}/{opt_n}' does not exist.",
                        remediation="Create the TLSOption via traefik_configure_tls_policy.",
                    )

            if sec_name:
                sec_obj = self.get_object("Secret", namespace, sec_name)
                if not sec_obj:
                    _add_code(
                        "TLS_SECRET_MISSING",
                        severity="error",
                        evidence=f"TLS Secret '{namespace}/{sec_name}' was not found.",
                        remediation=f"Check 'traefik://certificates/{namespace}' or update route TLS via traefik_update_route.",
                    )
                    tls_out = {"secret_name": sec_name, "exists": False}
                else:
                    crt_b64 = (sec_obj.get("data") or {}).get("tls.crt") or (sec_obj.get("stringData") or {}).get("tls.crt")
                    if crt_b64:
                        try:
                            cert_info = parse_pem_certificate(crt_b64)
                            cov_ok, _, uncovered = check_host_coverage(all_route_hosts, cert_info.get("sans") or [])
                            tls_out = {
                                "secret_name": sec_name,
                                "exists": True,
                                "days_remaining": cert_info["days_remaining"],
                                "not_after": cert_info["not_after"],
                                "sans": cert_info["sans"],
                                "covers_hosts": cov_ok,
                            }
                            if cert_info["expired"]:
                                _add_code(
                                    "TLS_CERT_EXPIRED",
                                    severity="critical",
                                    evidence=f"TLS Secret '{sec_name}' expired on {cert_info['not_after']}.",
                                    remediation="Rotate the TLS certificate Secret.",
                                )
                            elif cert_info["days_remaining"] <= self.config.cert_expiry_warning_days:
                                _add_code(
                                    "TLS_CERT_EXPIRING",
                                    severity="warning",
                                    evidence=f"TLS Secret '{sec_name}' expires in {cert_info['days_remaining']} days.",
                                    remediation="Renew the TLS certificate before expiration.",
                                )
                            if not cov_ok:
                                _add_code(
                                    "TLS_SAN_MISMATCH",
                                    severity="error",
                                    evidence=f"Certificate SANs {cert_info['sans']} do not match route host(s) {uncovered}.",
                                    remediation="Issue a certificate covering all route hostnames.",
                                )
                        except Exception:
                            tls_out = {"secret_name": sec_name, "exists": True}

        # Optional Metrics check
        metrics_out: Optional[Dict[str, Any]] = None
        if "metrics" in inc:
            m_sum = self.prometheus.get_service_summary(namespace, name)
            metrics_out = m_sum
            if m_sum.get("status") == "available":
                err_5xx = (m_sum.get("metrics") or {}).get("error_rate_5xx_pct", 0.0)
                if err_5xx >= 5.0:
                    _add_code(
                        "HIGH_ERROR_RATE",
                        severity="error",
                        evidence=f"5xx error rate is {err_5xx}% over the last 5m.",
                        remediation="Inspect access logs via traefik_analyze_logs or shift canary weight back via traefik_set_traffic_weights.",
                    )

        non_info_items = [
            it for it in items if it.code not in ("ARGO_ROLLOUT_MANAGED", "GITOPS_MANAGED")
        ]
        healthy = len(non_info_items) == 0
        if healthy:
            items.insert(
                0,
                DiagnosisCodeItem(
                    code="HEALTHY",
                    severity="info",
                    evidence=f"{kind} '{namespace}/{name}' and all dependencies are healthy.",
                    remediation="No remediation required.",
                    resource_uri=f"traefik://manifests/{kind}/{namespace}/{name}",
                ),
            )

        codes_list = list(dict.fromkeys(it.code for it in items))
        next_actions = list(dict.fromkeys(it.remediation for it in items if it.remediation and it.code != "HEALTHY"))
        verdict = (
            f"{kind} '{namespace}/{name}' is {'HEALTHY' if healthy else 'UNHEALTHY'} "
            f"(codes: {', '.join(codes_list)})."
        )

        report = RouteDiagnosisReport(
            kind=kind,
            name=name,
            namespace=namespace,
            healthy=healthy,
            verdict=verdict,
            diagnosis_codes=codes_list,
            diagnosis_items=items if detail == "full" else items[:5],
            runtime_router=runtime_router_info,
            backends=backends_out,
            middlewares=middlewares_out,
            tls=tls_out,
            metrics=metrics_out,
            warning_events=[],
            next_actions=next_actions,
        )
        return report.model_dump()

    def _diagnose_single_k8s_service(
        self,
        namespace: str,
        service_name: str,
        port: Any,
        weight: Optional[int],
        allow_ext_name: bool,
        allow_empty_svc: bool,
        add_code_fn: Any,
        backends_out: List[Dict[str, Any]],
    ) -> None:
        svc_obj = self.get_object("Service", namespace, service_name)
        if not svc_obj:
            add_code_fn(
                "BACKEND_SERVICE_MISSING",
                severity="critical",
                evidence=f"Backend Kubernetes Service '{namespace}/{service_name}' does not exist.",
                remediation="Verify Service name in namespace or deploy the target Kubernetes Service.",
            )
            backends_out.append({"name": service_name, "namespace": namespace, "port": port, "exists": False})
            return

        svc_spec = svc_obj.get("spec") or {}
        if svc_spec.get("type") == "ExternalName" and not allow_ext_name:
            add_code_fn(
                "EXTERNALNAME_NOT_ALLOWED",
                severity="error",
                evidence=f"Service '{service_name}' is of type ExternalName, which is blocked when allowExternalNameServices=false.",
                remediation="Enable providers.kubernetesCRD.allowExternalNameServices or route to an in-cluster Service.",
            )

        svc_ports = svc_spec.get("ports") or []
        if port is not None and svc_ports:
            matched_port = any(
                str(p.get("port")) == str(port) or str(p.get("name", "")) == str(port)
                for p in svc_ports
            )
            if not matched_port:
                avail = [p.get("port") or p.get("name") for p in svc_ports]
                add_code_fn(
                    "BACKEND_PORT_MISMATCH",
                    severity="error",
                    evidence=f"Route targets port '{port}' on Service '{service_name}', but Service exposes {avail}.",
                    remediation=f"Update backend port to {avail[0]} via traefik_configure_http_route or traefik_update_route.",
                )

        # Check Endpoint readiness
        ep_obj = self._memory_store.get(("Endpoints", namespace, service_name))
        if ep_obj is None and self._try_init_k8s() and self.k8s_core_v1:
            try:
                live_ep = self.k8s_core_v1.read_namespaced_endpoints(name=service_name, namespace=namespace)
                ep_obj = client.ApiClient().sanitize_for_serialization(live_ep)
            except Exception:
                ep_obj = None
        ready_count = 0
        not_ready_count = 0
        if ep_obj is not None:
            for sub in ep_obj.get("subsets") or []:
                ready_count += len(sub.get("addresses") or [])
                not_ready_count += len(sub.get("notReadyAddresses") or [])
            total_ep = ready_count + not_ready_count
            if ready_count == 0:
                if weight is not None and int(weight) > 0:
                    add_code_fn(
                        "WEIGHT_TO_EMPTY_BACKEND",
                        severity="critical",
                        evidence=f"Backend '{service_name}' has weight={weight} but 0 ready endpoints.",
                        remediation="Shift weight to 0 via traefik_set_traffic_weights until backend pods are Ready.",
                    )
                if not allow_empty_svc:
                    add_code_fn(
                        "EMPTY_SERVICE_NOT_ALLOWED",
                        severity="error",
                        evidence=f"Service '{service_name}' has 0 ready endpoints and allowEmptyServices=false.",
                        remediation="Scale up or fix crashing pods backing Service '" + service_name + "'.",
                    )
                add_code_fn(
                    "NO_READY_ENDPOINTS",
                    severity="critical",
                    evidence=f"Service '{namespace}/{service_name}' has 0 ready endpoints (notReady={not_ready_count}).",
                    remediation="Inspect pod readiness probes and container logs for Service '" + service_name + "'.",
                )
            elif not_ready_count > 0:
                add_code_fn(
                    "PARTIAL_ENDPOINTS",
                    severity="warning",
                    evidence=f"Service '{service_name}' has {ready_count}/{total_ep} ready endpoints ({not_ready_count} not ready).",
                    remediation="Investigate unhealthy pod replicas in Service '" + service_name + "'.",
                )

        # Check runtime serverStatus UP/DOWN
        server_status = "UP"
        for rts in self.runtime.get_protocol_snapshot("http").get("services") or []:
            if f"{namespace}-{service_name}".lower() in str(rts.get("name", "")).lower():
                st_map = rts.get("serverStatus") or {}
                if any(str(v).upper() != "UP" for v in st_map.values()):
                    server_status = "DOWN"
                    add_code_fn(
                        "BACKEND_HEALTHCHECK_DOWN",
                        severity="error",
                        evidence=f"Traefik active healthCheck reports backend server(s) DOWN for '{service_name}': {st_map}",
                        remediation="Verify backend healthCheck path and pod health.",
                    )

        backends_out.append({
            "name": service_name,
            "namespace": namespace,
            "port": port,
            "weight": weight,
            "exists": True,
            "ready_endpoints": ready_count,
            "server_status": server_status,
        })

    # ── T12: traefik_trace_request ─────────────────────────────────────────────

    def get_known_route_hosts(self) -> Set[str]:
        """Collect all hostnames configured across cluster routes and runtime routers."""
        hosts: Set[str] = set()
        for r in self.list_routes("_all").get("routes") or []:
            for h in r.get("hosts") or []:
                if h and h != "*":
                    hosts.add(h.lower())
        for proto in ("http", "tcp"):
            for rt in self.runtime.get_protocol_snapshot(proto).get("routers") or []:
                for h in extract_hosts_from_rule(rt.get("rule", "")):
                    if h and h != "*":
                        hosts.add(h.lower())
        return hosts

    async def trace_request(
        self,
        request: Union[TraceRequestSpec, Dict[str, Any]],
        entry_point: Optional[str] = None,
        probe: Optional[Union[bool, ProbeOptions, Dict[str, Any]]] = None,
        top_n: int = 5,
    ) -> Dict[str, Any]:
        req_obj = request if isinstance(request, TraceRequestSpec) else TraceRequestSpec.model_validate(request)
        if isinstance(probe, bool):
            probe_obj = ProbeOptions(enabled=probe)
        elif isinstance(probe, ProbeOptions):
            probe_obj = probe
        elif isinstance(probe, dict):
            probe_obj = ProbeOptions.model_validate(probe)
        else:
            probe_obj = ProbeOptions(enabled=False)

        # Parse url if provided
        host = req_obj.host or ""
        path = req_obj.path or "/"
        query_dict = dict(req_obj.query or {})
        scheme = "https"
        if req_obj.url:
            parts = urlsplit(req_obj.url)
            scheme = parts.scheme or "https"
            host = parts.hostname or host
            path = parts.path or "/"
            for qk, qv in parse_qsl(parts.query, keep_blank_values=True):
                query_dict.setdefault(qk, qv)

        if not host and not req_obj.sni:
            raise TraefikRouteConfigError("trace_request requires either request.url, request.host, or request.sni.")

        eval_req = {
            "host": host,
            "path": path,
            "method": req_obj.method,
            "headers": req_obj.headers or {},
            "query": query_dict,
            "client_ip": req_obj.client_ip,
            "sni": req_obj.sni or host,
        }

        proto = req_obj.protocol.lower()
        candidates: List[Dict[str, Any]] = []

        # Collect routers from runtime snapshot + stored routes
        rt_snap = self.runtime.get_protocol_snapshot(proto)
        if rt_snap.get("routers"):
            for r in rt_snap["routers"]:
                if str(r.get("status", "enabled")).lower() == "disabled":
                    continue
                r_eps = r.get("entryPoints") or []
                if entry_point:
                    if entry_point not in r_eps:
                        continue
                elif r_eps and set(r_eps).issubset({"traefik", "metrics"}):
                    # Skip internal Traefik dashboard/metrics routers unless explicitly requested
                    continue
                rule_str = r.get("rule", "")
                candidates.append({
                    "name": r["name"],
                    "rule": rule_str,
                    "priority": compute_default_priority(rule_str, r.get("priority")),
                    "entryPoints": r.get("entryPoints") or [],
                    "middlewares": r.get("middlewares") or [],
                    "service": r.get("service", ""),
                    "provider": r.get("provider", "kubernetescrd"),
                    "source_uri": None,
                })
        else:
            r_kind = "IngressRouteTCP" if proto == "tcp" else "IngressRoute"
            for obj in self.list_objects(r_kind, None):
                m = obj.get("metadata") or {}
                ns = m.get("namespace") or "default"
                r_name = m.get("name") or ""
                spec = obj.get("spec") or {}
                r_eps = spec.get("entryPoints") or []
                if entry_point and entry_point not in r_eps:
                    continue
                for idx, rl in enumerate(spec.get("routes") or []):
                    rule_str = rl.get("match", "")
                    candidates.append({
                        "name": f"{ns}-{r_name}-{idx}@kubernetescrd",
                        "rule": rule_str,
                        "priority": compute_default_priority(rule_str, rl.get("priority")),
                        "entryPoints": r_eps,
                        "middlewares": [mw.get("name", "") for mw in rl.get("middlewares") or []],
                        "service": (rl.get("services") or [{}])[0].get("name", ""),
                        "services": rl.get("services") or [],
                        "provider": "kubernetescrd",
                        "source_uri": f"traefik://manifests/{r_kind}/{ns}/{r_name}",
                    })

        # Sort by priority descending
        candidates.sort(key=lambda c: -int(c.get("priority", 0)))

        matched_list: List[Dict[str, Any]] = []
        near_misses: List[Dict[str, Any]] = []

        for cand in candidates:
            ok, matched_c, failed_c = evaluate_rule_against_request(cand["rule"], eval_req)
            if ok:
                matched_list.append({**cand, "matched_clauses": matched_c})
            elif matched_c:
                near_misses.append({
                    "router": cand["name"],
                    "rule": cand["rule"],
                    "priority": cand["priority"],
                    "matched_clauses": matched_c,
                    "failed_clauses": failed_c,
                })

        winner = matched_list[0] if matched_list else None
        shadowed = matched_list[1 : max(1, int(top_n))] if len(matched_list) > 1 else []

        mw_chain: List[Dict[str, Any]] = []
        svc_tree: List[Dict[str, Any]] = []
        if winner:
            for idx, mw_name in enumerate(winner.get("middlewares") or []):
                mw_chain.append({"order": idx, "name": mw_name})
            if winner.get("services"):
                svc_tree = list(winner["services"])
            elif winner.get("service"):
                svc_tree = [{"name": winner["service"]}]

        # Optional live HTTP/TLS probe with SSRF guard
        probe_res: Optional[Dict[str, Any]] = None
        if probe_obj.enabled:
            target_host = (host or req_obj.sni or "").lower().split(":")[0]
            known_hosts = self.get_known_route_hosts()
            if not self.config.probe_allow_any_host and target_host not in known_hosts:
                raise TraefikSSRFBlockedError(
                    f"SSRF guard blocked live probe to host '{target_host}' because it does not match any known route hostname in the cluster ({sorted(known_hosts)})."
                )
            query_suffix = f"?{urlsplit(req_obj.url).query}" if (req_obj.url and urlsplit(req_obj.url).query) else ""
            lb_base = self.config.traefik_https_url if scheme == "https" else self.config.traefik_http_url
            if not lb_base:
                lb_base = self.config.traefik_http_url or self.config.traefik_https_url
            if lb_base and target_host not in ("localhost", "127.0.0.1"):
                probe_url = f"{lb_base.rstrip('/')}{path}{query_suffix}"
            else:
                probe_url = req_obj.url or f"{scheme}://{target_host}{path}"
            probe_res = await self._execute_live_probe(probe_url, target_host, probe_obj, req_obj.headers)

        summary = (
            f"Matched router '{winner['name']}' (priority={winner['priority']}, service='{winner.get('service')}')"
            if winner
            else f"No active {proto.upper()} router matched host='{host}' path='{path}'."
        )
        trace = RequestTrace(
            matched=winner is not None,
            summary=summary,
            matched_router=winner,
            source_resource_uri=winner.get("source_uri") if winner else None,
            middleware_chain=mw_chain,
            service_tree=svc_tree,
            shadowed_routers=shadowed,
            near_misses=near_misses[: max(1, int(top_n))],
            probe_result=probe_res,
        )
        return trace.model_dump()

    async def _execute_live_probe(
        self,
        url: str,
        host: str,
        probe: ProbeOptions,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Perform a safe HEAD/GET probe without returning response bodies."""
        req_headers = dict(headers or {})
        req_headers.setdefault("Host", host)
        try:
            async with httpx.AsyncClient(
                verify=False,
                follow_redirects=False,
                timeout=float(probe.timeout_seconds),
            ) as hclient:
                resp = await hclient.request(probe.method, url, headers=req_headers)
                expected_ok = (
                    resp.status_code in probe.expect_status
                    if probe.expect_status
                    else 200 <= resp.status_code < 400
                )
                return {
                    "reachable": True,
                    "url": url,
                    "method": probe.method,
                    "status_code": resp.status_code,
                    "expected_status_ok": expected_ok,
                    "headers": redact_headers(dict(resp.headers)),
                    "request_headers_sent": redact_headers(req_headers),
                }
        except Exception as exc:
            return {
                "reachable": False,
                "url": url,
                "method": probe.method,
                "error": str(exc),
                "request_headers_sent": redact_headers(req_headers),
            }

    # ── T13: traefik_compare_traffic_metrics ───────────────────────────────────

    async def compare_traffic_metrics(
        self,
        scope: str = "service",
        name: str = "",
        namespace: str = "default",
        baseline_window: str = "1h",
        comparison_window: str = "15m",
        include_backend_split: bool = True,
    ) -> Dict[str, Any]:
        configured_backends: Optional[List[Dict[str, Any]]] = None
        if scope == "service":
            ts = self.get_object("TraefikService", namespace, name) or self.get_object(
                "TraefikService", namespace, f"{name}-wrr"
            )
            if ts:
                ts_spec = ts.get("spec") or {}
                configured_backends = ((ts_spec.get("weighted") or {}).get("services")) or []
                if not configured_backends and ts_spec.get("mirroring"):
                    mir = ts_spec["mirroring"]
                    configured_backends = [{"name": mir.get("name"), "port": mir.get("port"), "weight": 100}]
                    for ms in mir.get("mirrors") or []:
                        configured_backends.append({"name": ms.get("name"), "port": ms.get("port"), "weight": ms.get("percent", 0)})
        res = self.prometheus.compare_windows(
            scope=scope,
            name=name,
            namespace=namespace,
            baseline_window=baseline_window,
            comparison_window=comparison_window,
            configured_backends=configured_backends,
        )
        if not include_backend_split:
            res["backend_split"] = []
        return res

    # ── T14: traefik_analyze_logs ──────────────────────────────────────────────

    def set_mock_logs(self, source: str, lines: List[str]) -> None:
        self._mock_logs[source] = list(lines)

    async def analyze_logs(
        self,
        source: str = "access",
        since: str = "15m",
        filters: Optional[Dict[str, Any]] = None,
        group_by: str = "status",
        limit_samples: int = 5,
    ) -> Dict[str, Any]:
        src = source.strip().lower()
        if src not in ("access", "controller"):
            raise TraefikOperationError("source must be 'access' or 'controller'.")

        static_cfg = self.get_static_config()
        if src == "access" and (static_cfg.get("accessLog") or {}).get("enabled") is False:
            raise TraefikOperationError(
                "Traefik access logs are disabled in static configuration (accessLog.enabled=false). "
                "Enable accessLog in Traefik Helm values or use source='controller' to inspect controller logs."
            )

        lines = list(self._mock_logs.get(src) or [])
        if not lines and self._try_init_k8s() and self.k8s_core_v1:
            try:
                pods = self.k8s_core_v1.list_namespaced_pod(
                    namespace=self.config.traefik_namespace,
                    label_selector="app.kubernetes.io/name=traefik",
                )
                fetch_tail = max(int(self.config.log_max_lines) * 4, 5000)
                for pod in getattr(pods, "items", []) or []:
                    pod_name = getattr(getattr(pod, "metadata", None), "name", None)
                    if not pod_name:
                        continue
                    raw_log = self.k8s_core_v1.read_namespaced_pod_log(
                        name=pod_name,
                        namespace=self.config.traefik_namespace,
                        tail_lines=fetch_tail,
                    )
                    if raw_log:
                        for ln in raw_log.splitlines():
                            is_access_ln = (
                                '"DownstreamStatus"' in ln
                                or '"OriginStatus"' in ln
                                or (" - - [" in ln and "HTTP/" in ln)
                            )
                            if src == "access" and is_access_ln:
                                lines.append(ln)
                            elif src == "controller" and not is_access_ln:
                                lines.append(ln)
            except Exception:
                pass

        res = analyze_log_lines(
            lines=lines[-self.config.log_max_lines :],
            source=src,
            filters=filters,
            group_by=group_by,
            limit_samples=limit_samples,
        )
        res["since"] = since
        res["summary"] = (
            f"Scanned {res['total_lines_scanned']} {src} log line(s); "
            f"{res['matched_lines']} matched filter criteria (grouped by {group_by})."
        )
        return res

    # ── T15: traefik_audit_configuration ───────────────────────────────────────

    async def audit_configuration(
        self,
        namespaces: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        min_severity: str = "low",
        max_findings: int = 50,
    ) -> Dict[str, Any]:
        ns_filter = None if not namespaces else (namespaces[0] if len(namespaces) == 1 else None)
        static_cfg = self.get_static_config()
        routes = list(self.list_routes(ns_filter or "_all").get("routes") or [])
        # Also include standalone TraefikService CRDs so HYG-003 (unused TraefikService) and REL-002 (missing WRR healthCheck) run accurately
        for ts_obj in self.list_objects("TraefikService", ns_filter or "_all"):
            ts_meta = ts_obj.get("metadata") or {}
            ts_ns = ts_meta.get("namespace") or "default"
            ts_name = ts_meta.get("name") or ""
            ts_refs = self.find_references_to_object("TraefikService", ts_ns, ts_name)
            routes.append({
                "kind": "TraefikService",
                "name": ts_name,
                "namespace": ts_ns,
                "apiVersion": ts_obj.get("apiVersion", TRAEFIK_API_VERSION),
                "annotations": ts_meta.get("annotations") or {},
                "spec": ts_obj.get("spec") or {},
                "referenced_by": ts_refs,
                "referenced_by_count": len(ts_refs),
            })
        if namespaces and len(namespaces) > 1:
            ns_set = set(namespaces)
            routes = [r for r in routes if r.get("namespace") in ns_set]
        policies = self.list_policies(ns_filter or "_all").get("policies") or []
        if namespaces and len(namespaces) > 1:
            policies = [p for p in policies if p.get("namespace") in set(namespaces)]
        certs = self.list_certificates(ns_filter or "_all").get("certificates") or []
        if namespaces and len(namespaces) > 1:
            certs = [c for c in certs if c.get("namespace") in set(namespaces)]
        gw_items = self.list_gateway_resources(ns_filter or "_all").get("items") or []
        if namespaces and len(namespaces) > 1:
            gw_items = [g for g in gw_items if g.get("namespace") in set(namespaces)]

        existing_svcs = {
            ((s.get("metadata") or {}).get("namespace", "default"), (s.get("metadata") or {}).get("name", ""))
            for s in self.list_objects("Service", None)
        }

        return run_configuration_audit(
            static_config=static_cfg,
            routes=routes,
            policies=policies,
            certificates=certs,
            gateways=gw_items,
            existing_services=existing_svcs,
            has_legacy_containo_crds=self._has_legacy_containo_crds,
            cert_expiry_warning_days=self.config.cert_expiry_warning_days,
            categories=categories,
            min_severity=min_severity,
            max_findings=max_findings,
        )

    # ── 12 Read-Only MCP Resource Backing Methods ──────────────────────────────

    def get_server_capabilities(self) -> Dict[str, Any]:
        """R1: traefik://server/capabilities."""
        self._try_init_k8s()
        prom_status = self.prometheus.get_status()
        ver_info = self.runtime.get_version()
        static_cfg = self.get_static_config()
        provs = static_cfg.get("providers") or {}

        traefik_crds = {
            "ingressroutes": True,
            "ingressroutetcps": True,
            "ingressrouteudps": True,
            "traefikservices": True,
            "middlewares": True,
            "middlewaretcps": True,
            "tlsoptions": True,
            "tlsstores": True,
            "serverstransports": True,
            "serverstransporttcps": True,
        }
        gw_crds = {
            "gateways": True,
            "httproutes": True,
            "grpcroutes": True,
            "tlsroutes": True,
            "tcproutes": True,
        }
        legacy_containo = self._has_legacy_containo_crds
        if self._initialized and self.k8s_apiext_v1:
            try:
                crd_list = self.k8s_apiext_v1.list_custom_resource_definition()
                installed_names = {
                    getattr(getattr(c, "metadata", None), "name", "")
                    for c in (getattr(crd_list, "items", []) or [])
                }
                if installed_names:
                    for plural in list(traefik_crds.keys()):
                        traefik_crds[plural] = f"{plural}.traefik.io" in installed_names
                    for plural in list(gw_crds.keys()):
                        gw_crds[plural] = f"{plural}.gateway.networking.k8s.io" in installed_names
                    if any(n.endswith(".traefik.containo.us") for n in installed_names):
                        legacy_containo = True
                        self._has_legacy_containo_crds = True
            except Exception:
                pass

        return {
            "server_name": self.config.name,
            "server_version": self.config.version,
            "allow_write": bool(self.config.allow_write),
            "toolsets": list(self.config.toolsets),
            "cluster_connected": self._initialized or bool(self._memory_store),
            "traefik_version": ver_info.get("version", "3.6.x"),
            "runtime_api_reachable": self.runtime.is_reachable(),
            "prometheus": prom_status,
            "crds_installed": {
                "traefik.io": traefik_crds,
                "gateway.networking.k8s.io": gw_crds,
                "legacy_containo_us_present": legacy_containo,
            },
            "enabled_providers": [k for k, v in provs.items() if isinstance(v, dict) and v.get("enabled", True)],
            "watched_namespaces": static_cfg.get("watched_namespaces") or ["_all"],
            "protected_namespaces": list(self.config.protected_namespaces),
            "allowed_namespaces": self.config.allowed_namespaces,
        }

    def get_kube_contexts(self) -> Dict[str, Any]:
        """R2: traefik://cluster/contexts."""
        try:
            contexts, active = k8s_config.list_kube_config_contexts(
                config_file=self.config.kubernetes.kubeconfig if self.config.kubernetes else None
            )
            ctx_list = [
                {
                    "name": c.get("name"),
                    "cluster": (c.get("context") or {}).get("cluster"),
                    "namespace": (c.get("context") or {}).get("namespace", "default"),
                }
                for c in (contexts or [])
            ]
            return {
                "active_context": (active or {}).get("name"),
                "configured_context": self.config.kubernetes.context_name if self.config.kubernetes else None,
                "in_cluster": bool(self.config.kubernetes.in_cluster) if self.config.kubernetes else False,
                "contexts": ctx_list,
            }
        except Exception:
            return {
                "active_context": self.config.kubernetes.context_name if self.config.kubernetes else "default",
                "configured_context": self.config.kubernetes.context_name if self.config.kubernetes else None,
                "in_cluster": False,
                "contexts": [],
            }

    def set_static_config(self, cfg: Dict[str, Any]) -> None:
        self._static_config_override = copy.deepcopy(cfg)

    def get_static_config(self) -> Dict[str, Any]:
        """R3: traefik://instance/static-config (redacted)."""
        if self._static_config_override is not None:
            return redact_static_config(copy.deepcopy(self._static_config_override))

        default_static = {
            "traefikNamespace": self.config.traefik_namespace,
            "replicas": 2,
            "image": "traefik:v3.6",
            "api": {"dashboard": True, "insecure": False},
            "entryPoints": {
                "web": {
                    "address": ":80",
                    "http": {"redirections": {"entryPoint": {"to": "websecure", "scheme": "https", "permanent": True}}},
                },
                "websecure": {
                    "address": ":443",
                    "forwardedHeaders": {"insecure": False, "trustedIPs": ["10.0.0.0/8"]},
                    "http3": {"enabled": True},
                },
                "tcp": {"address": ":9443"},
                "udp": {"address": ":5353/udp"},
            },
            "providers": {
                "kubernetesCRD": {
                    "enabled": True,
                    "allowCrossNamespace": False,
                    "allowExternalNameServices": False,
                    "allowEmptyServices": False,
                    "ingressClass": None,
                },
                "kubernetesIngress": {"enabled": True, "ingressClass": None},
                "kubernetesIngressNGINX": {"enabled": False, "ingressClass": "nginx"},
                "kubernetesGateway": {"enabled": True, "experimentalChannel": True},
            },
            "certificatesResolvers": {
                "letsencrypt": {"challengeType": "tlsChallenge"},
            },
            "metrics": {"prometheus": {"enabled": True, "addRoutersLabels": True}},
            "accessLog": {"enabled": True, "format": "json"},
            "plugins": {},
            "watched_namespaces": ["_all"],
        }
        # Overlay live Traefik Deployment/DaemonSet CLI flags & runtime entrypoints when connected to a real cluster
        if self._try_init_k8s() and self.k8s_apps_v1:
            try:
                deploys = self.k8s_apps_v1.list_namespaced_deployment(namespace=self.config.traefik_namespace)
                target_dep = None
                for dep in getattr(deploys, "items", []) or []:
                    d_name = (getattr(getattr(dep, "metadata", None), "name", "") or "").lower()
                    if "traefik" in d_name:
                        target_dep = dep
                        break
                if target_dep is not None:
                    spec_d = getattr(target_dep, "spec", None)
                    if spec_d and getattr(spec_d, "replicas", None) is not None:
                        default_static["replicas"] = int(spec_d.replicas)
                    tmpl_spec = getattr(getattr(spec_d, "template", None), "spec", None)
                    containers = getattr(tmpl_spec, "containers", []) or []
                    if containers:
                        c0 = containers[0]
                        if getattr(c0, "image", None):
                            default_static["image"] = str(c0.image)
                        cli_args = [str(a) for a in (getattr(c0, "args", None) or getattr(c0, "command", None) or [])]
                        live_eps: Dict[str, Dict[str, Any]] = {}
                        live_plugins: Dict[str, Dict[str, Any]] = {}
                        live_resolvers: Dict[str, Dict[str, Any]] = {}
                        watched_ns: List[str] = []
                        has_ep_args = any(a.startswith("--entrypoints.") or a.startswith("--entryPoints.") for a in cli_args)
                        for arg in cli_args:
                            clean_arg = arg.lstrip("-")
                            k_part, eq, v_part = clean_arg.partition("=")
                            val_str = v_part if eq else "true"
                            val_bool = val_str.strip().lower() in ("1", "true", "yes", "on")
                            kl = k_part.lower()
                            if kl == "api.insecure":
                                default_static["api"]["insecure"] = val_bool
                            elif kl == "api.dashboard":
                                default_static["api"]["dashboard"] = val_bool
                            elif kl.startswith("entrypoints."):
                                rest = k_part.split(".", 1)[1]
                                ep_parts = rest.split(".")
                                ep_n = ep_parts[0]
                                ep_d = live_eps.setdefault(ep_n, {})
                                sub = ".".join(ep_parts[1:]).lower()
                                if sub == "address":
                                    ep_d["address"] = val_str
                                elif sub == "forwardedheaders.insecure":
                                    ep_d.setdefault("forwardedHeaders", {})["insecure"] = val_bool
                                elif sub == "forwardedheaders.trustedips":
                                    ep_d.setdefault("forwardedHeaders", {})["trustedIPs"] = [
                                        x.strip() for x in val_str.split(",") if x.strip()
                                    ]
                                elif sub == "http.redirections.entrypoint.to":
                                    ep_d.setdefault("http", {}).setdefault("redirections", {}).setdefault("entryPoint", {})["to"] = val_str
                                elif sub == "http.redirections.entrypoint.scheme":
                                    ep_d.setdefault("http", {}).setdefault("redirections", {}).setdefault("entryPoint", {})["scheme"] = val_str
                                elif sub == "http.redirections.entrypoint.permanent":
                                    ep_d.setdefault("http", {}).setdefault("redirections", {}).setdefault("entryPoint", {})["permanent"] = val_bool
                                elif sub == "http3" or sub == "http3.enabled":
                                    ep_d["http3"] = {"enabled": val_bool}
                            elif kl == "providers.kubernetescrd" or kl == "providers.kubernetescrd.enabled":
                                default_static["providers"]["kubernetesCRD"]["enabled"] = val_bool
                            elif kl == "providers.kubernetescrd.allowcrossnamespace":
                                default_static["providers"]["kubernetesCRD"]["allowCrossNamespace"] = val_bool
                            elif kl == "providers.kubernetescrd.allowexternalnameservices":
                                default_static["providers"]["kubernetesCRD"]["allowExternalNameServices"] = val_bool
                            elif kl == "providers.kubernetescrd.allowemptyservices":
                                default_static["providers"]["kubernetesCRD"]["allowEmptyServices"] = val_bool
                            elif kl == "providers.kubernetescrd.ingressclass":
                                default_static["providers"]["kubernetesCRD"]["ingressClass"] = val_str
                            elif kl == "providers.kubernetescrd.namespaces":
                                watched_ns.extend([x.strip() for x in val_str.split(",") if x.strip()])
                            elif kl == "providers.kubernetesingress" or kl == "providers.kubernetesingress.enabled":
                                default_static["providers"]["kubernetesIngress"]["enabled"] = val_bool
                            elif kl == "providers.kubernetesingress.ingressclass":
                                default_static["providers"]["kubernetesIngress"]["ingressClass"] = val_str
                            elif kl in ("providers.kubernetesingressnginx", "providers.kubernetesingressnginx.enabled"):
                                default_static["providers"]["kubernetesIngressNGINX"]["enabled"] = val_bool
                            elif kl == "providers.kubernetesingressnginx.ingressclass":
                                default_static["providers"]["kubernetesIngressNGINX"]["ingressClass"] = val_str
                            elif kl in ("providers.kubernetesgateway", "providers.kubernetesgateway.enabled"):
                                default_static["providers"]["kubernetesGateway"]["enabled"] = val_bool
                            elif kl == "providers.kubernetesgateway.experimentalchannel":
                                default_static["providers"]["kubernetesGateway"]["experimentalChannel"] = val_bool
                            elif kl.startswith("experimental.plugins.") or kl.startswith("experimental.localplugins."):
                                p_parts = k_part.split(".")
                                if len(p_parts) >= 3:
                                    p_name = p_parts[2]
                                    p_field = ".".join(p_parts[3:])
                                    live_plugins.setdefault(p_name, {})[p_field or "enabled"] = val_str
                            elif kl.startswith("certificatesresolvers."):
                                r_parts = k_part.split(".")
                                if len(r_parts) >= 2:
                                    r_name = r_parts[1]
                                    live_resolvers.setdefault(r_name, {})[".".join(r_parts[2:]) or "enabled"] = val_str
                            elif kl in ("accesslog", "accesslog.enabled"):
                                default_static["accessLog"]["enabled"] = val_bool
                            elif kl == "accesslog.format":
                                default_static["accessLog"]["format"] = val_str
                            elif kl in ("metrics.prometheus", "metrics.prometheus.enabled"):
                                default_static["metrics"]["prometheus"]["enabled"] = val_bool
                            elif kl == "metrics.prometheus.addrouterslabels":
                                default_static["metrics"]["prometheus"]["addRoutersLabels"] = val_bool
                            elif kl == "metrics.prometheus.addserviceslabels":
                                default_static["metrics"]["prometheus"]["addServicesLabels"] = val_bool
                        if has_ep_args and live_eps:
                            default_static["entryPoints"] = live_eps
                        default_static["plugins"] = live_plugins
                        if live_resolvers:
                            default_static["certificatesResolvers"] = live_resolvers
                        if watched_ns:
                            default_static["watched_namespaces"] = list(dict.fromkeys(watched_ns))
            except Exception:
                pass

            # Also merge runtime /api/entrypoints if reachable
            try:
                rt_eps = self.runtime.get_entrypoints()
                if rt_eps:
                    ep_map = default_static.setdefault("entryPoints", {})
                    for ep_item in rt_eps:
                        if isinstance(ep_item, dict) and ep_item.get("name"):
                            ep_entry = ep_map.setdefault(ep_item["name"], {})
                            if ep_item.get("address") and "address" not in ep_entry:
                                ep_entry["address"] = ep_item["address"]
            except Exception:
                pass

        return redact_static_config(default_static)

    def get_runtime_health(self) -> Dict[str, Any]:
        """R4: traefik://runtime/health."""
        return self.runtime.get_runtime_health()

    def get_runtime_protocol_snapshot(self, protocol: str = "http") -> Dict[str, Any]:
        """R5: traefik://runtime/{protocol}."""
        return self.runtime.get_protocol_snapshot(protocol)

    def get_runtime_protocol(self, protocol: str = "http") -> Dict[str, Any]:
        """Alias for get_runtime_protocol_snapshot (R5: traefik://runtime/{protocol})."""
        return self.get_runtime_protocol_snapshot(protocol)

    def list_routes(self, namespace: str = "_all") -> Dict[str, Any]:
        """R6: traefik://routes/{namespace}."""
        routes_out: List[Dict[str, Any]] = []
        rollouts = self.list_objects("Rollout", None if namespace == "_all" else namespace)
        argo_ts_names: Set[Tuple[str, str]] = set()
        for ro in rollouts:
            ro_ns = (ro.get("metadata") or {}).get("namespace", "default")
            tr = (
                (((ro.get("spec") or {}).get("strategy") or {}).get("canary") or {})
                .get("trafficRouting", {})
                .get("traefik", {})
            )
            if tr.get("weightedTraefikServiceName"):
                argo_ts_names.add((ro_ns, tr["weightedTraefikServiceName"]))

        for r_kind in ("IngressRoute", "IngressRouteTCP", "IngressRouteUDP"):
            for obj in self.list_objects(r_kind, namespace):
                meta = obj.get("metadata") or {}
                r_ns = meta.get("namespace") or "default"
                r_name = meta.get("name") or ""
                spec = obj.get("spec") or {}
                eps = spec.get("entryPoints") or []
                rules_match: List[str] = []
                rules_structured: List[Dict[str, Any]] = []
                mws: List[Dict[str, str]] = []
                backends: List[Dict[str, Any]] = []
                hosts: List[str] = []
                argo_managed = False

                for rl in spec.get("routes") or []:
                    m_str = rl.get("match", "")
                    if m_str:
                        rules_match.append(m_str)
                        rules_structured.append({"match": m_str, "priority": rl.get("priority")})
                        hosts.extend(extract_hosts_from_rule(m_str))
                    for mw in rl.get("middlewares") or []:
                        if isinstance(mw, dict):
                            mws.append(mw)
                    for svc in rl.get("services") or []:
                        if svc.get("kind") == "TraefikService":
                            ts_n = svc.get("name", "")
                            ts_ns = svc.get("namespace") or r_ns
                            if (ts_ns, ts_n) in argo_ts_names:
                                argo_managed = True
                            ts_obj = self.get_object("TraefikService", ts_ns, ts_n)
                            if ts_obj:
                                ts_meta = ts_obj.get("metadata") or {}
                                ts_anns = ts_meta.get("annotations") or {}
                                ts_lbls = ts_meta.get("labels") or {}
                                ts_orefs = ts_meta.get("ownerReferences") or []
                                if (
                                    ts_anns.get("argoproj.io/rollout-name")
                                    or ts_lbls.get("argoproj.io/rollout-name")
                                    or any(isinstance(o, dict) and o.get("kind") == "Rollout" for o in ts_orefs)
                                ):
                                    argo_managed = True
                                wrr = ((ts_obj.get("spec") or {}).get("weighted") or {}).get("services") or []
                                backends.append({
                                    "name": ts_n,
                                    "kind": "TraefikService",
                                    "weighted_backends": wrr,
                                    "argo_managed": argo_managed,
                                })
                            else:
                                backends.append({"name": ts_n, "kind": "TraefikService", "missing": True})
                        else:
                            backends.append(dict(svc))

                rt_router = self.runtime.find_runtime_router(
                    r_ns, r_name, protocol="tcp" if "TCP" in r_kind else ("udp" if "UDP" in r_kind else "http")
                )
                routes_out.append({
                    "kind": r_kind,
                    "name": r_name,
                    "namespace": r_ns,
                    "apiVersion": obj.get("apiVersion", TRAEFIK_API_VERSION),
                    "hosts": list(dict.fromkeys(hosts)),
                    "entryPoints": eps,
                    "tls": bool(spec.get("tls")),
                    "rules_match": rules_match,
                    "rules": rules_structured,
                    "middlewares": mws,
                    "middleware_count": len(mws),
                    "backends": backends,
                    "argo_managed": argo_managed,
                    "runtime_status": (rt_router or {}).get("status", "enabled"),
                })

        # Also include standard Kubernetes Ingress objects
        for ing in self.list_objects("Ingress", namespace):
            meta = ing.get("metadata") or {}
            i_ns = meta.get("namespace") or "default"
            i_name = meta.get("name") or ""
            anns = meta.get("annotations") or {}
            spec = ing.get("spec") or {}
            ing_class = spec.get("ingressClassName") or anns.get("kubernetes.io/ingress.class") or ""
            nginx_keys = sorted(k for k in anns if k.startswith("nginx.ingress.kubernetes.io/"))
            claimed_by = "kubernetesIngressNGINX" if (ing_class == "nginx" or nginx_keys) else "kubernetesIngress"
            hosts = [r.get("host") for r in spec.get("rules") or [] if r.get("host")]
            routes_out.append({
                "kind": "Ingress",
                "name": i_name,
                "namespace": i_ns,
                "hosts": hosts,
                "ingressClass": ing_class,
                "claimed_by_provider": claimed_by,
                "nginx_annotation_keys": nginx_keys,
                "tls": bool(spec.get("tls")),
                "backends": [],
                "runtime_status": "enabled",
            })

        return {"namespace": namespace, "count": len(routes_out), "routes": routes_out}

    def get_sanitized_manifest(self, kind: str, namespace: str, name: str) -> Dict[str, Any]:
        """R7: traefik://manifests/{kind}/{namespace}/{name}."""
        obj = self.get_object(kind, namespace, name)
        if not obj:
            return {
                "kind": kind,
                "namespace": namespace,
                "name": name,
                "found": False,
                "error": f"{kind} '{name}' not found in namespace '{namespace}'",
                "hint": f"Read traefik://routes/{namespace} or traefik://policies/{namespace}",
            }
        rv = (obj.get("metadata") or {}).get("resourceVersion")
        clean = sanitize_manifest(obj)
        return {
            "kind": kind,
            "namespace": namespace,
            "name": name,
            "found": True,
            "resource_version": rv,
            "manifest": clean,
            "yaml": yaml_dump(clean),
        }

    def list_policies(self, namespace: str = "_all") -> Dict[str, Any]:
        """R8: traefik://policies/{namespace}."""
        policies_out: List[Dict[str, Any]] = []
        for p_kind in ("Middleware", "MiddlewareTCP", "ServersTransport", "ServersTransportTCP", "TLSOption", "TLSStore"):
            for obj in self.list_objects(p_kind, namespace):
                meta = obj.get("metadata") or {}
                p_ns = meta.get("namespace") or "default"
                p_name = meta.get("name") or ""
                spec = obj.get("spec") or {}
                p_type = next(iter(spec.keys()), p_kind) if p_kind in ("Middleware", "MiddlewareTCP") else p_kind
                refs = self.find_references_to_object(p_kind, p_ns, p_name)
                policies_out.append({
                    "kind": p_kind,
                    "name": p_name,
                    "namespace": p_ns,
                    "type": p_type,
                    "spec": sanitize_manifest({"kind": p_kind, "spec": spec}).get("spec", {}),
                    "referenced_by": refs,
                    "runtime_status": "enabled",
                })
        return {"namespace": namespace, "count": len(policies_out), "policies": policies_out}

    def list_certificates(self, namespace: str = "_all") -> Dict[str, Any]:
        """R9: traefik://certificates/{namespace} (metadata only, NEVER private keys)."""
        certs_out: List[Dict[str, Any]] = []
        for sec in self.list_objects("Secret", namespace):
            meta = sec.get("metadata") or {}
            s_ns = meta.get("namespace") or "default"
            s_name = meta.get("name") or ""
            data = sec.get("data") or {}
            str_data = sec.get("stringData") or {}
            crt_raw = (
                data.get("tls.crt")
                or str_data.get("tls.crt")
                or data.get("ca.crt")
                or str_data.get("ca.crt")
                or data.get("tls.ca")
                or str_data.get("tls.ca")
            )
            if not crt_raw and sec.get("type") != "kubernetes.io/tls":
                continue
            if crt_raw:
                try:
                    info = parse_pem_certificate(crt_raw)
                    certs_out.append({
                        "secret_name": s_name,
                        "namespace": s_ns,
                        **info,
                    })
                except Exception:
                    certs_out.append({
                        "secret_name": s_name,
                        "namespace": s_ns,
                        "error": "Unable to parse X.509 certificate PEM",
                    })
        return {"namespace": namespace, "count": len(certs_out), "certificates": certs_out}

    def list_gateway_resources(self, namespace: str = "_all") -> Dict[str, Any]:
        """R10: traefik://gateway/{namespace} (read-only Gateway API inventory)."""
        items_out: List[Dict[str, Any]] = []
        for gw_kind in ("GatewayClass", "Gateway", "HTTPRoute", "GRPCRoute", "TLSRoute", "TCPRoute", "ReferenceGrant"):
            for obj in self.list_objects(gw_kind, namespace):
                meta = obj.get("metadata") or {}
                g_ns = meta.get("namespace") or "default"
                g_name = meta.get("name") or ""
                status = obj.get("status") or {}
                accepted = True
                programmed = True
                resolved_refs = True
                for cond in status.get("conditions") or []:
                    if cond.get("type") == "Accepted" and cond.get("status") == "False":
                        accepted = False
                    if cond.get("type") == "Programmed" and cond.get("status") == "False":
                        programmed = False
                for p in status.get("parents") or []:
                    for cond in p.get("conditions") or []:
                        if cond.get("type") == "Accepted" and cond.get("status") == "False":
                            accepted = False
                        if cond.get("type") == "ResolvedRefs" and cond.get("status") == "False":
                            resolved_refs = False
                items_out.append({
                    "kind": gw_kind,
                    "name": g_name,
                    "namespace": g_ns,
                    "accepted": accepted,
                    "programmed": programmed,
                    "resolved_refs": resolved_refs,
                    "spec": obj.get("spec") or {},
                })
        return {"namespace": namespace, "count": len(items_out), "items": items_out}

    def get_service_metrics_summary(self, namespace: str, service: str) -> Dict[str, Any]:
        """R11: traefik://metrics/{namespace}/{service}/summary."""
        configured_backends: Optional[List[Dict[str, Any]]] = None
        ts = self.get_object("TraefikService", namespace, service) or self.get_object(
            "TraefikService", namespace, f"{service}-wrr"
        )
        if ts:
            configured_backends = ((ts.get("spec") or {}).get("weighted") or {}).get("services") or []
        return self.prometheus.get_service_summary(
            namespace=namespace,
            service=service,
            configured_backends=configured_backends,
        )

    def set_crd_schema(self, kind: str, spec_properties: Dict[str, Any], strategies: Optional[Set[str]] = None) -> None:
        self._crd_schemas[kind] = dict(spec_properties)
        if strategies is not None:
            self._supported_strategies = set(strategies)

    def get_crd_schema(self, kind: str) -> Dict[str, Any]:
        """R12: traefik://schema/{kind}."""
        if kind in self._crd_schemas:
            return {
                "kind": kind,
                "apiVersion": TRAEFIK_API_VERSION,
                "spec_properties": self._crd_schemas[kind],
            }
        if kind in KIND_TO_CRD_META and self._try_init_k8s() and self.k8s_apiext_v1:
            grp, _, plural = KIND_TO_CRD_META[kind]
            crd_name = f"{plural}.{grp}"
            try:
                crd_obj = self.k8s_apiext_v1.read_custom_resource_definition(name=crd_name)
                crd_dict = client.ApiClient().sanitize_for_serialization(crd_obj)
                versions = (crd_dict.get("spec") or {}).get("versions") or []
                for ver_entry in versions:
                    if ver_entry.get("served", True):
                        spec_props = (
                            (((ver_entry.get("schema") or {}).get("openAPIV3Schema") or {}).get("properties") or {})
                            .get("spec", {})
                            .get("properties")
                        )
                        if isinstance(spec_props, dict) and spec_props:
                            summary_props = {
                                k: {"type": v.get("type", "object"), "description": (v.get("description") or "")[:140]}
                                for k, v in sorted(spec_props.items())
                                if isinstance(v, dict)
                            }
                            return {
                                "kind": kind,
                                "crd_name": crd_name,
                                "apiVersion": f"{grp}/{ver_entry.get('name', TRAEFIK_VERSION)}",
                                "source": "live_cluster_crd",
                                "spec_properties": summary_props,
                            }
            except Exception:
                pass
        default_props: Dict[str, Any] = {}
        if kind == "Middleware":
            default_props = {k: {"type": "object"} for k in sorted(DEFAULT_V3_MIDDLEWARE_SPEC_KEYS)}
        elif kind == "MiddlewareTCP":
            default_props = {k: {"type": "object"} for k in sorted(DEFAULT_V3_MIDDLEWARE_TCP_SPEC_KEYS)}
        elif kind == "IngressRoute":
            default_props = {
                "entryPoints": {"type": "array", "items": {"type": "string"}},
                "routes": {"type": "array", "strategies": sorted(self._supported_strategies)},
                "tls": {"type": "object"},
            }
        elif kind == "TraefikService":
            default_props = {
                "weighted": {"type": "object", "strategies": sorted(self._supported_strategies)},
                "mirroring": {"type": "object"},
            }
        else:
            default_props = {"spec": {"type": "object"}}
        return {
            "kind": kind,
            "apiVersion": TRAEFIK_API_VERSION,
            "spec_properties": default_props,
        }
