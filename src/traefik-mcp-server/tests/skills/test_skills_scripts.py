"""Tier-3 execution tests for all offline Python scripts in skills/*/scripts/*.py."""

import ast
from pathlib import Path
import subprocess
import sys
import yaml


ROOT_DIR = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT_DIR / "skills"


def test_all_skill_scripts_have_no_kubernetes_imports_and_run_offline():
    scripts = sorted(SKILLS_DIR.glob("*/scripts/*.py"))
    assert len(scripts) == 10

    for script_path in scripts:
        source = script_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("kubernetes"), (
                        f"{script_path.name} must not import kubernetes client"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("kubernetes"), (
                    f"{script_path.name} must not import from kubernetes client"
                )

        # Verify --help exits 0
        help_proc = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert help_proc.returncode == 0, f"{script_path.name} --help failed: {help_proc.stderr}"

        # Verify default invocation exits 0 and produces valid YAML/JSON/Markdown output
        run_proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert run_proc.returncode == 0, f"{script_path.name} default run failed: {run_proc.stderr}"
        assert run_proc.stdout.strip(), f"{script_path.name} produced empty output"

        if script_path.name != "render_audit_report.py":
            docs = list(yaml.safe_load_all(run_proc.stdout))
            assert len(docs) >= 1 and docs[0] is not None
