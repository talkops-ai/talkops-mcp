"""Contract tests for offline execution and stdlib/yaml isolation of skills/*/scripts/*.py."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

FORBIDDEN_IMPORTS = {"httpx", "kubernetes", "kargo_mcp_server", "requests", "urllib3"}


def test_all_skill_scripts_have_shebang_docstring_help_and_no_network_imports(
    server_root: Path,
) -> None:
    scripts = sorted((server_root / "skills").glob("*/scripts/*.py"))
    assert len(scripts) == 3

    for script in scripts:
        source = script.read_text(encoding="utf-8")
        assert source.startswith("#!/usr/bin/env python3\n"), (
            f"{script.name} must start with '#!/usr/bin/env python3'"
        )
        tree = ast.parse(source)
        assert ast.get_docstring(tree), f"{script.name} must have a module docstring"

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    assert root_mod not in FORBIDDEN_IMPORTS, (
                        f"{script.name} imports forbidden module '{root_mod}'"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                root_mod = node.module.split(".")[0]
                assert root_mod not in FORBIDDEN_IMPORTS, (
                    f"{script.name} imports from forbidden module '{root_mod}'"
                )

        proc = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"{script.name} --help failed: {proc.stderr}"
        assert "usage:" in proc.stdout.lower()


def test_render_promotion_steps_script_generates_valid_steps(
    server_root: Path,
) -> None:
    script = (
        server_root
        / "skills"
        / "onboarding-kargo-pipelines"
        / "scripts"
        / "render_promotion_steps.py"
    )
    for pattern in (
        "gitops-image-update",
        "gitops-kustomize",
        "gitops-helm-template",
        "gitops-pull-request",
    ):
        proc = subprocess.run(
            [sys.executable, str(script), "--pattern", pattern],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(proc.stdout)
        assert data["pattern"] == pattern
        assert isinstance(data["steps"], list) and len(data["steps"]) >= 4


def test_validate_pipeline_manifests_script_accepts_valid_and_flags_invalid(
    server_root: Path,
    fixtures_dir: Path,
) -> None:
    script = (
        server_root
        / "skills"
        / "onboarding-kargo-pipelines"
        / "scripts"
        / "validate_pipeline_manifests.py"
    )

    valid_proc = subprocess.run(
        [sys.executable, str(script), "--file", str(fixtures_dir / "pipeline-valid.yaml")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert valid_proc.returncode == 0
    valid_report = json.loads(valid_proc.stdout)
    assert valid_report["valid"] is True
    assert valid_report["errors"] == []

    invalid_proc = subprocess.run(
        [sys.executable, str(script), "--file", str(fixtures_dir / "pipeline-invalid.yaml")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert invalid_proc.returncode == 1
    invalid_report = json.loads(invalid_proc.stdout)
    assert invalid_report["valid"] is False
    errors_joined = " ".join(invalid_report["errors"])
    assert "Project 'legacy-project' defines 'spec'" in errors_joined
    assert "allowTags" in errors_joined
    assert "helm-update-image" in errors_joined
    assert "fromOrigin" in errors_joined
    assert "cycle" in errors_joined.lower()


def test_summarize_promotion_failure_script_parses_promotion_and_analysis_run(
    server_root: Path,
    fixtures_dir: Path,
) -> None:
    script = (
        server_root
        / "skills"
        / "troubleshooting-kargo-pipelines"
        / "scripts"
        / "summarize_promotion_failure.py"
    )

    promo_proc = subprocess.run(
        [sys.executable, str(script), "--input", str(fixtures_dir / "promotion-failed.json")],
        capture_output=True,
        text=True,
        check=True,
    )
    promo_summary = json.loads(promo_proc.stdout)
    assert promo_summary["diagnosis_code"] == "ARGOCD_SYNC_OR_AUTH_FAILED"
    assert len(promo_summary["failed_items"]) == 1

    ar_proc = subprocess.run(
        [sys.executable, str(script), "--input", str(fixtures_dir / "analysis-run-failed.json")],
        capture_output=True,
        text=True,
        check=True,
    )
    ar_summary = json.loads(ar_proc.stdout)
    assert ar_summary["diagnosis_code"] == "VERIFICATION_FAILED"
    assert len(ar_summary["failed_items"]) == 1
