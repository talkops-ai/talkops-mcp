"""Unit tests for Traefik v3 match rule compiler, v2 syntax linter, priority calculator, and static evaluator."""

import pytest
from traefik_mcp_server.exceptions.custom import TraefikRouteConfigError
from traefik_mcp_server.models.schemas import RouteMatch
from traefik_mcp_server.services.rule_engine import (
    compile_route_match,
    compute_default_priority,
    evaluate_rule_against_request,
    extract_hosts_from_rule,
    lint_v3_rule,
)


def test_compile_structured_route_match_to_v3():
    m = RouteMatch(
        host=["api.example.com", "v2.example.com"],
        path_prefix="/orders",
        methods=["GET", "POST"],
        headers={"X-Canary": "true"},
        cookies={"cohort": "beta"},
        query={"version": "2"},
        client_ip="10.0.0.0/8",
    )
    rule = compile_route_match(m)
    assert "(Host(`api.example.com`) || Host(`v2.example.com`))" in rule
    assert "PathPrefix(`/orders`)" in rule
    assert "(Method(`GET`) || Method(`POST`))" in rule
    assert "Header(`X-Canary`, `true`)" in rule
    assert "HeaderRegexp(`Cookie`," in rule
    assert "Query(`version`, `2`)" in rule
    assert "ClientIP(`10.0.0.0/8`)" in rule


def test_lint_v3_rule_rejects_v2_syntax():
    valid, issues, _ = lint_v3_rule("Headers(`X-Env`, `prod`)")
    assert valid is False
    assert any("Headers" in i for i in issues)

    valid_multi, issues_multi, _ = lint_v3_rule("Host(`a.example.com`, `b.example.com`)")
    assert valid_multi is False
    assert any("single argument" in i for i in issues_multi)

    valid_curly, issues_curly, _ = lint_v3_rule("HostRegexp(`{sub:[a-z]+}.example.com`)")
    assert valid_curly is False

    with pytest.raises(TraefikRouteConfigError):
        compile_route_match("Headers(`X-Env`, `prod`)")


def test_compute_default_priority_and_extract_hosts():
    rule = "Host(`api.example.com`) && PathPrefix(`/payments`)"
    assert compute_default_priority(rule, None) == len(rule)
    assert compute_default_priority(rule, 250) == 250
    assert extract_hosts_from_rule(rule) == ["api.example.com"]


def test_evaluate_rule_against_synthetic_request():
    rule = "Host(`api.example.com`) && PathPrefix(`/payments`) && Header(`X-Canary`, `true`)"
    ok, matched, failed = evaluate_rule_against_request(
        rule,
        {
            "host": "api.example.com",
            "path": "/payments/checkout",
            "method": "GET",
            "headers": {"x-canary": "true"},
        },
    )
    assert ok is True
    assert len(matched) == 3
    assert failed == []

    ok2, matched2, failed2 = evaluate_rule_against_request(
        rule,
        {
            "host": "api.example.com",
            "path": "/payments/checkout",
            "method": "GET",
            "headers": {},
        },
    )
    assert ok2 is False
    assert len(matched2) == 2
    assert len(failed2) == 1
