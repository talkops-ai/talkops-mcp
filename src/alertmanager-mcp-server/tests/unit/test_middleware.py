"""Unit tests for schema-aware `JsonCoercionMiddleware`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from alertmanager_mcp_server.server.bootstrap import ServerBootstrap
from alertmanager_mcp_server.server.middleware import JsonCoercionMiddleware


class TestJsonCoercionMiddleware:
    @pytest.mark.asyncio
    async def test_preserves_colons_in_string_parameters_and_native_dicts(
        self, test_server_config
    ) -> None:
        """Regression test for P1 & P11: comments with colons must stay strings, and dicts stay dicts."""
        mcp, _, _ = ServerBootstrap.initialize(config=test_server_config)
        mw = JsonCoercionMiddleware(mcp=mcp)

        msg = MagicMock()
        msg.name = "am_create_silence"
        msg.arguments = {
            "backend_id": "test-am",
            "matchers": [{"name": "service", "value": "checkout", "isRegex": False, "isEqual": True}],
            "created_by": "sre:oncall@example.com",
            "comment": "JIRA-123: planned database failover at 10:00:00Z",
            "starts_at": "2026-03-29T10:00:00Z",
        }
        ctx = MagicMock()
        ctx.message = msg
        ctx.fastmcp_context = None

        call_next = AsyncMock(return_value=MagicMock())
        await mw.on_call_tool(ctx, call_next)

        # String parameters with colons MUST remain untouched strings
        assert isinstance(msg.arguments["comment"], str)
        assert msg.arguments["comment"] == "JIRA-123: planned database failover at 10:00:00Z"
        assert isinstance(msg.arguments["created_by"], str)
        assert isinstance(msg.arguments["starts_at"], str)
        # Native list/dict on structured parameter MUST remain a list
        assert isinstance(msg.arguments["matchers"], list)

    @pytest.mark.asyncio
    async def test_coerces_json_strings_and_braced_selectors_for_object_parameters(
        self, test_server_config
    ) -> None:
        mcp, _, _ = ServerBootstrap.initialize(config=test_server_config)
        mw = JsonCoercionMiddleware(mcp=mcp)

        msg = MagicMock()
        msg.name = "am_explain_routing"
        msg.arguments = {
            "backend_id": "test-am",
            "labels": '{alertname="HighLatency", env="prod", service="checkout"}',
        }
        ctx = MagicMock()
        ctx.message = msg
        ctx.fastmcp_context = None

        call_next = AsyncMock(return_value=MagicMock())
        await mw.on_call_tool(ctx, call_next)

        assert msg.arguments["labels"] == {
            "alertname": "HighLatency",
            "env": "prod",
            "service": "checkout",
        }
