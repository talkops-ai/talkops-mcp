"""Tier-3 conformance tests for SKILL.md line budget (<500 lines), preconditions, checklists, gates, and reference links."""

from pathlib import Path
import re


ROOT_DIR = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT_DIR / "skills"
MD_LINK_RE = re.compile(r"\[[^\]]+\]\((references/[^)]+\.md)\)")


def test_skill_md_structure_line_budget_checklists_and_links():
    for skill_dir in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8")
        lines = text.splitlines()

        assert len(lines) < 500, f"{skill_dir.name}/SKILL.md exceeds 500 lines ({len(lines)})"
        assert "## Preconditions" in text, f"{skill_dir.name}/SKILL.md missing '## Preconditions'"
        assert "traefik://server/capabilities" in text
        assert "- [ ]" in text, f"{skill_dir.name}/SKILL.md missing '- [ ]' checklist"
        assert "[GATE]" in text, f"{skill_dir.name}/SKILL.md missing '[GATE]' confirmation gate"

        # Verify all linked reference files exist and are one level deep
        for rel_link in MD_LINK_RE.findall(text):
            assert rel_link.count("/") == 1, f"Reference link '{rel_link}' must be one level deep"
            target = skill_dir / rel_link
            assert target.exists(), f"Broken reference link '{rel_link}' in {skill_dir.name}/SKILL.md"

        # Any reference file > 100 lines must include ## Table of Contents
        refs_dir = skill_dir / "references"
        if refs_dir.is_dir():
            for ref_file in refs_dir.glob("*.md"):
                ref_text = ref_file.read_text(encoding="utf-8")
                if len(ref_text.splitlines()) > 100:
                    assert "## Table of Contents" in ref_text, (
                        f"{ref_file} exceeds 100 lines and must include '## Table of Contents'"
                    )
