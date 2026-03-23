"""NGINX Ingress scanner — list Ingress resources, detect controller, classify complexity.

Ported from ing-switch pkg/scanner (MIT license).
Reference: docs/ing-switch/pkg/scanner/{ingress.go, controller.go, types.go}
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kubernetes.client import (
    NetworkingV1Api,
    CoreV1Api,
    ApiException,
)


NGINX_ANNOTATION_PREFIX = "nginx.ingress.kubernetes.io/"

# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class PathInfo:
    host: str = ""
    path: str = ""
    path_type: str = "Prefix"
    service_name: str = ""
    service_port: int = 80


@dataclass
class ServiceRef:
    namespace: str = ""
    name: str = ""
    port: int = 0


@dataclass
class ControllerInfo:
    detected: bool = False
    type: str = "unknown"
    version: str = "unknown"
    namespace: str = ""
    pod_name: str = ""


@dataclass
class IngressInfo:
    namespace: str = ""
    name: str = ""
    ingress_class: str = ""
    hosts: List[str] = field(default_factory=list)
    paths: List[PathInfo] = field(default_factory=list)
    tls_enabled: bool = False
    tls_secrets: List[str] = field(default_factory=list)
    annotations: Dict[str, str] = field(default_factory=dict)
    nginx_annotations: Dict[str, str] = field(default_factory=dict)
    services: List[ServiceRef] = field(default_factory=list)
    complexity: str = "simple"


@dataclass
class ScanResult:
    cluster_name: str = ""
    controller: ControllerInfo = field(default_factory=ControllerInfo)
    ingresses: List[IngressInfo] = field(default_factory=list)
    namespaces: List[str] = field(default_factory=list)


# ── Complexity classification ──────────────────────────────────────────────────

UNSUPPORTED_ANNOTATIONS = frozenset({
    "client-body-buffer-size",
    "snippets",
    "lua-resty-waf",
    "modsecurity-snippet",
    "configuration-snippet",
    "server-snippet",
})

COMPLEX_ANNOTATIONS = frozenset({
    "auth-url",
    "auth-response-headers",
    "canary",
    "canary-weight",
    "limit-rps",
    "limit-connections",
    "rewrite-target",
    "use-regex",
    "app-root",
    "affinity",
    "whitelist-source-range",
    "denylist-source-range",
    "proxy-body-size",
    "proxy-read-timeout",
    "proxy-connect-timeout",
})


def classify_complexity(nginx_annotations: Dict[str, str]) -> str:
    """Classify ingress complexity as simple | complex | unsupported."""
    if not nginx_annotations:
        return "simple"
    keys = set(nginx_annotations.keys())
    if keys & UNSUPPORTED_ANNOTATIONS:
        return "unsupported"
    if keys & COMPLEX_ANNOTATIONS:
        return "complex"
    return "simple"


# ── Scanner ────────────────────────────────────────────────────────────────────

class NginxMigrationScanner:
    """Scans a Kubernetes cluster for Ingress resources and detects the controller."""

    # Label selectors and controller types to probe
    _CONTROLLER_SELECTORS = [
        ("app.kubernetes.io/name=ingress-nginx", "ingress-nginx"),
        ("app=ingress-nginx", "ingress-nginx"),
        ("app.kubernetes.io/name=traefik", "traefik"),
        ("app=traefik", "traefik"),
        ("app=kong", "kong"),
        ("app.kubernetes.io/name=kong", "kong"),
        ("app.kubernetes.io/name=haproxy-ingress", "haproxy"),
    ]

    _CANDIDATE_NAMESPACES = [
        "ingress-nginx", "nginx-ingress", "kube-system",
        "traefik", "kong", "default",
    ]

    def __init__(self, networking_api: NetworkingV1Api, core_api: CoreV1Api, cluster_name: str = ""):
        self._networking = networking_api
        self._core = core_api
        self._cluster_name = cluster_name

    # ── Public API ─────────────────────────────────────────────────────────

    def scan(self, namespace: Optional[str] = None) -> ScanResult:
        """Perform a full cluster scan.

        Args:
            namespace: Optional namespace filter; None = all namespaces.

        Returns:
            ScanResult with ingresses, controller info, and namespaces.
        """
        ingresses = self._list_ingresses(namespace)
        controller = self._detect_controller()
        namespaces = sorted({ing.namespace for ing in ingresses})

        return ScanResult(
            cluster_name=self._cluster_name,
            controller=controller,
            ingresses=ingresses,
            namespaces=namespaces,
        )

    # ── Private helpers ────────────────────────────────────────────────────

    def _list_ingresses(self, namespace: Optional[str] = None) -> List[IngressInfo]:
        """List Ingress v1 objects, parse into IngressInfo."""
        try:
            if namespace:
                result = self._networking.list_namespaced_ingress(namespace)
            else:
                result = self._networking.list_ingress_for_all_namespaces()
        except ApiException as e:
            return []

        infos = [self._parse_ingress(ing) for ing in result.items]
        infos.sort(key=lambda i: (i.namespace, i.name))
        return infos

    def _parse_ingress(self, ing: Any) -> IngressInfo:
        """Parse a V1Ingress object into an IngressInfo dataclass."""
        info = IngressInfo(
            namespace=ing.metadata.namespace or "default",
            name=ing.metadata.name,
            annotations=dict(ing.metadata.annotations or {}),
        )

        # Ingress class
        if ing.spec.ingress_class_name:
            info.ingress_class = ing.spec.ingress_class_name
        elif "kubernetes.io/ingress.class" in info.annotations:
            info.ingress_class = info.annotations["kubernetes.io/ingress.class"]

        # TLS
        if ing.spec.tls:
            info.tls_enabled = True
            for tls in ing.spec.tls:
                if tls.secret_name:
                    info.tls_secrets.append(tls.secret_name)

        # Hosts, paths, services
        host_set = set()
        service_map: Dict[str, ServiceRef] = {}

        for rule in (ing.spec.rules or []):
            if rule.host:
                host_set.add(rule.host)
            if not rule.http:
                continue
            for path_obj in (rule.http.paths or []):
                pi = PathInfo(host=rule.host or "")
                pi.path = path_obj.path or "/"
                if path_obj.path_type:
                    pi.path_type = path_obj.path_type
                if path_obj.backend and path_obj.backend.service:
                    svc = path_obj.backend.service
                    pi.service_name = svc.name
                    port = svc.port
                    if port:
                        pi.service_port = port.number if port.number else 80
                    key = f"{info.namespace}/{svc.name}"
                    service_map[key] = ServiceRef(
                        namespace=info.namespace,
                        name=svc.name,
                        port=pi.service_port,
                    )
                info.paths.append(pi)

        info.hosts = sorted(host_set)
        info.services = list(service_map.values())

        # Extract nginx annotations
        for k, v in info.annotations.items():
            if k.startswith(NGINX_ANNOTATION_PREFIX):
                short_key = k[len(NGINX_ANNOTATION_PREFIX):]
                info.nginx_annotations[short_key] = v

        info.complexity = classify_complexity(info.nginx_annotations)
        return info

    def _detect_controller(self) -> ControllerInfo:
        """Detect the running ingress controller by probing known label selectors."""
        for ns in self._CANDIDATE_NAMESPACES:
            for selector, ctrl_type in self._CONTROLLER_SELECTORS:
                try:
                    pods = self._core.list_namespaced_pod(
                        namespace=ns,
                        label_selector=selector,
                        limit=1,
                    )
                    if not pods.items:
                        continue

                    pod = pods.items[0]
                    version = self._extract_version(pod)
                    return ControllerInfo(
                        detected=True,
                        type=ctrl_type,
                        version=version,
                        namespace=ns,
                        pod_name=pod.metadata.name,
                    )
                except ApiException:
                    continue

        # Fallback: broad search
        try:
            pods = self._core.list_pod_for_all_namespaces(
                label_selector="app.kubernetes.io/name=ingress-nginx",
                limit=1,
            )
            if pods.items:
                pod = pods.items[0]
                return ControllerInfo(
                    detected=True,
                    type="ingress-nginx",
                    version=self._extract_version(pod),
                    namespace=pod.metadata.namespace,
                    pod_name=pod.metadata.name,
                )
        except ApiException:
            pass

        return ControllerInfo(detected=False, type="unknown")

    @staticmethod
    def _extract_version(pod: Any) -> str:
        """Extract version from pod container image tag."""
        try:
            for container in pod.spec.containers:
                image = container.image or ""
                if ":" in image:
                    return image.rsplit(":", 1)[-1]
        except Exception:
            pass
        return "unknown"


# ── Serialization helpers ──────────────────────────────────────────────────────

# Annotations that are internal Kubernetes bookkeeping and should never be
# sent to remote agents — they duplicate the spec and massively inflate
# payload size.
_NOISY_ANNOTATIONS = frozenset({
    "kubectl.kubernetes.io/last-applied-configuration",
})


def _clean_annotations(annotations: Dict[str, str]) -> Dict[str, str]:
    """Remove internal Kubernetes bookkeeping annotations."""
    return {k: v for k, v in annotations.items() if k not in _NOISY_ANNOTATIONS}


def scan_result_to_dict(result: ScanResult) -> Dict[str, Any]:
    """Convert a ScanResult to a JSON-serializable dict.

    Strips noisy internal annotations (e.g. ``last-applied-configuration``)
    that duplicate the spec and inflate payload size.
    """
    return {
        "clusterName": result.cluster_name,
        "controller": {
            "detected": result.controller.detected,
            "type": result.controller.type,
            "version": result.controller.version,
            "namespace": result.controller.namespace,
            "podName": result.controller.pod_name,
        },
        "ingresses": [
            {
                "namespace": ing.namespace,
                "name": ing.name,
                "ingressClass": ing.ingress_class,
                "hosts": ing.hosts,
                "paths": [
                    {
                        "host": p.host,
                        "path": p.path,
                        "pathType": p.path_type,
                        "serviceName": p.service_name,
                        "servicePort": p.service_port,
                    }
                    for p in ing.paths
                ],
                "tlsEnabled": ing.tls_enabled,
                "tlsSecrets": ing.tls_secrets,
                "annotations": _clean_annotations(ing.annotations),
                "nginxAnnotations": ing.nginx_annotations,
                "services": [
                    {"namespace": s.namespace, "name": s.name, "port": s.port}
                    for s in ing.services
                ],
                "complexity": ing.complexity,
            }
            for ing in result.ingresses
        ],
        "namespaces": result.namespaces,
    }


def scan_result_to_compact_dict(result: ScanResult) -> Dict[str, Any]:
    """Convert a ScanResult to a *compact* JSON-serializable dict.

    Drops full ``annotations`` and ``paths`` to keep the response small.
    Use when the full scan_result would push the total payload beyond
    transport / context-window limits.  The ``nginxAnnotations`` (which
    drive the analysis) are always preserved.
    """
    return {
        "clusterName": result.cluster_name,
        "controller": {
            "detected": result.controller.detected,
            "type": result.controller.type,
            "version": result.controller.version,
            "namespace": result.controller.namespace,
        },
        "ingresses": [
            {
                "namespace": ing.namespace,
                "name": ing.name,
                "ingressClass": ing.ingress_class,
                "hosts": ing.hosts,
                "tlsEnabled": ing.tls_enabled,
                "nginxAnnotations": ing.nginx_annotations,
                "complexity": ing.complexity,
            }
            for ing in result.ingresses
        ],
        "namespaces": result.namespaces,
    }

