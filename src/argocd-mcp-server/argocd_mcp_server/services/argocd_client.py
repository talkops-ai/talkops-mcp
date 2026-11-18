"""Shared async HTTP client for ArgoCD REST API."""

import asyncio
from typing import Any, Optional
import httpx

from argocd_mcp_server.config import ServerConfig
from argocd_mcp_server.exceptions import (
    ArgoCDConflictError,
    ArgoCDConnectionError,
    ArgoCDNotFoundError,
    ArgoCDOperationError,
    ArgoCDPermissionError,
    ArgoDBNotAvailable,
)


class ArgoCDClient:
    """Async HTTP client wrapper around httpx.AsyncClient for ArgoCD API calls."""

    def __init__(self, config: ServerConfig):
        """Initialize client with server configuration."""
        self.config = config
        self.argocd_url = config.argocd.server_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    def _build_headers(self) -> dict[str, str]:
        """Construct request headers with Bearer token if configured."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.config.argocd.auth_token:
            headers["Authorization"] = f"Bearer {self.config.argocd.auth_token}"
        return headers

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily initialize and return the underlying httpx.AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.argocd_url,
                headers=self._build_headers(),
                verify=not self.config.argocd.insecure,
                timeout=float(self.config.argocd.timeout),
            )
        return self._client

    async def aclose(self) -> None:
        """Close the underlying httpx.AsyncClient."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def check_write_access(
        self,
        operation: str,
        allow_dry_run: bool = False,
        dry_run: bool = False,
    ) -> None:
        """Verify write operations are permitted by server configuration."""
        if allow_dry_run and dry_run:
            return

        if not self.config.allow_write:
            hint = (
                " Pass dry_run=True to preview without mutating cluster state, or"
                if allow_dry_run
                else ""
            )
            raise ArgoCDOperationError(
                f"ArgoCD {operation} is blocked because the server is in read-only mode "
                f"(MCP_ALLOW_WRITE=false).{hint} set MCP_ALLOW_WRITE=true to enable mutations."
            )

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        """Extract human-readable error message from ArgoCD error response."""
        try:
            data = response.json()
            if isinstance(data, dict):
                return (
                    data.get("message")
                    or data.get("error")
                    or (data.get(" result", {}) or {}).get("message")
                    or response.text
                )
        except Exception:
            pass
        return response.text or f"HTTP {response.status_code}"

    async def request(
        self,
        method: str,
        path: str,
        *,
        is_json_response: bool = True,
        **kwargs: Any,
    ) -> Any:
        """Execute an HTTP request against the ArgoCD API with retry and typed errors."""
        client = self._get_client()
        method_upper = method.upper()
        max_attempts = max(1, (self.config.argocd.max_retries + 1) if method_upper == "GET" else 1)

        last_exc: Optional[Exception] = None
        for attempt in range(max_attempts):
            try:
                response = await client.request(method_upper, path, **kwargs)
                if response.status_code >= 500 and attempt < max_attempts - 1:
                    await asyncio.sleep(0.1 * (2**attempt))
                    continue
                response.raise_for_status()

                if not is_json_response:
                    return response.text

                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return response.json()
                # Also try parsing JSON if response text starts with { or [
                text = response.text.strip()
                if text.startswith("{") or text.startswith("["):
                    try:
                        return response.json()
                    except Exception:
                        pass
                return response.text

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                detail = self._extract_error_detail(e.response)
                url_str = f"{self.argocd_url}{path}"

                if status == 401:
                    raise ArgoCDConnectionError(
                        "Unauthorized (401): Invalid or expired ARGOCD_AUTH_TOKEN. "
                        "Verify the ARGOCD_AUTH_TOKEN environment variable."
                    ) from e
                if status == 403:
                    raise ArgoCDPermissionError(
                        f"Permission denied (403) for {method_upper} {path}: {detail}. "
                        "Verify ArgoCD RBAC permissions for the configured token."
                    ) from e
                if status == 404:
                    raise ArgoCDNotFoundError(
                        f"Resource not found (404) at {url_str}: {detail}"
                    ) from e
                if status == 409 or "already exists" in detail.lower():
                    raise ArgoCDConflictError(
                        f"Conflict (409) on {method_upper} {path}: {detail}"
                    ) from e
                if status >= 500:
                    raise ArgoDBNotAvailable(
                        f"ArgoCD server error ({status}) on {method_upper} {path}: {detail}"
                    ) from e

                raise ArgoCDOperationError(
                    f"ArgoCD API error ({status}) on {method_upper} {path}: {detail}"
                ) from e

            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
                last_exc = e
                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.1 * (2**attempt))
                    continue
                raise ArgoCDConnectionError(
                    f"Failed to connect to ArgoCD at {self.argocd_url}: {str(e)}. "
                    "Verify ARGOCD_SERVER_URL and network reachability."
                ) from e

            except httpx.HTTPError as e:
                raise ArgoCDOperationError(f"HTTP request failed: {str(e)}") from e

        raise ArgoCDConnectionError(
            f"Failed to connect to ArgoCD at {self.argocd_url}: {str(last_exc)}"
        )
