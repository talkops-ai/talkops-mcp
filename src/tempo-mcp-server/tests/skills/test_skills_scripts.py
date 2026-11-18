"""Execution conformance tests for all offline helper scripts under skills/*/scripts/*.py."""

import json
from pathlib import Path
import subprocess
import sys
import pytest
import yaml

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
ALL_SCRIPTS = sorted(SKILLS_DIR.glob("*/scripts/*.py"))


def test_scripts_exist():
    assert len(ALL_SCRIPTS) == 8, f"Expected 8 skill scripts, found {len(ALL_SCRIPTS)}"


@pytest.mark.parametrize("script_path", ALL_SCRIPTS)
def test_skill_script_help_and_default_execution(script_path: Path):
    help_proc = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert help_proc.returncode == 0, f"{script_path} --help failed: {help_proc.stderr}"

    run_proc = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert run_proc.returncode == 0, f"{script_path} failed: {run_proc.stderr}"
    out = run_proc.stdout.strip()
    assert out, f"{script_path} produced empty stdout"
    parsed = yaml.safe_load(out)
    assert isinstance(parsed, (dict, list)) or json.loads(out)
