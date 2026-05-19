"""Tests for PrometheusService."""

import pytest
import respx
from httpx import Response

from prometheus_mcp_server.services.prometheus_service import PrometheusService
from tests.conftest import (
    MOCK_INSTANT_RESPONSE,
    MOCK_LABELS_RESPONSE,
    MOCK_METADATA_RESPONSE,
    MOCK_RANGE_RESPONSE,
    MOCK_TARGETS_RESPONSE,
    MOCK_TSDB_STATUS_RESPONSE,
)


class TestPrometheusServiceBasics:
    def test_list_backends(self, prometheus_service):
        backends = prometheus_service.list_backends()
        assert len(backends) == 1
        assert backends[0].id == "test-backend"

    def test_unknown_backend_raises(self, prometheus_service):
        with pytest.raises(ValueError, match="Unknown backend_id"):
            prometheus_service._get_backend("nonexistent")


class TestPrometheusServiceQueries:
    @respx.mock
    @pytest.mark.asyncio
    async def test_instant_query(self, prometheus_service):
        respx.get("http://localhost:9090/api/v1/query").mock(return_value=Response(200, json=MOCK_INSTANT_RESPONSE))
        result = await prometheus_service.instant_query("test-backend", "up")
        assert result.resultType == "vector"
        assert len(result.result) == 1
        assert result.sample_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_range_query_with_downsampling(self, prometheus_service):
        respx.get("http://localhost:9090/api/v1/query_range").mock(return_value=Response(200, json=MOCK_RANGE_RESPONSE))
        result = await prometheus_service.range_query("test-backend", "up", 1700000000, 1700001500, "15s", max_points_per_series=50)
        assert len(result.series) == 1
        assert len(result.series[0].values) <= 50

    @respx.mock
    @pytest.mark.asyncio
    async def test_validate_query_empty(self, prometheus_service):
        result = await prometheus_service.validate_query("test-backend", "")
        assert result.valid is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_explore_label_topology(self, prometheus_service):
        respx.get("http://localhost:9090/api/v1/labels").mock(return_value=Response(200, json=MOCK_LABELS_RESPONSE))
        respx.get("http://localhost:9090/api/v1/label/job/values").mock(return_value=Response(200, json={"status": "success", "data": ["prometheus"]}))
        respx.get("http://localhost:9090/api/v1/label/instance/values").mock(return_value=Response(200, json={"status": "success", "data": ["localhost:9090"]}))
        respx.get("http://localhost:9090/api/v1/label/namespace/values").mock(return_value=Response(200, json={"status": "success", "data": ["default"]}))
        result = await prometheus_service.explore_label_topology("test-backend", "up")
        assert result.metric_name == "up"
        assert "job" in result.label_names


class TestPrometheusServiceMetadata:
    @respx.mock
    @pytest.mark.asyncio
    async def test_get_metric_catalog(self, prometheus_service):
        respx.get("http://localhost:9090/api/v1/metadata").mock(return_value=Response(200, json=MOCK_METADATA_RESPONSE))
        catalog = await prometheus_service.get_metric_catalog("test-backend")
        assert catalog.total_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_service_topology(self, prometheus_service):
        respx.get("http://localhost:9090/api/v1/targets").mock(return_value=Response(200, json=MOCK_TARGETS_RESPONSE))
        topology = await prometheus_service.get_service_topology("test-backend")
        assert len(topology.services) == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_failed_targets(self, prometheus_service):
        respx.get("http://localhost:9090/api/v1/targets").mock(return_value=Response(200, json=MOCK_TARGETS_RESPONSE))
        failed = await prometheus_service.get_failed_targets("test-backend")
        assert len(failed.failed_targets) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_cardinality(self, prometheus_service):
        respx.get("http://localhost:9090/api/v1/status/tsdb").mock(return_value=Response(200, json=MOCK_TSDB_STATUS_RESPONSE))
        summary = await prometheus_service.get_cardinality_summary("test-backend")
        assert summary.overview.total_series == 50000

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_health_healthy(self, prometheus_service):
        respx.get("http://localhost:9090/-/healthy").mock(return_value=Response(200, text="OK"))
        health = await prometheus_service.check_health("test-backend")
        assert health == "healthy"


class TestCounterRule:
    @respx.mock
    @pytest.mark.asyncio
    async def test_blocks_raw_counter(self, prometheus_service):
        respx.get("http://localhost:9090/api/v1/metadata").mock(return_value=Response(200, json=MOCK_METADATA_RESPONSE))
        with pytest.raises(ValueError, match="must be wrapped in rate"):
            await prometheus_service.enforce_counter_rule("test-backend", "http_requests_total", False)

    @respx.mock
    @pytest.mark.asyncio
    async def test_allows_rate_wrapped(self, prometheus_service):
        await prometheus_service.enforce_counter_rule("test-backend", "rate(http_requests_total[5m])", False)

    @respx.mock
    @pytest.mark.asyncio
    async def test_allows_raw_override(self, prometheus_service):
        await prometheus_service.enforce_counter_rule("test-backend", "http_requests_total", True)


class TestDownsampling:
    def test_no_downsampling_needed(self):
        values = [(i, float(i)) for i in range(10)]
        assert len(PrometheusService._downsample_series(values, 20)) == 10

    def test_downsample_to_5(self):
        values = [(float(i), float(i)) for i in range(100)]
        assert len(PrometheusService._downsample_series(values, 5)) <= 5
