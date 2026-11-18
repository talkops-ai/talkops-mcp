"""Unit tests for JsonCoercionMiddleware."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from helm_mcp_server.server.middleware import JsonCoercionMiddleware


@pytest.mark.asyncio
async def test_json_coercion_middleware_parses_json_and_yaml_dicts() -> None:
    """Stringified JSON and multi-line YAML dicts/lists should be coerced while plain strings remain untouched."""
    middleware = JsonCoercionMiddleware()

    args = {
        "values": '{"replicaCount": 3, "auth": {"enabled": true}}',
        "required_api_resources": '["Deployment", "Service"]',
        "yaml_values": "image:\n  tag: '16.4.0'\n",
        "release_name": "my-postgres",
        "version": "16.4.0",
    }
    ctx = SimpleNamespace(
        message=SimpleNamespace(name="helm_install_chart", arguments=args)
    )
    call_next = AsyncMock(return_value="ok")

    await middleware.on_call_tool(ctx, call_next)  # type: ignore[arg-type]

    assert args["values"] == {"replicaCount": 3, "auth": {"enabled": True}}
    assert args["required_api_resources"] == ["Deployment", "Service"]
    assert args["yaml_values"] == {"image": {"tag": "16.4.0"}}
    assert args["release_name"] == "my-postgres"
    assert args["version"] == "16.4.0"
    call_next.assert_awaited_once_with(ctx)
