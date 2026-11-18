"""Unit tests for ArgoCDClient async HTTP error mapping and retry behavior."""

import httpx
import pytest
import respx

from argocd_mcp_server.config import ServerConfig
from argocd_mcp_server.exceptions import (
    ArgoCDConflictError,
    ArgoCDConnectionError,
    ArgoCDNotFoundError,
    ArgoCDOperationError,
    ArgoCDPermissionError,
    ArgoDBNotAvailable,
)
from argocd_mcp_server.services.argocd_client import ArgoCDClient
from tests.conftest import BASE_URL


@pytest.mark.asyncio
async def test_client_headers_include_bearer_token(argocd_client: ArgoCDClient) -> None:
    """Client sets Authorization Bearer header when auth_token is configured."""
    headers = argocd_client._build_headers()
    assert headers["Authorization"] == "Bearer test-jwt-token-12345"
    assert headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "response_body", "expected_exc", "expected_substr"),
    [
        (401, {"message": "invalid session"}, ArgoCDConnectionError, "ARGOCD_AUTH_TOKEN"),
        (403, {"message": "permission denied"}, ArgoCDPermissionError, "RBAC permissions"),
        (404, {"message": "not found"}, ArgoCDNotFoundError, "not found (404)"),
        (409, {"message": "already exists"}, ArgoCDConflictError, "Conflict (409)"),
        (500, {"message": "internal error"}, ArgoDBNotAvailable, "server error (500)"),
        (422, {"message": "invalid spec"}, ArgoCDOperationError, "API error (422)"),
    ],
)
async def test_client_http_error_mapping(
    respx_mock: respx.MockRouter,
    write_config: ServerConfig,
    status_code: int,
    response_body: dict,
    expected_exc: type[Exception],
    expected_substr: str,
) -> None:
    """HTTP error codes map to model-directed custom exceptions."""
    write_config.argocd.max_retries = 0
    client = ArgoCDClient(write_config)
    respx_mock.get(f"{BASE_URL}/api/v1/applications/test").mock(
        return_value=httpx.Response(status_code, json=response_body)
    )

    with pytest.raises(expected_exc) as exc_info:
        await client.request("GET", "/api/v1/applications/test")

    assert expected_substr in str(exc_info.value)
    await client.aclose()


@pytest.mark.asyncio
async def test_client_retries_transient_500_on_get(
    respx_mock: respx.MockRouter,
    write_config: ServerConfig,
) -> None:
    """GET requests retry on transient HTTP 500 and succeed if subsequent attempt returns 200."""
    write_config.argocd.max_retries = 1
    client = ArgoCDClient(write_config)
    route = respx_mock.get(f"{BASE_URL}/api/version").mock(
        side_effect=[
            httpx.Response(502, json={"message": "bad gateway"}),
            httpx.Response(200, json={"Version": "v2.13.1"}),
        ]
    )

    result = await client.request("GET", "/api/version")
    assert result["Version"] == "v2.13.1"
    assert route.call_count == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_client_network_error_raises_connection_error(
    respx_mock: respx.MockRouter,
    write_config: ServerConfig,
) -> None:
    """ConnectError maps to ArgoCDConnectionError with server URL guidance."""
    write_config.argocd.max_retries = 0
    client = ArgoCDClient(write_config)
    respx_mock.get(f"{BASE_URL}/api/version").mock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    with pytest.raises(ArgoCDConnectionError, match="Verify ARGOCD_SERVER_URL"):
        await client.request("GET", "/api/version")
    await client.aclose()
