"""Cross-reference conformance tests verifying every tempo_* tool and tempo:// resource in skills exists on the live server."""

from pathlib import Path
import re
import pytest
from fastmcp import Client

from tempo_mcp_server.config import Config
from tempo_mcp_server.models.diagnostics import ALL_DIAGNOSIS_CODES
from tempo_mcp_server.server.bootstrap import ServerBootstrap

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
TOOL_RE = re.compile(r"\b(tempo_[a-z0-9_]+)\b")
RESOURCE_RE = re.compile(r"(tempo://[a-zA-Z0-9_/{}-]+)")


@pytest.mark.asyncio
async def test_all_skill_tool_and_resource_references_exist():
    cfg = Config.from_cli_and_env(["--allow-write", "--toolsets", "all"])
    mcp, _, _ = ServerBootstrap.build(cfg)
    async with Client(mcp) as client:
        registered_tools = {t.name for t in await client.list_tools()}
        static_res = {str(r.uri) for r in await client.list_resources()}
        tmpl_res = {str(r.uriTemplate) for r in await client.list_resource_templates()}
        all_resources = static_res | tmpl_res

    ignored_identifiers = {
        "tempo_mcp_server",
        "tempo_major_version",
        "tempo_discarded_spans_total",
        "tempo_ingest_group_partition_lag_seconds",
        "tempo_request_duration_seconds",
        "tempo_ingester_blocks_flushed_total",
        "tempo_distributor_spans_received_total",
    }

    for md_file in SKILLS_DIR.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        for tool_name in set(TOOL_RE.findall(content)) - ignored_identifiers:
            assert tool_name in registered_tools, (
                f"{md_file} references non-existent MCP tool '{tool_name}'. "
                f"Registered: {sorted(registered_tools)}"
            )
        for uri in set(RESOURCE_RE.findall(content)):
            if any(
                uri == r or uri.startswith(r.split("{")[0]) for r in all_resources
            ):
                continue
            pytest.fail(
                f"{md_file} references unknown MCP resource URI '{uri}'. "
                f"Registered: {sorted(all_resources)}"
            )


def test_all_diagnosis_codes_documented_in_skill_reference():
    ref_md = (
        SKILLS_DIR
        / "diagnosing-tempo-ingestion-and-health"
        / "references"
        / "diagnosis-codes.md"
    ).read_text(encoding="utf-8")
    for code in ALL_DIAGNOSIS_CODES:
        assert f"`{code}`" in ref_md, (
            f"Diagnosis code {code} missing from diagnosis-codes.md"
        )
