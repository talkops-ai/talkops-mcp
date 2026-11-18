"""T-S4: Validate Preconditions, checklists, and [GATE] markers across all SKILL.md files."""

from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT_DIR / "skills"


def test_every_skill_has_preconditions_checklists_and_gates():
    skill_files = sorted(SKILLS_DIR.glob("*/SKILL.md"))
    assert len(skill_files) == 7

    for skill_md in skill_files:
        content = skill_md.read_text(encoding="utf-8")
        assert "## Preconditions" in content, f"{skill_md} must contain '## Preconditions' section"
        assert "otel://server/capabilities" in content, (
            f"{skill_md} Preconditions must reference 'otel://server/capabilities'"
        )
        assert "- [ ]" in content, f"{skill_md} must contain '- [ ]' workflow checklist items"
        assert "[GATE]" in content, (
            f"{skill_md} must contain '[GATE]' user confirmation markers before mutations"
        )
