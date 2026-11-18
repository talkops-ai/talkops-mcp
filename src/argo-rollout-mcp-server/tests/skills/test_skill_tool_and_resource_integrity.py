"""Skill tool and resource cross-reference integrity tests against live FastMCP server (T-S3)."""

import re
from pathlib import Path
import pytest
from fastmcp import Client
from tests.conftest import make_test_server

FORBIDDEN_LEGACY_NAMES = {
    "argo_update_rollout",
    "validate_deployment_ready",
    "create_stable_canary_services",
    "generate_argocd_ignore_differences",
    "argorollout://health/summary",
    "argorollout://history/all",
}


@pytest.mark.asyncio
async def test_skills_reference_only_registered_tools_and_resources(
    server_root: Path, fake_argo_service, fake_generator_service
):
    mcp = make_test_server(
        allow_write=True,
        toolsets=["all"],
        argo_service=fake_argo_service,
        generator_service=fake_generator_service,
    )
    async with Client(mcp) as client:
        tools = await client.list_tools()
        valid_tools = {t.name for t in tools}

        static_res = await client.list_resources()
        templates = await client.list_resource_templates()
        valid_static_uris = {str(r.uri) for r in static_res}
        valid_template_prefixes = {
            str(t.uriTemplate).split("{")[0] for t in templates
        }

    skills_dir = server_root / "skills"
    md_files = list(skills_dir.rglob("*.md"))
    assert len(md_files) >= 12

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")

        # 1. Verify no forbidden legacy MCP tool/resource names appear (exclude .py script names)
        scrubbed_for_legacy = re.sub(r"[a-zA-Z0-9_/-]+\.py\b", "", content)
        for legacy in FORBIDDEN_LEGACY_NAMES:
            assert legacy not in scrubbed_for_legacy, (
                f"Legacy symbol '{legacy}' found in {md_file.relative_to(server_root)}"
            )

        # 2. Verify every argo_* tool token is a registered MCP tool
        found_tools = set(re.findall(r"\bargo_[a-z0-9_]+\b", content))
        unknown_tools = found_tools - valid_tools
        assert not unknown_tools, (
            f"Unregistered tool(s) {unknown_tools} referenced in {md_file.relative_to(server_root)}"
        )

        # 3. Verify every argorollout:// URI matches a registered static or template resource
        found_uris = set(re.findall(r"argorollout://[a-zA-Z0-9_{}/-]+", content))
        for uri in found_uris:
            matches_static = uri in valid_static_uris
            matches_template = any(uri.startswith(prefix) for prefix in valid_template_prefixes)
            assert matches_static or matches_template, (
                f"Unregistered resource URI '{uri}' in {md_file.relative_to(server_root)}"
            )
