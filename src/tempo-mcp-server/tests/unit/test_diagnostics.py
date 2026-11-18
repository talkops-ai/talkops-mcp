"""Unit tests for facts-only diagnostics aggregation.

Covers combining readiness + buildinfo + services + rings + /metrics
and emitting structured observation codes without severity or remediation prose.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from tempo_mcp_server.config import ServerConfig
from tempo_mcp_server.models.diagnostics import ALL_OBSERVATION_CODES
from tempo_mcp_server.tools.diagnostics.diagnostics_tools import DiagnosticsTools


def _make_service_locator(tempo_svc=None, k8s_svc=None):
    return {
        "tempo_service": tempo_svc or MagicMock(),
        "kubernetes_service": k8s_svc or MagicMock(is_available=False),
        "config": ServerConfig(),
    }


def _register_tools(tool_instance):
    mcp = MagicMock()
    captured = {}

    def capture_tool(**kwargs):
        def decorator(fn):
            captured[fn.__name__] = fn
            return fn

        return decorator

    mcp.tool = capture_tool
    tool_instance.register(mcp)
    return captured


class TestDiagnosticsAggregation:
    """Verify diagnostics combines status endpoints into facts-only observations."""

    def setup_method(self):
        self.tempo = MagicMock()
        backend = MagicMock()
        backend.deployment_mode = "microservices"
        backend.multi_tenant = False
        backend.default_tenant = None
        self.tempo._get_backend = MagicMock(return_value=backend)
        self.tempo.check_health = AsyncMock(return_value={"ready": True})
        self.tempo.get_build_info = AsyncMock(
            return_value={"version": "2.9.0", "revision": "abc123"}
        )
        self.tempo.detect_tempo_generation = MagicMock(return_value=(2, "2.x"))
        self.tempo.get_status_services = AsyncMock(
            return_value={
                "ingester": "Running",
                "querier": "Running",
                "compactor": "Running",
            }
        )
        self.tempo.check_rings = AsyncMock(
            return_value={
                "distributor_ring": {"status": "ok", "total_members": 2, "active": 2},
                "ingester_ring": {"status": "ok", "total_members": 3, "active": 3},
            }
        )
        self.tempo.get_safe_status_config = AsyncMock(
            return_value={
                "metrics_generator_processors": ["service-graphs", "span-metrics", "local-blocks"],
                "user_configurable_overrides_enabled": True,
            }
        )
        self.tempo.get_prometheus_metrics_facts = AsyncMock(
            return_value={
                "discarded_spans_by_reason": {},
                "total_discarded_spans": 0,
                "max_partition_lag_seconds": None,
            }
        )
        self.tools = _register_tools(DiagnosticsTools(_make_service_locator(self.tempo)))

    @pytest.mark.asyncio
    async def test_healthy_diagnostics(self):
        result = await self.tools["tempo_get_diagnostics"](backend_id="test", ctx=AsyncMock())
        assert result["ready"] is True
        assert result["tempo_major_version"] == 2
        assert result["build_info"]["version"] == "2.9.0"
        assert result["findings"] == []
        assert result["observation_codes"] == []

    @pytest.mark.asyncio
    async def test_unhealthy_when_not_ready(self):
        self.tempo.check_health = AsyncMock(
            return_value={"ready": False, "error": "starting up"}
        )
        result = await self.tools["tempo_get_diagnostics"](backend_id="test", ctx=AsyncMock())
        assert result["ready"] is False
        assert "BACKEND_UNREACHABLE" in result["observation_codes"]
        for obs in result["findings"]:
            assert obs["code"] in ALL_OBSERVATION_CODES
            assert "severity" not in obs
            assert "suggested_action" not in obs

    @pytest.mark.asyncio
    async def test_component_not_running_observation(self):
        self.tempo.get_status_services = AsyncMock(
            return_value={
                "ingester": "Running",
                "compactor": "Stopping",
            }
        )
        result = await self.tools["tempo_get_diagnostics"](backend_id="test", ctx=AsyncMock())
        assert "COMPONENT_NOT_RUNNING" in result["observation_codes"]
        comp_obs = [o for o in result["findings"] if o["code"] == "COMPONENT_NOT_RUNNING"][0]
        assert comp_obs["component"] == "compactor"

    @pytest.mark.asyncio
    async def test_buildinfo_failure_emits_observation_code(self):
        self.tempo.get_build_info = AsyncMock(side_effect=Exception("endpoint not found"))
        result = await self.tools["tempo_get_diagnostics"](backend_id="test", ctx=AsyncMock())
        assert result["build_info"] is None
        assert "BUILD_INFO_UNAVAILABLE" in result["observation_codes"]


class TestDeploymentModeAndRings:
    """Verify ring checks and deployment mode observation codes."""

    def setup_method(self):
        self.tempo = MagicMock()
        self.tempo.check_health = AsyncMock(return_value={"ready": True})
        self.tempo.get_build_info = AsyncMock(return_value={"version": "2.9.0"})
        self.tempo.detect_tempo_generation = MagicMock(return_value=(2, "2.x"))
        self.tempo.get_status_services = AsyncMock(
            return_value={
                "cache-provider": "Running",
                "internal-server": "Running",
                "query-frontend": "Running",
            }
        )
        self.tempo.check_rings = AsyncMock(return_value={})
        self.tempo.get_safe_status_config = AsyncMock(
            return_value={
                "metrics_generator_processors": ["service-graphs", "span-metrics", "local-blocks"],
                "user_configurable_overrides_enabled": True,
            }
        )
        self.tempo.get_prometheus_metrics_facts = AsyncMock(
            return_value={
                "discarded_spans_by_reason": {},
                "total_discarded_spans": 0,
                "max_partition_lag_seconds": None,
            }
        )
        self.tools = _register_tools(DiagnosticsTools(_make_service_locator(self.tempo)))

    @pytest.mark.asyncio
    async def test_unknown_mode_skips_ring_checks(self):
        backend = MagicMock()
        backend.deployment_mode = "unknown"
        backend.multi_tenant = False
        backend.default_tenant = None
        self.tempo._get_backend = MagicMock(return_value=backend)

        result = await self.tools["tempo_get_diagnostics"](backend_id="test", ctx=AsyncMock())

        self.tempo.check_rings.assert_not_called()
        assert result["deployment_mode"] == "unknown"
        assert result["ring_checks"] is None
        assert "DEPLOYMENT_MODE_UNKNOWN" in result["observation_codes"]

    @pytest.mark.asyncio
    async def test_configured_microservices_runs_ring_checks(self):
        backend = MagicMock()
        backend.deployment_mode = "microservices"
        backend.multi_tenant = False
        backend.default_tenant = None
        self.tempo._get_backend = MagicMock(return_value=backend)
        self.tempo.check_rings = AsyncMock(
            return_value={
                "distributor_ring": {"status": "ok", "total_members": 3, "active": 3},
                "ingester_ring": {"status": "ok", "total_members": 3, "active": 3},
                "compactor_ring": {"status": "ok", "total_members": 1, "active": 1},
            }
        )

        result = await self.tools["tempo_get_diagnostics"](backend_id="test", ctx=AsyncMock())

        self.tempo.check_rings.assert_called_once_with(
            "test",
            deployment_mode_override="microservices",
            architecture_generation="2.x",
        )
        assert result["deployment_mode"] == "microservices"
        assert result["ring_checks"] is not None

    @pytest.mark.asyncio
    async def test_ring_error_emits_ring_check_failed(self):
        backend = MagicMock()
        backend.deployment_mode = "microservices"
        backend.multi_tenant = False
        backend.default_tenant = None
        self.tempo._get_backend = MagicMock(return_value=backend)
        self.tempo.check_rings = AsyncMock(
            return_value={
                "distributor_ring": {"status": "error", "error": "no healthy members"},
                "ingester_ring": {"status": "ok", "total_members": 3, "active": 2, "leaving": 1},
            }
        )

        result = await self.tools["tempo_get_diagnostics"](backend_id="test", ctx=AsyncMock())
        assert "RING_CHECK_FAILED" in result["observation_codes"]
        assert "RING_MEMBER_UNHEALTHY" in result["observation_codes"]
