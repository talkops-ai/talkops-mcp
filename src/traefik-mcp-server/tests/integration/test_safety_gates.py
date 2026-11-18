"""Integration tests for safety gates: Argo Rollouts ownership, empty backend weight guard, and MCP Elicitation."""

import pytest
from fastmcp.client import Client
from fastmcp.client.elicitation import ElicitResult
from fastmcp.exceptions import ToolError


@pytest.mark.asyncio
async def test_argo_rollout_ownership_refuses_weight_mutation(mcp_rw, traefik_service):
    traefik_service._seed([
        {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Rollout",
            "metadata": {"name": "payments-rollout", "namespace": "default"},
            "spec": {
                "strategy": {
                    "canary": {
                        "trafficRouting": {
                            "traefik": {"weightedTraefikServiceName": "payments-wrr"}
                        }
                    }
                }
            },
        }
    ])
    async with Client(mcp_rw) as client:
        res = await client.call_tool(
            "traefik_set_traffic_weights",
            {
                "name": "payments-wrr",
                "namespace": "default",
                "weights": {"payments-stable": 50, "payments-canary": 50},
                "dry_run": False,
            },
        )
        data = res.structured_content
        assert data["status"] == "refused"
        assert "argo_manage_rollout_lifecycle" in data["summary"]


@pytest.mark.asyncio
async def test_empty_backend_weight_guard_blocks_shifting_traffic_to_zero_endpoints(mcp_rw):
    async with Client(mcp_rw) as client:
        with pytest.raises(ToolError, match="WEIGHT_TO_EMPTY_BACKEND"):
            await client.call_tool(
                "traefik_configure_weighted_service",
                {
                    "name": "empty-target-wrr",
                    "namespace": "default",
                    "backends": [
                        {"name": "payments-stable", "port": 80, "weight": 80},
                        {"name": "payments-empty", "port": 80, "weight": 20},
                    ],
                },
            )


@pytest.mark.asyncio
async def test_mcp_elicitation_accept_and_decline_on_destructive_delete(mcp_rw):
    async def decline_handler(message, response_type, params, context):
        return ElicitResult(action="decline")

    async with Client(mcp_rw, elicitation_handler=decline_handler) as client:
        declined = await client.call_tool(
            "traefik_delete_resource",
            {"kind": "TLSOption", "name": "modern-tls", "namespace": "default", "force": True, "confirm": False},
        )
        assert declined.structured_content["status"] == "cancelled"

    async def accept_handler(message, response_type, params, context):
        return ElicitResult(action="accept", content={"value": "confirm"})

    async with Client(mcp_rw, elicitation_handler=accept_handler) as client:
        accepted = await client.call_tool(
            "traefik_delete_resource",
            {"kind": "TLSOption", "name": "modern-tls", "namespace": "default", "force": True, "confirm": False},
        )
        assert accepted.structured_content["status"] == "success"
