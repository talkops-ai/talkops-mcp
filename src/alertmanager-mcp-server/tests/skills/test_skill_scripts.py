"""Tests for bundled skill scripts and 100% parity with `alertmanager_mcp_server.domain`."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import pytest
import yaml

from alertmanager_mcp_server.domain.inhibition import (
    evaluate_inhibition,
    parse_inhibit_rules,
)
from alertmanager_mcp_server.domain.routing import RouteTree
from alertmanager_mcp_server.domain.silence_policy import SilencePolicy
from tests.conftest import SAMPLE_COMPLEX_CONFIG_YAML

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
PLAN_WINDOW_SCRIPT = (
    SKILLS_DIR
    / "managing-alert-silences"
    / "scripts"
    / "plan_maintenance_window.py"
)
VALIDATE_SILENCE_SCRIPT = (
    SKILLS_DIR
    / "managing-alert-silences"
    / "scripts"
    / "validate_silence_request.py"
)
LINT_CONFIG_SCRIPT = (
    SKILLS_DIR
    / "validating-alertmanager-routing"
    / "scripts"
    / "lint_alertmanager_config.py"
)
TEST_ROUTES_SCRIPT = (
    SKILLS_DIR
    / "validating-alertmanager-routing"
    / "scripts"
    / "test_routes.py"
)


def _load_script_module(path: Path, mod_name: str):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSkillScriptsExecutionAndParity:
    @pytest.mark.parametrize(
        "script_path",
        [
            PLAN_WINDOW_SCRIPT,
            VALIDATE_SILENCE_SCRIPT,
            LINT_CONFIG_SCRIPT,
            TEST_ROUTES_SCRIPT,
        ],
    )
    def test_all_scripts_support_help_flag(self, script_path: Path) -> None:
        proc = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0
        assert "usage:" in proc.stdout.lower()

    def test_plan_maintenance_window_cli(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(PLAN_WINDOW_SCRIPT),
                "--start",
                "2026-03-29T15:30:00+05:30",
                "--duration-minutes",
                "60",
                "--buffer-before-minutes",
                "5",
                "--buffer-after-minutes",
                "10",
                "--matchers",
                'service="checkout",env="prod"',
                "--created-by",
                "sre@example.com",
                "--comment",
                "CHG-1042: upgrade",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert data["valid"] is True
        assert data["core_starts_at"] == "2026-03-29T10:00:00Z"
        assert data["starts_at"] == "2026-03-29T09:55:00Z"
        assert data["ends_at"] == "2026-03-29T11:10:00Z"
        assert data["duration_minutes"] == 75

    def test_parity_between_validate_silence_script_and_domain_silence_policy(
        self,
    ) -> None:
        """Verify 100% agreement between `validate_silence_request.py` and `SilencePolicy`."""
        script_mod = _load_script_module(
            VALIDATE_SILENCE_SCRIPT, "validate_silence_request"
        )
        policy = SilencePolicy(max_duration_minutes=1440)
        ref_now = datetime(2026, 3, 29, 10, 0, 0, tzinfo=timezone.utc)

        test_cases = [
            # Valid scoped silence
            {
                "matchers": [{"name": "service", "value": "checkout", "isRegex": False, "isEqual": True}],
                "duration_minutes": 120,
                "created_by": "sre@example.com",
                "comment": "CHG-101: valid maintenance",
            },
            # SP001: Empty matchers
            {
                "matchers": [],
                "duration_minutes": 60,
                "created_by": "sre@example.com",
                "comment": "CHG-101: empty",
            },
            # SP002 & SP003: Wildcard regex
            {
                "matchers": [{"name": "alertname", "value": ".*", "isRegex": True, "isEqual": True}],
                "duration_minutes": 60,
                "created_by": "sre@example.com",
                "comment": "CHG-101: wildcard",
            },
            # SP004: Sole broad label
            {
                "matchers": [{"name": "env", "value": "prod", "isRegex": False, "isEqual": True}],
                "duration_minutes": 60,
                "created_by": "sre@example.com",
                "comment": "CHG-101: broad",
            },
            # SP005: Watchdog
            {
                "matchers": [{"name": "alertname", "value": "Watchdog", "isRegex": False, "isEqual": True}],
                "duration_minutes": 60,
                "created_by": "sre@example.com",
                "comment": "CHG-101: watchdog",
            },
            # SP006: Naive timestamp
            {
                "matchers": [{"name": "service", "value": "checkout", "isRegex": False, "isEqual": True}],
                "starts_at": "2026-03-29T10:00:00",
                "ends_at": "2026-03-29T12:00:00",
                "created_by": "sre@example.com",
                "comment": "CHG-101: naive",
            },
            # SP007: Exceeds max duration
            {
                "matchers": [{"name": "service", "value": "checkout", "isRegex": False, "isEqual": True}],
                "duration_minutes": 2880,
                "created_by": "sre@example.com",
                "comment": "CHG-101: too long",
            },
            # SP008 & SP009: Placeholder author + short comment
            {
                "matchers": [{"name": "service", "value": "checkout", "isRegex": False, "isEqual": True}],
                "duration_minutes": 60,
                "created_by": "mcp",
                "comment": "no",
            },
        ]

        for case in test_cases:
            domain_res = policy.evaluate(
                matchers=case["matchers"],
                starts_at=case.get("starts_at"),
                ends_at=case.get("ends_at"),
                duration_minutes=case.get("duration_minutes"),
                created_by=case["created_by"],
                comment=case["comment"],
                now=ref_now,
            )
            script_res = script_mod.validate_silence_payload(
                matchers_raw=case["matchers"],
                starts_at=case.get("starts_at"),
                ends_at=case.get("ends_at"),
                duration_minutes=case.get("duration_minutes"),
                created_by=case["created_by"],
                comment=case["comment"],
                now=ref_now,
            )
            assert script_res["valid"] == domain_res.valid
            domain_rules = {v.rule_id for v in domain_res.violations}
            script_rules = {v["rule_id"] for v in script_res["violations"]}
            assert script_rules == domain_rules

    def test_parity_between_test_routes_script_and_domain_routing_engine(
        self, tmp_path: Path
    ) -> None:
        """Verify 100% agreement between `test_routes.py` and `RouteTree.evaluate` + `evaluate_inhibition`."""
        script_mod = _load_script_module(TEST_ROUTES_SCRIPT, "test_routes")
        raw_cfg = yaml.safe_load(SAMPLE_COMPLEX_CONFIG_YAML)
        tree = RouteTree.from_config(raw_cfg)
        inh_rules = parse_inhibit_rules(raw_cfg)

        sat_noon = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)
        active_alerts = [
            {
                "fingerprint": "fp-node",
                "labels": {
                    "alertname": "NodeDown",
                    "severity": "critical",
                    "env": "prod",
                    "cluster": "us-east-1",
                    "service": "checkout",
                },
            }
        ]

        label_sets = [
            {"alertname": "Watchdog", "severity": "none"},
            {"alertname": "HighLatency", "env": "prod", "service": "checkout", "severity": "critical"},
            {"alertname": "HighLatency", "env": "staging", "service": "checkout", "severity": "critical"},
            {
                "alertname": "HighCPU",
                "env": "prod",
                "cluster": "us-east-1",
                "service": "checkout",
                "severity": "warning",
            },
        ]

        for lset in label_sets:
            dom_route = tree.evaluate(lset, at_time=sat_noon)
            dom_inh = evaluate_inhibition(lset, inh_rules, active_alerts)
            scr_res = script_mod.simulate_config_routing(
                raw_cfg, lset, at_time=sat_noon, active_alerts=active_alerts
            )
            assert scr_res["receivers"] == dom_route.receivers
            assert scr_res["active_receivers"] == dom_route.active_receivers
            assert scr_res["muted_receivers"] == dom_route.muted_receivers
            assert scr_res["fell_back_to_default"] == dom_route.fell_back_to_default
            assert scr_res["is_inhibited"] == dom_inh.is_inhibited

    def test_lint_alertmanager_config_detects_shadowed_and_undefined_receivers(
        self, tmp_path: Path
    ) -> None:
        bad_cfg = {
            "route": {
                "receiver": "missing-root-rcv",
                "routes": [
                    {"receiver": "used-rcv", "continue": False},
                    {"match": {"env": "prod"}, "receiver": "used-rcv"},
                ],
            },
            "receivers": [
                {"name": "used-rcv"},
                {"name": "unused-rcv"},
            ],
        }
        cfg_file = tmp_path / "bad_am.json"
        cfg_file.write_text(json.dumps(bad_cfg), encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, str(LINT_CONFIG_SCRIPT), "--config", str(cfg_file)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 1
        report = json.loads(proc.stdout)
        assert report["valid"] is False
        rule_ids = {f["rule_id"] for f in report["findings"]}
        assert "LINT002" in rule_ids  # undefined receiver
        assert "LINT003" in rule_ids  # unused receiver
        assert "LINT005" in rule_ids  # deprecated match
        assert "LINT006" in rule_ids  # shadowed sibling route
