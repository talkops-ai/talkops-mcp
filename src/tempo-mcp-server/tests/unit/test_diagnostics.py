"""Unit tests for diagnostics aggregation.

Covers §6.5: combining readiness + buildinfo + services,
classifying partial failures, and constructing findings.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from tempo_mcp_server.tools.diagnostics.diagnostics_tools import DiagnosticsTools


def _make_service_locator(tempo_svc=None):
    return {
        "tempo_service": tempo_svc or MagicMock(),
        "kubernetes_service": MagicMock(),
        "config": MagicMock(),
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


# §11 #7: test_get_diagnostics_combines_status_endpoints
class TestDiagnosticsAggregation:
    """Verify diagnostics combines multiple status endpoints."""

    def setup_method(self):
        self.tempo = MagicMock()
        self.tempo.check_health = AsyncMock(return_value={"ready": True})
        self.tempo.get_build_info = AsyncMock(return_value={
            "data": {"version": "2.9.0", "revision": "abc123"},
        })
        self.tempo.get_status_services = AsyncMock(return_value={
            "ingester": "Running",
            "querier": "Running",
            "compactor": "Running",
        })
        self.tempo.check_rings = AsyncMock(return_value={})
        self.tools = _register_tools(DiagnosticsTools(_make_service_locator(self.tempo)))

    @pytest.mark.asyncio
    async def test_healthy_diagnostics(self):
        result = await self.tools["tempo_get_diagnostics"](backend_id="test", ctx=AsyncMock())
        assert result["status"] == "healthy"
        assert result["ready"] is True
        assert result["build_info"]["data"]["version"] == "2.9.0"
        assert result["issues"] == 0

    @pytest.mark.asyncio
    async def test_unhealthy_when_not_ready(self):
        self.tempo.check_health = AsyncMock(return_value={"ready": False, "error": "starting up"})
        result = await self.tools["tempo_get_diagnostics"](backend_id="test", ctx=AsyncMock())
        assert result["status"] == "unhealthy"
        assert result["ready"] is False
        assert result["issues"] >= 1
        assert any(f["severity"] == "critical" for f in result["findings"])

    @pytest.mark.asyncio
    async def test_degraded_when_component_unhealthy(self):
        self.tempo.get_status_services = AsyncMock(return_value={
            "ingester": "Running",
            "compactor": "Stopping",
        })
        result = await self.tools["tempo_get_diagnostics"](backend_id="test", ctx=AsyncMock())
        assert result["status"] == "degraded"
        assert any("compactor" in f["message"].lower() for f in result["findings"])

    @pytest.mark.asyncio
    async def test_buildinfo_failure_adds_warning(self):
        self.tempo.get_build_info = AsyncMock(side_effect=Exception("endpoint not found"))
        result = await self.tools["tempo_get_diagnostics"](backend_id="test", ctx=AsyncMock())
        assert result["build_info"] is None
        assert any(f["severity"] == "warning" and "build info" in f["message"].lower()
                    for f in result["findings"])


class TestDeploymentModeDetection:
    """B-03 (revised): Verify diagnostics skips ring checks when mode is unknown."""

    def setup_method(self):
        self.tempo = MagicMock()
        self.tempo.check_health = AsyncMock(return_value={"ready": True})
        self.tempo.get_build_info = AsyncMock(return_value={
            "data": {"version": "2.9.0"},
        })
        self.tempo.get_status_services = AsyncMock(return_value={
            "cache-provider": "Running",
            "internal-server": "Running",
            "query-frontend": "Running",
        })
        self.tempo.check_rings = AsyncMock(return_value={})
        self.tools = _register_tools(DiagnosticsTools(_make_service_locator(self.tempo)))

    @pytest.mark.asyncio
    async def test_unknown_mode_skips_ring_checks(self):
        """B-03: Unknown deployment mode skips ring probes to avoid false degraded findings."""
        backend = MagicMock()
        backend.deployment_mode = "unknown"
        self.tempo._get_backend = MagicMock(return_value=backend)

        result = await self.tools["tempo_get_diagnostics"](backend_id="test", ctx=AsyncMock())

        # Ring checks should NOT be called
        self.tempo.check_rings.assert_not_called()
        # Should remain healthy (no false degraded from 404s)
        assert result["status"] == "healthy"
        assert result["deployment_mode"] == "unknown"
        assert result["ring_checks"] is None
        # Should have an info finding advising to set TEMPO_DEPLOYMENT_MODE
        config_findings = [f for f in result["findings"] if f["category"] == "configuration"]
        assert len(config_findings) == 1
        assert "TEMPO_DEPLOYMENT_MODE" in config_findings[0]["suggested_action"]

    @pytest.mark.asyncio
    async def test_configured_microservices_runs_ring_checks(self):
        """When deployment_mode is explicitly set to microservices, ring checks run."""
        backend = MagicMock()
        backend.deployment_mode = "microservices"
        self.tempo._get_backend = MagicMock(return_value=backend)
        self.tempo.check_rings = AsyncMock(return_value={
            "distributor_ring": {"status": "ok", "total_members": 3, "active": 3},
            "ingester_ring": {"status": "ok", "total_members": 3, "active": 3},
            "compactor_ring": {"status": "ok", "total_members": 1, "active": 1},
        })

        result = await self.tools["tempo_get_diagnostics"](backend_id="test", ctx=AsyncMock())

        self.tempo.check_rings.assert_called_once_with(
            "test", deployment_mode_override="microservices",
        )
        assert result["status"] == "healthy"
        assert result["deployment_mode"] == "microservices"
        assert result["ring_checks"] is not None

    @pytest.mark.asyncio
    async def test_configured_monolithic_runs_ring_checks(self):
        """When deployment_mode is explicitly set to monolithic, ring checks run."""
        backend = MagicMock()
        backend.deployment_mode = "monolithic"
        self.tempo._get_backend = MagicMock(return_value=backend)
        self.tempo.check_rings = AsyncMock(return_value={
            "ingester_ring": {"status": "ok", "total_members": 1, "active": 1},
            "_deployment_note": "Monolithic mode: distributor/compactor rings are not exposed.",
        })

        result = await self.tools["tempo_get_diagnostics"](backend_id="test", ctx=AsyncMock())

        self.tempo.check_rings.assert_called_once_with(
            "test", deployment_mode_override="monolithic",
        )
        assert result["deployment_mode"] == "monolithic"

    @pytest.mark.asyncio
    async def test_ring_error_in_distributed_causes_degraded(self):
        """Ring failures in distributed mode should still report degraded status."""
        backend = MagicMock()
        backend.deployment_mode = "microservices"
        self.tempo._get_backend = MagicMock(return_value=backend)
        self.tempo.check_rings = AsyncMock(return_value={
            "distributor_ring": {"status": "error", "error": "no healthy members"},
            "ingester_ring": {"status": "ok", "total_members": 3, "active": 3},
            "compactor_ring": {"status": "ok", "total_members": 1, "active": 1},
        })

        result = await self.tools["tempo_get_diagnostics"](backend_id="test", ctx=AsyncMock())
        assert result["status"] == "degraded"
        assert any("distributor_ring" in f["message"] for f in result["findings"])


