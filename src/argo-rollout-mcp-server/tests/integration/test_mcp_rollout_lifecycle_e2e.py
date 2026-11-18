"""End-to-end stateful in-memory MCP integration test for onboarding & rollout progression (T-I8)."""

import pytest
from fastmcp import Client
from tests.conftest import make_test_server


@pytest.mark.asyncio
async def test_end_to_end_onboarding_and_rollout_progression(
    fake_argo_service, fake_generator_service
):
    mcp = make_test_server(
        allow_write=True,
        toolsets=["all"],
        argo_service=fake_argo_service,
        generator_service=fake_generator_service,
    )
    async with Client(mcp) as client:
        # 1. Validate Deployment readiness
        readiness = await client.call_tool(
            "argo_validate_deployment_readiness",
            {"deployment_name": "payments-api", "namespace": "default"},
        )
        assert readiness.data.ready is True
        assert readiness.data.detected_container_port == 8080

        # 2. Preview Deployment -> Rollout conversion (dry_run=True)
        preview = await client.call_tool(
            "argo_convert_deployment_to_rollout",
            {
                "deployment_name": "payments-api",
                "namespace": "default",
                "strategy": "canary",
                "migration_mode": "workload_ref",
                "dry_run": True,
            },
        )
        assert preview.data.status == "preview"
        assert "workloadRef:" in preview.data.manifest

        # 3. Execute Deployment -> Rollout conversion (dry_run=False)
        applied = await client.call_tool(
            "argo_convert_deployment_to_rollout",
            {
                "deployment_name": "payments-api",
                "namespace": "default",
                "strategy": "canary",
                "migration_mode": "workload_ref",
                "dry_run": False,
            },
        )
        assert applied.data.status == "success"
        fake_generator_service.apply_rollout_crd.assert_called_once()

        # 4. Trigger image update
        img_res = await client.call_tool(
            "argo_set_rollout_image",
            {
                "name": "payments-api",
                "image": "ghcr.io/talkops/payments-api:1.5.0",
                "namespace": "default",
            },
        )
        assert img_res.data.status == "success"

        # 5. Diagnose rollout
        diag = await client.call_tool(
            "argo_diagnose_rollout",
            {"name": "payments-api", "namespace": "default"},
        )
        assert "HEALTHY" in diag.data.diagnosis_codes

        # 6. Promote next canary step
        promo = await client.call_tool(
            "argo_manage_rollout_lifecycle",
            {"name": "payments-api", "action": "promote", "namespace": "default"},
        )
        assert promo.data.status == "success"
        fake_argo_service.promote_rollout.assert_called_with(
            name="payments-api", namespace="default", full=False
        )

        # 7. Scale down legacy Deployment (with dry_run=False and confirm=True)
        scale_res = await client.call_tool(
            "argo_manage_legacy_deployment",
            {
                "name": "payments-api",
                "action": "scale",
                "replicas": 0,
                "rollout_name": "payments-api",
                "confirm": True,
                "dry_run": False,
            },
        )
        assert scale_res.data.status == "success"
        fake_argo_service.verify_rollout_healthy.assert_called_once()
        fake_argo_service.scale_deployment.assert_called_once()
