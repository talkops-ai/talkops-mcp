"""Idempotency-aware async HTTP client pool for Alertmanager backends."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

from alertmanager_mcp_server.config import BackendConfig, ServerConfig
from alertmanager_mcp_server.exceptions import (
    AlertmanagerConnectionError,
    AlertmanagerNotFoundError,
    AlertmanagerOperationError,
    AlertmanagerValidationError,
)

logger = logging.getLogger(__name__)

_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "DELETE"})


class AlertmanagerHttpClient:
    """Manages per-backend `httpx.AsyncClient` instances with safe retry rules.

    Retry policy:
    - Idempotent methods (`GET`, `HEAD`, `OPTIONS`, `DELETE`) retry up to
      `max_retries` on HTTP 5xx, `ConnectError`, and `TimeoutException`.
    - Non-idempotent methods (`POST`, `PUT`, `PATCH`) retry **only** on
      `ConnectError` (before request transmission) and NEVER retry on HTTP 5xx
      or `ReadTimeout` to prevent duplicate silence or alert creation.
    """

    def __init__(
        self,
        config: ServerConfig,
        *,
        max_retries: int = 2,
        retry_backoff: float = 0.5,
    ) -> None:
        self._config = config
        self._backends: Dict[str, BackendConfig] = {
            b.id: b for b in config.backends
        }
        self._clients: Dict[str, httpx.AsyncClient] = {}
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff

    @property
    def backends(self) -> Dict[str, BackendConfig]:
        return self._backends

    def get_backend(self, backend_id: Optional[str] = None) -> BackendConfig:
        """Resolve `backend_id` or return the default backend."""
        if not backend_id:
            return self.get_default_backend()
        backend = self._backends.get(backend_id)
        if not backend:
            available = list(self._backends.keys())
            raise AlertmanagerNotFoundError(
                f"Unknown backend_id '{backend_id}'. Available backends: {available}. "
                "Read resource 'am://backends' to inspect configured Alertmanager instances."
            )
        return backend

    def get_default_backend(self) -> BackendConfig:
        """Return the configured default backend (or the first configured backend)."""
        for b in self._backends.values():
            if b.is_default:
                return b
        if self._backends:
            return next(iter(self._backends.values()))
        raise AlertmanagerValidationError("No Alertmanager backends configured.")

    def ensure_client(self, backend_id: str) -> httpx.AsyncClient:
        """Return or initialize the `httpx.AsyncClient` for `backend_id`."""
        if (
            backend_id not in self._clients
            or self._clients[backend_id].is_closed
        ):
            backend = self.get_backend(backend_id)
            basic_auth = backend.resolve_basic_auth()
            self._clients[backend_id] = httpx.AsyncClient(
                base_url=backend.api_base_url,
                verify=backend.verify_ssl,
                timeout=backend.timeout,
                auth=basic_auth,
            )
        return self._clients[backend_id]

    def build_headers(self, backend: BackendConfig) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        headers.update(backend.build_request_headers())
        return headers

    async def request(
        self,
        method: str,
        backend_id: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute an HTTP request against `backend_id` with idempotency-safe retries."""
        method_upper = method.strip().upper()
        is_idempotent = method_upper in _IDEMPOTENT_METHODS
        backend = self.get_backend(backend_id)
        client = self.ensure_client(backend.id)
        headers = self.build_headers(backend)
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = await client.request(
                    method_upper, path, headers=headers, **kwargs
                )

                # Only retry 5xx on idempotent methods
                if (
                    resp.status_code >= 500
                    and is_idempotent
                    and attempt < self._max_retries
                ):
                    logger.warning(
                        "Alertmanager %s %s returned %d, retrying (%d/%d)",
                        method_upper,
                        path,
                        resp.status_code,
                        attempt + 1,
                        self._max_retries,
                    )
                    await asyncio.sleep(self._retry_backoff * (attempt + 1))
                    continue

                if resp.status_code == 404:
                    raise AlertmanagerNotFoundError(
                        f"Alertmanager resource not found ({method_upper} {path} on "
                        f"backend '{backend.id}'): {resp.text[:300]}"
                    )
                if resp.status_code in (400, 422):
                    raise AlertmanagerValidationError(
                        f"Alertmanager rejected request ({resp.status_code} on "
                        f"{method_upper} {path}): {resp.text[:500]}"
                    )
                if resp.status_code >= 400:
                    raise AlertmanagerOperationError(
                        f"Alertmanager API error {resp.status_code} on "
                        f"{method_upper} {path} (backend '{backend.id}'): {resp.text[:500]}"
                    )
                return resp

            except httpx.ConnectError as exc:
                last_exc = exc
                if attempt >= self._max_retries:
                    raise AlertmanagerConnectionError(
                        f"Failed to connect to Alertmanager backend '{backend.id}' "
                        f"at {backend.api_base_url}: {exc}"
                    ) from exc
                logger.warning(
                    "Alertmanager %s %s failed with ConnectError, retrying (%d/%d)",
                    method_upper,
                    path,
                    attempt + 1,
                    self._max_retries,
                )
                await asyncio.sleep(self._retry_backoff * (attempt + 1))

            except httpx.TimeoutException as exc:
                last_exc = exc
                # Never retry POST/non-idempotent requests after a timeout
                if not is_idempotent or attempt >= self._max_retries:
                    raise AlertmanagerConnectionError(
                        f"Request timed out on Alertmanager backend '{backend.id}' "
                        f"({method_upper} {path}): {exc}"
                    ) from exc
                logger.warning(
                    "Alertmanager %s %s timed out, retrying (%d/%d)",
                    method_upper,
                    path,
                    attempt + 1,
                    self._max_retries,
                )
                await asyncio.sleep(self._retry_backoff * (attempt + 1))

        assert last_exc is not None
        raise AlertmanagerConnectionError(str(last_exc))

    async def close(self) -> None:
        """Close all open `httpx.AsyncClient` instances."""
        for client in self._clients.values():
            if not client.is_closed:
                await client.aclose()
        self._clients.clear()
        logger.info("All Alertmanager HTTP clients closed.")
