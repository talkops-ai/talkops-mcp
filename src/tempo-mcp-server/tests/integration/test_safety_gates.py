"""Integration tests for write-gates, dry_run=True defaults, unified diff, and ctx.elicit() confirmation."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from tempo_mcp_server.config import ServerConfig
from tempo_mcp_server.tools.operator.operator_tools import OperatorTools


def _register_operator_tools(allow_write: bool, tempo_svc=None, k8s_svc=None):
    locator = {
        "tempo_service": tempo_svc or MagicMock(),
        "kubernetes_service": k8s_svc or MagicMock(),
        "config": ServerConfig(allow_write=allow_write, toolsets=["overrides", "operator"]),
    }
    mcp = MagicMock()
    captured = {}

    def capture_tool(**kwargs):
        def decorator(fn):
            captured[fn.__name__] = fn
            return fn

        return decorator

    mcp.tool = capture_tool
    OperatorTools(locator).register(mcp)
    return captured


class TestSafetyGatesAndElicitation:
    """Verify dry-run diff preview, write-gate enforcement, and ctx.elicit() behavior."""

    def test_write_tools_not_registered_when_allow_write_false(self):
        captured = _register_operator_tools(allow_write=False)
        assert captured == {}

    @pytest.mark.asyncio
    async def test_patch_tenant_overrides_dry_run_default_computes_diff_without_writing(self):
        tempo = MagicMock()
        tempo.get_tenant_overrides = AsyncMock(
            return_value={
                "backend_id": "default",
                "tenant": "team-a",
                "overrides": {"max_bytes_per_trace": 5000000},
                "etag": '"v1"',
            }
        )
        tempo.patch_tenant_overrides = AsyncMock()
        tools = _register_operator_tools(allow_write=True, tempo_svc=tempo)

        res = await tools["tempo_patch_tenant_overrides"](
            backend_id="default",
            tenant="team-a",
            merge_patch={"max_bytes_per_trace": 10000000},
            dry_run=True,
            ctx=AsyncMock(),
        )
        assert res["dry_run"] is True
        assert res["action"] == "dry_run"
        assert "+max_bytes_per_trace: 10000000" in res["diff"]
        tempo.patch_tenant_overrides.assert_not_called()

    @pytest.mark.asyncio
    async def test_patch_tenant_overrides_live_cancelled_when_user_declines_elicit(self):
        tempo = MagicMock()
        tempo.get_tenant_overrides = AsyncMock(
            return_value={
                "backend_id": "default",
                "tenant": "team-a",
                "overrides": {"max_bytes_per_trace": 5000000},
                "etag": '"v1"',
            }
        )
        tempo.patch_tenant_overrides = AsyncMock()
        tools = _register_operator_tools(allow_write=True, tempo_svc=tempo)

        ctx = AsyncMock()
        elicit_resp = MagicMock()
        elicit_resp.action = "decline"
        ctx.elicit = AsyncMock(return_value=elicit_resp)

        res = await tools["tempo_patch_tenant_overrides"](
            backend_id="default",
            tenant="team-a",
            merge_patch={"max_bytes_per_trace": 10000000},
            dry_run=False,
            ctx=ctx,
        )
        assert res["action"] == "aborted"
        tempo.patch_tenant_overrides.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_operator_cr_dry_run_and_live_accept(self):
        k8s = MagicMock()
        k8s.apply_tempo_cr_manifest = AsyncMock(
            return_value={
                "kind": "TempoStack",
                "namespace": "observability",
                "name": "tempo-prod",
                "action": "applied",
                "dry_run": False,
                "server_dry_run_validated": True,
                "diff": "--- before\n+++ after\n",
            }
        )
        tools = _register_operator_tools(allow_write=True, k8s_svc=k8s)

        ctx = AsyncMock()
        elicit_resp = MagicMock()
        elicit_resp.action = "accept"
        elicit_resp.data = "confirm"
        ctx.elicit = AsyncMock(return_value=elicit_resp)

        manifest = {
            "apiVersion": "tempo.grafana.com/v1alpha1",
            "kind": "TempoStack",
            "metadata": {"name": "tempo-prod", "namespace": "observability"},
            "spec": {"replicationFactor": 2},
        }
        res = await tools["tempo_apply_operator_cr"](
            manifest=manifest,
            dry_run=False,
            ctx=ctx,
        )
        assert res["action"] == "applied"
        assert res["server_dry_run_validated"] is True
