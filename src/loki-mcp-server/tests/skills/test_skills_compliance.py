"""Tests for Agent Skills v1.0.0 structural and progressive-disclosure compliance."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT_DIR / "skills"

EXPECTED_SKILLS = {
    "authoring-logql-and-analyzing-logs",
    "triaging-loki-incidents-and-errors",
    "discovering-loki-schema-and-log-structure",
    "optimizing-loki-cardinality-and-finops",
    "authoring-loki-alerting-and-recording-rules",
    "operating-loki-deployments-and-ingestion",
}

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _parse_frontmatter(text: str) -> dict:
    assert text.startswith("---\n"), "SKILL.md must begin with YAML frontmatter delimiter '---'"
    end_idx = text.find("\n---\n", 4)
    assert end_idx != -1, "SKILL.md must close YAML frontmatter with '---'"
    return yaml.safe_load(text[4:end_idx])


class TestSkillsCompliance:
    """Enforces Agent Skills v1.0.0 standards across all 6 Loki skills."""

    def test_expected_six_skills_exist(self):
        assert SKILLS_DIR.exists()
        actual = {
            p.name
            for p in SKILLS_DIR.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        }
        assert actual == EXPECTED_SKILLS

    @pytest.mark.parametrize("skill_name", sorted(EXPECTED_SKILLS))
    def test_skill_md_frontmatter_and_line_budget(self, skill_name: str):
        skill_dir = SKILLS_DIR / skill_name
        skill_md = skill_dir / "SKILL.md"
        assert skill_md.exists(), f"{skill_name}/SKILL.md is missing"

        text = skill_md.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 250, f"{skill_name}/SKILL.md exceeds 250-line budget ({len(lines)} lines)"

        fm = _parse_frontmatter(text)
        assert fm["name"] == skill_name
        assert 3 <= len(fm["name"]) <= 64
        assert NAME_RE.match(fm["name"])

        desc = fm.get("description", "")
        assert isinstance(desc, str)
        assert 20 <= len(desc) <= 1024
        assert "<" not in desc and ">" not in desc
        assert "Use when" in desc, f"{skill_name} description must include 'Use when'"
        assert "Do not use" in desc, f"{skill_name} description must include 'Do not use'"

        assert fm.get("license") == "Apache-2.0"
        meta = fm.get("metadata", {})
        assert meta.get("author") == "TalkOps"
        assert meta.get("service") == "grafana-loki"

    @pytest.mark.parametrize("skill_name", sorted(EXPECTED_SKILLS))
    def test_skill_links_resolve_one_hop_deep(self, skill_name: str):
        skill_dir = SKILLS_DIR / skill_name
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")

        links = [
            target
            for target in MD_LINK_RE.findall(text)
            if not target.startswith(("http://", "https://", "#"))
        ]
        assert len(links) >= 2, f"{skill_name}/SKILL.md must link to at least 2 references/scripts"

        for rel_path in links:
            parts = Path(rel_path).parts
            assert len(parts) == 2 and parts[0] in ("references", "scripts"), (
                f"Link '{rel_path}' in {skill_name}/SKILL.md must be 1 hop deep under references/ or scripts/"
            )
            resolved = skill_dir / rel_path
            assert resolved.exists(), f"Broken link '{rel_path}' in {skill_name}/SKILL.md"

    @pytest.mark.parametrize("skill_name", sorted(EXPECTED_SKILLS))
    def test_reference_files_have_table_of_contents(self, skill_name: str):
        ref_dir = SKILLS_DIR / skill_name / "references"
        assert ref_dir.exists()
        ref_files = list(ref_dir.glob("*.md"))
        assert len(ref_files) >= 2
        for ref_file in ref_files:
            content = ref_file.read_text(encoding="utf-8")
            assert "## Table of Contents" in content, (
                f"{ref_file.relative_to(ROOT_DIR)} must include '## Table of Contents'"
            )
