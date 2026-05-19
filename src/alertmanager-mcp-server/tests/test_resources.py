from typing import Any
"""Tests for MCP resource handlers."""
import json
from unittest.mock import MagicMock

import pytest
import respx
from httpx import Response

from alertmanager_mcp_server.resources import initialize_resources
from alertmanager_mcp_server.resources.backend_resources import BackendResources
from alertmanager_mcp_server.resources.alert_resources import AlertResources
from alertmanager_mcp_server.resources.silence_resources import SilenceResources
from alertmanager_mcp_server.resources.config_resources import ConfigResources
from alertmanager_mcp_server.resources.static_resources import StaticResources
from alertmanager_mcp_server.resources.audit_resources import AuditResources
from alertmanager_mcp_server.utils.audit import add_audit_entry, clear_audit_log
from tests.conftest import (
    MOCK_ALERTS_RESPONSE, MOCK_RECEIVERS_RESPONSE,
    MOCK_SILENCES_RESPONSE, MOCK_STATUS_RESPONSE,
)


class TestResourceRegistration:
    """Test that resources register correctly."""

    def test_initialize_resources_creates_registry(self, service_locator):
        registry = initialize_resources(service_locator)
        # 7 resource handlers: backends, alerts, silences, config, static, audit, status
        assert len(registry.resources) == 7

    def test_registry_registers_all_resources(self, service_locator):
        registry = initialize_resources(service_locator)
        mcp = MagicMock()
        mcp.resource = MagicMock(return_value=lambda f: f)
        registry.register_all_resources(mcp)
        # Static registers 2 (best-practices + onboarding), others register 1 each
        assert mcp.resource.call_count >= 6


class TestBackendResources:
    """Test am://system/backends and am://system/backends/{backend_id} resources."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_backends_resource(self, service_locator):
        respx.get("http://localhost:9093/-/healthy").mock(return_value=Response(200, text="OK"))
        resource = BackendResources(service_locator)
        mcp = MagicMock()
        captured_fns: Dict[str, Any] = {}

        def capture_resource(uri, *args, **kwargs):
            def decorator(f):
                captured_fns[uri] = f
                return f
            return decorator
        mcp.resource = capture_resource
        resource.register(mcp)

        fn = captured_fns.get("am://system/backends")
        assert fn is not None
        result = await fn()
        data = json.loads(result)
        assert "backends" in data
        assert len(data["backends"]) == 1
        assert data["backends"][0]["health"] == "healthy"

    @respx.mock
    @pytest.mark.asyncio
    async def test_backend_detail_resource(self, service_locator):
        respx.get("http://localhost:9093/-/healthy").mock(return_value=Response(200, text="OK"))
        respx.get("http://localhost:9093/api/v2/status").mock(return_value=Response(200, json=MOCK_STATUS_RESPONSE))
        resource = BackendResources(service_locator)
        mcp = MagicMock()
        captured_fns: Dict[str, Any] = {}

        def capture_resource(uri, *args, **kwargs):
            def decorator(f):
                captured_fns[uri] = f
                return f
            return decorator
        mcp.resource = capture_resource
        resource.register(mcp)

        fn = captured_fns.get("am://system/backends/{backend_id}")
        assert fn is not None
        result = await fn(backend_id="test-am")
        data = json.loads(result)
        assert "backend" in data
        assert data["backend"]["id"] == "test-am"
        assert data["backend"]["version"] == "0.27.0"
        assert "cluster" in data


class TestAlertResources:
    """Test am://alerts/active resource."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_active_alerts_resource(self, service_locator):
        respx.get("http://localhost:9093/api/v2/alerts").mock(return_value=Response(200, json=MOCK_ALERTS_RESPONSE))
        resource = AlertResources(service_locator)
        mcp = MagicMock()
        captured_fns = {}

        def capture_resource(uri, *args, **kwargs):
            def decorator(f):
                captured_fns[uri] = f
                return f
            return decorator
        mcp.resource = capture_resource
        resource.register(mcp)

        alerts_fn = captured_fns.get("am://alerts/active")
        assert alerts_fn is not None
        result = await alerts_fn()
        data = json.loads(result)
        assert "alerts" in data
        assert len(data["alerts"]) == 2


class TestSilenceResources:
    """Test am://silences/active resource."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_active_silences_resource(self, service_locator):
        respx.get("http://localhost:9093/api/v2/silences").mock(return_value=Response(200, json=MOCK_SILENCES_RESPONSE))
        resource = SilenceResources(service_locator)
        mcp = MagicMock()
        resource_fn: Any = None

        def capture_resource(*args, **kwargs):
            def decorator(f):
                nonlocal resource_fn
                resource_fn = f
                return f
            return decorator
        mcp.resource = capture_resource
        resource.register(mcp)

        assert resource_fn is not None
        result = await resource_fn()
        data = json.loads(result)
        assert "silences" in data
        assert len(data["silences"]) == 1


class TestConfigResources:
    """Test am://system/config and am://system/receivers resources."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_config_resource_returns_parsed(self, service_locator):
        respx.get("http://localhost:9093/api/v2/status").mock(return_value=Response(200, json=MOCK_STATUS_RESPONSE))
        respx.get("http://localhost:9093/api/v2/receivers").mock(return_value=Response(200, json=MOCK_RECEIVERS_RESPONSE))
        resource = ConfigResources(service_locator)
        mcp = MagicMock()
        captured_fns = []

        def capture_resource(*args, **kwargs):
            def decorator(f):
                captured_fns.append(f)
                return f
            return decorator
        mcp.resource = capture_resource
        resource.register(mcp)

        # Config resource should be one of the registered functions
        for fn in captured_fns:
            result = await fn()
            data = json.loads(result)
            # Should have either routes/inhibitions or receivers
            assert isinstance(data, dict)

    @respx.mock
    @pytest.mark.asyncio
    async def test_receivers_resource(self, service_locator):
        respx.get("http://localhost:9093/api/v2/receivers").mock(return_value=Response(200, json=MOCK_RECEIVERS_RESPONSE))
        resource = ConfigResources(service_locator)
        mcp = MagicMock()
        captured_fns = {}

        def capture_resource(uri, *args, **kwargs):
            def decorator(f):
                captured_fns[uri] = f
                return f
            return decorator
        mcp.resource = capture_resource
        resource.register(mcp)

        # Get the receivers function
        recv_fn = captured_fns.get("am://system/receivers")
        if recv_fn:
            result = await recv_fn()
            data = json.loads(result)
            assert "receivers" in data


class TestAuditResources:
    """Test am://system/audit-log resource."""

    @pytest.mark.asyncio
    async def test_audit_log_empty(self, service_locator):
        clear_audit_log()
        resource = AuditResources(service_locator)
        mcp = MagicMock()
        resource_fn: Any = None

        def capture_resource(*args, **kwargs):
            def decorator(f):
                nonlocal resource_fn
                resource_fn = f
                return f
            return decorator
        mcp.resource = capture_resource
        resource.register(mcp)

        assert resource_fn is not None
        result = await resource_fn()
        data = json.loads(result)
        assert data["entries"] == []

    @pytest.mark.asyncio
    async def test_audit_log_with_entries(self, service_locator):
        clear_audit_log()
        add_audit_entry("test-am", "create_silence", "admin", "id=123")
        add_audit_entry("test-am", "expire_silence", "admin", "id=456")

        resource = AuditResources(service_locator)
        mcp = MagicMock()
        resource_fn: Any = None

        def capture_resource(*args, **kwargs):
            def decorator(f):
                nonlocal resource_fn
                resource_fn = f
                return f
            return decorator
        mcp.resource = capture_resource
        resource.register(mcp)

        assert resource_fn is not None
        result = await resource_fn()
        data = json.loads(result)
        assert len(data["entries"]) == 2
        assert data["entries"][0]["operation"] == "create_silence"
        assert data["entries"][1]["operation"] == "expire_silence"


class TestStaticResources:
    """Test static document resources."""

    def test_static_resources_register(self, service_locator):
        resource = StaticResources(service_locator)
        mcp = MagicMock()
        mcp.resource = MagicMock(return_value=lambda f: f)
        resource.register(mcp)
        # Should register at least 2 static resources (best practices, onboarding)
        assert mcp.resource.call_count >= 2
