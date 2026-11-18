"""Contract tests for SKILL.md YAML frontmatter, gerund naming, pronoun bans, and line budgets."""

from __future__ import annotations

import re
from pathlib import Path

import yaml


def _split_frontmatter(text: str) -> tuple[dict, str]:
    assert text.startswith("---\n"), "SKILL.md must begin with YAML frontmatter '---'"
    parts = text.split("---\n", 2)
    assert len(parts) == 3, "SKILL.md must have closing '---' for YAML frontmatter"
    meta = yaml.safe_load(parts[1])
    assert isinstance(meta, dict)
    return meta, parts[2]


def test_all_skills_frontmatter_and_line_budgets(server_root: Path) -> None:
    skills_dir = server_root / "skills"
    skill_files = sorted(skills_dir.glob("*/SKILL.md"))
    assert len(skill_files) == 5

    for skill_file in skill_files:
        raw = skill_file.read_text(encoding="utf-8")
        meta, body = _split_frontmatter(raw)

        # Strict frontmatter keys
        assert set(meta.keys()) == {"name", "description"}, (
            f"{skill_file}: frontmatter must contain only 'name' and 'description'"
        )
        name = meta["name"]
        desc = meta["description"]

        assert name == skill_file.parent.name
        assert len(name) <= 64
        assert re.fullmatch(r"[a-z0-9-]+", name)
        first_word = name.split("-")[0]
        assert first_word.endswith("ing"), (
            f"{skill_file}: skill name '{name}' must start with a gerund (-ing)"
        )

        assert 20 <= len(desc) <= 1024
        assert "<" not in desc and ">" not in desc
        assert "Use when" in desc, f"{skill_file}: description must include 'Use when'"
        assert not re.search(r"\b(I|you|your|we)\b", desc, re.IGNORECASE), (
            f"{skill_file}: description must be third-person without I/you/your/we pronouns"
        )

        body_lines = body.strip().splitlines()
        assert len(body_lines) < 500, (
            f"{skill_file}: body has {len(body_lines)} lines, exceeding 500-line budget"
        )


def test_reference_files_over_100_lines_have_table_of_contents(
    server_root: Path,
) -> None:
    ref_files = sorted((server_root / "skills").glob("*/references/*.md"))
    assert len(ref_files) >= 6

    for ref_file in ref_files:
        text = ref_file.read_text(encoding="utf-8")
        lines = text.splitlines()
        if len(lines) > 100:
            assert "## Table of Contents" in text, (
                f"{ref_file.name} has {len(lines)} lines and must include '## Table of Contents'"
            )
