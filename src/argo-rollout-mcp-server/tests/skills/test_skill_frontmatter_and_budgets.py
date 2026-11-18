"""Skill frontmatter, gerund naming, description rules, line count, and reference TOC checks (T-S2)."""

import re
from pathlib import Path
import yaml

EXPECTED_SKILLS = {
    "onboarding-and-migrating-to-argo-rollouts",
    "progressing-argo-rollouts",
    "gating-rollouts-with-analysis-and-experiments",
    "troubleshooting-argo-rollouts",
}


def _parse_frontmatter(md_text: str) -> tuple[dict, str]:
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", md_text, re.DOTALL)
    assert match, "SKILL.md must begin with YAML frontmatter delimited by ---"
    return yaml.safe_load(match.group(1)), match.group(2)


def test_all_four_skills_frontmatter_and_line_budgets(server_root: Path):
    skills_dir = server_root / "skills"
    assert skills_dir.is_dir()

    found_skills = {p.name for p in skills_dir.iterdir() if p.is_dir()}
    assert found_skills == EXPECTED_SKILLS

    for skill_name in EXPECTED_SKILLS:
        skill_md = skills_dir / skill_name / "SKILL.md"
        assert skill_md.is_file(), f"Missing SKILL.md in {skill_name}"

        raw = skill_md.read_text(encoding="utf-8")
        lines = raw.splitlines()
        assert len(lines) < 500, f"{skill_name}/SKILL.md has {len(lines)} lines (must be < 500)"

        fm, body = _parse_frontmatter(raw)
        assert fm.get("name") == skill_name
        assert len(skill_name) <= 64
        assert re.match(r"^[a-z0-9-]+$", skill_name)
        assert "--" not in skill_name

        # Gerund check: first word ends with 'ing'
        first_word = skill_name.split("-")[0]
        assert first_word.endswith("ing"), f"Skill name '{skill_name}' must use gerund form"

        desc = fm.get("description", "")
        assert 20 <= len(desc) <= 1024
        assert "<" not in desc and ">" not in desc
        assert "Use when" in desc, f"{skill_name} description must include 'Use when' trigger clause"
        assert not re.search(r"\b(I|you|your|we)\b", desc, re.IGNORECASE), (
            f"{skill_name} description must be written in 3rd-person"
        )

        # Check reference files > 100 lines have a Table of Contents
        refs_dir = skills_dir / skill_name / "references"
        if refs_dir.is_dir():
            for ref_file in refs_dir.glob("*.md"):
                ref_lines = ref_file.read_text(encoding="utf-8").splitlines()
                if len(ref_lines) > 100:
                    assert "## Table of Contents" in ref_file.read_text(encoding="utf-8"), (
                        f"Reference file {ref_file.name} (>100 lines) must include '## Table of Contents'"
                    )
