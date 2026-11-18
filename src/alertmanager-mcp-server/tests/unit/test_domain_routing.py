"""Unit tests for `alertmanager_mcp_server.domain.routing`."""

from __future__ import annotations

from datetime import datetime, timezone
import yaml

from alertmanager_mcp_server.domain.routing import RouteTree
from tests.conftest import SAMPLE_COMPLEX_CONFIG_YAML


class TestRouteTreeEvaluation:
    def test_nested_parent_gating_prevents_false_child_match(self) -> None:
        """Regression test for P4: child route must NOT match if parent matcher fails."""
        raw_cfg = yaml.safe_load(SAMPLE_COMPLEX_CONFIG_YAML)
        tree = RouteTree.from_config(raw_cfg)

        # env="staging" does NOT match parent `{env="prod", service=~"checkout|payments"}`,
        # even though child has `severity: critical`. Must fall back to root `default-slack`!
        res = tree.evaluate(
            {"alertname": "HighLatency", "env": "staging", "service": "checkout", "severity": "critical"}
        )
        assert res.fell_back_to_default is True
        assert res.receivers == ["default-slack"]

    def test_continue_true_fans_out_to_subsequent_sibling(self) -> None:
        """Regression test for P4: child route with `continue: true` delivers to both siblings."""
        raw_cfg = yaml.safe_load(SAMPLE_COMPLEX_CONFIG_YAML)
        tree = RouteTree.from_config(raw_cfg)

        # Weekday 12:00 UTC (not muted by offhours-weekend)
        wed_noon = datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc)
        res = tree.evaluate(
            {"alertname": "HighLatency", "env": "prod", "service": "checkout", "severity": "critical"},
            at_time=wed_noon,
        )
        assert res.fell_back_to_default is False
        assert res.receivers == ["payments-pagerduty", "payments-audit-webhook"]
        assert res.active_receivers == ["payments-pagerduty", "payments-audit-webhook"]
        assert res.muted_receivers == []
        # Child routes inherit group_by from `payments-slack` parent
        assert res.matched_routes[0].group_by == ["alertname", "service", "instance"]
        # First child overrides repeat_interval to 30m; second child inherits 4h from root/parent
        assert res.matched_routes[0].repeat_interval == "30m"
        assert res.matched_routes[1].repeat_interval == "4h"

    def test_continue_false_stops_sibling_evaluation(self) -> None:
        raw_cfg = yaml.safe_load(SAMPLE_COMPLEX_CONFIG_YAML)
        tree = RouteTree.from_config(raw_cfg)

        # Watchdog matches first child (continue: false) -> stops immediately
        res = tree.evaluate(
            {"alertname": "Watchdog", "env": "prod", "service": "checkout", "severity": "critical"}
        )
        assert res.receivers == ["deadmanssnitch"]
        assert len(res.matched_routes) == 1
        assert res.matched_routes[0].path == "root/0"

    def test_falls_back_to_parent_route_when_no_grandchild_matches(self) -> None:
        raw_cfg = yaml.safe_load(SAMPLE_COMPLEX_CONFIG_YAML)
        tree = RouteTree.from_config(raw_cfg)

        # Matches parent `{env="prod", service=~"checkout|payments"}`, but severity="info"
        # matches neither child -> falls back to parent `payments-slack`
        res = tree.evaluate(
            {"alertname": "CheckoutDeploy", "env": "prod", "service": "checkout", "severity": "info"}
        )
        assert res.fell_back_to_default is False
        assert res.receivers == ["payments-slack"]
        assert res.matched_routes[0].path == "root/1"

    def test_mute_time_interval_mutes_only_targeted_route(self) -> None:
        raw_cfg = yaml.safe_load(SAMPLE_COMPLEX_CONFIG_YAML)
        tree = RouteTree.from_config(raw_cfg)

        # Saturday 12:00 UTC -> `offhours-weekend` is active, muting `payments-audit-webhook`
        sat_noon = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)
        res = tree.evaluate(
            {"alertname": "HighLatency", "env": "prod", "service": "checkout", "severity": "critical"},
            at_time=sat_noon,
        )
        assert res.receivers == ["payments-pagerduty", "payments-audit-webhook"]
        assert res.active_receivers == ["payments-pagerduty"]
        assert res.muted_receivers == ["payments-audit-webhook"]
