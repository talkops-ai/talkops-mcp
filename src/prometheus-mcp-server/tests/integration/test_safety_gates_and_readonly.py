"""Integration tests for `--read-only`, `--toolsets` gating, `dry_run`, and `ctx.elicit()` safety gates."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from prometheus_mcp_server.config import KubernetesConfig, ServerConfig
from prometheus_mcp_server.exceptions import (
    ConfirmationRequiredError,
    WriteAccessDeniedError,
)
from prometheus_mcp_server.server.bootstrap import ServerBootstrap
from prometheus_mcp_server.tools import initialize_tools


class TestSafetyGatesAndReadOnly:
    @pytest.mark.asyncio
    async def test_read_only_mode_hides_all_write_tools(self) -> None:
        cfg = ServerConfig(allow_write=False)
        mcp, _ = ServerBootstrap.initialize(config=cfg)
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}

        # 13 read-only tools remain; 6 write/destructive tools are unregistered
        assert len(tool_names) == 13
        for t in tools:
            assert t.annotations.readOnlyHint is True

    @pytest.mark.asyncio
    async def test_toolsets_scoping_registers_only_selected_toolsets(self) -> None:
        cfg = ServerConfig(allow_write=True, toolsets=["diagnostics", "exporter"])
        mcp, _ = ServerBootstrap.initialize(config=cfg)
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}

        assert tool_names == {
            "prom_get_diagnostics",
            "prom_analyze_cardinality",
            "prom_install_exporter",
            "prom_uninstall_exporter",
        }

    @pytest.mark.asyncio
    async def test_confirmation_and_interactive_elicitation_gates(self) -> None:
        cfg = ServerConfig(allow_write=True, kubernetes=KubernetesConfig(enabled=True))
        k8s_svc = MagicMock()
        k8s_svc.delete_rule_group_crd = AsyncMock(
            return_value={"found": True, "action": "deleted_crd", "remaining_group_count": 0}
        )
        locator: Dict[str, Any] = {
            "prometheus_service": MagicMock(),
            "kubernetes_service": k8s_svc,
            "config": cfg,
        }

        mcp = MagicMock()
        captured = {}

        def capture(**_kwargs: Any):
            def _wrap(fn):
                captured[fn.__name__] = fn
                return fn

            return _wrap

        mcp.tool = capture
        initialize_tools(locator).register_all_tools(mcp)
        delete_fn = captured["prom_delete_rule_group"]

        # 1. Calling with dry_run=False and confirm=False without elicitation raises ConfirmationRequiredError
        with pytest.raises(ConfirmationRequiredError):
            await delete_fn(
                backend_id="default",
                group_name="critical-rules",
                namespace="monitoring",
                dry_run=False,
                confirm=False,
                ctx=None,
            )

        # 2. Calling with ctx.elicit() declining raises ConfirmationRequiredError
        decline_ctx = MagicMock()
        decline_ctx.elicit = AsyncMock(
            return_value=SimpleNamespace(action="decline", data=False)
        )
        with pytest.raises(ConfirmationRequiredError):
            await delete_fn(
                backend_id="default",
                group_name="critical-rules",
                namespace="monitoring",
                dry_run=False,
                confirm=False,
                ctx=decline_ctx,
            )

        # 3. Calling with ctx.elicit() accepting succeeds even when confirm=False
        accept_ctx = MagicMock()
        accept_ctx.elicit = AsyncMock(
            return_value=SimpleNamespace(action="accept", data=True)
        )
        res = await delete_fn(
            backend_id="default",
            group_name="critical-rules",
            namespace="monitoring",
            dry_run=False,
            confirm=False,
            ctx=accept_ctx,
        )
        assert res["status"] == "deleted"

        # 4. Flipping config.allow_write = False blocks runtime execution with WriteAccessDeniedError
        cfg.allow_write = False
        with pytest.raises(WriteAccessDeniedError):
            await delete_fn(
                backend_id="default",
                group_name="critical-rules",
                namespace="monitoring",
                dry_run=True,
                confirm=False,
            )
