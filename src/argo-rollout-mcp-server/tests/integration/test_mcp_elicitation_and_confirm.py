"""In-memory MCP integration tests for destructive confirmation gates (T-I4)."""

import pytest
from fastmcp import Client
from tests.conftest import make_test_server


@pytest.mark.asyncio
async def test_destructive_tools_cancel_without_confirm_and_succeed_with_confirm(
    fake_argo_service, fake_generator_service
):
    mcp = make_test_server(
        allow_write=True,
        toolsets=["all"],
        argo_service=fake_argo_service,
        generator_service=fake_generator_service,
    )
    async with Client(mcp) as client:
        # 1. argo_delete_rollout without confirm -> cancelled
        del_cancel = await client.call_tool(
            "argo_delete_rollout",
            {"name": "payments-api", "namespace": "default", "confirm": False},
        )
        assert del_cancel.data.status == "cancelled"
        fake_argo_service.delete_rollout.assert_not_called()

        # With confirm=True -> success
        del_ok = await client.call_tool(
            "argo_delete_rollout",
            {"name": "payments-api", "namespace": "default", "confirm": True},
        )
        assert del_ok.data.status == "success"
        fake_argo_service.delete_rollout.assert_called_once()

        # 2. argo_manage_rollout_lifecycle(action="abort") without confirm -> cancelled
        abort_cancel = await client.call_tool(
            "argo_manage_rollout_lifecycle",
            {"name": "payments-api", "action": "abort", "confirm": False},
        )
        assert abort_cancel.data.status == "cancelled"
        fake_argo_service.abort_rollout.assert_not_called()

        abort_ok = await client.call_tool(
            "argo_manage_rollout_lifecycle",
            {"name": "payments-api", "action": "abort", "confirm": True},
        )
        assert abort_ok.data.status == "success"
        fake_argo_service.abort_rollout.assert_called_once()

        # 3. argo_delete_analysis_template without confirm -> cancelled (fixes B11)
        at_cancel = await client.call_tool(
            "argo_delete_analysis_template",
            {"name": "payments-api-analysis", "confirm": False},
        )
        assert at_cancel.data.status == "cancelled"
        fake_argo_service.delete_analysis_template.assert_not_called()

        at_ok = await client.call_tool(
            "argo_delete_analysis_template",
            {"name": "payments-api-analysis", "confirm": True},
        )
        assert at_ok.data.status == "success"
        fake_argo_service.delete_analysis_template.assert_called_once()

        # 4. argo_delete_experiment without confirm -> cancelled
        exp_cancel = await client.call_tool(
            "argo_delete_experiment",
            {"name": "payments-exp", "confirm": False},
        )
        assert exp_cancel.data.status == "cancelled"
        fake_argo_service.delete_experiment.assert_not_called()

        exp_ok = await client.call_tool(
            "argo_delete_experiment",
            {"name": "payments-exp", "confirm": True},
        )
        assert exp_ok.data.status == "success"
        fake_argo_service.delete_experiment.assert_called_once()
