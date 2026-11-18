"""In-memory MCP integration test verifying dry_run=True defaults on structural mutations (T-I3)."""

import pytest
from fastmcp import Client
from tests.conftest import make_test_server


@pytest.mark.asyncio
async def test_structural_mutation_tools_default_to_dry_run_preview(
    fake_argo_service, fake_generator_service
):
    mcp = make_test_server(
        allow_write=True,
        toolsets=["all"],
        argo_service=fake_argo_service,
        generator_service=fake_generator_service,
    )
    async with Client(mcp) as client:
        # 1. argo_create_rollout
        res1 = await client.call_tool(
            "argo_create_rollout",
            {"name": "payments-api", "image": "nginx:1.25"},
        )
        data1 = res1.data
        assert data1.status == "preview"
        assert data1.dry_run is True
        assert "kind: Rollout" in data1.manifest
        fake_argo_service.create_rollout.assert_not_called()

        # 2. argo_convert_deployment_to_rollout
        res2 = await client.call_tool(
            "argo_convert_deployment_to_rollout",
            {"deployment_name": "payments-api", "namespace": "default"},
        )
        data2 = res2.data
        assert data2.status == "preview"
        assert data2.dry_run is True
        assert "kind: Rollout" in data2.manifest
        assert len(data2.warnings) >= 1  # direct mode double-workload warning
        fake_generator_service.apply_rollout_crd.assert_not_called()

        # 3. argo_convert_rollout_to_deployment
        res3 = await client.call_tool(
            "argo_convert_rollout_to_deployment",
            {"name": "payments-api", "namespace": "default"},
        )
        data3 = res3.data
        assert data3.status == "preview"
        assert data3.dry_run is True
        assert "kind: Deployment" in data3.manifest

        # 4. argo_configure_rollout_strategy
        res4 = await client.call_tool(
            "argo_configure_rollout_strategy",
            {"name": "payments-api", "steps": [{"setWeight": 10}, {"pause": {}}]},
        )
        data4 = res4.data
        assert data4.status == "preview"
        assert data4.dry_run is True
        fake_argo_service.update_canary_strategy.assert_not_called()

        # 5. argo_configure_analysis_template
        res5 = await client.call_tool(
            "argo_configure_analysis_template",
            {"rollout_name": "payments-api", "namespace": "default"},
        )
        data5 = res5.data
        assert data5.status == "preview"
        assert data5.dry_run is True
        assert "kind: AnalysisTemplate" in data5.manifest
        fake_argo_service.set_analysis_template.assert_not_called()

        # 6. argo_manage_legacy_deployment
        res6 = await client.call_tool(
            "argo_manage_legacy_deployment",
            {"name": "payments-api", "action": "scale", "replicas": 0},
        )
        data6 = res6.data
        assert data6.status == "preview"
        assert data6.dry_run is True
        fake_argo_service.scale_deployment.assert_not_called()
