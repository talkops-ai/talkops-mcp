"""Tier-3 cross-check of all tool names, resource URIs, diagnosis codes, and audit check IDs referenced across skills."""

from pathlib import Path
import re
import pytest
from fastmcp.client import Client
from traefik_mcp_server.models.schemas import ALL_DIAGNOSIS_CODES
from traefik_mcp_server.services.audit_checks import ALL_AUDIT_CHECK_IDS


ROOT_DIR = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT_DIR / "skills"

TOOL_RE = re.compile(r"\b(traefik_[a-z0-9_]+)\b")
URI_RE = re.compile(r"(traefik://[a-zA-Z0-9_/{}-]+)")


def _uri_matches_registered(uri: str, static_uris: set[str], template_regexes: list[re.Pattern]) -> bool:
    if uri in static_uris:
        return True
    return any(rx.fullmatch(uri) for rx in template_regexes)


@pytest.mark.asyncio
async def test_no_hallucinated_tools_or_resources_in_skills(mcp_rw):
    async with Client(mcp_rw) as client:
        registered_tools = {t.name for t in await client.list_tools()}
        # Also allow resource names or script argument names that are not MCP tools
        ignored_identifiers = {"traefik_service"}
        static_uris = {str(r.uri) for r in await client.list_resources()}
        templates = [r.uriTemplate for r in await client.list_resource_templates()]

    template_regexes = []
    for tpl in templates:
        pattern = re.sub(r"\{[^}]+\}", r"[^/\\s`'\")]+", tpl)
        template_regexes.append(re.compile(f"^{pattern}$"))

    for md_file in SKILLS_DIR.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        for tool_match in TOOL_RE.findall(content):
            if tool_match in ignored_identifiers:
                continue
            assert tool_match in registered_tools, (
                f"Unregistered tool '{tool_match}' referenced in {md_file.relative_to(ROOT_DIR)}"
            )
        for uri_match in URI_RE.findall(content):
            cleaned_uri = uri_match.rstrip(".,;:)")
            assert _uri_matches_registered(cleaned_uri, static_uris, template_regexes), (
                f"Unregistered resource URI '{cleaned_uri}' referenced in {md_file.relative_to(ROOT_DIR)}"
            )


def test_all_41_diagnosis_codes_and_20_audit_check_ids_documented_in_skill_references():
    error_catalog = (
        SKILLS_DIR / "troubleshooting-traefik-routing" / "references" / "traefik-error-catalog.md"
    ).read_text(encoding="utf-8")
    for code in ALL_DIAGNOSIS_CODES:
        assert f"`{code}`" in error_catalog, f"Diagnosis code '{code}' missing from traefik-error-catalog.md"

    hardening_checklist = (
        SKILLS_DIR / "auditing-traefik-security-posture" / "references" / "hardening-checklist.md"
    ).read_text(encoding="utf-8")
    for check_id in ALL_AUDIT_CHECK_IDS:
        assert f"`{check_id}`" in hardening_checklist, f"Audit check ID '{check_id}' missing from hardening-checklist.md"
