"""Agent Skills Open Spec (agentskills.io) compliance tests for all 4 ArgoCD skills."""

import re
from pathlib import Path
from typing import Any, Dict, List

import pytest

PLUGIN_DIR = Path(__file__).parent.parent.parent
SKILLS_DIR = PLUGIN_DIR / "skills"

EXPECTED_SKILLS = [
    "deploying-argocd-applications",
    "rolling-back-argocd-applications",
    "troubleshooting-argocd-applications",
    "onboarding-argocd-repositories-and-projects",
]


def _parse_frontmatter(skill_md_path: Path) -> Dict[str, Any]:
    text = skill_md_path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{skill_md_path} must start with YAML frontmatter '---'"
    end_idx = text.find("\n---\n", 4)
    assert end_idx != -1, f"{skill_md_path} is missing closing YAML frontmatter '---'"
    fm_block = text[4:end_idx]

    result: Dict[str, Any] = {}
    current_list_key: str | None = None
    for line in fm_block.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") or line.startswith("- "):
            assert current_list_key is not None
            result[current_list_key].append(line.split("- ", 1)[1].strip())
        elif ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            if val == "":
                result[key] = []
                current_list_key = key
            else:
                result[key] = val
                current_list_key = None
    return result


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_frontmatter_and_line_budget(skill_name: str) -> None:
    """Verify SKILL.md frontmatter name, 3rd-person description <= 1024 chars, and < 500 line budget."""
    skill_dir = SKILLS_DIR / skill_name
    skill_md = skill_dir / "SKILL.md"
    assert skill_md.exists(), f"Missing {skill_md}"

    lines = skill_md.read_text(encoding="utf-8").splitlines()
    assert len(lines) < 500, f"{skill_md} has {len(lines)} lines (must be < 500)"

    fm = _parse_frontmatter(skill_md)
    name = fm.get("name", "")
    description = fm.get("description", "")

    assert name == skill_name
    assert 1 <= len(name) <= 64
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name), f"Invalid skill name: {name}"

    assert 20 <= len(description) <= 1024
    assert "<" not in description and ">" not in description
    # Ensure third-person description (no first/second person pronouns)
    lower_words = set(re.findall(r"\b[a-z]+\b", description.lower()))
    assert not ({"i", "you", "your", "we", "our"} & lower_words), (
        f"Skill description for {skill_name} must be written in third person"
    )


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_relative_links_and_reference_toc(skill_name: str) -> None:
    """Verify all relative links in SKILL.md exist and are 1 level deep, and references > 100 lines have a TOC."""
    skill_dir = SKILLS_DIR / skill_name
    skill_md = skill_dir / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")

    # Match markdown links [label](target)
    links: List[str] = re.findall(r"\[[^\]]+\]\(([^)]+)\)", content)
    for target in links:
        if target.startswith(("http://", "https://", "argocd://", "#")):
            continue
        assert "\\" not in target, f"Backslash in link path: {target}"
        parts = Path(target).parts
        assert len(parts) == 2 and parts[0] in ("references", "scripts", "assets"), (
            f"Relative link '{target}' in {skill_name}/SKILL.md must be 1 level deep under references/, scripts/, or assets/"
        )
        resolved = skill_dir / target
        assert resolved.exists(), f"Broken link '{target}' in {skill_name}/SKILL.md"

    refs_dir = skill_dir / "references"
    if refs_dir.exists():
        for ref_file in refs_dir.glob("*.md"):
            ref_text = ref_file.read_text(encoding="utf-8")
            assert "## Table of Contents" in ref_text, (
                f"Reference file {ref_file.name} should include a Table of Contents"
            )
