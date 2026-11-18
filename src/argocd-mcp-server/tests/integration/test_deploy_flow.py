"""Layer 3 E2E workflow test for deploying an ArgoCD application (matching deploying-argocd-applications skill)."""

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
async def test_e2e_safe_deployment_workflow_without_stale_caching(
    mcp_server_write: Any,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """Execute the full Discover -> Diff & Validate -> Dry-Run -> Sync -> Verify workflow."""
    out_of_sync_app = load_json_fixture("application_detail.json")
    synced_app = json.loads(json.dumps(out_of_sync_app))
    synced_app["status"]["sync"]["status"] = "Synced"
    synced_app["status"]["health"]["status"] = "Healthy"

    # First two GETs return OutOfSync (for details + diff/validate), post-sync GET returns Synced
    standard_argocd_routes.get(f"{BASE_URL}/api/v1/applications/payments-service").mock(
        side_effect=[
            httpx.Response(200, json=out_of_sync_app),
            httpx.Response(200, json=out_of_sync_app),
            httpx.Response(200, json=synced_app),
            httpx.Response(200, json=synced_app),
        ]
    )

    async with Client(mcp_server_write) as client:
        # Step 1: Inspect initial state (OutOfSync)
        initial = _extract_data(
            await client.call_tool(
                "get_application_details",
                {"app_name": "payments-service", "detail_level": "summary"},
            )
        )
        assert initial["sync_status"] == "OutOfSync"

        # Step 2: Compute live-vs-target diff & validate
        diff = _extract_data(
            await client.call_tool(
                "get_application_diff",
                {"app_name": "payments-service", "revision": "v1.4.0", "validate": True},
            )
        )
        assert diff["changes_detected"] is True
        assert diff["validation"]["valid"] is True

        # Step 3: Dry-run sync preview
        dry_run = _extract_data(
            await client.call_tool(
                "sync_application",
                {"app_name": "payments-service", "revision": "v1.4.0", "dry_run": True},
            )
        )
        assert dry_run["mode"] == "dry_run"

        # Step 4: Live sync execution
        live_sync = _extract_data(
            await client.call_tool(
                "sync_application",
                {"app_name": "payments-service", "revision": "v1.4.0", "dry_run": False},
            )
        )
        assert live_sync["mode"] == "executed"

        # Step 5: Verify convergence (proves call_tool is NOT cached across polling calls)
        status = _extract_data(
            await client.call_tool("get_sync_status", {"app_name": "payments-service"})
        )
        assert status["overall_sync_status"] == "Synced"
        assert status["health_status"] == "Healthy"

        final = _extract_data(
            await client.call_tool(
                "get_application_details",
                {"app_name": "payments-service", "detail_level": "summary"},
            )
        )
        assert final["sync_status"] == "Synced"
