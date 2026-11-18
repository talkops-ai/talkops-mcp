"""Skill workflow checklist, Preconditions, and [GATE] marker contract tests (T-S5)."""

from pathlib import Path


def test_every_skill_has_preconditions_checklists_and_gate_markers(server_root: Path):
    skills_dir = server_root / "skills"
    skill_files = list(skills_dir.glob("*/SKILL.md"))
    assert len(skill_files) == 4

    for skill_md in skill_files:
        text = skill_md.read_text(encoding="utf-8")
        assert "## Preconditions" in text, f"{skill_md} must contain a '## Preconditions' section"
        assert "argorollout://server/capabilities" in text, (
            f"{skill_md} Preconditions must check argorollout://server/capabilities"
        )
        assert "- [ ]" in text, f"{skill_md} must contain trackable '- [ ]' workflow checklist items"
        assert "[GATE]" in text, f"{skill_md} must contain explicit '[GATE]' confirmation markers"
