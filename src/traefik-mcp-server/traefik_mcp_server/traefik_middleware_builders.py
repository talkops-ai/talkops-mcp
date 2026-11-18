"""Shared Traefik HTTP & TCP Middleware CRD builders (Traefik v3 / traefik.io/v1alpha1).

Used by TraefikService (cluster upsert & dry-run preview) and offline skill scripts.
Field names match the Kubernetes CRD spec (camelCase).
"""

from __future__ import annotations

import ipaddress
from typing import Any, Dict, List, Optional, Tuple

import yaml as pyyaml

from traefik_mcp_server.exceptions.custom import (
    TraefikCircuitBreakerError,
    TraefikMiddlewareError,
)

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
    protocol: str = "http",
) -> Dict[str, Any]:
    """Build full Middleware or MiddlewareTCP object: apiVersion, kind, metadata, spec."""
    metadata: Dict[str, Any] = {"name": name, "namespace": namespace}
    if labels:
        metadata["labels"] = dict(labels)
    kind = "MiddlewareTCP" if protocol.lower() == "tcp" else "Middleware"
    return {
        "apiVersion": TRAEFIK_MIDDLEWARE_API_VERSION,
        "kind": kind,
        "metadata": metadata,
        "spec": spec,
    }


# ── Spec fragments (each value is the full `spec` dict) ──────────────────────


def spec_redirect_scheme(
    permanent: bool = True,
    scheme: str = "https",
    port: Optional[str] = None,
) -> Dict[str, Any]:
    rs: Dict[str, Any] = {
        "scheme": scheme,
        "permanent": permanent,
    }
    if port:
        rs["port"] = str(port)
    return {"redirectScheme": rs}


def spec_redirect_regex(
    regex: str,
    replacement: str,
    permanent: bool = False,
) -> Dict[str, Any]:
    return {
        "redirectRegex": {
            "regex": regex,
            "replacement": replacement,
            "permanent": permanent,
        }
    }


def spec_rate_limit(
    average: int,
    burst: int,
    period: str = "1s",
    source_criterion: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rl: Dict[str, Any] = {
        "average": int(average),
        "burst": int(burst),
        "period": str(period),
    }
    if source_criterion:
        rl["sourceCriterion"] = dict(source_criterion)
    return {"rateLimit": rl}


def spec_circuit_breaker(
    expression: str,
    response_code: int = 503,
    check_period: Optional[str] = None,
    fallback_duration: Optional[str] = None,
    recovery_duration: Optional[str] = None,
) -> Dict[str, Any]:
    cb: Dict[str, Any] = {
        "expression": expression,
        "responseCode": int(response_code),
    }
    if check_period:
        cb["checkPeriod"] = check_period
    if fallback_duration:
        cb["fallbackDuration"] = fallback_duration
    if recovery_duration:
        cb["recoveryDuration"] = recovery_duration
    return {"circuitBreaker": cb}


def spec_strip_prefix(
    prefixes: List[str],
    force_slash: Optional[bool] = None,
) -> Dict[str, Any]:
    sp: Dict[str, Any] = {"prefixes": list(prefixes)}
    if force_slash is not None:
        sp["forceSlash"] = bool(force_slash)
    return {"stripPrefix": sp}


def spec_strip_prefix_regex(regex: List[str]) -> Dict[str, Any]:
    return {"stripPrefixRegex": {"regex": list(regex)}}


def spec_inflight_req(
    amount: int,
    source_criterion: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ifr: Dict[str, Any] = {"amount": int(amount)}
    if source_criterion:
        ifr["sourceCriterion"] = dict(source_criterion)
    return {"inFlightReq": ifr}


def spec_inflight_conn(amount: int) -> Dict[str, Any]:
    return {"inFlightConn": {"amount": int(amount)}}


def spec_ip_allowlist(
    source_ranges: List[str],
    ip_strategy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cleaned = [s.strip() for s in source_ranges if s and s.strip()]
    for cidr in cleaned:
        try:
            ipaddress.ip_network(cidr, strict=False)
        except ValueError as exc:
            raise TraefikMiddlewareError(
                f"Invalid IP/CIDR '{cidr}' in ip_allow_list. Provide valid IPv4/IPv6 CIDR blocks (e.g. '10.0.0.0/8')."
            ) from exc
    block: Dict[str, Any] = {"sourceRange": cleaned}
    if ip_strategy:
        block["ipStrategy"] = dict(ip_strategy)
    return {"ipAllowList": block}


def spec_ip_denylist(source_ranges: List[str]) -> Dict[str, Any]:
    return {"ipDenyList": {"sourceRange": [s.strip() for s in source_ranges if s.strip()]}}


def spec_forward_auth(
    address: str,
    auth_response_headers: Optional[List[str]] = None,
    trust_forward_header: bool = True,
    auth_request_headers: Optional[List[str]] = None,
    tls: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    fa: Dict[str, Any] = {
        "address": address,
        "trustForwardHeader": trust_forward_header,
    }
    if auth_response_headers:
        fa["authResponseHeaders"] = [h.strip() for h in auth_response_headers if h.strip()]
    if auth_request_headers:
        fa["authRequestHeaders"] = [h.strip() for h in auth_request_headers if h.strip()]
    if tls:
        fa["tls"] = dict(tls)
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
    sts_seconds: Optional[int] = None,
    sts_include_subdomains: Optional[bool] = None,
    sts_preload: Optional[bool] = None,
    force_sts_header: Optional[bool] = None,
    content_type_nosniff: Optional[bool] = None,
    browser_xss_filter: Optional[bool] = None,
    referrer_policy: Optional[str] = None,
    frame_deny: Optional[bool] = None,
) -> Dict[str, Any]:
    """Single `headers` middleware spec (CORS, HSTS, security, and custom headers)."""
    h: Dict[str, Any] = {}
    if access_control_allow_origin_list:
        h["accessControlAllowOriginList"] = list(access_control_allow_origin_list)
    if access_control_allow_methods:
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
    if sts_seconds is not None:
        h["stsSeconds"] = int(sts_seconds)
    if sts_include_subdomains is not None:
        h["stsIncludeSubdomains"] = bool(sts_include_subdomains)
    if sts_preload is not None:
        h["stsPreload"] = bool(sts_preload)
    if force_sts_header is not None:
        h["forceSTSHeader"] = bool(force_sts_header)
    if content_type_nosniff is not None:
        h["contentTypeNosniff"] = bool(content_type_nosniff)
    if browser_xss_filter is not None:
        h["browserXssFilter"] = bool(browser_xss_filter)
    if referrer_policy:
        h["referrerPolicy"] = str(referrer_policy)
    if frame_deny is not None:
        h["frameDeny"] = bool(frame_deny)
    return {"headers": h}


def spec_basic_auth(
    secret: str,
    realm: Optional[str] = None,
    remove_header: Optional[bool] = None,
    header_field: Optional[str] = None,
) -> Dict[str, Any]:
    ba: Dict[str, Any] = {"secret": secret}
    if realm:
        ba["realm"] = realm
    if remove_header is not None:
        ba["removeHeader"] = bool(remove_header)
    if header_field:
        ba["headerField"] = header_field
    return {"basicAuth": ba}


def spec_digest_auth(
    secret: str,
    realm: Optional[str] = None,
    remove_header: Optional[bool] = None,
    header_field: Optional[str] = None,
) -> Dict[str, Any]:
    da: Dict[str, Any] = {"secret": secret}
    if realm:
        da["realm"] = realm
    if remove_header is not None:
        da["removeHeader"] = bool(remove_header)
    if header_field:
        da["headerField"] = header_field
    return {"digestAuth": da}


def spec_buffering(
    max_request_body_bytes: int,
    mem_request_body_bytes: Optional[int] = None,
    max_response_body_bytes: Optional[int] = None,
    mem_response_body_bytes: Optional[int] = None,
    retry_expression: Optional[str] = None,
) -> Dict[str, Any]:
    buf: Dict[str, Any] = {"maxRequestBodyBytes": int(max_request_body_bytes)}
    if mem_request_body_bytes is not None:
        buf["memRequestBodyBytes"] = int(mem_request_body_bytes)
    if max_response_body_bytes is not None:
        buf["maxResponseBodyBytes"] = int(max_response_body_bytes)
    if mem_response_body_bytes is not None:
        buf["memResponseBodyBytes"] = int(mem_response_body_bytes)
    if retry_expression:
        buf["retryExpression"] = retry_expression
    return {"buffering": buf}


def spec_replace_path(path: str) -> Dict[str, Any]:
    return {"replacePath": {"path": path}}


def spec_replace_path_regex(regex: str, replacement: str) -> Dict[str, Any]:
    return {"replacePathRegex": {"regex": regex, "replacement": replacement}}


def spec_add_prefix(prefix: str) -> Dict[str, Any]:
    return {"addPrefix": {"prefix": prefix}}


def spec_chain(middlewares: List[Dict[str, str]]) -> Dict[str, Any]:
    return {"chain": {"middlewares": list(middlewares)}}


def spec_compress(
    excluded_content_types: Optional[List[str]] = None,
    min_response_body_bytes: Optional[int] = None,
    default_encoding: Optional[str] = None,
) -> Dict[str, Any]:
    comp: Dict[str, Any] = {}
    if excluded_content_types:
        comp["excludedContentTypes"] = list(excluded_content_types)
    if min_response_body_bytes is not None:
        comp["minResponseBodyBytes"] = int(min_response_body_bytes)
    if default_encoding:
        comp["defaultEncoding"] = str(default_encoding)
    return {"compress": comp}


def spec_content_type(auto_detect: bool = True) -> Dict[str, Any]:
    return {"contentType": {"autoDetect": bool(auto_detect)}}


def spec_errors(
    status: List[str],
    service: Dict[str, Any],
    query: str = "/{status}.html",
) -> Dict[str, Any]:
    return {
        "errors": {
            "status": list(status),
            "service": dict(service),
            "query": query,
        }
    }


def spec_grpc_web(allow_origins: Optional[List[str]] = None) -> Dict[str, Any]:
    return {"grpcWeb": {"allowOrigins": list(allow_origins or ["*"])}}


def spec_pass_tls_client_cert(
    pem: bool = True,
    info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    block: Dict[str, Any] = {"pem": bool(pem)}
    if info:
        block["info"] = dict(info)
    return {"passTLSClientCert": block}


def spec_plugin(plugin_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    return {"plugin": {plugin_name: dict(config)}}


def spec_retry(attempts: int = 3, initial_interval: str = "100ms") -> Dict[str, Any]:
    return {
        "retry": {
            "attempts": int(attempts),
            "initialInterval": str(initial_interval),
        }
    }


def build_middleware_spec_from_type(
    protocol: str,
    middleware_type: str,
    raw_spec: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str]]:
    """Convert a typed middleware request into a canonical Traefik CRD spec dict and lint warnings."""
    warnings: List[str] = []
    proto = protocol.strip().lower()
    mtype = middleware_type.strip().lower()
    spec_in = dict(raw_spec or {})

    if proto == "tcp":
        if mtype in ("ip_allow_list", "ipallowlist"):
            ranges = (
                spec_in.get("source_ranges")
                or spec_in.get("source_range")
                or spec_in.get("sourceRange")
                or []
            )
            if isinstance(ranges, str):
                ranges = [r.strip() for r in ranges.split(",") if r.strip()]
            if not ranges:
                raise TraefikMiddlewareError("TCP ip_allow_list requires non-empty 'source_ranges'.")
            if "0.0.0.0/0" in ranges or "::/0" in ranges:
                warnings.append("TCP ipAllowList includes 0.0.0.0/0 or ::/0, allowing all external IPs.")
            return spec_ip_allowlist(ranges), warnings
        if mtype in ("in_flight_conn", "inflightconn"):
            amount = spec_in.get("amount")
            if amount is None or int(amount) <= 0:
                raise TraefikMiddlewareError("TCP in_flight_conn requires 'amount' > 0.")
            return spec_inflight_conn(int(amount)), warnings
        raise TraefikMiddlewareError(
            f"Unsupported TCP middleware type '{middleware_type}'. Valid TCP types: ip_allow_list, in_flight_conn."
        )

    # HTTP Middleware types
    if mtype == "add_prefix":
        prefix = spec_in.get("prefix", "")
        if not prefix or not str(prefix).startswith("/"):
            raise TraefikMiddlewareError("add_prefix requires 'prefix' starting with '/'.")
        return spec_add_prefix(str(prefix)), warnings

    if mtype in ("basic_auth", "digest_auth"):
        if "users" in spec_in or "usersFile" in spec_in or "users_file" in spec_in:
            raise TraefikMiddlewareError(
                f"{mtype} rejects inline 'users' or 'usersFile' (0->1 security policy). "
                "Provide a Kubernetes Secret name via 'secret'."
            )
        secret = spec_in.get("secret")
        if not secret:
            raise TraefikMiddlewareError(f"{mtype} requires 'secret' referencing a Kubernetes Secret.")
        fn = spec_basic_auth if mtype == "basic_auth" else spec_digest_auth
        return (
            fn(
                secret=str(secret),
                realm=spec_in.get("realm"),
                remove_header=spec_in.get("remove_header", spec_in.get("removeHeader")),
                header_field=spec_in.get("header_field", spec_in.get("headerField")),
            ),
            warnings,
        )

    if mtype == "buffering":
        max_req = spec_in.get("max_request_body_bytes", spec_in.get("maxRequestBodyBytes"))
        if max_req is None or int(max_req) <= 0:
            raise TraefikMiddlewareError("buffering requires 'max_request_body_bytes' > 0.")
        return (
            spec_buffering(
                max_request_body_bytes=int(max_req),
                mem_request_body_bytes=spec_in.get("mem_request_body_bytes", spec_in.get("memRequestBodyBytes")),
                max_response_body_bytes=spec_in.get("max_response_body_bytes", spec_in.get("maxResponseBodyBytes")),
                mem_response_body_bytes=spec_in.get("mem_response_body_bytes", spec_in.get("memResponseBodyBytes")),
                retry_expression=spec_in.get("retry_expression", spec_in.get("retryExpression")),
            ),
            warnings,
        )

    if mtype == "chain":
        mws = spec_in.get("middlewares") or []
        if not mws:
            raise TraefikMiddlewareError("chain middleware requires a non-empty 'middlewares' list.")
        normalized_mws: List[Dict[str, str]] = []
        for item in mws:
            if isinstance(item, str):
                normalized_mws.append({"name": item})
            elif isinstance(item, dict) and item.get("name"):
                entry: Dict[str, str] = {"name": str(item["name"])}
                if item.get("namespace"):
                    entry["namespace"] = str(item["namespace"])
                normalized_mws.append(entry)
        return spec_chain(normalized_mws), warnings

    if mtype == "circuit_breaker":
        expr = spec_in.get("expression")
        if not expr:
            trigger = spec_in.get("trigger_type", "network_error")
            threshold = float(spec_in.get("threshold", 0.30))
            if trigger == "network_error":
                expr = f"NetworkErrorRatio() > {threshold}"
            elif trigger == "status_code":
                expr = f"ResponseCodeRatio(500, 600, 0, 600) > {threshold}"
            elif trigger == "latency":
                expr = f"LatencyAtQuantileMS(50.0) > {int(threshold)}"
            else:
                raise TraefikCircuitBreakerError(f"Unknown circuit_breaker trigger_type '{trigger}'.")
        expr_str = str(expr).strip()
        if expr_str.count("(") != expr_str.count(")") or not any(
            fn in expr_str for fn in ("NetworkErrorRatio(", "ResponseCodeRatio(", "LatencyAtQuantileMS(")
        ):
            raise TraefikCircuitBreakerError(
                f"Invalid circuitBreaker expression '{expr_str}'. Must use NetworkErrorRatio(), ResponseCodeRatio(...), or LatencyAtQuantileMS(...)."
            )
        return (
            spec_circuit_breaker(
                expression=expr_str,
                response_code=int(spec_in.get("response_code", spec_in.get("responseCode", 503))),
                check_period=spec_in.get("check_period", spec_in.get("checkPeriod")),
                fallback_duration=spec_in.get("fallback_duration", spec_in.get("fallbackDuration")),
                recovery_duration=spec_in.get("recovery_duration", spec_in.get("recoveryDuration")),
            ),
            warnings,
        )

    if mtype == "compress":
        return (
            spec_compress(
                excluded_content_types=spec_in.get("excluded_content_types", spec_in.get("excludedContentTypes")),
                min_response_body_bytes=spec_in.get("min_response_body_bytes", spec_in.get("minResponseBodyBytes")),
                default_encoding=spec_in.get("default_encoding", spec_in.get("defaultEncoding")),
            ),
            warnings,
        )

    if mtype == "content_type":
        return spec_content_type(bool(spec_in.get("auto_detect", spec_in.get("autoDetect", True)))), warnings

    if mtype == "errors":
        status = spec_in.get("status") or ["500-599"]
        service = spec_in.get("service")
        if not service or not isinstance(service, dict) or not service.get("name"):
            raise TraefikMiddlewareError("errors middleware requires 'service' dict with 'name' and 'port'.")
        return spec_errors(status=status, service=service, query=spec_in.get("query", "/{status}.html")), warnings

    if mtype == "forward_auth":
        address = spec_in.get("address")
        if not address or not str(address).startswith(("http://", "https://")):
            raise TraefikMiddlewareError("forward_auth requires 'address' starting with http:// or https://.")
        return (
            spec_forward_auth(
                address=str(address),
                auth_response_headers=spec_in.get("auth_response_headers", spec_in.get("authResponseHeaders")),
                trust_forward_header=bool(spec_in.get("trust_forward_header", spec_in.get("trustForwardHeader", True))),
                auth_request_headers=spec_in.get("auth_request_headers", spec_in.get("authRequestHeaders")),
                tls=spec_in.get("tls"),
            ),
            warnings,
        )

    if mtype == "grpc_web":
        return spec_grpc_web(spec_in.get("allow_origins", spec_in.get("allowOrigins"))), warnings

    if mtype == "headers":
        origins = (
            spec_in.get("access_control_allow_origin_list")
            or spec_in.get("access_control_allow_origins_list")
            or spec_in.get("accessControlAllowOriginList")
        )
        allow_creds = spec_in.get("access_control_allow_credentials", spec_in.get("accessControlAllowCredentials"))
        if origins and "*" in origins and allow_creds:
            warnings.append(
                "CORS configuration combines accessControlAllowOriginList=['*'] with accessControlAllowCredentials=True, "
                "which browsers reject or treat as insecure."
            )
        block = spec_headers_block(
            access_control_allow_origin_list=origins,
            access_control_allow_methods=spec_in.get("access_control_allow_methods", spec_in.get("accessControlAllowMethods")),
            access_control_allow_headers=spec_in.get("access_control_allow_headers", spec_in.get("accessControlAllowHeaders")),
            access_control_allow_credentials=allow_creds,
            access_control_max_age=spec_in.get("access_control_max_age", spec_in.get("accessControlMaxAge")),
            access_control_expose_headers=spec_in.get("access_control_expose_headers", spec_in.get("accessControlExposeHeaders")),
            custom_request_headers=spec_in.get("custom_request_headers", spec_in.get("customRequestHeaders")),
            custom_response_headers=spec_in.get("custom_response_headers", spec_in.get("customResponseHeaders")),
            sts_seconds=spec_in.get("sts_seconds", spec_in.get("stsSeconds")),
            sts_include_subdomains=spec_in.get("sts_include_subdomains", spec_in.get("stsIncludeSubdomains")),
            sts_preload=spec_in.get("sts_preload", spec_in.get("stsPreload")),
            force_sts_header=spec_in.get("force_sts_header", spec_in.get("forceSTSHeader")),
            content_type_nosniff=spec_in.get("content_type_nosniff", spec_in.get("contentTypeNosniff")),
            browser_xss_filter=spec_in.get("browser_xss_filter", spec_in.get("browserXssFilter")),
            referrer_policy=spec_in.get("referrer_policy", spec_in.get("referrerPolicy")),
            frame_deny=spec_in.get("frame_deny", spec_in.get("frameDeny")),
        )
        if not block["headers"]:
            raise TraefikMiddlewareError("headers middleware requires at least one header, CORS, or HSTS field.")
        return block, warnings

    if mtype in ("ip_allow_list", "ipallowlist"):
        ranges = (
            spec_in.get("source_ranges")
            or spec_in.get("source_range")
            or spec_in.get("sourceRange")
            or []
        )
        if isinstance(ranges, str):
            ranges = [r.strip() for r in ranges.split(",") if r.strip()]
        if not ranges:
            raise TraefikMiddlewareError("ip_allow_list requires non-empty 'source_ranges'.")
        if "0.0.0.0/0" in ranges or "::/0" in ranges:
            warnings.append("ipAllowList includes 0.0.0.0/0 or ::/0, effectively allowing all IPs.")
        ip_strategy = spec_in.get("ip_strategy", spec_in.get("ipStrategy"))
        return spec_ip_allowlist(ranges, ip_strategy=ip_strategy), warnings

    if mtype in ("ip_deny_list", "ipdenylist"):
        ranges = (
            spec_in.get("source_ranges")
            or spec_in.get("source_range")
            or spec_in.get("sourceRange")
            or []
        )
        if isinstance(ranges, str):
            ranges = [r.strip() for r in ranges.split(",") if r.strip()]
        if not ranges:
            raise TraefikMiddlewareError("ip_deny_list requires non-empty 'source_ranges'.")
        return spec_ip_denylist(ranges), warnings

    if mtype in ("in_flight_req", "inflight_req", "inflightreq"):
        amount = spec_in.get("amount")
        if amount is None or int(amount) <= 0:
            raise TraefikMiddlewareError("in_flight_req requires 'amount' > 0.")
        return (
            spec_inflight_req(
                amount=int(amount),
                source_criterion=spec_in.get("source_criterion", spec_in.get("sourceCriterion")),
            ),
            warnings,
        )

    if mtype == "pass_tls_client_cert":
        return (
            spec_pass_tls_client_cert(
                pem=bool(spec_in.get("pem", True)),
                info=spec_in.get("info"),
            ),
            warnings,
        )

    if mtype == "plugin":
        plugin_name = spec_in.get("plugin_name") or spec_in.get("name")
        config = spec_in.get("config")
        if not plugin_name or not isinstance(config, dict):
            raise TraefikMiddlewareError("plugin middleware requires 'plugin_name' and 'config' dict.")
        return spec_plugin(str(plugin_name), config), warnings

    if mtype == "rate_limit":
        avg = int(spec_in.get("average", 100))
        burst = int(spec_in.get("burst", 200))
        period = str(spec_in.get("period", "1s"))
        if avg <= 0 or burst <= 0:
            raise TraefikMiddlewareError("rate_limit requires 'average' > 0 and 'burst' > 0.")
        return (
            spec_rate_limit(
                average=avg,
                burst=burst,
                period=period,
                source_criterion=spec_in.get("source_criterion", spec_in.get("sourceCriterion")),
            ),
            warnings,
        )

    if mtype == "redirect_regex":
        regex = spec_in.get("regex")
        replacement = spec_in.get("replacement")
        if not regex or replacement is None:
            raise TraefikMiddlewareError("redirect_regex requires 'regex' and 'replacement'.")
        return (
            spec_redirect_regex(
                regex=str(regex),
                replacement=str(replacement),
                permanent=bool(spec_in.get("permanent", False)),
            ),
            warnings,
        )

    if mtype == "redirect_scheme":
        return (
            spec_redirect_scheme(
                permanent=bool(spec_in.get("permanent", True)),
                scheme=str(spec_in.get("scheme", "https")),
                port=spec_in.get("port"),
            ),
            warnings,
        )

    if mtype == "replace_path":
        path = spec_in.get("path")
        if not path or not str(path).startswith("/"):
            raise TraefikMiddlewareError("replace_path requires 'path' starting with '/'.")
        return spec_replace_path(str(path)), warnings

    if mtype == "replace_path_regex":
        regex = spec_in.get("regex")
        replacement = spec_in.get("replacement")
        if not regex or replacement is None:
            raise TraefikMiddlewareError("replace_path_regex requires 'regex' and 'replacement'.")
        return spec_replace_path_regex(str(regex), str(replacement)), warnings

    if mtype == "retry":
        attempts = int(spec_in.get("attempts", 3))
        if attempts <= 0:
            raise TraefikMiddlewareError("retry requires 'attempts' > 0.")
        return (
            spec_retry(
                attempts=attempts,
                initial_interval=str(spec_in.get("initial_interval", spec_in.get("initialInterval", "100ms"))),
            ),
            warnings,
        )

    if mtype == "strip_prefix":
        prefixes = spec_in.get("prefixes") or []
        if isinstance(prefixes, str):
            prefixes = [p.strip() for p in prefixes.split(",") if p.strip()]
        if not prefixes:
            raise TraefikMiddlewareError("strip_prefix requires non-empty 'prefixes'.")
        raw_fs = spec_in.get("force_slash", spec_in.get("forceSlash"))
        return (
            spec_strip_prefix(
                prefixes=prefixes,
                force_slash=bool(raw_fs) if raw_fs is not None else None,
            ),
            warnings,
        )

    if mtype == "strip_prefix_regex":
        regex = spec_in.get("regex") or []
        if isinstance(regex, str):
            regex = [regex]
        if not regex:
            raise TraefikMiddlewareError("strip_prefix_regex requires non-empty 'regex' list.")
        return spec_strip_prefix_regex(regex), warnings

    raise TraefikMiddlewareError(f"Unsupported HTTP middleware type '{middleware_type}'.")
