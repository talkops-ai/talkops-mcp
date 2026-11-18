"""Boundary-enforcement tests verifying strict separation between MCP execution and Agent Skills."""

from pathlib import Path
import re
import pytest
from fastmcp import Client

from tempo_mcp_server.config import Config
from tempo_mcp_server.models.diagnostics import (
    ALL_OBSERVATION_CODES,
    DiagnosticsOutput,
    ObservationFinding,
)
from tempo_mcp_server.models.trace import TraceSummaryOutput
from tempo_mcp_server.server.bootstrap import ServerBootstrap

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INSTRUCTIONS_PATH = (
    PROJECT_ROOT
    / "tempo_mcp_server"
    / "static"
    / "TEMPO_MCP_INSTRUCTIONS.md"
)
DIAGNOSIS_CODES_MD = (
    PROJECT_ROOT
    / "skills"
    / "diagnosing-tempo-ingestion-and-health"
    / "references"
    / "diagnosis-codes.md"
)


class TestExecutionSkillBoundaryEnforcement:
    """Ensure execution layer outputs only facts and delegates judgement to skills."""

    def test_models_free_of_judgement_fields(self):
        forbidden_fields = {
            "severity",
            "suggested_action",
            "suspected_root_cause",
            "recommended_next_queries",
            "anomaly",
            "verdict",
        }
        for model_cls in (ObservationFinding, DiagnosticsOutput, TraceSummaryOutput):
            schema_props = set(model_cls.model_json_schema().get("properties", {}).keys())
            overlap = schema_props & forbidden_fields
            assert not overlap, f"{model_cls.__name__} contains forbidden fields: {overlap}"

    @pytest.mark.asyncio
    async def test_tool_descriptions_are_concise_and_under_60_words(self):
        cfg = Config.from_cli_and_env(["--allow-write", "--toolsets", "all"])
        mcp, _, _ = ServerBootstrap.build(cfg)
        async with Client(mcp) as client:
            tools = await client.list_tools()
            for tool in tools:
                desc = (tool.description or "").strip()
                word_count = len(desc.split())
                assert word_count <= 60, (
                    f"Tool {tool.name} description has {word_count} words (>60): {desc!r}"
                )

    def test_tempo_mcp_instructions_contains_no_workflow_or_runbook_sections(self):
        text = INSTRUCTIONS_PATH.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 45, f"TEMPO_MCP_INSTRUCTIONS.md has {len(lines)} lines (>45)"
        forbidden_headings = ["workflow", "runbook", "decision tree", "threshold"]
        for heading in forbidden_headings:
            assert heading not in text.lower()

    def test_all_observation_codes_documented_bidirectionally_in_skill_reference(self):
        md = DIAGNOSIS_CODES_MD.read_text(encoding="utf-8")
        for code in ALL_OBSERVATION_CODES:
            assert f"`{code}`" in md, (
                f"Observation code {code} missing from {DIAGNOSIS_CODES_MD}"
            )
        documented_codes = set(re.findall(r"`([A-Z][A-Z0-9_]{3,})`", md))
        assert documented_codes == set(ALL_OBSERVATION_CODES)
