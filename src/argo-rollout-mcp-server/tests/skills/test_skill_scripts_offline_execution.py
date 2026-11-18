"""Offline execution and zero-cluster-dependency tests for all 8 skill scripts (T-S4)."""

import ast
import json
import subprocess
import sys
from pathlib import Path
import yaml


def test_no_skill_script_imports_kubernetes(server_root: Path):
    scripts = list((server_root / "skills").glob("*/scripts/*.py"))
    assert len(scripts) == 8

    for script in scripts:
        tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("kubernetes"), (
                        f"Offline script {script.name} must not import kubernetes"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("kubernetes"), (
                    f"Offline script {script.name} must not import from kubernetes"
                )


def test_all_skill_scripts_support_help_flag(server_root: Path):
    scripts = list((server_root / "skills").glob("*/scripts/*.py"))
    for script in scripts:
        proc = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"{script.name} --help failed: {proc.stderr}"
        assert "usage:" in proc.stdout.lower()


def test_onboarding_skill_scripts_offline_execution(server_root: Path, fixtures_dir: Path):
    scripts_dir = server_root / "skills" / "onboarding-and-migrating-to-argo-rollouts" / "scripts"
    dep_basic = fixtures_dir / "deployment-basic.yaml"
    rollout_canary = fixtures_dir / "rollout-canary.yaml"

    # 1. lint_deployment_manifest.py
    lint_proc = subprocess.run(
        [sys.executable, str(scripts_dir / "lint_deployment_manifest.py"), "--input", str(dep_basic)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert lint_proc.returncode == 0
    lint_data = json.loads(lint_proc.stdout)
    assert lint_data["ready"] is True
    assert lint_data["detected_container_port"] == 8080

    # Invalid kind -> exit code 1
    bad_lint = subprocess.run(
        [sys.executable, str(scripts_dir / "lint_deployment_manifest.py"), "--input", str(rollout_canary)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad_lint.returncode != 0

    # 2. convert_deployment_to_rollout.py
    conv_proc = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "convert_deployment_to_rollout.py"),
            "--input",
            str(dep_basic),
            "--strategy",
            "canary",
            "--migration-mode",
            "workload_ref",
            "--include-services",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert conv_proc.returncode == 0
    docs = list(yaml.safe_load_all(conv_proc.stdout))
    assert len(docs) == 3
    assert docs[0]["kind"] == "Rollout"
    assert docs[0]["spec"]["workloadRef"]["name"] == "api-service"
    assert docs[1]["spec"]["ports"][0]["targetPort"] == 8080

    # 3. convert_rollout_to_deployment.py
    rev_proc = subprocess.run(
        [sys.executable, str(scripts_dir / "convert_rollout_to_deployment.py"), "--input", str(rollout_canary)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rev_proc.returncode == 0
    rev_doc = yaml.safe_load(rev_proc.stdout)
    assert rev_doc["kind"] == "Deployment"
    assert rev_doc["metadata"]["name"] == "api-service"

    # 4. generate_scale_down_manifest.py
    scale_proc = subprocess.run(
        [sys.executable, str(scripts_dir / "generate_scale_down_manifest.py"), "--input", str(dep_basic)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert scale_proc.returncode == 0
    scale_doc = yaml.safe_load(scale_proc.stdout)
    assert scale_doc["spec"]["replicas"] == 0

    # 5. generate_argocd_ignore_differences.py
    ignore_proc = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "generate_argocd_ignore_differences.py"),
            "--include-rollout-traffic-routing",
            "--include-deployment-replicas",
            "--deployment-name",
            "payments-api",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ignore_proc.returncode == 0
    ignore_doc = yaml.safe_load(ignore_proc.stdout)
    assert ignore_doc["kind"] == "Application"
    assert len(ignore_doc["spec"]["ignoreDifferences"]) >= 3


def test_progressing_and_analysis_skill_scripts(server_root: Path, fixtures_dir: Path):
    # 6. render_canary_steps.py
    render_script = (
        server_root / "skills" / "progressing-argo-rollouts" / "scripts" / "render_canary_steps.py"
    )
    steps_proc = subprocess.run(
        [
            sys.executable,
            str(render_script),
            "--profile",
            "cost-optimized",
            "--analysis-template",
            "payments-api-analysis",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert steps_proc.returncode == 0
    steps = json.loads(steps_proc.stdout)
    assert any("setCanaryScale" in s for s in steps)
    assert any("analysis" in s for s in steps)

    # 7. generate_analysis_template.py
    gen_at_script = (
        server_root
        / "skills"
        / "gating-rollouts-with-analysis-and-experiments"
        / "scripts"
        / "generate_analysis_template.py"
    )
    gen_proc = subprocess.run(
        [
            sys.executable,
            str(gen_at_script),
            "--service-name",
            "payments-api",
            "--scope",
            "cluster",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert gen_proc.returncode == 0
    at_doc = yaml.safe_load(gen_proc.stdout)
    assert at_doc["kind"] == "ClusterAnalysisTemplate"

    # 8. validate_analysis_template.py
    val_at_script = (
        server_root
        / "skills"
        / "gating-rollouts-with-analysis-and-experiments"
        / "scripts"
        / "validate_analysis_template.py"
    )
    val_proc = subprocess.run(
        [
            sys.executable,
            str(val_at_script),
            "--input",
            str(fixtures_dir / "analysis-template.yaml"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert val_proc.returncode == 0
    val_data = json.loads(val_proc.stdout)
    assert val_data["valid"] is True
