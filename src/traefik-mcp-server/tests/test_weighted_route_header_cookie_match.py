"""Unit tests for weighted IngressRoute match rules with header/cookie constraints."""

import asyncio
from unittest.mock import MagicMock

from traefik_mcp_server.config import KubernetesConfig, ServerConfig
from traefik_mcp_server.services.traefik_service import TraefikService


def _cfg() -> ServerConfig:
    return ServerConfig(kubernetes=KubernetesConfig())


def test_append_header_match():
    svc = TraefikService(_cfg())
    base = "Host(`app.example.com`)"
    out = svc._append_header_or_cookie_match(
        base, header_name="X-Canary", header_value="true"
    )
    assert out == "Host(`app.example.com`) && Header(`X-Canary`, `true`)"


def test_append_header_match_default_value():
    svc = TraefikService(_cfg())
    base = "Host(`app.example.com`)"
    out = svc._append_header_or_cookie_match(base, header_name="X-Beta", header_value=None)
    assert out == "Host(`app.example.com`) && Header(`X-Beta`, `true`)"


def test_append_cookie_match_with_regex():
    svc = TraefikService(_cfg())
    base = "Host(`app.example.com`) && PathPrefix(`/api`)"
    out = svc._append_header_or_cookie_match(
        base, cookie_name="canary", cookie_regex=".*yes.*"
    )
    assert (
        out
        == "Host(`app.example.com`) && PathPrefix(`/api`) && HeaderRegexp(`Cookie`, `canary=.*yes.*`)"
    )


def test_append_cookie_match_default_regex():
    svc = TraefikService(_cfg())
    base = "Host(`app.example.com`)"
    out = svc._append_header_or_cookie_match(base, cookie_name="canary", cookie_regex=None)
    assert (
        out
        == "Host(`app.example.com`) && HeaderRegexp(`Cookie`, `.*canary=true.*`)"
    )


def test_cookie_wins_over_header():
    svc = TraefikService(_cfg())
    base = "Host(`x`)"
    out = svc._append_header_or_cookie_match(
        base,
        cookie_name="c",
        cookie_regex=".*",
        header_name="H",
        header_value="v",
    )
    assert "Cookie" in out and "Header(`H`" not in out


def test_create_weighted_route_passes_match_to_ingress():
    svc = TraefikService(_cfg())
    ts_api = MagicMock()
    ir_api = MagicMock()
    svc._initialized = True
    svc._k8s_client = MagicMock()
    svc._traefikservice_api = ts_api
    svc._ingressroute_api = ir_api

    asyncio.run(
        svc.create_weighted_route(
            route_name="r1",
            namespace="ns1",
            hostname="api.example.com",
            stable_service="st",
            canary_service="ca",
            stable_weight=50,
            canary_weight=50,
            path_prefix="/v2",
            header_name="Accept",
            header_value="application/vnd.v2+json",
        )
    )

    ir_api.create.assert_called_once()
    body = ir_api.create.call_args.kwargs["body"]
    assert body["spec"]["routes"][0]["match"] == (
        "Host(`api.example.com`) && PathPrefix(`/v2`) "
        "&& Header(`Accept`, `application/vnd.v2+json`)"
    )
