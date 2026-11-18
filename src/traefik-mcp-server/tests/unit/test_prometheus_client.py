"""Unit tests for PrometheusClient label regex builder, window comparison, and graceful degradation."""

from traefik_mcp_server.services.prometheus_client import (
    PrometheusClient,
    build_traefik_label_regex,
)
from tests.fixtures.prometheus_responses import get_prometheus_fixture


def test_build_traefik_label_regex_matches_kubernetes_and_crd_suffixes():
    regex = build_traefik_label_regex("default", "payments-wrr", scope="service")
    assert "default-payments-wrr" in regex
    assert "@kubernetes" in regex


def test_prometheus_client_graceful_degradation_when_unconfigured():
    client = PrometheusClient(base_url=None)
    assert client.is_reachable() is False
    summary = client.get_service_summary("default", "payments-wrr")
    assert summary["status"] == "unavailable"
    cmp_res = client.compare_windows("service", "payments-wrr", "default")
    assert cmp_res["prometheus_available"] is False


def test_prometheus_client_compare_windows_with_fixture_and_backend_split():
    client = PrometheusClient(
        base_url="http://prometheus:9090",
        fixture_data=get_prometheus_fixture(),
    )
    assert client.is_reachable() is True
    res = client.compare_windows(
        scope="service",
        name="payments-wrr",
        namespace="default",
        baseline_window="1h",
        comparison_window="15m",
        configured_backends=[
            {"name": "payments-stable", "weight": 90},
            {"name": "payments-canary", "weight": 10},
        ],
    )
    assert res["prometheus_available"] is True
    assert res["baseline"]["rps"] == 135.0
    assert res["comparison"]["rps"] == 142.0
    assert len(res["backend_split"]) == 2
