"""Regression tests for Domain 5 live-cluster & schema-alias fixes."""

import pytest
from fastmcp.client import Client

from traefik_mcp_server.models.schemas import (
    HttpRouteRule,
    MiddlewarePatchSpec,
    MirroringSpec,
    RouteTLS,
    StickyCookie,
)
from traefik_mcp_server.services.guards import check_ownership
from traefik_mcp_server.services.rule_engine import evaluate_rule_against_request, lint_v3_rule


def test_schema_aliases_and_normalizers():
    sc = StickyCookie(name="shop_aff", same_site="Lax")
    assert sc.same_site == "lax"

    mw_patch = MiddlewarePatchSpec(action="attach", items=["mw-a", {"name": "mw-b"}])
    assert [r.name for r in mw_patch.refs] == ["mw-a", "mw-b"]

    tls = RouteTLS(secretName="shop-tls", options_name="mozilla-modern", options_namespace="otel-demo")
    assert tls.secret_name == "shop-tls"
    assert tls.options == {"name": "mozilla-modern", "namespace": "otel-demo"}

    rule = HttpRouteRule(
        match="Host(`shop.otel-demo.talkops.io`)",
        service={"name": "frontend-proxy-wrr", "kind": "TraefikService"},
        middlewares=["storefront-rl"],
    )
    assert len(rule.services) == 1
    assert rule.services[0].name == "frontend-proxy-wrr"
    assert rule.middlewares[0].name == "storefront-rl"

    mir = MirroringSpec(
        primary_service={"name": "image-provider", "port": 8081},
        mirrors=[{"name": "image-provider-shadow", "port": 8081, "percent": 10}],
        mirrorBody=False,
        maxBodySize=1048576,
    )
    assert mir.main.name == "image-provider"
    assert mir.mirror_body is False
    assert mir.max_body_size == 1048576


def test_argo_rollouts_owner_references_guard():
    ts_obj = {
        "apiVersion": "traefik.io/v1alpha1",
        "kind": "TraefikService",
        "metadata": {
            "name": "frontend-wrr",
            "namespace": "otel-demo",
            "ownerReferences": [
                {"apiVersion": "argoproj.io/v1alpha1", "kind": "Rollout", "name": "frontend"}
            ],
        },
    }
    guard, owner_type = check_ownership("TraefikService", "frontend-wrr", "otel-demo", existing_obj=ts_obj)
    assert guard.passed is False
    assert owner_type == "argo_rollouts"


def test_v2_single_arg_query_lint_and_paren_evaluation():
    ok, issues, _ = lint_v3_rule("Host(`shop.example.com`) && Query(`currency=EUR`)")
    assert ok is False
    assert any("Query" in i for i in issues)

    cohort_rule = (
        "Host(`shop.otel-demo.talkops.io`) && PathPrefix(`/`) && "
        "(Header(`X-Canary`, `true`) || HeaderRegexp(`Cookie`, `(?:^|;\\s*)otel_cohort=beta(?:;|$)`))"
    )
    matched, _, _ = evaluate_rule_against_request(
        cohort_rule,
        {
            "host": "shop.otel-demo.talkops.io",
            "path": "/cart",
            "headers": {"Cookie": "a=1; otel_cohort=beta; b=2"},
        },
    )
    assert matched is True


@pytest.mark.asyncio
async def test_weighted_healthcheck_dict_and_nondestructive_tls_patch(mcp_rw):
    async with Client(mcp_rw) as client:
        wrr = await client.call_tool(
            "traefik_configure_weighted_service",
            {
                "name": "storefront-wrr",
                "namespace": "default",
                "backends": [
                    {"name": "payments-stable", "port": 80, "weight": 95},
                    {"name": "payments-canary", "port": 80, "weight": 5},
                ],
                "health_check": {"path": "/", "interval": "10s", "timeout": "3s"},
                "dry_run": False,
            },
        )
        assert wrr.structured_content["status"] == "success"
        assert "healthCheck:" in wrr.structured_content["manifest"]
        assert "weighted:\n    healthCheck" not in wrr.structured_content["manifest"]

        # Patch only TLSOption on payments-route and verify secretName is preserved
        patched = await client.call_tool(
            "traefik_update_route",
            {
                "name": "payments-route",
                "namespace": "default",
                "changes": {"tls": {"options_name": "modern-tls"}},
                "dry_run": True,
            },
        )
        manifest = patched.structured_content["manifest"]
        assert "secretName: prod-wildcard-tls" in manifest
        assert "modern-tls" in manifest

        # TLSStore snake_case default_certificate.secret_name
        store_res = await client.call_tool(
            "traefik_configure_tls_policy",
            {
                "kind": "TLSStore",
                "name": "default",
                "namespace": "traefik",
                "spec": {"default_certificate": {"secret_name": "otel-demo-wildcard-tls"}},
                "dry_run": True,
                "confirm": True,
            },
        )
        assert store_res.structured_content["status"] == "preview"
        assert "otel-demo-wildcard-tls" in store_res.structured_content["manifest"]

        # RouteChanges ingress_class + backend camelCase serversTransport
        cls_patch = await client.call_tool(
            "traefik_update_route",
            {
                "name": "payments-route",
                "namespace": "default",
                "changes": {
                    "ingress_class": "traefik",
                    "backend": {"serversTransport": "slow-query-transport"},
                },
                "dry_run": True,
            },
        )
        assert cls_patch.structured_content["status"] == "preview"
        assert "kubernetes.io/ingress.class: traefik" in cls_patch.structured_content["manifest"]
        assert "serversTransport: slow-query-transport" in cls_patch.structured_content["manifest"]
