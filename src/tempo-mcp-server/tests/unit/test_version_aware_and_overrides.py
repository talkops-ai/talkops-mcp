"""Unit tests for Tempo 2.x vs 3.x version detection, ring checks, and /api/overrides ETag handling."""

import httpx
import pytest
import respx

from tempo_mcp_server.config import BackendConfig, KubernetesConfig, QueryPolicyConfig, ServerConfig
from tempo_mcp_server.exceptions.custom import TempoOperationError
from tempo_mcp_server.services.tempo_service import TempoService
from tempo_mcp_server.utils.traceql_helpers import apply_query_hints, compute_next_window


@pytest.fixture
def svc() -> TempoService:
    cfg = ServerConfig(
        backends=[
            BackendConfig(
                id="default",
                base_url="http://tempo-test:3200",
                deployment_mode="microservices",
            )
        ],
        query_policy=QueryPolicyConfig(),
        kubernetes=KubernetesConfig(enabled=False),
    )
    return TempoService(cfg)


class TestVersionDetectionAndRings:
    """Verify Tempo 2.x vs 3.x detection and ring probing."""

    def test_detects_tempo_3_and_recognizes_ingest_and_block_builder(self):
        major, gen = TempoService.detect_tempo_generation(
            build_info={"version": "3.0.1", "revision": "r3"},
            services={"distributor": "Running", "ingest": "Running", "block-builder": "Running"},
            config_facts={"block_version": "vParquet4"},
        )
        assert major == 3
        assert gen == "3.x"

    def test_detects_v_prefixed_tempo_2_version(self):
        major, gen = TempoService.detect_tempo_generation(
            build_info={"version": "v2.7.1", "revision": "35cf98066"},
        )
        assert major == 2
        assert gen == "2.x"

    @pytest.mark.asyncio
    async def test_parses_ascii_table_status_services(self, svc):
        table = (
            "GET /status/services\n"
            "+-------------------+----------+--------------+\n"
            "| SERVICE NAME      |   STATUS | FAILURE CASE |\n"
            "+-------------------+----------+--------------+\n"
            "| distributor       |  Running |              |\n"
            "| ingester          |  Running |              |\n"
            "| usage-report      | Disabled |              |\n"
            "+-------------------+----------+--------------+\n"
        )
        with respx.mock(assert_all_called=False) as mock:
            mock.get("http://tempo-test:3200/status/services").mock(
                return_value=httpx.Response(200, text=table)
            )
            parsed = await svc.get_status_services("default")
            assert parsed == {
                "distributor": "Running",
                "ingester": "Running",
                "usage-report": "Disabled",
            }

    @pytest.mark.asyncio
    async def test_get_and_patch_tenant_overrides_with_etag(self, svc):
        with respx.mock(assert_all_called=False) as mock:
            mock.get("http://tempo-test:3200/api/overrides").mock(
                return_value=httpx.Response(
                    200,
                    json={"ingestion_rate_limit_bytes": 15000000},
                    headers={"ETag": '"etag-1"'},
                )
            )
            mock.patch("http://tempo-test:3200/api/overrides").mock(
                return_value=httpx.Response(
                    200,
                    json={"ingestion_rate_limit_bytes": 30000000},
                    headers={"ETag": '"etag-2"'},
                )
            )

            current = await svc.get_tenant_overrides("default", tenant="team-a")
            assert current["etag"] == '"etag-1"'
            assert current["overrides"]["ingestion_rate_limit_bytes"] == 15000000

            updated = await svc.patch_tenant_overrides(
                "default",
                tenant="team-a",
                merge_patch={"ingestion_rate_limit_bytes": 30000000},
                expected_etag='"etag-1"',
            )
            assert updated["etag"] == '"etag-2"'

    @pytest.mark.asyncio
    async def test_patch_tenant_overrides_412_raises_etag_conflict(self, svc):
        with respx.mock(assert_all_called=False) as mock:
            mock.patch("http://tempo-test:3200/api/overrides").mock(
                return_value=httpx.Response(412, text="Precondition Failed")
            )
            with pytest.raises(TempoOperationError) as exc_info:
                await svc.patch_tenant_overrides(
                    "default",
                    tenant="team-a",
                    merge_patch={"max_bytes_per_trace": 9000000},
                    expected_etag='"stale-etag"',
                )
            assert "412" in str(exc_info.value)


class TestQueryHintsAndPagination:
    """Verify with(most_recent=true) hint and deterministic next_window pagination."""

    def test_apply_query_hints_appends_most_recent(self):
        q = '{ resource.service.name = "checkout" && status = error }'
        hinted = apply_query_hints(q, most_recent=True)
        assert hinted.endswith("with(most_recent=true)")
        assert apply_query_hints(hinted, most_recent=True) == hinted

    def test_compute_next_window_when_limit_saturated(self):
        traces = [
            {"trace_id": "t1", "start_time": "1700000010000000000"},
            {"trace_id": "t2", "start_time": "1700000005000000000"},
        ]
        nw = compute_next_window(
            traces,
            resolved_start=1700000000.0,
            resolved_end=1700000020.0,
        )
        assert nw is not None
        assert nw["start"] == 1700000000.0
        assert nw["end"] < 1700000005.0

        assert compute_next_window([], resolved_start=1700000000.0, resolved_end=1700000020.0) is None
