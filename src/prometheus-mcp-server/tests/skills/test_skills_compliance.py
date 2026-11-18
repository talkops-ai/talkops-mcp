"""Agent Skills specification compliance tests for all 6 skills under `skills/`."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"

EXPECTED_SKILLS = {
    "triaging-prometheus-incidents-and-slos",
    "authoring-promql-and-analyzing-metrics",
    "authoring-and-testing-prometheus-rules",
    "optimizing-tsdb-cardinality-and-finops",
    "configuring-prometheus-scraping-and-discovery",
    "onboarding-exporters-and-instrumentation",
}

ALLOWED_FRONTMATTER_KEYS = frozenset(
    {
        "name",
        "description",
        "license",
        "compatibility",
        "metadata",
        "allowed-tools",
    }
)

MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    assert text.startswith("---\n"), "SKILL.md must start with YAML frontmatter '---'"
    parts = text.split("---\n", 2)
    assert len(parts) == 3, "SKILL.md must have closing '---' for YAML frontmatter"
    fm = yaml.safe_load(parts[1])
    assert isinstance(fm, dict)
    return fm, parts[2]


class TestSkillsCompliance:
    def test_all_6_expected_skills_exist(self) -> None:
        assert SKILLS_DIR.exists()
        actual = {
            p.name
            for p in SKILLS_DIR.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        }
        assert actual == EXPECTED_SKILLS

    @pytest.mark.parametrize("skill_name", sorted(EXPECTED_SKILLS))
    def test_skill_frontmatter_and_line_budget(self, skill_name: str) -> None:
        skill_dir = SKILLS_DIR / skill_name
        skill_md = skill_dir / "SKILL.md"
        assert skill_md.exists()

        text = skill_md.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 100, (
            f"{skill_name}/SKILL.md has {len(lines)} lines (exceeds 100-line progressive disclosure budget)"
        )

        fm, _ = _parse_frontmatter(text)
        assert set(fm.keys()).issubset(ALLOWED_FRONTMATTER_KEYS)
        assert fm.get("name") == skill_name
        assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", fm["name"])

        desc = fm.get("description", "")
        assert isinstance(desc, str) and 20 <= len(desc) <= 1024
        assert "Use when" in desc, (
            f"{skill_name} description must include 'Use when' trigger guidance"
        )
        assert "Do not use" in desc, (
            f"{skill_name} description must include 'Do not use' negative boundary"
        )
        assert "<" not in desc and ">" not in desc

    @pytest.mark.parametrize("skill_name", sorted(EXPECTED_SKILLS))
    def test_skill_relative_links_resolve_and_are_one_hop_deep(
        self, skill_name: str
    ) -> None:
        skill_dir = SKILLS_DIR / skill_name
        skill_md = skill_dir / "SKILL.md"
        _, body = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))

        links = MD_LINK_RE.findall(body)
        assert len(links) >= 2, (
            f"{skill_name}/SKILL.md should link to its bundled references and scripts"
        )

        for target in links:
            if target.startswith(("http://", "https://", "#")):
                continue
            resolved = (skill_dir / target).resolve()
            assert resolved.exists(), (
                f"Broken relative link '{target}' in {skill_name}/SKILL.md"
            )
            rel_parts = resolved.relative_to(skill_dir).parts
            assert len(rel_parts) == 2 and rel_parts[0] in ("references", "scripts")

    def test_reference_files_over_100_lines_have_table_of_contents(self) -> None:
        for ref_md in SKILLS_DIR.glob("*/references/*.md"):
            text = ref_md.read_text(encoding="utf-8")
            lines = text.splitlines()
            if len(lines) > 100:
                assert "Table of Contents" in text, (
                    f"{ref_md.relative_to(SKILLS_DIR)} has {len(lines)} lines (>100) "
                    "and must include a 'Table of Contents' section at the top."
                )
