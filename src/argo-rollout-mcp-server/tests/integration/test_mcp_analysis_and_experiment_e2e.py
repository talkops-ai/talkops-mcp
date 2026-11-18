"""End-to-end in-memory MCP integration test for AnalysisTemplates, Experiments, and Canary Metrics (T-I9)."""

import json
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from tests.conftest import make_test_server


@pytest.mark.asyncio
async def test_analysis_and_experiment_lifecycle_e2e(
    fake_argo_service, fake_generator_service
):
    mcp = make_test_server(
        allow_write=True,
        toolsets=["all"],
        prometheus_url="http://127.0.0.1:59999",  # unreachable local port for negative check
        argo_service=fake_argo_service,
        generator_service=fake_generator_service,
    )
    async with Client(mcp) as client:
        # 1. Preview ClusterAnalysisTemplate (dry_run=True)
        at_prev = await client.call_tool(
            "argo_configure_analysis_template",
            {
                "rollout_name": "payments-api",
                "namespace": "default",
                "scope": "cluster",
                "thresholds": {"error_rate_percent": 2.5, "latency_p99_ms": 1500.0},
                "dry_run": True,
            },
        )
        assert at_prev.data.status == "preview"
        assert "kind: ClusterAnalysisTemplate" in at_prev.data.manifest

        # 2. Apply AnalysisTemplate (dry_run=False)
        at_apply = await client.call_tool(
            "argo_configure_analysis_template",
            {
                "rollout_name": "payments-api",
                "namespace": "default",
                "scope": "namespace",
                "dry_run": False,
            },
        )
        assert at_apply.data.status == "success"
        fake_argo_service.set_analysis_template.assert_called_once()

        # 3. Create Experiment
        exp_res = await client.call_tool(
            "argo_create_experiment",
            {
                "name": "payments-exp",
                "namespace": "default",
                "templates": [
                    {"name": "baseline", "replicas": 1, "specRef": "stable"},
                    {"name": "candidate", "replicas": 1, "specRef": "canary"},
                ],
                "rollout_name": "payments-api",
                "duration": "20m",
            },
        )
        assert exp_res.data.status == "success"
        assert len(exp_res.data.warnings) == 1  # Traefik note

        # 4. Read Experiment status resource
        exp_status_res = await client.read_resource(
            "argorollout://experiments/default/payments-exp/status"
        )
        exp_status = json.loads(exp_status_res[0].text)
        assert exp_status["phase"] == "Running"

        # 5. Compare canary metrics raises actionable ToolError when Prometheus is unreachable
        with pytest.raises(ToolError, match="Prometheus metrics comparison unavailable"):
            await client.call_tool(
                "argo_compare_canary_metrics",
                {"rollout_name": "payments-api", "namespace": "default", "window": "5m"},
            )

        # 6. Delete Experiment and AnalysisTemplate with confirm=True
        del_exp = await client.call_tool(
            "argo_delete_experiment",
            {"name": "payments-exp", "namespace": "default", "confirm": True},
        )
        assert del_exp.data.status == "success"

        del_at = await client.call_tool(
            "argo_delete_analysis_template",
            {"name": "payments-api-analysis", "namespace": "default", "confirm": True},
        )
        assert del_at.data.status == "success"
