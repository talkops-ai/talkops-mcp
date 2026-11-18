"""Execution tests for all 6 zero-network deterministic CLI scripts under `skills/*/scripts/`."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"


def _run_script(rel_path: str, *args: str) -> subprocess.CompletedProcess[str]:
    script_path = SKILLS_DIR / rel_path
    assert script_path.exists(), f"Missing script {script_path}"
    return subprocess.run(
        [sys.executable, str(script_path), *args],
        capture_output=True,
        text=True,
        timeout=15,
    )


class TestSkillScripts:
    def test_generate_slo_rules_script(self) -> None:
        res = _run_script(
            "triaging-prometheus-incidents-and-slos/scripts/generate_slo_rules.py",
            "--service",
            "checkout",
            "--slo-target",
            "0.999",
            "--error-metric",
            'http_requests_total{job="checkout",status=~"5.."}',
            "--total-metric",
            'http_requests_total{job="checkout"}',
            "--format",
            "json",
        )
        assert res.returncode == 0, res.stderr
        data = json.loads(res.stdout)
        group = data["group"]
        assert group["name"] == "checkout-slo-multiwindow-rules"
        assert len(group["rules"]) == 11  # 7 recording windows + 4 multi-window alerts

        # Invalid SLO target fails cleanly
        bad = _run_script(
            "triaging-prometheus-incidents-and-slos/scripts/generate_slo_rules.py",
            "--service",
            "checkout",
            "--slo-target",
            "1.5",
            "--error-metric",
            "err_total",
            "--total-metric",
            "req_total",
        )
        assert bad.returncode != 0

    def test_lint_promql_script(self) -> None:
        ok = _run_script(
            "authoring-promql-and-analyzing-metrics/scripts/lint_promql.py",
            "--query",
            'histogram_quantile(0.95, sum by (le, job) (rate(http_request_duration_seconds_bucket{job="api"}[5m])))',
        )
        assert ok.returncode == 0
        assert json.loads(ok.stdout)["valid"] is True

        # Missing 'le' in classic histogram fails
        bad = _run_script(
            "authoring-promql-and-analyzing-metrics/scripts/lint_promql.py",
            "--query",
            'histogram_quantile(0.95, sum by (job) (rate(http_request_duration_seconds_bucket{job="api"}[5m])))',
        )
        assert bad.returncode != 0
        assert json.loads(bad.stdout)["valid"] is False

    def test_build_promtool_test_suite_script(self) -> None:
        res = _run_script(
            "authoring-and-testing-prometheus-rules/scripts/build_promtool_test_suite.py",
            "--alert",
            "HighErrorRate",
            "--expr",
            'job:http_errors:ratio5m{job="api"} > 0.05',
            "--for-duration",
            "5m",
            "--series",
            'job:http_errors:ratio5m{job="api"}',
            "--values",
            "0.08+0x10",
            "--eval-time",
            "10m",
            "--exp-labels",
            "alertname=HighErrorRate,job=api,severity=critical",
        )
        assert res.returncode == 0, res.stderr
        payload = json.loads(res.stdout)
        assert payload["rule_group"]["rules"][0]["alert"] == "HighErrorRate"
        assert len(payload["unit_tests"]) == 1

    def test_generate_finops_config_script(self) -> None:
        relabel_res = _run_script(
            "optimizing-tsdb-cardinality-and-finops/scripts/generate_finops_config.py",
            "--mode",
            "relabel",
            "--action",
            "labeldrop",
            "--regex",
            "user_id|session_id",
            "--format",
            "json",
        )
        assert relabel_res.returncode == 0
        data = json.loads(relabel_res.stdout)
        assert data["operator_crd_spec"]["metricRelabelings"][0]["action"] == "labeldrop"

        rw_res = _run_script(
            "optimizing-tsdb-cardinality-and-finops/scripts/generate_finops_config.py",
            "--mode",
            "remote_write",
            "--remote-url",
            "https://mimir.example.com/api/v1/push",
            "--keep-regex",
            "job:.*|up",
        )
        assert rw_res.returncode == 0
        parsed_yaml = yaml.safe_load(rw_res.stdout)
        assert parsed_yaml["remote_write"][0]["url"] == "https://mimir.example.com/api/v1/push"

    def test_validate_scrape_manifest_script(self) -> None:
        ok = _run_script(
            "configuring-prometheus-scraping-and-discovery/scripts/validate_scrape_manifest.py",
            "--kind",
            "ServiceMonitor",
            "--name",
            "checkout-sm",
            "--spec-json",
            '{"selector":{"matchLabels":{"app":"checkout"}},"endpoints":[{"port":"metrics","path":"/metrics"}]}',
        )
        assert ok.returncode == 0
        assert json.loads(ok.stdout)["valid"] is True

        bad = _run_script(
            "configuring-prometheus-scraping-and-discovery/scripts/validate_scrape_manifest.py",
            "--kind",
            "ServiceMonitor",
            "--name",
            "invalid_underscore",
            "--spec-json",
            "{}",
        )
        assert bad.returncode != 0

    def test_render_exporter_bundle_script(self) -> None:
        res = _run_script(
            "onboarding-exporters-and-instrumentation/scripts/render_exporter_bundle.py",
            "--exporter-type",
            "redis_exporter",
            "--namespace",
            "monitoring",
            "--env",
            "REDIS_ADDR=redis://redis:6379",
            "--env",
            "REDIS_PASSWORD=supersecret",
        )
        assert res.returncode == 0, res.stderr
        data = json.loads(res.stdout)
        assert data["exporter_type"] == "redis_exporter"
        assert len(data["security_warnings"]) >= 1
        # Verify REDIS_PASSWORD was redacted in rendered manifests
        serialized = json.dumps(data["manifests"])
        assert "supersecret" not in serialized
        assert "***REDACTED***" in serialized
