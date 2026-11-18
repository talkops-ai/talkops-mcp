"""Unit tests for all 24 HTTP and 2 TCP Traefik v3 middleware builders."""

import pytest
from traefik_mcp_server.exceptions.custom import (
    TraefikCircuitBreakerError,
    TraefikMiddlewareError,
)
from traefik_mcp_server.traefik_middleware_builders import (
    build_middleware_crd,
    build_middleware_spec_from_type,
)


@pytest.mark.parametrize(
    "mw_type,raw_spec,expected_key",
    [
        ("rate_limit", {"average": 50, "burst": 100}, "rateLimit"),
        ("in_flight_req", {"amount": 25}, "inFlightReq"),
        ("circuit_breaker", {"expression": "NetworkErrorRatio() > 0.30"}, "circuitBreaker"),
        ("retry", {"attempts": 3, "initial_interval": "100ms"}, "retry"),
        ("strip_prefix", {"prefixes": ["/api"]}, "stripPrefix"),
        ("strip_prefix_regex", {"regex": ["^/v[0-9]+"]}, "stripPrefixRegex"),
        ("add_prefix", {"prefix": "/v2"}, "addPrefix"),
        ("replace_path", {"path": "/target"}, "replacePath"),
        ("replace_path_regex", {"regex": "^/old/(.*)", "replacement": "/new/$1"}, "replacePathRegex"),
        ("redirect_scheme", {"scheme": "https", "permanent": True}, "redirectScheme"),
        ("redirect_regex", {"regex": "^http://example.com/(.*)", "replacement": "https://example.com/$1"}, "redirectRegex"),
        ("headers", {"sts_seconds": 31536000, "frame_deny": True}, "headers"),
        ("ip_allow_list", {"source_range": ["10.0.0.0/8"]}, "ipAllowList"),
        ("ip_deny_list", {"source_range": ["192.0.2.0/24"]}, "ipDenyList"),
        ("basic_auth", {"secret": "admin-htpasswd"}, "basicAuth"),
        ("digest_auth", {"secret": "admin-digest"}, "digestAuth"),
        ("forward_auth", {"address": "https://auth.example.com/verify"}, "forwardAuth"),
        ("compress", {"min_response_body_bytes": 1024}, "compress"),
        ("buffering", {"max_request_body_bytes": 1048576}, "buffering"),
        ("errors", {"status": ["500-599"], "service": {"name": "err-svc", "port": 80}}, "errors"),
        ("chain", {"middlewares": [{"name": "mw-a"}, {"name": "mw-b"}]}, "chain"),
        ("plugin", {"plugin_name": "coraza", "config": {"directives": []}}, "plugin"),
        ("grpc_web", {"allow_origins": ["*"]}, "grpcWeb"),
        ("pass_tls_client_cert", {"pem": True}, "passTLSClientCert"),
        ("content_type", {"auto_detect": True}, "contentType"),
    ],
)
def test_all_24_http_middleware_builders(mw_type, raw_spec, expected_key):
    spec_dict, _ = build_middleware_spec_from_type("http", mw_type, raw_spec)
    assert expected_key in spec_dict
    crd = build_middleware_crd("test-mw", "default", spec_dict, protocol="http")
    assert crd["apiVersion"] == "traefik.io/v1alpha1"
    assert crd["kind"] == "Middleware"


def test_tcp_middleware_builders():
    spec_allow, _ = build_middleware_spec_from_type("tcp", "ip_allow_list", {"source_range": ["10.0.0.0/8"]})
    assert "ipAllowList" in spec_allow
    crd = build_middleware_crd("tcp-allow", "default", spec_allow, protocol="tcp")
    assert crd["kind"] == "MiddlewareTCP"

    spec_conn, _ = build_middleware_spec_from_type("tcp", "in_flight_conn", {"amount": 50})
    assert "inFlightConn" in spec_conn


def test_inline_basic_and_digest_auth_users_rejected():
    with pytest.raises(TraefikMiddlewareError, match="secret"):
        build_middleware_spec_from_type("http", "basic_auth", {"users": ["admin:$apr1$..."]})

    with pytest.raises(TraefikMiddlewareError, match="secret"):
        build_middleware_spec_from_type("http", "digest_auth", {"users": ["admin:realm:hash"]})


def test_invalid_circuit_breaker_expression_rejected():
    with pytest.raises(TraefikCircuitBreakerError):
        build_middleware_spec_from_type("http", "circuit_breaker", {"expression": "InvalidExpr() > 1"})
