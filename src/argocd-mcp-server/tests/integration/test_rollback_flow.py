"""Layer 3 E2E workflow test for rolling back an application with auto-sync enabled (matching rolling-back-argocd-applications skill)."""

import json
from typing import Any, Dict

import httpx
import pytest
import respx
from fastmcp import Client

from tests.conftest import BASE_URL, load_json_fixture


def _extract_data(result: Any) -> Dict[str, Any]:
    if getattr(result, "data", None) is not None and isinstance(result.data, dict):
        return result.data
    return json.loads(result.content[0].text)


@pytest.mark.asyncio
async def test_e2e_rollback_workflow_with_autosync_disable(
    mcp_server_write: Any,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """Execute History Inspection -> Dry-Run Preview (detects auto-sync) -> Disable Auto-Sync -> Execute Rollback -> Verify."""
    autosync_app = load_json_fixture("application_detail_autosync.json")
    manual_app = json.loads(json.dumps(autosync_app))
    manual_app["spec"]["syncPolicy"].pop("automated", None)
    recovered_app = json.loads(json.dumps(manual_app))
    recovered_app["status"]["health"]["status"] = "Healthy"
    recovered_app["status"]["sync"]["revision"] = "3333cccc4444dddd"

    standard_argocd_routes.get(f"{BASE_URL}/api/v1/applications/payments-service").mock(
        side_effect=[
            httpx.Response(200, json=autosync_app),  # get_application_details
            httpx.Response(200, json=autosync_app),  # rollback_application(dry_run=True)
            httpx.Response(200, json=autosync_app),  # update_application GET
            httpx.Response(200, json=manual_app),    # rollback_application(dry_run=False)
            httpx.Response(200, json=recovered_app), # get_sync_status verification
        ]
    )

    async with Client(mcp_server_write) as client:
        # Step 1: Inspect history and auto-sync state
        details = _extract_data(
            await client.call_tool(
                "get_application_details",
                {"app_name": "payments-service", "detail_level": "full"},
            )
        )
        assert details["auto_sync_enabled"] is True
        target_history_id = details["sync_history"][-2]["id"]
        assert target_history_id == 12

        # Step 2: Dry-run rollback preview warns about auto-sync blocker
        preview = _extract_data(
            await client.call_tool(
                "rollback_application",
                {
                    "app_name": "payments-service",
                    "history_id": target_history_id,
                    "dry_run": True,
                },
            )
        )
        assert preview["auto_sync_blocker"] is True
        assert preview["target_revision"] == "3333cccc4444dddd"

        # Step 3: Disable auto-sync via update_application
        updated = _extract_data(
            await client.call_tool(
                "update_application",
                {
                    "app_name": "payments-service",
                    "sync_policy": {"automated": False},
                },
            )
        )
        assert updated["auto_sync_enabled"] is False

        # Step 4: Execute rollback with confirm=True
        executed = _extract_data(
            await client.call_tool(
                "rollback_application",
                {
                    "app_name": "payments-service",
                    "history_id": target_history_id,
                    "dry_run": False,
                    "confirm": True,
                },
            )
        )
        assert executed["mode"] == "executed"
        assert executed["history_id"] == 12

        # Step 5: Verify recovery
        status = _extract_data(
            await client.call_tool("get_sync_status", {"app_name": "payments-service"})
        )
        assert status["health_status"] == "Healthy"
        assert status["sync_details"]["revision"] == "3333cccc4444dddd"
