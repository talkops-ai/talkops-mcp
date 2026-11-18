"""T-S5 & T-S7: Verify every otel_* tool and otel:// resource in skills/ matches live server."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastmcp import Client

from opentelemetry_mcp_server.server import ServerBootstrap

ROOT_DIR = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT_DIR / "skills"

TOOL_TOKEN_RE = re.compile(r"\botel_[a-z0-9_]+\b")
RESOURCE_URI_RE = re.compile(r"otel://[a-zA-Z0-9_{}/-]+")
INTERNAL_LINK_RE = re.compile(r"\b(references|scripts)/[a-zA-Z0-9_.-]+\.(?:md|py)\b")


async def _fetch_live_surface() -> tuple[set[str], set[str]]:
    mcp, _ = ServerBootstrap.initialize(argv=["--allow-write", "--toolsets", "all"])
    async with Client(mcp) as client:
        tools = await client.list_tools()
        resources = await client.list_resources()
        templates = await client.list_resource_templates()

    tool_names = {t.name for t in tools}
    resource_uris = {str(r.uri) for r in resources} | {str(rt.uriTemplate) for rt in templates}
    return tool_names, resource_uris


def test_skill_tool_and_resource_tokens_match_registered_server_surface():
    registered_tools, registered_resources = asyncio.run(_fetch_live_surface())

    for md_file in sorted(SKILLS_DIR.rglob("*.md")):
        text = md_file.read_text(encoding="utf-8")

        for match in TOOL_TOKEN_RE.finditer(text):
            token = match.group(0)
            assert token in registered_tools, (
                f"Unregistered tool token '{token}' referenced in {md_file}. "
                f"Registered tools: {sorted(registered_tools)}"
            )

        for match in RESOURCE_URI_RE.finditer(text):
            uri = match.group(0).rstrip(".,;:")
            assert uri in registered_resources, (
                f"Unregistered resource URI '{uri}' referenced in {md_file}. "
                f"Registered resources: {sorted(registered_resources)}"
            )


def test_skill_internal_reference_and_script_links_resolve():
    for skill_dir in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()):
        for md_file in sorted(skill_dir.rglob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            for match in INTERNAL_LINK_RE.finditer(text):
                rel_path = match.group(0)
                target = skill_dir / rel_path
                assert target.exists(), (
                    f"Broken link '{rel_path}' in {md_file}: {target} does not exist"
                )
