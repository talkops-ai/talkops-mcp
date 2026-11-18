"""Unit tests for Agent Plugin v1.0.0 manifests (plugin.json, mcp.json), SKILL.md compliance, and local scripts."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = PROJECT_ROOT / "skills"

EXPECTED_SKILLS = [
    "deploying-helm-charts",
    "upgrading-and-rolling-back-helm-releases",
    "troubleshooting-helm-releases",
    "reviewing-helm-release-security",
]

ALLOWED_PLUGIN_FIELDS = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "extensions",
}


def test_plugin_json_conforms_to_closed_v1_schema() -> None:
    """plugin.json must use only allowed Agent Plugins v1.0.0 fields and relative ./ paths."""
    plugin_path = PROJECT_ROOT / "plugin.json"
    assert plugin_path.exists(), "plugin.json must exist at package root"

    data = json.loads(plugin_path.read_text(encoding="utf-8"))
    unknown_keys = set(data.keys()) - ALLOWED_PLUGIN_FIELDS
    assert not unknown_keys, f"Forbidden fields in plugin.json: {unknown_keys}"

    assert data["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert re.match(r"^[a-z0-9-]+$", data["name"])
    assert re.match(r"^\d+\.\d+\.\d+$", data["version"])

    ext = data["extensions"]["com.talkops"]
    assert ext["mcpServers"] == "./mcp.json"

    for skill_rel in ext["skills"]:
        assert skill_rel.startswith("./skills/")
        assert ".." not in skill_rel
        skill_dir = PROJECT_ROOT / skill_rel.lstrip("./")
        assert (skill_dir / "SKILL.md").exists(), f"Missing SKILL.md in {skill_dir}"


def test_mcp_json_is_valid() -> None:
    """mcp.json must define mcpServers.helm-mcp-server with stdio transport and read-only default env."""
    mcp_path = PROJECT_ROOT / "mcp.json"
    assert mcp_path.exists()

    data = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert "mcpServers" in data
    helm_srv = data["mcpServers"]["helm-mcp-server"]
    assert helm_srv["command"] == "helm-mcp-server"
    assert any("--transport" in a for a in helm_srv["args"])
    assert helm_srv["env"]["MCP_ALLOW_WRITE"] == "false"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_frontmatter_line_budget_and_links(skill_name: str) -> None:
    """Every SKILL.md must satisfy Agent Skills spec frontmatter, <500 line body, and 1-level relative links."""
    skill_dir = SKILLS_DIR / skill_name
    skill_md = skill_dir / "SKILL.md"
    assert skill_md.exists()

    raw = skill_md.read_text(encoding="utf-8")
    assert raw.startswith("---\n"), f"{skill_name}/SKILL.md must start with YAML frontmatter"

    parts = raw.split("---\n", 2)
    assert len(parts) == 3, f"{skill_name}/SKILL.md must have closing --- frontmatter delimiter"

    frontmatter = yaml.safe_load(parts[1])
    body = parts[2]

    # Frontmatter checks
    assert frontmatter["name"] == skill_name
    assert len(frontmatter["name"]) <= 64
    assert re.match(r"^[a-z0-9-]+$", frontmatter["name"])

    desc = frontmatter["description"]
    assert isinstance(desc, str) and 20 <= len(desc) <= 1024
    assert "<" not in desc and ">" not in desc

    # Body line count check (< 500 lines)
    body_lines = body.strip().splitlines()
    assert len(body_lines) < 500, f"{skill_name}/SKILL.md body has {len(body_lines)} lines (>= 500)"

    # Verify all relative markdown links exist and are 1 level deep
    link_targets = re.findall(r"\]\((?:\./)?((?:references|scripts)/[^)]+)\)", body)
    assert link_targets, f"{skill_name}/SKILL.md should reference its bundled files"
    for target in link_targets:
        assert target.count("/") == 1, f"Relative link '{target}' must be exactly one level deep"
        target_path = skill_dir / target
        assert target_path.exists(), f"Broken link '{target}' in {skill_name}/SKILL.md"


def test_long_reference_files_contain_table_of_contents() -> None:
    """Any reference markdown file over 100 lines must include a Table of Contents."""
    for ref_file in SKILLS_DIR.glob("*/references/*.md"):
        lines = ref_file.read_text(encoding="utf-8").splitlines()
        if len(lines) > 100:
            content = "\n".join(lines)
            assert "Table of Contents" in content, (
                f"{ref_file} has {len(lines)} lines (>100) and must include a Table of Contents"
            )


def test_validate_values_script_execution() -> None:
    """skills/deploying-helm-charts/scripts/validate_values.py should validate values and exit 0 or 1."""
    script = SKILLS_DIR / "deploying-helm-charts" / "scripts" / "validate_values.py"
    assert script.exists()

    # Valid values
    ok_proc = subprocess.run(
        [sys.executable, str(script), "-"],
        input=json.dumps({"replicaCount": 2, "resources": {"requests": {"cpu": "250m", "memory": "512Mi"}}}),
        text=True,
        capture_output=True,
        check=False,
    )
    assert ok_proc.returncode == 0
    ok_report = json.loads(ok_proc.stdout)
    assert ok_report["valid"] is True

    # Invalid values (negative replicaCount and invalid CPU quantity)
    bad_proc = subprocess.run(
        [sys.executable, str(script), "-"],
        input=json.dumps({"replicaCount": -1, "resources": {"requests": {"cpu": "invalid-cpu"}}}),
        text=True,
        capture_output=True,
        check=False,
    )
    assert bad_proc.returncode == 1
    bad_report = json.loads(bad_proc.stdout)
    assert bad_report["valid"] is False
    assert bad_report["error_count"] >= 2


def test_validate_manifests_script_execution() -> None:
    """skills/deploying-helm-charts/scripts/validate_manifests.py should validate multi-doc YAML manifests."""
    script = SKILLS_DIR / "deploying-helm-charts" / "scripts" / "validate_manifests.py"
    assert script.exists()

    valid_yaml = """---
apiVersion: v1
kind: Service
metadata:
  name: my-svc
spec:
  ports:
    - port: 80
"""
    ok_proc = subprocess.run(
        [sys.executable, str(script), "-"],
        input=valid_yaml,
        text=True,
        capture_output=True,
        check=False,
    )
    assert ok_proc.returncode == 0
    assert json.loads(ok_proc.stdout)["valid"] is True

    invalid_yaml = """---
apiVersion: apps/v1
kind: Deployment
metadata: {}
"""
    bad_proc = subprocess.run(
        [sys.executable, str(script), "-"],
        input=invalid_yaml,
        text=True,
        capture_output=True,
        check=False,
    )
    assert bad_proc.returncode == 1
    assert json.loads(bad_proc.stdout)["valid"] is False


def test_scan_manifest_security_script_execution() -> None:
    """skills/reviewing-helm-release-security/scripts/scan_manifest_security.py should detect security risks."""
    script = SKILLS_DIR / "reviewing-helm-release-security" / "scripts" / "scan_manifest_security.py"
    assert script.exists()

    insecure_manifest = """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: insecure-app
  namespace: prod
spec:
  template:
    spec:
      hostNetwork: true
      containers:
        - name: app
          image: nginx:latest
          securityContext:
            privileged: true
"""
    proc = subprocess.run(
        [sys.executable, str(script), "-"],
        input=insecure_manifest,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert report["passed"] is False
    rules = {f["rule"] for f in report["findings"]}
    assert "no-privileged-container" in rules
    assert "no-hostnetwork" in rules
    assert "pin-image-tag" in rules
