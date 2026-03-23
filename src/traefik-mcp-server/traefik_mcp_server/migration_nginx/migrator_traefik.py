"""Traefik migration — generate Middleware CRDs and updated Ingress manifests.

Ported from ing-switch pkg/migrator/traefik (MIT license).
Reference: docs/ing-switch/pkg/migrator/traefik/{middleware.go, migrator.go}
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import yaml as pyyaml

from traefik_mcp_server.migration_nginx.scanner import IngressInfo, ScanResult
from traefik_mcp_server.migration_nginx.analyzer import AnalysisReport
from traefik_mcp_server.migration_nginx.migration_plan import (
    filter_ingress_for_plan,
    format_inject_middleware_ref,
    normalize_ignore_key,
    parse_migration_plan,
    plan_entry_for_ingress,
)
from traefik_mcp_server.traefik_middleware_builders import (
    build_middleware_crd,
    middleware_dict_to_yaml,
    nginx_rate_limit_from_annotations,
    parse_nginx_proxy_body_size_to_bytes,
    spec_add_prefix,
    spec_basic_auth,
    spec_buffering,
    spec_forward_auth,
    spec_headers_block,
    spec_inflight_req,
    spec_ip_allowlist,
    spec_ip_denylist,
    spec_rate_limit,
    spec_redirect_scheme,
    spec_replace_path,
    spec_replace_path_regex,
)



# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class MiddlewareSpec:
    name: str = ""
    namespace: str = ""
    yaml: str = ""


@dataclass
class GeneratedFile:
    rel_path: str = ""
    content: str = ""
    description: str = ""
    category: str = ""  # install | middleware | ingress | verify | guide | cleanup


# ── Middleware generators ──────────────────────────────────────────────────────

def _get(annotations: Dict[str, str], key: str, default: str = "") -> str:
    """Safely look up an annotation value."""
    v = annotations.get(key, "")
    return v if v else default


_MIGRATION_LABEL = "migration.source"


def _mw_yaml(
    mw_name: str,
    ns: str,
    ing_name: str,
    spec: Dict[str, Any],
    preamble: str = "",
) -> MiddlewareSpec:
    obj = build_middleware_crd(
        mw_name,
        ns,
        spec,
        labels={_MIGRATION_LABEL: ing_name},
    )
    body = middleware_dict_to_yaml(obj)
    if preamble:
        body = preamble.rstrip() + "\n" + body
    return MiddlewareSpec(name=mw_name, namespace=ns, yaml=body)


def _gen_ssl_redirect(name: str, ns: str, permanent: bool) -> MiddlewareSpec:
    suffix = "-force-ssl-redirect" if permanent else "-ssl-redirect"
    mw_name = name + suffix
    return _mw_yaml(mw_name, ns, name, spec_redirect_scheme(permanent=permanent))


def _gen_cors(name: str, ns: str, ann: Dict[str, str]) -> MiddlewareSpec:
    mw_name = f"{name}-cors"
    origin = _get(ann, "cors-allow-origin", "*")
    methods = _get(
        ann,
        "cors-allow-methods",
        "GET, PUT, POST, DELETE, PATCH, OPTIONS",
    )
    headers = _get(
        ann,
        "cors-allow-headers",
        "DNT,Keep-Alive,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization",
    )
    cred_raw = _get(ann, "cors-allow-credentials", "true")
    cred = cred_raw.lower() == "true"
    max_age = int(_get(ann, "cors-max-age", "1728000"))
    expose_raw = _get(ann, "cors-expose-headers")
    expose_list = (
        [x.strip() for x in expose_raw.split(",") if x.strip()] if expose_raw else None
    )
    spec = spec_headers_block(
        access_control_allow_origin_list=[origin],
        access_control_allow_methods=[methods],
        access_control_allow_headers=[headers],
        access_control_allow_credentials=cred,
        access_control_max_age=max_age,
        access_control_expose_headers=expose_list,
    )
    return _mw_yaml(mw_name, ns, name, spec)


def _gen_forward_auth(name: str, ns: str, ann: Dict[str, str]) -> MiddlewareSpec:
    mw_name = f"{name}-auth"
    auth_url = ann.get("auth-url", "")
    rh = ann.get("auth-response-headers")
    resp = (
        [h.strip() for h in rh.split(",") if h.strip()] if rh else None
    )
    spec = spec_forward_auth(
        auth_url,
        auth_response_headers=resp,
        trust_forward_header=True,
    )
    return _mw_yaml(mw_name, ns, name, spec)


def _gen_basic_auth(name: str, ns: str, ann: Dict[str, str]) -> MiddlewareSpec:
    mw_name = f"{name}-basicauth"
    secret = _get(ann, "auth-secret", f"{name}-basic-auth")
    realm = _get(ann, "auth-realm", "traefik")
    note = (
        f"# NOTE: Secret must contain htpasswd-encoded credentials.\n"
        f"# kubectl create secret generic {secret} "
        f'--from-literal=users="$(htpasswd -nb user password)" -n {ns}\n'
    )
    return _mw_yaml(mw_name, ns, name, spec_basic_auth(secret, realm), preamble=note)


def _gen_rate_limit(name: str, ns: str, ann: Dict[str, str]) -> MiddlewareSpec:
    mw_name = f"{name}-ratelimit"
    avg, burst, period = nginx_rate_limit_from_annotations(ann)
    return _mw_yaml(mw_name, ns, name, spec_rate_limit(avg, burst, period))


def _gen_inflight_req(name: str, ns: str, ann: Dict[str, str]) -> MiddlewareSpec:
    mw_name = f"{name}-inflightreq"
    amount = int(_get(ann, "limit-connections", "10"))
    return _mw_yaml(mw_name, ns, name, spec_inflight_req(amount))


def _gen_ip_list(name: str, ns: str, cidr: str, deny: bool = False) -> MiddlewareSpec:
    kind = "ipdenylist" if deny else "ipallowlist"
    mw_name = f"{name}-{kind}"
    cidrs = [c.strip() for c in cidr.split(",") if c.strip()]
    spec = spec_ip_denylist(cidrs) if deny else spec_ip_allowlist(cidrs)
    return _mw_yaml(mw_name, ns, name, spec)


def _gen_rewrite(name: str, ns: str, target: str, ann: Dict[str, str]) -> MiddlewareSpec:
    mw_name = f"{name}-rewrite"
    if "use-regex" in ann:
        preamble = "# NOTE: Adjust regex to match your Ingress path pattern.\n"
        spec = spec_replace_path_regex("^/[^/]*(.*)", target)
    else:
        preamble = ""
        spec = spec_replace_path(target)
    return _mw_yaml(mw_name, ns, name, spec, preamble=preamble)


def _gen_headers(name: str, ns: str, ann: Dict[str, str]) -> MiddlewareSpec:
    mw_name = f"{name}-headers"
    custom_ref = _get(ann, "custom-headers")
    preamble = ""
    if custom_ref:
        preamble = (
            f"# NOTE: Original annotation referenced ConfigMap: {custom_ref}\n"
            f"# Inline the headers below from that ConfigMap.\n"
        )
    spec = spec_headers_block(
        custom_response_headers={"X-Custom-Header": "value"},
    )
    return _mw_yaml(mw_name, ns, name, spec, preamble=preamble)


def _gen_buffering(name: str, ns: str, ann: Dict[str, str]) -> MiddlewareSpec:
    mw_name = f"{name}-buffering"
    raw = (ann.get("proxy-body-size") or "").strip()
    max_b = parse_nginx_proxy_body_size_to_bytes(raw)
    preamble = (
        f"# Maps nginx.ingress.kubernetes.io/proxy-body-size: {raw!r} "
        f"→ Traefik buffering.maxRequestBodyBytes ({max_b} bytes).\n"
    )
    return _mw_yaml(mw_name, ns, name, spec_buffering(max_b), preamble=preamble)


def _gen_app_root(name: str, ns: str, app_root: str) -> MiddlewareSpec:
    mw_name = f"{name}-app-root"
    p = app_root.strip()
    if not p.startswith("/"):
        p = f"/{p}"
    preamble = (
        "# Maps nginx app-root via addPrefix. NGINX may redirect / to this path; "
        "Traefik addPrefix prepends the prefix to the request path — verify behavior for your app.\n"
    )
    return _mw_yaml(mw_name, ns, name, spec_add_prefix(p), preamble=preamble)


# ── ServersTransport CRD generator ─────────────────────────────────────────────

def _parse_nginx_timeout(val: str) -> str:
    """Convert an NGINX timeout value (bare number = seconds) to a Go duration string."""
    val = val.strip()
    if not val:
        return "30s"
    # Already has a unit suffix (e.g. "30s", "1m")
    if val[-1] in ("s", "m", "h"):
        return val
    # Bare number → seconds
    try:
        secs = int(val)
        return f"{secs}s"
    except ValueError:
        return "30s"


def generate_servers_transports(ing: IngressInfo) -> List[GeneratedFile]:
    """Generate ServersTransport CRDs for timeout/backend-protocol annotations.

    Maps NGINX timeout annotations to Traefik ServersTransport:
      - proxy-read-timeout  → forwardingTimeouts.responseHeaderTimeout
      - proxy-connect-timeout → forwardingTimeouts.dialTimeout
      - proxy-send-timeout   → forwardingTimeouts.dialTimeout (fallback)
      - backend-protocol: HTTPS → insecureSkipVerify + serversScheme
    """
    ann = ing.nginx_annotations
    has_timeouts = any(
        k in ann for k in ("proxy-read-timeout", "proxy-send-timeout", "proxy-connect-timeout")
    )
    has_https_backend = (ann.get("backend-protocol") or "").upper() == "HTTPS"

    if not has_timeouts and not has_https_backend:
        return []

    st_name = f"{ing.name}-transport"
    spec: Dict[str, Any] = {}

    # Forwarding timeouts
    if has_timeouts:
        timeouts: Dict[str, str] = {}
        if "proxy-read-timeout" in ann:
            timeouts["responseHeaderTimeout"] = _parse_nginx_timeout(ann["proxy-read-timeout"])
        # dialTimeout: prefer proxy-connect-timeout, fall back to proxy-send-timeout
        connect_val = ann.get("proxy-connect-timeout", "")
        send_val = ann.get("proxy-send-timeout", "")
        dial_source = connect_val or send_val
        if dial_source:
            timeouts["dialTimeout"] = _parse_nginx_timeout(dial_source)
        if timeouts:
            spec["forwardingTimeouts"] = timeouts

    # HTTPS backend → insecureSkipVerify (user must add rootCAs for proper mTLS)
    if has_https_backend:
        spec["insecureSkipVerify"] = True

    if not spec:
        return []

    st_obj: Dict[str, Any] = {
        "apiVersion": "traefik.io/v1alpha1",
        "kind": "ServersTransport",
        "metadata": {
            "name": st_name,
            "namespace": ing.namespace,
            "labels": {_MIGRATION_LABEL: ing.name},
        },
        "spec": spec,
    }

    preamble_parts = []
    if has_timeouts:
        preamble_parts.append(
            "# ServersTransport for backend timeouts (migrated from NGINX proxy-*-timeout annotations)."
        )
    if has_https_backend:
        preamble_parts.append(
            "# backend-protocol: HTTPS — insecureSkipVerify is set. "
            "Add rootCAs for proper TLS verification."
        )
    # Service annotation hint
    svc_ref = f"{ing.namespace}-{st_name}@kubernetescrd"
    preamble_parts.append(
        f"# Link to backend Service via annotation:\n"
        f"#   traefik.ingress.kubernetes.io/service.serverstransport: {svc_ref}"
    )
    if has_https_backend:
        preamble_parts.append(
            "#   traefik.ingress.kubernetes.io/service.serversscheme: https"
        )

    preamble = "\n".join(preamble_parts) + "\n"
    content = preamble + pyyaml.dump(st_obj, default_flow_style=False, sort_keys=False)

    key = f"{ing.namespace}-{ing.name}"
    return [
        GeneratedFile(
            rel_path=f"02-middlewares/{key}-serverstransport.yaml",
            content=content,
            description=f"ServersTransport for backend timeouts/TLS — {ing.namespace}/{ing.name}",
            category="serverstransport",
        )
    ]


# ── Service sticky session patch generator ─────────────────────────────────────

def generate_service_patches(ing: IngressInfo) -> List[GeneratedFile]:
    """Generate Kubernetes Service annotation patches for sticky session annotations.

    Maps NGINX affinity annotations to Traefik Service annotations:
      - affinity: cookie     → service.sticky.cookie: "true"
      - session-cookie-name  → service.sticky.cookie.name
      - session-cookie-max-age / session-cookie-expires → service.sticky.cookie.maxage
      - session-cookie-samesite → service.sticky.cookie.samesite
      - session-cookie-secure   → service.sticky.cookie.secure
    """
    ann = ing.nginx_annotations
    if ann.get("affinity") != "cookie":
        return []

    traefik_prefix = "traefik.ingress.kubernetes.io/"
    svc_annotations: Dict[str, str] = {
        f"{traefik_prefix}service.sticky.cookie": "true",
    }

    if cookie_name := ann.get("session-cookie-name"):
        svc_annotations[f"{traefik_prefix}service.sticky.cookie.name"] = cookie_name

    # maxage: prefer session-cookie-max-age, fall back to session-cookie-expires
    maxage = ann.get("session-cookie-max-age") or ann.get("session-cookie-expires")
    if maxage:
        svc_annotations[f"{traefik_prefix}service.sticky.cookie.maxage"] = maxage.strip()

    if samesite := ann.get("session-cookie-samesite"):
        svc_annotations[f"{traefik_prefix}service.sticky.cookie.samesite"] = samesite

    if secure := ann.get("session-cookie-secure"):
        svc_annotations[f"{traefik_prefix}service.sticky.cookie.secure"] = secure

    files: List[GeneratedFile] = []
    for svc_ref in ing.services:
        patch_obj: Dict[str, Any] = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": svc_ref.name,
                "namespace": svc_ref.namespace or ing.namespace,
                "annotations": svc_annotations,
            },
        }

        preamble = (
            f"# Sticky session annotations for Service {svc_ref.name}\n"
            f"# Migrated from NGINX affinity/session-cookie-* annotations.\n"
            f"# Apply via: kubectl patch svc {svc_ref.name} -n {svc_ref.namespace or ing.namespace} "
            f"--type=merge -p '{{\"metadata\":{{\"annotations\":{{}}}}}}'\n"
        )
        content = preamble + pyyaml.dump(patch_obj, default_flow_style=False, sort_keys=False)

        key = f"{ing.namespace}-{ing.name}-{svc_ref.name}"
        files.append(
            GeneratedFile(
                rel_path=f"02-middlewares/{key}-service-patch.yaml",
                content=content,
                description=f"Service sticky session patch for {svc_ref.namespace or ing.namespace}/{svc_ref.name}",
                category="service_patch",
            )
        )

    return files


# ── Middleware orchestrator ────────────────────────────────────────────────────

def generate_middlewares(ing: IngressInfo) -> List[MiddlewareSpec]:
    """Generate all Traefik Middleware CRDs required for an Ingress."""
    middlewares: List[MiddlewareSpec] = []
    ann = ing.nginx_annotations

    if ann.get("ssl-redirect") == "true":
        middlewares.append(_gen_ssl_redirect(ing.name, ing.namespace, permanent=False))
    if ann.get("force-ssl-redirect") == "true":
        middlewares.append(_gen_ssl_redirect(ing.name, ing.namespace, permanent=True))

    if ann.get("enable-cors") == "true":
        middlewares.append(_gen_cors(ing.name, ing.namespace, ann))

    if ann.get("auth-url"):
        middlewares.append(_gen_forward_auth(ing.name, ing.namespace, ann))

    if ann.get("auth-type") == "basic":
        middlewares.append(_gen_basic_auth(ing.name, ing.namespace, ann))

    if "limit-rps" in ann or "limit-rpm" in ann:
        middlewares.append(_gen_rate_limit(ing.name, ing.namespace, ann))

    if "limit-connections" in ann:
        middlewares.append(_gen_inflight_req(ing.name, ing.namespace, ann))

    if cidr := ann.get("whitelist-source-range"):
        middlewares.append(_gen_ip_list(ing.name, ing.namespace, cidr, deny=False))

    if cidr := ann.get("denylist-source-range"):
        middlewares.append(_gen_ip_list(ing.name, ing.namespace, cidr, deny=True))

    if target := ann.get("rewrite-target"):
        middlewares.append(_gen_rewrite(ing.name, ing.namespace, target, ann))

    if "custom-headers" in ann:
        middlewares.append(_gen_headers(ing.name, ing.namespace, ann))

    if (ann.get("proxy-body-size") or "").strip():
        try:
            middlewares.append(_gen_buffering(ing.name, ing.namespace, ann))
        except ValueError:
            pass

    if (ann.get("app-root") or "").strip():
        middlewares.append(
            _gen_app_root(ing.name, ing.namespace, ann["app-root"])
        )

    return middlewares


# ── Ingress manifest generation ───────────────────────────────────────────────

# Annotations that are consumed by generated middleware and should be stripped
_NGINX_ANNOTATIONS_TO_STRIP = {
    "nginx.ingress.kubernetes.io/ssl-redirect",
    "nginx.ingress.kubernetes.io/force-ssl-redirect",
    "nginx.ingress.kubernetes.io/enable-cors",
    "nginx.ingress.kubernetes.io/cors-allow-origin",
    "nginx.ingress.kubernetes.io/cors-allow-methods",
    "nginx.ingress.kubernetes.io/cors-allow-headers",
    "nginx.ingress.kubernetes.io/cors-expose-headers",
    "nginx.ingress.kubernetes.io/cors-allow-credentials",
    "nginx.ingress.kubernetes.io/cors-max-age",
    "nginx.ingress.kubernetes.io/auth-url",
    "nginx.ingress.kubernetes.io/auth-response-headers",
    "nginx.ingress.kubernetes.io/auth-method",
    "nginx.ingress.kubernetes.io/limit-rps",
    "nginx.ingress.kubernetes.io/limit-rpm",
    "nginx.ingress.kubernetes.io/limit-connections",
    "nginx.ingress.kubernetes.io/whitelist-source-range",
    "nginx.ingress.kubernetes.io/denylist-source-range",
    "nginx.ingress.kubernetes.io/rewrite-target",
    "nginx.ingress.kubernetes.io/use-regex",
    "nginx.ingress.kubernetes.io/proxy-body-size",
    "nginx.ingress.kubernetes.io/app-root",
    # ServersTransport annotations (timeout / backend protocol)
    "nginx.ingress.kubernetes.io/proxy-read-timeout",
    "nginx.ingress.kubernetes.io/proxy-send-timeout",
    "nginx.ingress.kubernetes.io/proxy-connect-timeout",
    "nginx.ingress.kubernetes.io/backend-protocol",
    # Service sticky session annotations
    "nginx.ingress.kubernetes.io/affinity",
    "nginx.ingress.kubernetes.io/session-cookie-name",
    "nginx.ingress.kubernetes.io/session-cookie-max-age",
    "nginx.ingress.kubernetes.io/session-cookie-expires",
    "nginx.ingress.kubernetes.io/session-cookie-samesite",
    "nginx.ingress.kubernetes.io/session-cookie-secure",
}


def _generate_updated_ingress(
    ing: IngressInfo,
    middleware_refs: List[str],
    retain_ignored_annotation_short_keys: Optional[Set[str]] = None,
) -> str:
    """Generate an updated Ingress manifest with Traefik annotations.

    Uses pyyaml for safe annotation serialization (handles quoting, escaping,
    and multi-line values correctly).

    ``retain_ignored_annotation_short_keys``: short nginx keys the agent asked to
    ignore — we keep those full annotations on the Ingress even if they would
    normally be stripped after middleware generation.
    """
    retain = retain_ignored_annotation_short_keys or set()
    prefix = "nginx.ingress.kubernetes.io/"
    annotations: Dict[str, str] = {}
    for k, v in ing.annotations.items():
        # Strip Kubernetes bookkeeping annotations (noisy, large)
        if k.startswith("kubectl.kubernetes.io/"):
            continue
        if k in _NGINX_ANNOTATIONS_TO_STRIP:
            if k.startswith(prefix):
                short = k[len(prefix) :]
                if short in retain:
                    annotations[k] = v
            continue
        annotations[k] = v

    if middleware_refs:
        annotations["traefik.ingress.kubernetes.io/router.middlewares"] = ",".join(middleware_refs)

    # Build the full Ingress object as a dict, then use pyyaml.dump
    ingress_obj: Dict[str, Any] = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {
            "name": ing.name,
            "namespace": ing.namespace,
            "annotations": annotations,
        },
        "spec": {
            "ingressClassName": ing.ingress_class or "nginx",
            "rules": [],
        },
    }

    # Rules
    host_paths: Dict[str, list] = {}
    for p in ing.paths:
        host_paths.setdefault(p.host, []).append(p)

    for host, paths in host_paths.items():
        rule: Dict[str, Any] = {}
        if host:
            rule["host"] = host
        rule["http"] = {
            "paths": [
                {
                    "path": p.path or "/",
                    "pathType": p.path_type or "Prefix",
                    "backend": {
                        "service": {
                            "name": p.service_name,
                            "port": {"number": p.service_port},
                        }
                    },
                }
                for p in paths
            ]
        }
        ingress_obj["spec"]["rules"].append(rule)

    # TLS section
    if ing.tls_enabled and ing.tls_secrets:
        ingress_obj["spec"]["tls"] = [
            {
                "hosts": ing.hosts,
                "secretName": secret,
            }
            for secret in ing.tls_secrets
        ]

    return pyyaml.dump(ingress_obj, default_flow_style=False, sort_keys=False)


# ── Static file templates ─────────────────────────────────────────────────────

_HELM_INSTALL_SCRIPT = """\
#!/bin/bash
# Install Traefik alongside existing NGINX Ingress Controller
# Both will run in parallel — zero downtime migration
set -e

echo "Adding Traefik Helm repository..."
helm repo add traefik https://traefik.github.io/charts
helm repo update

echo "Installing Traefik with Kubernetes Ingress NGINX provider..."
helm upgrade --install traefik traefik/traefik \\
  --namespace traefik \\
  --create-namespace \\
  --values values.yaml \\
  --version ">=3.6.2"

echo "Waiting for Traefik to be ready..."
kubectl rollout status deployment/traefik -n traefik --timeout=120s

echo ""
echo "Traefik installed successfully!"
echo ""
echo "Get Traefik LoadBalancer IP:"
kubectl get svc -n traefik traefik
echo ""
echo "Test that Traefik can serve your Ingress resources:"
echo "  bash ../04-verify.sh"
"""

_HELM_VALUES = """\
# Traefik Helm values for NGINX Ingress migration
# Requires Traefik v3.6.2+

providers:
  kubernetesIngressNginx:
    enabled: true
  kubernetesIngress:
    enabled: true
    allowCrossNamespace: false

deployment:
  replicas: 2

affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            app.kubernetes.io/name: traefik
            app.kubernetes.io/instance: traefik
        topologyKey: kubernetes.io/hostname

podDisruptionBudget:
  enabled: true
  minAvailable: 1

service:
  enabled: true
  type: LoadBalancer

ports:
  web:
    port: 8000
    expose:
      default: true
    exposedPort: 80
  websecure:
    port: 8443
    expose:
      default: true
    exposedPort: 443
    tls:
      enabled: true

logs:
  general:
    level: INFO
  access:
    enabled: true
"""

_DNS_GUIDE = """\
# DNS Migration Guide

## Overview
- NGINX is still running and handling all production traffic
- Traefik is running with its own LoadBalancer IP
- Both controllers are watching the same Ingress resources
- You have verified Traefik works correctly (verify.sh passed)

## Step 1: Get both LoadBalancer IPs
```bash
NGINX_IP=$(kubectl get svc -n ingress-nginx ingress-nginx-controller -o go-template='{{ $ing := index .status.loadBalancer.ingress 0 }}{{ if $ing.ip }}{{ $ing.ip }}{{ else }}{{ $ing.hostname }}{{ end }}')
TRAEFIK_IP=$(kubectl get svc -n traefik traefik -o go-template='{{ $ing := index .status.loadBalancer.ingress 0 }}{{ if $ing.ip }}{{ $ing.ip }}{{ else }}{{ $ing.hostname }}{{ end }}')
echo "NGINX:   $NGINX_IP"
echo "Traefik: $TRAEFIK_IP"
```

## Step 2: Add Traefik to DNS (parallel traffic)
In your DNS provider, add the Traefik IP alongside the NGINX IP.
**Set a low TTL (e.g., 60s) before making changes** so rollback is fast.

## Step 3: Monitor
```bash
kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx -f
kubectl logs -n traefik -l app.kubernetes.io/name=traefik -f
```

## Step 4: Remove NGINX from DNS
Once confident, remove the NGINX IP from DNS. Wait 24-48 hours.

## Step 5: Cleanup
Proceed to **06-cleanup/**.

## Rollback
Remove Traefik from DNS records; traffic returns to NGINX within TTL seconds.
"""

_PRESERVE_INGRESS_CLASS = """\
# Preserve the NGINX IngressClass so Traefik continues watching these Ingresses.
# Apply BEFORE uninstalling NGINX.
apiVersion: networking.k8s.io/v1
kind: IngressClass
metadata:
  name: nginx
  annotations:
    ingressclass.kubernetes.io/is-default-class: "false"
    helm.sh/resource-policy: keep
spec:
  controller: k8s.io/ingress-nginx
"""

_CLEANUP_SCRIPT = """\
#!/bin/bash
# Remove Ingress NGINX Controller after migration is complete.
set -e

echo "=== Removing Ingress NGINX Controller ==="
echo "Step 1: Preserving nginx IngressClass..."
kubectl apply -f 01-preserve-ingressclass.yaml
kubectl annotate ingressclass nginx helm.sh/resource-policy=keep --overwrite

echo "Step 2: Removing NGINX admission webhooks..."
kubectl delete validatingwebhookconfiguration ingress-nginx-admission --ignore-not-found
kubectl delete mutatingwebhookconfiguration ingress-nginx-admission --ignore-not-found

echo "Step 3: Uninstalling NGINX Helm release..."
if helm list -n ingress-nginx | grep -q ingress-nginx; then
  helm uninstall ingress-nginx -n ingress-nginx
else
  echo "  NGINX Helm release not found."
fi

echo "Step 4: Verifying IngressClass still exists..."
kubectl get ingressclass nginx

echo "Step 5: Cleaning up ingress-nginx namespace..."
kubectl delete namespace ingress-nginx --ignore-not-found

echo ""
echo "=== Migration Complete ==="
echo "Verify: kubectl get ingress --all-namespaces"
"""


# ── Shadow mode — TraefikService mirroring manifest ────────────────────────────

def _generate_shadow_traefik_service(
    ing: IngressInfo,
    mirror_percent: int = 20,
) -> GeneratedFile:
    """Generate a TraefikService CRD with mirroring for shadow testing.

    This mirrors ``mirror_percent`` of live traffic to ``{service}-shadow``
    while the main service continues serving real users. Mirror responses
    are discarded — there is zero user impact.
    """
    # Use the first backend service from the Ingress as the main service
    main_service = ing.paths[0].service_name if ing.paths else ing.name
    main_port = ing.paths[0].service_port if ing.paths else 80
    shadow_service = f"{main_service}-shadow"

    traefik_svc = {
        "apiVersion": "traefik.io/v1alpha1",
        "kind": "TraefikService",
        "metadata": {
            "name": f"{ing.name}-mirror",
            "namespace": ing.namespace,
            "labels": {_MIGRATION_LABEL: ing.name},
        },
        "spec": {
            "mirroring": {
                "name": main_service,
                "port": main_port,
                "mirrors": [
                    {
                        "name": shadow_service,
                        "port": main_port,
                        "percent": mirror_percent,
                    }
                ],
            },
        },
    }

    preamble = (
        f"# Shadow testing — mirrors {mirror_percent}% of traffic to {shadow_service}.\n"
        f"# Mirror responses are discarded (no impact on clients).\n"
        f"# Standard Kubernetes Ingress cannot reference a TraefikService; mirroring is a Traefik CRD feature.\n"
        f"# Use an IngressRoute (or your Traefik routing CRD) whose backend targets TraefikService\n"
        f"# '{ing.name}-mirror', or another supported mirroring flow. Provision Service/workload\n"
        f"# '{shadow_service}' yourself before enabling mirroring.\n"
    )
    content = preamble + pyyaml.dump(
        traefik_svc, default_flow_style=False, sort_keys=False,
    )

    key = f"{ing.namespace}-{ing.name}"
    return GeneratedFile(
        rel_path=f"07-shadow/{key}-mirror.yaml",
        content=content,
        description=f"TraefikService mirroring for shadow testing {ing.namespace}/{ing.name}",
        category="shadow",
    )


# ── Migrator ───────────────────────────────────────────────────────────────────

class TraefikMigrator:
    """Generates Traefik migration artifacts from NGINX Ingress resources."""

    def migrate(
        self,
        scan_result: ScanResult,
        analysis: Optional[AnalysisReport] = None,
        migration_plan: Optional[Dict[str, Any]] = None,
    ) -> List[GeneratedFile]:
        """Generate all migration files for a Traefik target.

        Args:
            scan_result: Output from NginxMigrationScanner.scan()
            analysis: Optional AnalysisReport (for report enrichment)
            migration_plan: Optional per-Ingress overrides from the agent
                (``ignore_annotations``, ``inject_middlewares``); see
                ``migration_plan.parse_migration_plan``.

        Returns:
            List of GeneratedFile objects with relative paths and YAML content.
        """
        files: List[GeneratedFile] = []
        plan = parse_migration_plan(migration_plan)

        # 1. Helm install scripts
        files.append(GeneratedFile(
            rel_path="01-install-traefik/helm-install.sh",
            content=_HELM_INSTALL_SCRIPT,
            description="Helm install script for Traefik",
            category="install",
        ))
        files.append(GeneratedFile(
            rel_path="01-install-traefik/values.yaml",
            content=_HELM_VALUES,
            description="Traefik Helm values file",
            category="install",
        ))

        # 2. Middlewares per ingress
        middleware_names: Dict[str, List[str]] = {}  # key → [ns-name@kubernetescrd, ...]

        for ing in scan_result.ingresses:
            entry = plan_entry_for_ingress(plan, ing.namespace, ing.name)
            effective = (
                filter_ingress_for_plan(ing, list(entry.ignore_annotations))
                if entry.ignore_annotations
                else ing
            )
            mws = generate_middlewares(effective)
            refs = [f"{ing.namespace}-{mw.name}@kubernetescrd" for mw in mws]
            for raw_inj in entry.inject_middlewares:
                ref = format_inject_middleware_ref(raw_inj, ing.namespace)
                if ref:
                    refs.append(ref)

            if not refs:
                continue

            key = f"{ing.namespace}-{ing.name}"
            middleware_names[key] = refs

            if mws:
                yaml_parts = [mw.yaml for mw in mws]
                files.append(GeneratedFile(
                    rel_path=f"02-middlewares/{key}-middlewares.yaml",
                    content="---\n".join(yaml_parts),
                    description=f"Traefik Middlewares for {ing.namespace}/{ing.name}",
                    category="middleware",
                ))

        # 2b. ServersTransport CRDs per ingress
        for ing in scan_result.ingresses:
            entry = plan_entry_for_ingress(plan, ing.namespace, ing.name)
            effective = (
                filter_ingress_for_plan(ing, list(entry.ignore_annotations))
                if entry.ignore_annotations
                else ing
            )
            st_files = generate_servers_transports(effective)
            files.extend(st_files)

        # 2c. Service sticky session patches per ingress
        for ing in scan_result.ingresses:
            entry = plan_entry_for_ingress(plan, ing.namespace, ing.name)
            effective = (
                filter_ingress_for_plan(ing, list(entry.ignore_annotations))
                if entry.ignore_annotations
                else ing
            )
            sp_files = generate_service_patches(effective)
            files.extend(sp_files)

        # 3. Updated Ingress manifests
        for ing in scan_result.ingresses:
            key = f"{ing.namespace}-{ing.name}"
            refs = middleware_names.get(key, [])
            entry = plan_entry_for_ingress(plan, ing.namespace, ing.name)
            retain = {
                normalize_ignore_key(x) for x in entry.ignore_annotations
            }
            yaml_str = _generate_updated_ingress(
                ing,
                refs,
                retain_ignored_annotation_short_keys=retain or None,
            )
            files.append(GeneratedFile(
                rel_path=f"03-ingresses/{key}.yaml",
                content=yaml_str,
                description=f"Updated Ingress for {ing.namespace}/{ing.name} with Traefik annotations",
                category="ingress",
            ))

        # 3b. Shadow mode — generate TraefikService mirroring manifests
        for ing in scan_result.ingresses:
            entry = plan_entry_for_ingress(plan, ing.namespace, ing.name)
            if not entry.shadow_mode:
                continue
            shadow_file = _generate_shadow_traefik_service(
                ing, entry.shadow_mirror_percent,
            )
            files.append(shadow_file)

        # 4. Verify script
        files.append(self._generate_verify_script(scan_result))

        # 5. DNS guide
        files.append(GeneratedFile(
            rel_path="05-dns-migration.md",
            content=_DNS_GUIDE,
            description="Step-by-step DNS migration guide",
            category="guide",
        ))

        # 6. Cleanup scripts
        files.append(GeneratedFile(
            rel_path="06-cleanup/01-preserve-ingressclass.yaml",
            content=_PRESERVE_INGRESS_CLASS,
            description="Preserve nginx IngressClass before removing NGINX",
            category="cleanup",
        ))
        files.append(GeneratedFile(
            rel_path="06-cleanup/02-remove-nginx.sh",
            content=_CLEANUP_SCRIPT,
            description="Remove NGINX after migration is verified complete",
            category="cleanup",
        ))

        return files

    def _generate_verify_script(self, scan_result: ScanResult) -> GeneratedFile:
        """Generate a verification script that tests each host via Traefik."""
        test_lines = []
        for ing in scan_result.ingresses:
            for host in ing.hosts:
                test_lines.append(
                    f'echo "Testing {ing.namespace}/{ing.name} → {host}"\n'
                    f'curl -s --connect-to "{host}:80:${{TRAEFIK_IP}}:80" '
                    f'"http://{host}" -o /dev/null -w "HTTP %{{http_code}}\\n" || true'
                )

        tests_block = "\n\n".join(test_lines) if test_lines else 'echo "No hosts to test."'

        content = (
            "#!/bin/bash\n"
            "# Verify Traefik is handling your Ingress resources correctly.\n"
            "# Run BEFORE cutting over DNS to Traefik.\n"
            "set -e\n\n"
            'echo "=== Migration Verification Script ==="\n'
            'echo ""\n\n'
            "TRAEFIK_IP=$(kubectl get svc -n traefik traefik "
            "-o go-template='{{ $ing := index .status.loadBalancer.ingress 0 }}"
            "{{ if $ing.ip }}{{ $ing.ip }}{{ else }}{{ $ing.hostname }}{{ end }}' "
            "2>/dev/null || echo \"\")\n\n"
            'if [ -z "$TRAEFIK_IP" ]; then\n'
            '  echo "ERROR: Traefik LoadBalancer IP not assigned yet."\n'
            '  kubectl get svc -n traefik traefik\n'
            '  exit 1\n'
            'fi\n\n'
            'echo "Traefik LoadBalancer: $TRAEFIK_IP"\n'
            'echo ""\n\n'
            f"{tests_block}\n\n"
            'echo ""\n'
            'echo "If all tests pass, proceed to 05-dns-migration.md"\n'
        )

        return GeneratedFile(
            rel_path="04-verify.sh",
            content=content,
            description="Verification script to test Traefik before DNS cutover",
            category="verify",
        )


# ── Serialization helper ──────────────────────────────────────────────────────

def generated_files_to_dict(files: List[GeneratedFile]) -> Dict[str, Any]:
    """Convert generated files to JSON-serializable map of {path: content}."""
    return {
        "files": {
            f.rel_path: {
                "content": f.content,
                "description": f.description,
                "category": f.category,
            }
            for f in files
        },
        "summary": {
            "total_files": len(files),
            "categories": list(set(f.category for f in files)),
        },
    }
