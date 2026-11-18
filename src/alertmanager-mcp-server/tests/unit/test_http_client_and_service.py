"""Unit tests for `AlertmanagerService` and idempotency-safe retry behavior."""

from __future__ import annotations

import httpx
import pytest
import respx

from alertmanager_mcp_server.exceptions import (
    AlertmanagerConnectionError,
    AlertmanagerOperationError,
    SilenceSafetyError,
)
from alertmanager_mcp_server.models.alert import AlertMatcher
from alertmanager_mcp_server.models.silence import PostableSilence
from alertmanager_mcp_server.services import AlertmanagerService
from tests.conftest import (
    MOCK_ALERTS_RESPONSE,
    MOCK_RECEIVERS_RESPONSE,
    MOCK_SILENCES_RESPONSE,
    MOCK_STATUS_RESPONSE,
    SAMPLE_METRICS_TEXT,
    _END_1H_AHEAD,
    _START_2H_AGO,
)


class TestIdempotencyAwareRetries:
    @respx.mock
    @pytest.mark.asyncio
    async def test_idempotent_get_retries_on_500_then_succeeds(
        self, alertmanager_service: AlertmanagerService
    ) -> None:
        alertmanager_service._retry_backoff = 0.01
        route = respx.get("http://localhost:9093/-/healthy").mock(
            side_effect=[
                httpx.Response(503, text="unavailable"),
                httpx.Response(200, text="OK"),
            ]
        )
        health = await alertmanager_service.check_health("test-am")
        assert health == "healthy"
        assert route.call_count == 2
        await alertmanager_service.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_non_idempotent_post_never_retries_on_500_or_read_timeout(
        self, alertmanager_service: AlertmanagerService
    ) -> None:
        """Regression test for P12: POST /api/v2/silences must NOT retry on 5xx or ReadTimeout."""
        alertmanager_service._retry_backoff = 0.01
        post_route_500 = respx.post("http://localhost:9093/api/v2/alerts").mock(
            return_value=httpx.Response(500, text="internal error")
        )
        with pytest.raises(AlertmanagerOperationError):
            await alertmanager_service.push_alerts(
                "test-am", [{"labels": {"alertname": "Test"}}]
            )
        assert post_route_500.call_count == 1

        post_route_timeout = respx.post("http://localhost:9093/api/v2/alerts").mock(
            side_effect=httpx.ReadTimeout("read timed out")
        )
        post_route_timeout.calls.clear()
        with pytest.raises(AlertmanagerConnectionError):
            await alertmanager_service.push_alerts(
                "test-am", [{"labels": {"alertname": "Test"}}]
            )
        assert post_route_timeout.call_count == 1
        await alertmanager_service.close()


class TestServiceOperations:
    @respx.mock
    @pytest.mark.asyncio
    async def test_single_config_fetch_in_get_default_route_alerts_and_preview_silence(
        self, alertmanager_service: AlertmanagerService
    ) -> None:
        """Regression test for P13: no N+1 /api/v2/status calls per alert."""
        status_route = respx.get("http://localhost:9093/api/v2/status").mock(
            return_value=httpx.Response(200, json=MOCK_STATUS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/alerts").mock(
            return_value=httpx.Response(200, json=MOCK_ALERTS_RESPONSE)
        )
        respx.get("http://localhost:9093/api/v2/silences").mock(
            return_value=httpx.Response(200, json=MOCK_SILENCES_RESPONSE)
        )

        default_alerts = await alertmanager_service.get_default_route_alerts("test-am")
        assert len(default_alerts) == 1
        assert default_alerts[0].fingerprint == "def456"
        # Only 1 status call regardless of how many alerts were evaluated!
        assert status_route.call_count == 1

        preview = await alertmanager_service.preview_silence(
            "test-am",
            matchers=['service="checkout"', 'alertname="HighLatency"'],
            duration_minutes=60,
            created_by="sre@example.com",
            comment="CHG-101: preview test",
        )
        assert preview["valid"] is True
        assert preview["affected_alert_count"] == 1
        assert "payments-pagerduty" in preview["affected_receivers"]
        assert status_route.call_count == 2
        await alertmanager_service.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_atomic_update_silence_posts_with_id_and_enforces_lifetime_cap(
        self, alertmanager_service: AlertmanagerService
    ) -> None:
        """Regression test for P14 & D4: update_silence uses POST with `id` (no DELETE) and enforces lifetime cap."""
        respx.get("http://localhost:9093/api/v2/silence/silence-001").mock(
            return_value=httpx.Response(200, json=MOCK_SILENCES_RESPONSE[0])
        )
        post_route = respx.post("http://localhost:9093/api/v2/silences").mock(
            return_value=httpx.Response(200, json=MOCK_SILENCES_RESPONSE[0])
        )
        delete_route = respx.delete("http://localhost:9093/api/v2/silence/silence-001").mock(
            return_value=httpx.Response(200)
        )

        updated, pol = await alertmanager_service.update_silence(
            "test-am",
            "silence-001",
            duration_minutes=120,
            new_comment="CHG-101: extended by 2h",
            updated_by="sre@example.com",
        )
        assert updated.id == "silence-001"
        assert post_route.call_count == 1
        assert delete_route.call_count == 0
        sent_json = post_route.calls.last.request.read().decode("utf-8")
        assert '"id":"silence-001"' in sent_json or '"id": "silence-001"' in sent_json

        # Attempting to extend beyond 1440m total lifetime must fail with SP007
        with pytest.raises(SilenceSafetyError, match="SP007"):
            await alertmanager_service.update_silence(
                "test-am",
                "silence-001",
                duration_minutes=2000,
                updated_by="sre@example.com",
            )
        await alertmanager_service.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_notification_health_parses_metrics_and_receivers(
        self, alertmanager_service: AlertmanagerService
    ) -> None:
        respx.get("http://localhost:9093/-/healthy").mock(
            return_value=httpx.Response(200, text="OK")
        )
        respx.get("http://localhost:9093/-/ready").mock(
            return_value=httpx.Response(200, text="OK")
        )
        respx.get("http://localhost:9093/api/v2/status").mock(
            return_value=httpx.Response(200, json=MOCK_STATUS_RESPONSE)
        )
        respx.get("http://localhost:9093/metrics").mock(
            return_value=httpx.Response(200, text=SAMPLE_METRICS_TEXT)
        )
        respx.get("http://localhost:9093/api/v2/receivers").mock(
            return_value=httpx.Response(200, json=MOCK_RECEIVERS_RESPONSE)
        )

        report = await alertmanager_service.check_notification_health("test-am")
        assert report["status"] == "degraded"
        assert report["metrics_available"] is True
        assert report["degraded_integrations"] == ["pagerduty"]
        assert report["total_failed_notifications"] == 3
        await alertmanager_service.close()
