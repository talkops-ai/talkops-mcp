"""Shared Traefik HTTP Middleware CRD builders (Traefik v3 / traefik.io/v1alpha1).

Used by TraefikService (cluster upsert) and TraefikMigrator (YAML bundles).
Field names match the Kubernetes CRD spec (camelCase).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import yaml as pyyaml

TRAEFIK_MIDDLEWARE_API_VERSION = "traefik.io/v1alpha1"


def middleware_dict_to_yaml(obj: Dict[str, Any]) -> str:
    """Serialize a Middleware manifest dict to multi-doc-safe YAML."""
    return pyyaml.dump(
        obj,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    ).rstrip() + "\n"


def build_middleware_crd(
    name: str,
    namespace: str,
    spec: Dict[str, Any],
    labels: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build full Middleware object: apiVersion, kind, metadata, spec."""
    metadata: Dict[str, Any] = {"name": name, "namespace": namespace}
    if labels:
        metadata["labels"] = dict(labels)
    return {
        "apiVersion": TRAEFIK_MIDDLEWARE_API_VERSION,
        "kind": "Middleware",
        "metadata": metadata,
        "spec": spec,
    }


# ── Spec fragments (each value is the full `spec` dict) ──────────────────────


def spec_redirect_scheme(permanent: bool = True) -> Dict[str, Any]:
    return {
        "redirectScheme": {
            "scheme": "https",
            "permanent": permanent,
        }
    }


def spec_rate_limit(average: int, burst: int, period: str) -> Dict[str, Any]:
    return {
        "rateLimit": {
            "average": average,
            "burst": burst,
            "period": period,
        }
    }


def spec_circuit_breaker(expression: str, response_code: int = 503) -> Dict[str, Any]:
    return {
        "circuitBreaker": {
            "expression": expression,
            "responseCode": response_code,
        }
    }


def spec_strip_prefix(
    prefixes: List[str],
    force_slash: bool = True,
) -> Dict[str, Any]:
    return {
        "stripPrefix": {
            "prefixes": list(prefixes),
            "forceSlash": force_slash,
        }
    }


def spec_strip_prefix_regex(regex: List[str]) -> Dict[str, Any]:
    return {"stripPrefixRegex": {"regex": list(regex)}}


def spec_inflight_req(amount: int) -> Dict[str, Any]:
    return {"inFlightReq": {"amount": amount}}


def spec_ip_allowlist(source_ranges: List[str]) -> Dict[str, Any]:
    return {"ipAllowList": {"sourceRange": [s.strip() for s in source_ranges if s.strip()]}}


def spec_ip_denylist(source_ranges: List[str]) -> Dict[str, Any]:
    return {"ipDenyList": {"sourceRange": [s.strip() for s in source_ranges if s.strip()]}}


def spec_forward_auth(
    address: str,
    auth_response_headers: Optional[List[str]] = None,
    trust_forward_header: bool = True,
    auth_request_headers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    fa: Dict[str, Any] = {
        "address": address,
        "trustForwardHeader": trust_forward_header,
    }
    if auth_response_headers:
        fa["authResponseHeaders"] = [h.strip() for h in auth_response_headers if h.strip()]
    if auth_request_headers:
        fa["authRequestHeaders"] = [h.strip() for h in auth_request_headers if h.strip()]
    return {"forwardAuth": fa}


def spec_headers_block(
    *,
    access_control_allow_origin_list: Optional[List[str]] = None,
    access_control_allow_methods: Optional[List[str]] = None,
    access_control_allow_headers: Optional[List[str]] = None,
    access_control_allow_credentials: Optional[bool] = None,
    access_control_max_age: Optional[int] = None,
    access_control_expose_headers: Optional[List[str]] = None,
    custom_request_headers: Optional[Dict[str, str]] = None,
    custom_response_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Single `headers` middleware spec (CORS and/or custom headers)."""
    h: Dict[str, Any] = {}
    if access_control_allow_origin_list:
        h["accessControlAllowOriginList"] = list(access_control_allow_origin_list)
    if access_control_allow_methods:
        # Traefik accepts list of strings; migrator used one string — split if needed
        methods: List[str] = []
        for m in access_control_allow_methods:
            methods.extend([x.strip() for x in m.split(",") if x.strip()])
        if methods:
            h["accessControlAllowMethods"] = methods
    if access_control_allow_headers:
        hdrs: List[str] = []
        for x in access_control_allow_headers:
            hdrs.extend([y.strip() for y in x.split(",") if y.strip()])
        if hdrs:
            h["accessControlAllowHeaders"] = hdrs
    if access_control_allow_credentials is not None:
        h["accessControlAllowCredentials"] = access_control_allow_credentials
    if access_control_max_age is not None:
        h["accessControlMaxAge"] = access_control_max_age
    if access_control_expose_headers:
        exp: List[str] = []
        for x in access_control_expose_headers:
            exp.extend([y.strip() for y in x.split(",") if y.strip()])
        if exp:
            h["accessControlExposeHeaders"] = exp
    if custom_request_headers:
        h["customRequestHeaders"] = dict(custom_request_headers)
    if custom_response_headers:
        h["customResponseHeaders"] = dict(custom_response_headers)
    return {"headers": h}


def spec_basic_auth(secret: str, realm: str) -> Dict[str, Any]:
    return {"basicAuth": {"secret": secret, "realm": realm}}


def spec_buffering(
    max_request_body_bytes: int,
    mem_request_body_bytes: Optional[int] = None,
    max_response_body_bytes: Optional[int] = None,
    retry_expression: Optional[str] = None,
) -> Dict[str, Any]:
    buf: Dict[str, Any] = {"maxRequestBodyBytes": max_request_body_bytes}
    if mem_request_body_bytes is not None:
        buf["memRequestBodyBytes"] = mem_request_body_bytes
    if max_response_body_bytes is not None:
        buf["maxResponseBodyBytes"] = max_response_body_bytes
    if retry_expression:
        buf["retryExpression"] = retry_expression
    return {"buffering": buf}


def spec_replace_path(path: str) -> Dict[str, Any]:
    return {"replacePath": {"path": path}}


def spec_replace_path_regex(regex: str, replacement: str) -> Dict[str, Any]:
    return {"replacePathRegex": {"regex": regex, "replacement": replacement}}


def spec_add_prefix(prefix: str) -> Dict[str, Any]:
    return {"addPrefix": {"prefix": prefix}}


# ── NGINX annotation helpers (migration) ───────────────────────────────────────


def nginx_rate_limit_from_annotations(ann: Dict[str, str]) -> tuple[int, int, str]:
    """Derive average, burst, period from nginx limit-rps / limit-rpm annotations."""
    rps = ann.get("limit-rps", "").strip()
    rpm = ann.get("limit-rpm", "").strip()
    mult = int((ann.get("limit-burst-multiplier") or "5").strip() or "5")

    if rps:
        avg = int(rps)
        period = "1s"
    elif rpm:
        avg = int(rpm)
        period = "1m"
    else:
        avg = 100
        period = "1s"
    burst = avg * mult
    return avg, burst, period


def parse_nginx_proxy_body_size_to_bytes(value: str) -> int:
    """Parse NGINX-style size: 8m, 1024k, 1g, or plain integer (bytes)."""
    s = value.strip().lower()
    if not s:
        raise ValueError("empty proxy-body-size")
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([kmg]?)$", s)
    if not m:
        raise ValueError(f"invalid proxy-body-size: {value!r}")
    num = float(m.group(1))
    suf = m.group(2)
    mult = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}.get(suf, 1)
    return int(num * mult)

