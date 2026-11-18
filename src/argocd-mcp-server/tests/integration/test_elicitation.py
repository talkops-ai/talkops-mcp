"""Layer 2 integration tests for destructive action confirmation (confirm=True fallback and MCP Elicitation)."""

import json
from typing import Any, Dict

import pytest
import respx
from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult


def _extract_data(result: Any) -> Dict[str, Any]:
    if getattr(result, "data", None) is not None and isinstance(result.data, dict):
        return result.data
    return json.loads(result.content[0].text)


@pytest.mark.asyncio
async def test_destructive_tools_return_confirmation_required_without_elicit_handler(
    mcp_server_write: Any,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """When client has no elicitation handler and confirm=False, destructive tools return confirmation_required."""
    async with Client(mcp_server_write) as client:
        # 1. delete_application without confirm=True
        del_preview = _extract_data(
            await client.call_tool(
                "delete_application",
                {"app_name": "payments-service", "cascade": True, "confirm": False},
            )
        )
        assert del_preview["status"] == "confirmation_required"
        assert del_preview["requires_confirmation"] is True
        assert del_preview["impact_preview"]["app_name"] == "payments-service"

        # 2. delete_application with confirm=True executes
        del_exec = _extract_data(
            await client.call_tool(
                "delete_application",
                {"app_name": "payments-service", "cascade": True, "confirm": True},
            )
        )
        assert del_exec["deleted"] is True

        # 3. sync_application with prune=True and dry_run=False requires confirmation
        sync_gate = _extract_data(
            await client.call_tool(
                "sync_application",
                {
                    "app_name": "payments-service",
                    "dry_run": False,
                    "prune": True,
                    "confirm": False,
                },
            )
        )
        assert sync_gate["status"] == "confirmation_required"


@pytest.mark.asyncio
async def test_destructive_tools_with_interactive_mcp_elicitation_handler(
    mcp_server_write: Any,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """When client provides an elicitation_handler, accepting 'confirm' proceeds and 'abort' cancels."""
    decisions = ["abort", "confirm"]

    async def elicitation_handler(message: str, response_type: Any, params: Any, context: Any):
        choice = decisions.pop(0)
        return ElicitResult(action="accept", content={"value": choice})

    async with Client(mcp_server_write, elicitation_handler=elicitation_handler) as client:
        # First call: operator chooses 'abort'
        aborted = _extract_data(
            await client.call_tool(
                "delete_repository",
                {"repo_url": "https://github.com/org/gitops-manifests.git"},
            )
        )
        assert aborted["status"] == "aborted"
        assert aborted["confirmed"] is False

        # Second call: operator chooses 'confirm'
        confirmed = _extract_data(
            await client.call_tool(
                "delete_repository",
                {"repo_url": "https://github.com/org/gitops-manifests.git"},
            )
        )
        assert confirmed["deleted"] is True
