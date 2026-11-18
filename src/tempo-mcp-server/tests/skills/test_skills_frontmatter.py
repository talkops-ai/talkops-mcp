"""Conformance tests for YAML frontmatter across all SKILL.md files."""

from pathlib import Path
import re
from typing import Any, Dict, Tuple
import pytest
import yaml

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FIRST_OR_SECOND_PERSON_RE = re.compile(r"\b(I|you|your|we|our)\b", re.IGNORECASE)


def _parse_frontmatter(skill_md: Path) -> Tuple[Dict[str, Any], str]:
    text = skill_md.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{skill_md} must start with YAML frontmatter"
    _, fm_raw, body = text.split("---", 2)
    return yaml.safe_load(fm_raw), body


def test_expected_six_skills_present():
    skill_dirs = sorted(p.name for p in SKILLS_DIR.iterdir() if p.is_dir())
    assert skill_dirs == [
        "authoring-traceql-and-metrics-queries",
        "diagnosing-tempo-ingestion-and-health",
        "investigating-tempo-latency-regressions",
        "mapping-tempo-topology-and-alerts",
        "operating-tempo-deployments-and-tenants",
        "triaging-tempo-service-errors",
    ]


@pytest.mark.parametrize("skill_dir", sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()))
def test_skill_frontmatter(skill_dir: Path):
    skill_md = skill_dir / "SKILL.md"
    assert skill_md.is_file(), f"Missing SKILL.md in {skill_dir}"
    fm, _ = _parse_frontmatter(skill_md)

    name = fm.get("name", "")
    assert 1 <= len(name) <= 64
    assert NAME_RE.match(name), f"Invalid skill name: {name}"
    assert name == skill_dir.name, f"Frontmatter name {name} != dir {skill_dir.name}"
    assert name.split("-")[0].endswith("ing"), (
        f"Skill name {name} must start with a gerund (*ing)"
    )

    desc = fm.get("description", "")
    assert 20 <= len(desc) <= 1024
    assert "Use when" in desc, (
        f"{skill_md}: description must include 'Use when' trigger clause"
    )
    assert not FIRST_OR_SECOND_PERSON_RE.search(desc), (
        f"{skill_md}: description must be third-person"
    )
