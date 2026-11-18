"""Unit tests for middleware caching policy (B1 fix), traceback suppression (B14 fix), and JSON coercion (T-U8)."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from argo_rollout_mcp_server.config import ServerConfig
from argo_rollout_mcp_server.server.core import create_mcp_server
from argo_rollout_mcp_server.server.middleware import JsonCoercionMiddleware


def test_middleware_disables_live_tool_and_resource_caching():
    mcp = create_mcp_server(ServerConfig())
    middlewares = getattr(mcp, "middleware", [])
    assert len(middlewares) >= 4

    # Verify ErrorHandlingMiddleware has include_traceback=False
    err_mw = next(m for m in middlewares if "ErrorHandling" in type(m).__name__)
    assert getattr(err_mw, "include_traceback", False) is False

    # Verify ResponseCachingMiddleware disables call_tool, read_resource, and get_prompt caching
    cache_mw = next(m for m in middlewares if "ResponseCaching" in type(m).__name__)
    call_tool_cfg = getattr(cache_mw, "_call_tool_settings", None) or getattr(cache_mw, "call_tool_settings", {})
    read_res_cfg = getattr(cache_mw, "_read_resource_settings", None) or getattr(cache_mw, "read_resource_settings", {})
    get_prompt_cfg = getattr(cache_mw, "_get_prompt_settings", None) or getattr(cache_mw, "get_prompt_settings", {})
    assert call_tool_cfg.get("enabled") is False
    assert read_res_cfg.get("enabled") is False
    assert get_prompt_cfg.get("enabled") is False


@pytest.mark.asyncio
async def test_json_coercion_middleware_coerces_json_yaml_and_bools():
    mw = JsonCoercionMiddleware()
    msg = MagicMock()
    msg.arguments = {
        "strategy_options": '{"steps": [{"setWeight": 10}]}',
        "templates": '[{"name": "base", "replicas": 1}]',
        "dry_run": "false",
        "confirm": "true",
        "name": "payments-api",
    }
    ctx = MagicMock()
    ctx.message = msg
    call_next = AsyncMock(return_value="ok")

    res = await mw.on_call_tool(ctx, call_next)
    assert res == "ok"
    assert isinstance(msg.arguments["strategy_options"], dict)
    assert msg.arguments["strategy_options"]["steps"][0]["setWeight"] == 10
    assert isinstance(msg.arguments["templates"], list)
    assert msg.arguments["dry_run"] is False
    assert msg.arguments["confirm"] is True
    assert msg.arguments["name"] == "payments-api"
