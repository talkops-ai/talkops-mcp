"""Unit tests for shared Traefik Middleware CRD builders and migrator wiring."""

import pytest
import yaml as pyyaml

from traefik_mcp_server.migration_nginx.migrator_traefik import generate_middlewares
from traefik_mcp_server.migration_nginx.scanner import IngressInfo, PathInfo, ServiceRef
from traefik_mcp_server.traefik_middleware_builders import (
    TRAEFIK_MIDDLEWARE_API_VERSION,
    build_middleware_crd,
    middleware_dict_to_yaml,
    nginx_rate_limit_from_annotations,
    parse_nginx_proxy_body_size_to_bytes,
    spec_add_prefix,
    spec_buffering,
    spec_circuit_breaker,
    spec_forward_auth,
    spec_headers_block,
    spec_inflight_req,
    spec_ip_allowlist,
    spec_rate_limit,
    spec_redirect_scheme,
    spec_replace_path,
    spec_replace_path_regex,
    spec_strip_prefix,
)


def test_spec_redirect_scheme():
    s = spec_redirect_scheme(permanent=True)
    assert s["redirectScheme"]["scheme"] == "https"
    assert s["redirectScheme"]["permanent"] is True


def test_spec_rate_limit():
    s = spec_rate_limit(50, 100, "1s")
    assert s["rateLimit"]["average"] == 50
    assert s["rateLimit"]["burst"] == 100
    assert s["rateLimit"]["period"] == "1s"


def test_spec_circuit_breaker():
    s = spec_circuit_breaker("NetworkErrorRatio() > 0.1", 503)
    assert s["circuitBreaker"]["expression"] == "NetworkErrorRatio() > 0.1"
    assert s["circuitBreaker"]["responseCode"] == 503


def test_spec_strip_prefix():
    s = spec_strip_prefix(["/api"], force_slash=True)
    assert s["stripPrefix"]["prefixes"] == ["/api"]
    assert s["stripPrefix"]["forceSlash"] is True


def test_spec_inflight_req():
    s = spec_inflight_req(42)
    assert s["inFlightReq"]["amount"] == 42


def test_spec_ip_allowlist():
    s = spec_ip_allowlist(["10.0.0.0/8", "192.168.1.1/32"])
    assert s["ipAllowList"]["sourceRange"] == ["10.0.0.0/8", "192.168.1.1/32"]


def test_spec_forward_auth():
    s = spec_forward_auth(
        "http://auth.internal/verify",
        auth_response_headers=["X-User", "X-Groups"],
        trust_forward_header=True,
    )
    assert s["forwardAuth"]["address"] == "http://auth.internal/verify"
    assert s["forwardAuth"]["trustForwardHeader"] is True
    assert s["forwardAuth"]["authResponseHeaders"] == ["X-User", "X-Groups"]


def test_spec_headers_cors_and_custom():
    s = spec_headers_block(
        access_control_allow_origin_list=["https://a.example"],
        access_control_allow_methods=["GET", "POST"],
        custom_response_headers={"X-App": "1"},
    )
    h = s["headers"]
    assert h["accessControlAllowOriginList"] == ["https://a.example"]
    assert "GET" in h["accessControlAllowMethods"]
    assert h["customResponseHeaders"]["X-App"] == "1"


def test_spec_buffering():
    s = spec_buffering(8388608, mem_request_body_bytes=1048576)
    assert s["buffering"]["maxRequestBodyBytes"] == 8388608
    assert s["buffering"]["memRequestBodyBytes"] == 1048576


def test_spec_replace_path_and_regex():
    assert spec_replace_path("/new")["replacePath"]["path"] == "/new"
    rx = spec_replace_path_regex("^/a", "/b")
    assert rx["replacePathRegex"]["regex"] == "^/a"
    assert rx["replacePathRegex"]["replacement"] == "/b"


def test_spec_add_prefix():
    assert spec_add_prefix("/prefix")["addPrefix"]["prefix"] == "/prefix"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("8m", 8 * 1024**2),
        ("1024k", 1024 * 1024),
        ("1g", 1024**3),
        ("4096", 4096),
    ],
)
def test_parse_nginx_proxy_body_size(raw, expected):
    assert parse_nginx_proxy_body_size_to_bytes(raw) == expected


def test_parse_nginx_proxy_body_size_invalid():
    with pytest.raises(ValueError):
        parse_nginx_proxy_body_size_to_bytes("")
    with pytest.raises(ValueError):
        parse_nginx_proxy_body_size_to_bytes("12xb")


def test_nginx_rate_limit_from_annotations():
    avg, burst, period = nginx_rate_limit_from_annotations({"limit-rps": "10"})
    assert avg == 10 and period == "1s" and burst == 50
    avg2, burst2, period2 = nginx_rate_limit_from_annotations(
        {"limit-rpm": "60", "limit-burst-multiplier": "2"}
    )
    assert avg2 == 60 and period2 == "1m" and burst2 == 120


def test_middleware_yaml_round_trip():
    obj = build_middleware_crd(
        "mw1",
        "default",
        spec_redirect_scheme(False),
        labels={"migration.source": "ing-a"},
    )
    y = middleware_dict_to_yaml(obj)
    loaded = pyyaml.safe_load(y)
    assert loaded["kind"] == "Middleware"
    assert loaded["apiVersion"] == TRAEFIK_MIDDLEWARE_API_VERSION
    assert loaded["metadata"]["labels"]["migration.source"] == "ing-a"
    assert loaded["spec"]["redirectScheme"]["scheme"] == "https"


def _minimal_ingress(**nginx_ann):
    return IngressInfo(
        namespace="default",
        name="demo",
        ingress_class="nginx",
        hosts=["demo.example"],
        paths=[
            PathInfo(
                host="demo.example",
                path="/",
                path_type="Prefix",
                service_name="svc",
                service_port=80,
            )
        ],
        tls_enabled=False,
        tls_secrets=[],
        annotations={},
        nginx_annotations=dict(nginx_ann),
        services=[ServiceRef(namespace="default", name="svc", port=80)],
        complexity="complex",
    )


def test_generate_middlewares_includes_buffering_and_app_root():
    ing = _minimal_ingress(**{"proxy-body-size": "8m", "app-root": "/home"})
    mws = generate_middlewares(ing)
    by_name = {m.name: m for m in mws}
    assert "demo-buffering" in by_name
    assert "demo-app-root" in by_name
    assert "buffering" in by_name["demo-buffering"].yaml
    assert "maxRequestBodyBytes" in by_name["demo-buffering"].yaml
    assert "addPrefix" in by_name["demo-app-root"].yaml
    assert "/home" in by_name["demo-app-root"].yaml


def test_generate_middlewares_skips_invalid_proxy_body_size():
    ing = _minimal_ingress(**{"proxy-body-size": "not-a-size"})
    mws = generate_middlewares(ing)
    assert not any(m.name.endswith("-buffering") for m in mws)
