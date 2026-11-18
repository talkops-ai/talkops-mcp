"""Functional tests for all 6 deterministic Python CLI helper scripts in skills/*/scripts/."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT_DIR / "skills"


def _run_script(rel_path: str, args: list[str]) -> tuple[int, dict]:
    script_path = SKILLS_DIR / rel_path
    assert script_path.exists(), f"Missing skill script: {script_path}"
    proc = subprocess.run(
        [sys.executable, str(script_path), *args, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    data = json.loads(proc.stdout)
    return proc.returncode, data


class TestSkillScripts:
    """Verify deterministic behavior of all 6 skill helper scripts."""

    def test_lint_logql_valid_and_warnings(self):
        # Good query
        code, good = _run_script(
            "authoring-logql-and-analyzing-logs/scripts/lint_logql.py",
            ["--query", '{service_name="checkout", namespace="prod"} |= "error" | json status="status" | status >= 500'],
        )
        assert code == 0
        assert good["valid"] is True
        assert good["errors"] == []

        # Anti-pattern: parser before line filter + high-cardinality label in selector
        code_warn, warn = _run_script(
            "authoring-logql-and-analyzing-logs/scripts/lint_logql.py",
            ["--query", '{service_name="checkout", trace_id="abc"} | json |= "error"'],
        )
        assert code_warn == 0
        assert len(warn["warnings"]) >= 2

        # Invalid syntax: empty selector
        code_err, err = _run_script(
            "authoring-logql-and-analyzing-logs/scripts/lint_logql.py",
            ["--query", '{} |= "error"'],
        )
        assert code_err == 1
        assert err["valid"] is False

    def test_extract_error_signatures(self):
        code, data = _run_script(
            "triaging-loki-incidents-and-errors/scripts/extract_error_signatures.py",
            [
                "--line",
                '2025-05-10T14:22:01Z ERROR db timeout host=10.0.1.5:5432 trace_id="4bf92f3577b34da6a3ce929d0e0e4736"',
                "--line",
                '2025-05-10T14:22:05Z ERROR db timeout host=10.0.1.9:5432 trace_id="99a12f3577b34da6a3ce929d0e0e1111"',
            ],
        )
        assert code == 0
        assert data["total_lines"] == 2
        assert data["unique_signatures"] == 1
        assert data["clusters"][0]["count"] == 2
        assert "4bf92f3577b34da6a3ce929d0e0e4736" in data["trace_ids"]

    def test_infer_log_parser(self):
        # JSON
        code, json_res = _run_script(
            "discovering-loki-schema-and-log-structure/scripts/infer_log_parser.py",
            ["--sample", '{"level":"error","msg":"failed","duration_ms":42}'],
        )
        assert code == 0
        assert json_res["format"] == "json"
        assert "| json" in json_res["recommended_parser"]

        # Nginx access log
        code, nginx_res = _run_script(
            "discovering-loki-schema-and-log-structure/scripts/infer_log_parser.py",
            ["--sample", '10.0.1.4 - - [10/May/2025:14:22:01 +0000] "POST /v1/orders HTTP/1.1" 503 142 "-" "curl/8.0"'],
        )
        assert code == 0
        assert nginx_res["format"] == "nginx_access"
        assert "| pattern" in nginx_res["recommended_parser"]

    def test_audit_label_cardinality(self):
        code, res = _run_script(
            "optimizing-loki-cardinality-and-finops/scripts/audit_label_cardinality.py",
            [
                "--cardinality-json",
                '{"service_name": 25, "namespace": 6, "pod": 2400, "trace_id": 90000}',
                "--threshold",
                "500",
            ],
        )
        assert code == 0
        assert res["high_cardinality_count"] == 2
        assert "pod" in res["move_to_structured_metadata"]
        assert "trace_id" in res["move_to_structured_metadata"]
        assert "stage.structured_metadata" in res["alloy_remediation_snippet"]

    def test_validate_loki_rules(self):
        valid_yaml = (
            "name: checkout-slo\n"
            "interval: 1m\n"
            "rules:\n"
            "  - alert: HighCheckoutErrors\n"
            "    expr: rate({service_name=\"checkout\"} |= \"error\" [5m]) > 1\n"
            "    for: 5m\n"
            "    annotations:\n"
            "      summary: High error rate\n"
        )
        code, res = _run_script(
            "authoring-loki-alerting-and-recording-rules/scripts/validate_loki_rules.py",
            ["--yaml", valid_yaml],
        )
        assert code == 0
        assert res["valid"] is True
        assert res["total_rules"] == 1

    def test_render_loki_architecture_config(self):
        code, res = _run_script(
            "operating-loki-deployments-and-ingestion/scripts/render_loki_architecture_config.py",
            ["--mode", "lokistack", "--size", "1x.small", "--storage", "s3", "--retention-days", "30"],
        )
        assert code == 0
        assert res["mode"] == "lokistack"
        assert res["manifest"]["kind"] == "LokiStack"
        assert res["manifest"]["spec"]["size"] == "1x.small"
