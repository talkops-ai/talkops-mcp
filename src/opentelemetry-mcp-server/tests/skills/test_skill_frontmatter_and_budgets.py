"""T-S3 & T-S6: Validate SKILL.md YAML frontmatter, gerund naming, line budgets, and reference TOCs."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT_DIR / "skills"

EXPECTED_SKILLS = {
    "provisioning-opentelemetry-collectors",
    "instrumenting-kubernetes-workloads",
    "troubleshooting-telemetry-pipelines",
    "tuning-sampling-and-trace-derived-metrics",
    "controlling-telemetry-cardinality-and-noise",
    "auditing-observability-security-posture",
    "upgrading-opentelemetry-components",
}

FIRST_OR_SECOND_PERSON_RE = re.compile(r"\b(I|you|your|we)\b", re.IGNORECASE)


def _parse_frontmatter(md_text: str) -> tuple[dict, str]:
    assert md_text.startswith("---\n"), "SKILL.md must begin with YAML frontmatter delimiter '---'"
    parts = md_text.split("---\n", 2)
    assert len(parts) == 3, "SKILL.md must have opening and closing '---' frontmatter delimiters"
    frontmatter = yaml.safe_load(parts[1])
    return frontmatter, parts[2]


def test_all_seven_skills_exist():
    actual = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")}
    assert actual == EXPECTED_SKILLS


def test_skill_frontmatter_and_line_budgets():
    for skill_name in sorted(EXPECTED_SKILLS):
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        assert skill_md.exists(), f"Missing SKILL.md for {skill_name}"

        text = skill_md.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) < 500, f"{skill_name}/SKILL.md exceeds 500-line budget ({len(lines)} lines)"

        fm, _ = _parse_frontmatter(text)
        assert set(fm.keys()) == {"name", "description"}, (
            f"{skill_name}/SKILL.md frontmatter must have only 'name' and 'description'"
        )
        assert fm["name"] == skill_name

        # Gerund name check (first hyphenated word ends with 'ing')
        first_word = skill_name.split("-")[0]
        assert first_word.endswith("ing"), (
            f"Skill name '{skill_name}' must start with a gerund verb ending in 'ing'"
        )
        assert re.fullmatch(r"[a-z0-9-]+", skill_name) and len(skill_name) <= 64

        desc = fm["description"]
        assert 20 <= len(desc) <= 1024, f"{skill_name} description length out of bounds"
        assert "<" not in desc and ">" not in desc, (
            f"{skill_name} description must not contain '<' or '>'"
        )
        assert "Use when" in desc, f"{skill_name} description must include 'Use when' trigger clause"
        assert not FIRST_OR_SECOND_PERSON_RE.search(desc), (
            f"{skill_name} description must be 3rd-person (found I/you/your/we)"
        )


def test_reference_files_one_level_deep_and_have_toc():
    for skill_name in sorted(EXPECTED_SKILLS):
        ref_dir = SKILLS_DIR / skill_name / "references"
        assert ref_dir.exists() and ref_dir.is_dir(), f"Missing references/ dir in {skill_name}"
        ref_files = list(ref_dir.iterdir())
        assert ref_files, f"No reference files in {skill_name}/references/"

        for item in ref_files:
            assert item.is_file() and item.suffix == ".md", (
                f"References in {skill_name} must be 1-level-deep .md files, found: {item}"
            )
            content = item.read_text(encoding="utf-8")
            assert "## Table of Contents" in content, (
                f"Reference file {item} must include '## Table of Contents'"
            )
