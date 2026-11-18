"""Unit tests for consolidated history-ID rollback logic and auto-sync blocker handling (Fixes N2)."""

import httpx
import pytest
import respx

from argocd_mcp_server.exceptions import ArgoCDOperationError, SyncOperationFailed
from argocd_mcp_server.services import ArgoCDService
from tests.conftest import BASE_URL, load_json_fixture


@pytest.mark.asyncio
async def test_rollback_resolves_previous_history_id_when_omitted(
    argocd_service: ArgoCDService,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """When history_id is None, rollback_application selects history[-2] (ID 12, revision 3333cccc4444dddd)."""
    preview = await argocd_service.rollback_application(
        app_name="payments-service",
        history_id=None,
        dry_run=True,
    )
    assert preview["mode"] == "dry_run"
    assert preview["history_id"] == 12
    assert preview["target_revision"] == "3333cccc4444dddd"
    assert preview["current_revision"] == "8f3c1a9d4e2b"
    assert preview["auto_sync_blocker"] is False


@pytest.mark.asyncio
async def test_rollback_specific_history_id_execution(
    argocd_service: ArgoCDService,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """When history_id=11 and dry_run=False, rollback_application posts ID 11 to /rollback."""
    executed = await argocd_service.rollback_application(
        app_name="payments-service",
        history_id=11,
        dry_run=False,
        prune=True,
    )
    assert executed["mode"] == "executed"
    assert executed["history_id"] == 11
    assert executed["target_revision"] == "1111aaaa2222bbbb"
    assert executed["status"] == "RollingBack"


@pytest.mark.asyncio
async def test_rollback_invalid_history_id_lists_valid_ids(
    argocd_service: ArgoCDService,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """Passing a non-existent history_id raises ArgoCDOperationError listing valid IDs."""
    with pytest.raises(ArgoCDOperationError, match=r"Valid history IDs: \[11, 12, 13\]"):
        await argocd_service.rollback_application(
            app_name="payments-service",
            history_id=999,
            dry_run=True,
        )


@pytest.mark.asyncio
async def test_rollback_blocks_execution_when_autosync_enabled(
    argocd_service: ArgoCDService,
    respx_mock: respx.MockRouter,
) -> None:
    """When auto-sync is enabled, dry_run=True warns and dry_run=False raises SyncOperationFailed."""
    autosync_app = load_json_fixture("application_detail_autosync.json")
    rollback_resp = load_json_fixture("rollback_response.json")
    respx_mock.get(f"{BASE_URL}/api/v1/applications/payments-service").mock(
        return_value=httpx.Response(200, json=autosync_app)
    )
    respx_mock.post(f"{BASE_URL}/api/v1/applications/payments-service/rollback").mock(
        return_value=httpx.Response(200, json=rollback_resp)
    )

    preview = await argocd_service.rollback_application(
        app_name="payments-service",
        history_id=12,
        dry_run=True,
    )
    assert preview["auto_sync_blocker"] is True
    assert "update_application" in preview["warning"]

    with pytest.raises(SyncOperationFailed, match="while auto-sync is enabled"):
        await argocd_service.rollback_application(
            app_name="payments-service",
            history_id=12,
            dry_run=False,
        )
