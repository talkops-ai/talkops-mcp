"""Tier-3 conformance tests for Agent Skills v1 YAML frontmatter across all 7 skills."""

from pathlib import Path
import re
import yaml


ROOT_DIR = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT_DIR / "skills"

EXPECTED_7_SKILLS = {
    "managing-traefik-traffic-routing",
    "configuring-traefik-middlewares",
    "securing-traefik-tls-and-certificates",
    "routing-traefik-tcp-and-udp",
    "troubleshooting-traefik-routing",
    "auditing-traefik-security-posture",
    "adopting-traefik-nginx-ingress-provider",
}

FORBIDDEN_PRONOUN_RE = re.compile(r"\b(i|you|your|yours|we|our|ours)\b", re.IGNORECASE)


def test_all_7_skills_present_with_valid_gerund_frontmatter():
    skill_dirs = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}
    assert skill_dirs == EXPECTED_7_SKILLS

    for s_name in sorted(EXPECTED_7_SKILLS):
        skill_md = SKILLS_DIR / s_name / "SKILL.md"
        assert skill_md.exists(), f"Missing SKILL.md in {s_name}"
        text = skill_md.read_text(encoding="utf-8")
        assert text.startswith("---\n"), f"{s_name}/SKILL.md must start with YAML frontmatter"
        parts = text.split("---", 2)
        fm = yaml.safe_load(parts[1])

        name = fm["name"]
        desc = fm["description"]

        assert name == s_name
        assert len(name) <= 64
        assert re.fullmatch(r"[a-z0-9-]+", name)
        first_token = name.split("-")[0]
        assert first_token.endswith("ing"), f"Skill name '{name}' must start with a gerund verb (*ing)"

        assert 20 <= len(desc) <= 1024
        assert "Use when" in desc, f"{s_name} description must contain 'Use when'"
        assert not FORBIDDEN_PRONOUN_RE.search(desc), f"{s_name} description must be strictly third-person"
