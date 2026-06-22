"""Unit tests for LokiService — health check and retry logic.

Tests cover the two QA-reported bugs:
  1. health_check() false-negative when /ready returns non-200
  2. get_patterns() 404 when Pattern Ingester is disabled

Also covers the DRY-refactored _request_with_retry shared method.
"""

import httpx
import pytest
import respx

from loki_mcp_server.config import AuthConfig, LokiConfig
from loki_mcp_server.exceptions import (
    LokiConnectionError,
    LokiQueryError,
    LokiResourceNotFoundError,
)
from loki_mcp_server.services.loki_service import LokiService

LOKI_BASE = "http://test-loki:3100"


@pytest.fixture
def loki_config() -> LokiConfig:
    """Standard LokiConfig pointing at test URL."""
    return LokiConfig(base_url=LOKI_BASE, timeout=5, verify_ssl=False)


@pytest.fixture
def auth_config() -> AuthConfig:
    """No-auth config for testing."""
    return AuthConfig()


@pytest.fixture
def service(loki_config, auth_config) -> LokiService:
    """Create a fresh LokiService per test."""
    return LokiService(loki_config, auth_config)


# ──────────────────────────────────────────────
# Health Check Tests (Bug 1)
# ──────────────────────────────────────────────


class TestHealthCheck:
    """Tests for LokiService.health_check().

    Validates that /ready is the canonical health signal:
    - 200 → healthy
    - non-200 → degraded
    - unreachable → unhealthy
    """

    @respx.mock
    @pytest.mark.asyncio
    async def test_all_ok(self, service):
        """Both /ready=200 and labels succeed → healthy."""
        respx.get(f"{LOKI_BASE}/ready").mock(
            return_value=httpx.Response(200, text="ready")
        )
        respx.get(f"{LOKI_BASE}/loki/api/v1/labels").mock(
            return_value=httpx.Response(
                200,
                json={"status": "success", "data": ["app", "namespace"]},
            )
        )

        result = await service.health_check()

        assert result["status"] == "healthy"
        assert result["reachable"] is True
        assert result["ready"] is True
        assert result["label_count"] == 2
        assert "200" in result["ready_detail"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_ready_503_labels_ok(self, service):
        """/ready returns 503 but labels work → degraded, not healthy."""
        respx.get(f"{LOKI_BASE}/ready").mock(
            return_value=httpx.Response(
                503, text="Ingester not ready: waiting for ring"
            )
        )
        respx.get(f"{LOKI_BASE}/loki/api/v1/labels").mock(
            return_value=httpx.Response(
                200,
                json={"status": "success", "data": ["app", "namespace"]},
            )
        )

        result = await service.health_check()

        assert result["status"] == "degraded"
        assert result["reachable"] is True
        assert result["ready"] is False
        assert result["label_count"] == 2
        assert "503" in result["ready_detail"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_unreachable(self, service):
        """Connection refused → unhealthy + reachable=False."""
        respx.get(f"{LOKI_BASE}/ready").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await service.health_check()

        assert result["status"] == "unhealthy"
        assert result["reachable"] is False
        assert result["ready"] is False
        assert result["label_count"] == 0
        assert "Connection failed" in result["ready_detail"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_ready_ok_labels_fail(self, service):
        """/ready=200 but labels fail → still healthy (labels are enrichment)."""
        respx.get(f"{LOKI_BASE}/ready").mock(
            return_value=httpx.Response(200, text="ready")
        )
        respx.get(f"{LOKI_BASE}/loki/api/v1/labels").mock(
            return_value=httpx.Response(500, text="internal error")
        )

        result = await service.health_check()

        assert result["status"] == "healthy"
        assert result["reachable"] is True
        assert result["ready"] is True
        assert result["label_count"] == 0

    @respx.mock
    @pytest.mark.asyncio
    async def test_timeout(self, service):
        """Request timeout → unhealthy."""
        respx.get(f"{LOKI_BASE}/ready").mock(
            side_effect=httpx.ReadTimeout("Timed out")
        )

        result = await service.health_check()

        assert result["status"] == "unhealthy"
        assert result["reachable"] is False
        assert "Connection failed" in result["ready_detail"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_ready_detail_truncated(self, service):
        """Very long /ready body is truncated in ready_detail."""
        long_body = "x" * 500
        respx.get(f"{LOKI_BASE}/ready").mock(
            return_value=httpx.Response(200, text=long_body)
        )
        respx.get(f"{LOKI_BASE}/loki/api/v1/labels").mock(
            return_value=httpx.Response(
                200, json={"status": "success", "data": []}
            )
        )

        result = await service.health_check()

        # Body should be truncated to 100 chars
        assert len(result["ready_detail"]) <= 110  # "HTTP 200: " + 100 chars


# ──────────────────────────────────────────────
# Patterns 404 Tests (Bug 2)
# ──────────────────────────────────────────────


class TestGetPatterns:
    """Tests for LokiService.get_patterns() — 404 handling."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_patterns_404_raises(self, service):
        """Patterns endpoint returning 404 raises LokiResourceNotFoundError."""
        respx.get(f"{LOKI_BASE}/loki/api/v1/patterns").mock(
            return_value=httpx.Response(404, text="Not Found")
        )

        with pytest.raises(LokiResourceNotFoundError):
            await service.get_patterns(
                query='{app="checkout"}', start="1h", end="now"
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_patterns_success(self, service):
        """Patterns endpoint returns valid data when enabled."""
        respx.get(f"{LOKI_BASE}/loki/api/v1/patterns").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": [
                        {
                            "pattern": "<_> level=info <_>",
                            "samples": [["1700000000", "42"]],
                        }
                    ],
                },
            )
        )

        result = await service.get_patterns(
            query='{app="checkout"}', start="1h", end="now"
        )

        assert len(result) == 1
        assert result[0]["pattern"] == "<_> level=info <_>"


# ──────────────────────────────────────────────
# Retry Logic Tests (DRY refactor)
# ──────────────────────────────────────────────


class TestRequestWithRetry:
    """Tests for the shared _request_with_retry method."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_retry_on_503(self, service):
        """503 triggers retry, succeeds on second attempt."""
        route = respx.get(f"{LOKI_BASE}/loki/api/v1/labels")
        route.side_effect = [
            httpx.Response(503, text="Service Unavailable"),
            httpx.Response(
                200,
                json={"status": "success", "data": ["app"]},
            ),
        ]

        # Should succeed after retry
        labels = await service.get_labels()
        assert labels == ["app"]
        assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_400_no_retry(self, service):
        """400 Bad Request does not retry — raises immediately."""
        respx.get(f"{LOKI_BASE}/loki/api/v1/labels").mock(
            return_value=httpx.Response(400, text="bad query syntax")
        )

        with pytest.raises(LokiQueryError, match="bad request"):
            await service.get_labels()

    @respx.mock
    @pytest.mark.asyncio
    async def test_404_raises_not_found(self, service):
        """404 raises LokiResourceNotFoundError without retrying."""
        route = respx.get(f"{LOKI_BASE}/loki/api/v1/labels")
        route.mock(return_value=httpx.Response(404, text="Not Found"))

        with pytest.raises(LokiResourceNotFoundError):
            await service.get_labels()

        # 404 should NOT retry
        assert route.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_connection_error_retries_then_fails(self, service):
        """Connection errors retry MAX_RETRIES times then raise."""
        route = respx.get(f"{LOKI_BASE}/loki/api/v1/labels")
        route.mock(side_effect=httpx.ConnectError("refused"))

        with pytest.raises(LokiConnectionError, match="Cannot connect"):
            await service.get_labels()

        # 1 initial + 3 retries = 4 total
        assert route.call_count == 4
