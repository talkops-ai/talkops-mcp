"""End-to-End Workflow Test: Troubleshooting Investigation Flow.

Matches the `troubleshooting-telemetry-pipelines` skill workflow:
  1. Read `otel://server/capabilities`
  2. Survey cluster state via `otel_survey_cluster`
  3. Run single-call collector diagnosis via `otel_diagnose_collector`
  4. Validate collector config via `otel_validate_collector_config`
  5. Inspect rollback history via `otel://collector/{namespace}/{name}/history`
"""

import json
import pytest
from fastmcp import Client

pytestmark = pytest.mark.asyncio


async def test_investigation_flow(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        # 1. Check capabilities
        caps = json.loads((await client.read_resource("otel://server/capabilities"))[0].text)
        assert caps["allow_write"] is True

        # 2. Survey cluster
        survey = await client.call_tool("otel_survey_cluster", {"namespaces": ["observability"]})
        survey_data = json.loads(survey.content[0].text)
        assert "collectors" in survey_data

        # 3. Diagnose collector
        diag = await client.call_tool(
            "otel_diagnose_collector",
            {"namespace": "observability", "name": "my-collector", "include": ["status", "pods", "config_lint"]},
        )
        diag_data = json.loads(diag.content[0].text)
        assert diag_data["collector"] == "observability/my-collector"
        assert "findings" in diag_data

        # 4. Read live config & validate
        cfg_text = (
            await client.read_resource("otel://collector/observability/my-collector/config")
        )[0].text
        val_res = await client.call_tool(
            "otel_validate_collector_config",
            {"namespace": "observability", "name": "my-collector", "config_yaml": cfg_text},
        )
        val_data = json.loads(val_res.content[0].text)
        assert "findings" in val_data

        # 5. Read rollback history
        hist_text = (
            await client.read_resource("otel://collector/observability/my-collector/history")
        )[0].text
        assert "has_snapshot" in json.loads(hist_text)
