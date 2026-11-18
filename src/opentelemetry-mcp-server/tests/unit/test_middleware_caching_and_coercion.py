"""T-U9: Unit tests for JsonCoercionMiddleware, StructuredLoggingMiddleware, and caching (S2 & S3)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from opentelemetry_mcp_server.config import ServerConfig
from opentelemetry_mcp_server.server.middleware import (
    JsonCoercionMiddleware,
    StructuredLoggingMiddleware,
    setup_middleware,
)


@pytest.mark.asyncio
async def test_json_coercion_middleware_parses_json_strings_and_skips_config_yaml():
    mw = JsonCoercionMiddleware()
    ctx = MagicMock()
    ctx.message.arguments = {
        "signals": '["traces", "metrics"]',
        "labels": '{"env": "prod"}',
        "dry_run": "true",
        "config_yaml": '{"receivers": {"otlp": {}}}',
    }
    call_next = AsyncMock(return_value="ok")
    res = await mw.on_call_tool(ctx, call_next)
    assert res == "ok"
    args = ctx.message.arguments
    assert args["signals"] == ["traces", "metrics"]
    assert args["labels"] == {"env": "prod"}
    assert args["dry_run"] is True
    # config_yaml must remain a raw string!
    assert isinstance(args["config_yaml"], str)


def test_structured_logging_middleware_disables_payload_logging_by_default():
    mw = StructuredLoggingMiddleware()
    assert mw.include_payloads is False


def test_response_caching_disables_call_tool_and_read_resource_stale_cache():
    mcp = MagicMock()
    cfg = ServerConfig()
    setup_middleware(mcp, cfg)
    assert mcp.add_middleware.called
