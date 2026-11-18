"""T-S8: Verify every script in skills/*/scripts/*.py is 100% offline and executes cleanly."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT_DIR / "skills"

FORBIDDEN_IMPORTS = {
    "kubernetes",
    "urllib",
    "requests",
    "httpx",
    "aiohttp",
    "socket",
    "opentelemetry_mcp_server",
}


def test_no_forbidden_network_or_cluster_imports_in_skill_scripts():
    scripts = sorted(SKILLS_DIR.glob("*/scripts/*.py"))
    assert len(scripts) == 12, f"Expected 12 skill scripts across 7 skills, found {len(scripts)}"

    for script in scripts:
        tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    assert root_mod not in FORBIDDEN_IMPORTS, (
                        f"Forbidden import '{alias.name}' in offline script {script}"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                root_mod = node.module.split(".")[0]
                assert root_mod not in FORBIDDEN_IMPORTS, (
                    f"Forbidden from-import '{node.module}' in offline script {script}"
                )


def test_all_scripts_support_help_flag():
    for script in sorted(SKILLS_DIR.glob("*/scripts/*.py")):
        proc = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert proc.returncode == 0, f"{script} --help failed: {proc.stderr}"
        assert "usage:" in proc.stdout.lower()


def test_offline_execution_positive_and_negative_inputs(tmp_path: Path):
    # 1. plan_collector_topology.py
    s1 = SKILLS_DIR / "provisioning-opentelemetry-collectors/scripts/plan_collector_topology.py"
    res = subprocess.run(
        [sys.executable, str(s1), "--nodes", "10", "--workloads", "50", "--tail-sampling"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert json.loads(res.stdout)["recommended_pattern"] == "three-tier-tail-sampling"

    bad = subprocess.run(
        [sys.executable, str(s1), "--nodes", "0", "--workloads", "10"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode == 1

    # 2. render_collector_cr.py & 3. lint_collector_config.py
    s2 = SKILLS_DIR / "provisioning-opentelemetry-collectors/scripts/render_collector_cr.py"
    res2 = subprocess.run(
        [
            sys.executable,
            str(s2),
            "--name",
            "otel-agent",
            "--namespace",
            "opentelemetry-system",
            "--role",
            "agent",
            "--traces-endpoint",
            "tempo.observability.svc:4317",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res2.returncode == 0
    docs = list(yaml.safe_load_all(res2.stdout))
    assert len(docs) == 3
    cr_file = tmp_path / "collector.yaml"
    cr_file.write_text(yaml.safe_dump(docs[0], sort_keys=False), encoding="utf-8")

    s3 = SKILLS_DIR / "provisioning-opentelemetry-collectors/scripts/lint_collector_config.py"
    res3 = subprocess.run(
        [sys.executable, str(s3), "--config", str(cr_file), "--mode", "daemonset"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res3.returncode == 0
    assert json.loads(res3.stdout)["valid"] is True

    # 4. lint_workload_manifest.py
    s4 = SKILLS_DIR / "instrumenting-kubernetes-workloads/scripts/lint_workload_manifest.py"
    bad_go_workload = tmp_path / "go-deploy.yaml"
    bad_go_workload.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "payment-go"},
                "spec": {
                    "template": {
                        "metadata": {"annotations": {}},
                        "spec": {"containers": [{"name": "app", "image": "golang:1.23"}]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    res4_bad = subprocess.run(
        [sys.executable, str(s4), "--file", str(bad_go_workload), "--language", "go"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res4_bad.returncode == 1

    # 5. render_instrumentation_cr.py
    s5 = SKILLS_DIR / "instrumenting-kubernetes-workloads/scripts/render_instrumentation_cr.py"
    res5 = subprocess.run(
        [
            sys.executable,
            str(s5),
            "--name",
            "default-inst",
            "--namespace",
            "default",
            "--collector-service",
            "otel-agent.opentelemetry-system.svc.cluster.local",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res5.returncode == 0
    inst_doc = yaml.safe_load(res5.stdout)
    assert inst_doc["spec"]["python"]["env"][0]["value"].endswith(":4318")
    assert inst_doc["spec"]["java"]["env"][0]["value"].endswith(":4317")

    # 6. render_obi_manifest.py
    s6 = SKILLS_DIR / "instrumenting-kubernetes-workloads/scripts/render_obi_manifest.py"
    res6 = subprocess.run(
        [
            sys.executable,
            str(s6),
            "--namespace",
            "opentelemetry-system",
            "--otlp-endpoint",
            "http://otel-agent:4317",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res6.returncode == 0
    obi_docs = list(yaml.safe_load_all(res6.stdout))
    assert len(obi_docs) == 4

    # 7. analyze_internal_metrics.py
    s7 = SKILLS_DIR / "troubleshooting-telemetry-pipelines/scripts/analyze_internal_metrics.py"
    metrics_file = tmp_path / "metrics.txt"
    metrics_file.write_text(
        "otelcol_receiver_accepted_spans 1200\n"
        "otelcol_exporter_sent_spans 1190\n"
        "otelcol_exporter_send_failed_spans 10\n"
        "otelcol_exporter_queue_size 90\n"
        "otelcol_exporter_queue_capacity 100\n",
        encoding="utf-8",
    )
    res7 = subprocess.run(
        [sys.executable, str(s7), "--file", str(metrics_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res7.returncode == 0
    codes = {f["code"] for f in json.loads(res7.stdout)["findings"]}
    assert "RT_EXPORTER_DROPPING_DATA" in codes
    assert "RT_QUEUE_SATURATED" in codes

    # 8. estimate_tail_sampling_capacity.py & 9. render_tail_sampling_policies.py
    s8 = (
        SKILLS_DIR
        / "tuning-sampling-and-trace-derived-metrics/scripts/estimate_tail_sampling_capacity.py"
    )
    res8 = subprocess.run(
        [sys.executable, str(s8), "--spans-per-sec", "20000"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res8.returncode == 0
    assert json.loads(res8.stdout)["per_pod_recommendations"]["mode"] == "statefulset"

    s9 = (
        SKILLS_DIR
        / "tuning-sampling-and-trace-derived-metrics/scripts/render_tail_sampling_policies.py"
    )
    res9 = subprocess.run(
        [sys.executable, str(s9), "--sampling-percentage", "5.0"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res9.returncode == 0

    # 10. render_ottl_statements.py
    s10 = SKILLS_DIR / "controlling-telemetry-cardinality-and-noise/scripts/render_ottl_statements.py"
    res10 = subprocess.run(
        [sys.executable, str(s10), "--parse-json-logs", "--redact-pii"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res10.returncode == 0

    # 11. render_audit_report.py
    s11 = SKILLS_DIR / "auditing-observability-security-posture/scripts/render_audit_report.py"
    audit_json = tmp_path / "audit.json"
    audit_json.write_text(
        json.dumps(
            {
                "compliant": False,
                "namespace": "default",
                "collectors_audited": 1,
                "findings": [
                    {
                        "code": "SEC_INSECURE_TLS",
                        "severity": "WARNING",
                        "component": "exporters.otlp",
                        "message": "Insecure TLS enabled",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    res11 = subprocess.run(
        [sys.executable, str(s11), "--input", str(audit_json)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res11.returncode == 0
    assert "SEC_INSECURE_TLS" in res11.stdout

    # 12. check_config_deprecations.py
    s12 = SKILLS_DIR / "upgrading-opentelemetry-components/scripts/check_config_deprecations.py"
    dep_cfg = tmp_path / "deprecated.yaml"
    dep_cfg.write_text(
        yaml.safe_dump(
            {
                "exporters": {"logging": {"loglevel": "info"}},
                "service": {"telemetry": {"metrics": {"address": "0.0.0.0:8888"}}},
            }
        ),
        encoding="utf-8",
    )
    res12 = subprocess.run(
        [sys.executable, str(s12), "--file", str(dep_cfg)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res12.returncode == 1
    assert json.loads(res12.stdout)["compatible"] is False
