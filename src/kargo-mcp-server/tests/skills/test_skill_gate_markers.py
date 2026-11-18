"""Contract tests verifying every SKILL.md enforces Preconditions, capabilities check, checklists, and [GATE] markers."""

from __future__ import annotations

from pathlib import Path


def test_every_skill_has_preconditions_checklist_and_gate_markers(
    server_root: Path,
) -> None:
    skill_files = sorted((server_root / "skills").glob("*/SKILL.md"))
    assert len(skill_files) == 5

    for skill_file in skill_files:
        text = skill_file.read_text(encoding="utf-8")
        assert "## Preconditions" in text, f"{skill_file} must include '## Preconditions'"
        assert "kargo://server/capabilities" in text, (
            f"{skill_file} must instruct reading 'kargo://server/capabilities'"
        )
        assert "- [ ]" in text, f"{skill_file} must include a markdown task checklist ('- [ ]')"
        assert "[GATE]" in text, f"{skill_file} must include at least one '[GATE]' marker"
