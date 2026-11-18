"""Conformance tests for SKILL.md structure, line budgets, checklists, gates, and reference links."""

from pathlib import Path
import re
import pytest

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
MD_LINK_RE = re.compile(r"\[[^\]]+\]\((references/[^)]+\.md)\)")


@pytest.mark.parametrize("skill_dir", sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()))
def test_skill_line_budget_and_links(skill_dir: Path):
    skill_md = skill_dir / "SKILL.md"
    lines = skill_md.read_text(encoding="utf-8").splitlines()
    assert len(lines) < 500, f"{skill_md} exceeds 500 lines ({len(lines)})"

    text = "\n".join(lines)
    assert "## Preconditions" in text
    assert "tempo://server/capabilities" in text
    assert "- [ ]" in text, f"{skill_md} must contain a workflow checklist"
    assert "[GATE]" in text, f"{skill_md} must contain explicit [GATE] confirmation points"

    for rel_target in MD_LINK_RE.findall(text):
        assert rel_target.count("/") == 1, f"Reference link too deep: {rel_target}"
        target_path = skill_dir / rel_target
        assert target_path.is_file(), f"Broken reference link in {skill_md}: {rel_target}"

    refs_dir = skill_dir / "references"
    if refs_dir.is_dir():
        for ref_file in refs_dir.glob("*.md"):
            ref_lines = ref_file.read_text(encoding="utf-8").splitlines()
            if len(ref_lines) > 100:
                assert "## Table of Contents" in "\n".join(ref_lines[:35]), (
                    f"{ref_file} (>100 lines) must include a '## Table of Contents' section"
                )
