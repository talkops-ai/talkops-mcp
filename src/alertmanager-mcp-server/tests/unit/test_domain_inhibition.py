"""Unit tests for `alertmanager_mcp_server.domain.inhibition`."""

from __future__ import annotations

import yaml

from alertmanager_mcp_server.domain.inhibition import (
    evaluate_inhibition,
    parse_inhibit_rules,
)
from tests.conftest import SAMPLE_COMPLEX_CONFIG_YAML


class TestInhibitionEvaluation:
    def test_not_inhibited_when_no_source_alert_is_firing(self) -> None:
        """Regression test for P6: target_matchers match alone must NOT report inhibited."""
        raw_cfg = yaml.safe_load(SAMPLE_COMPLEX_CONFIG_YAML)
        rules = parse_inhibit_rules(raw_cfg)

        target = {
            "alertname": "HighCPU",
            "severity": "warning",
            "env": "prod",
            "cluster": "us-east-1",
            "service": "checkout",
        }
        res = evaluate_inhibition(target, rules, active_alerts=[])
        assert res.is_inhibited is False
        assert res.inhibited_by_fingerprints == []
        # Potential rule match is recorded separately for dry-run inspection
        assert len(res.potential_target_rule_Matches) == 1
        assert res.potential_target_rule_Matches[0].active_source_found is False

    def test_inhibited_when_matching_source_alert_is_firing_with_equal_labels(self) -> None:
        raw_cfg = yaml.safe_load(SAMPLE_COMPLEX_CONFIG_YAML)
        rules = parse_inhibit_rules(raw_cfg)

        target = {
            "alertname": "HighCPU",
            "severity": "warning",
            "env": "prod",
            "cluster": "us-east-1",
            "service": "checkout",
        }
        active_source = {
            "fingerprint": "fp-nodedown-1",
            "labels": {
                "alertname": "NodeDown",
                "severity": "critical",
                "env": "prod",
                "cluster": "us-east-1",
                "service": "checkout",
            },
        }
        res = evaluate_inhibition(target, rules, active_alerts=[active_source])
        assert res.is_inhibited is True
        assert res.inhibited_by_fingerprints == ["fp-nodedown-1"]

    def test_not_inhibited_when_equal_labels_differ(self) -> None:
        raw_cfg = yaml.safe_load(SAMPLE_COMPLEX_CONFIG_YAML)
        rules = parse_inhibit_rules(raw_cfg)

        target = {
            "alertname": "HighCPU",
            "severity": "warning",
            "env": "prod",
            "cluster": "us-east-1",
            "service": "checkout",
        }
        different_service_source = {
            "fingerprint": "fp-nodedown-auth",
            "labels": {
                "alertname": "NodeDown",
                "severity": "critical",
                "env": "prod",
                "cluster": "us-east-1",
                "service": "auth",
            },
        }
        res = evaluate_inhibition(target, rules, active_alerts=[different_service_source])
        assert res.is_inhibited is False

    def test_never_inhibits_self_or_alert_matching_both_source_and_target(self) -> None:
        cfg = {
            "inhibit_rules": [
                {
                    "source_matchers": ['severity="critical"'],
                    "target_matchers": ['severity=~"warning|critical"'],
                    "equal": ["service"],
                }
            ]
        }
        rules = parse_inhibit_rules(cfg)
        crit_alert = {
            "fingerprint": "fp-crit-1",
            "labels": {"alertname": "DBDown", "severity": "critical", "service": "db"},
        }
        other_crit_alert = {
            "fingerprint": "fp-crit-2",
            "labels": {"alertname": "NodeDown", "severity": "critical", "service": "db"},
        }
        res = evaluate_inhibition(
            crit_alert["labels"],
            rules,
            active_alerts=[crit_alert, other_crit_alert],
            target_fingerprint="fp-crit-1",
        )
        assert res.is_inhibited is False
