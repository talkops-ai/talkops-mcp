"""Unit tests for middleware caching (B6 regression) and JSON/YAML parameter coercion."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from kargo_mcp_server.config import ServerConfig
from kargo_mcp_server.server.middleware import JsonCoercionMiddleware, setup_middleware


@pytest.mark.asyncio
async def test_json_coercion_middleware_coerces_strings_and_booleans() -> None:
    mw = JsonCoercionMiddleware()
    ctx = MagicMock()
    raw_args: dict[str, Any] = {
        "dry_run": "false",
        "subscriptions": '[{"image": {"repoURL": "ghcr.io/org/app", "constraint": "^1.0.0"}}]',
        "options": "{secret_ref: GITHUB_CREDS, replicate_to_all_projects: true}",
        "stage": "dev",
    }
    ctx.message.arguments = raw_args
    call_next = AsyncMock(return_value="ok")

    res = await mw.on_call_tool(ctx, call_next)
    assert res == "ok"
    args: dict[str, Any] = ctx.message.arguments
    assert args["dry_run"] is False
    assert isinstance(args["subscriptions"], list)
    assert args["subscriptions"][0]["image"]["repoURL"] == "ghcr.io/org/app"
    assert isinstance(args["options"], dict)
    assert args["options"]["secret_ref"] == "GITHUB_CREDS"
    assert args["stage"] == "dev"


def test_middleware_disables_tool_and_resource_caching_and_tracebacks() -> None:
    """Regression test for B6: tool calls and live resources must never serve cached responses."""
    mcp = MagicMock()
    cfg = ServerConfig()
    setup_middleware(mcp, cfg)

    added = [call.args[0] for call in mcp.add_middleware.call_args_list]
    cls_names = [type(m).__name__ for m in added]
    assert "JsonCoercionMiddleware" in cls_names
    assert "ErrorHandlingMiddleware" in cls_names
    assert "ResponseCachingMiddleware" in cls_names

    error_mw = next(m for m in added if type(m).__name__ == "ErrorHandlingMiddleware")
    assert getattr(error_mw, "include_traceback", False) is False
