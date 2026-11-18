"""Shared test fixtures for the OpenTelemetry MCP server test suite.

Provides mock service locators, sample K8s API responses, and
collector configurations for deterministic testing without K8s access.
"""

import json
import os
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import FastMCP

from opentelemetry_mcp_server.config import (
    KubernetesConfig,
    ServerConfig,
)
from opentelemetry_mcp_server.services.collector_config_service import (
    CollectorConfigService,
)
from opentelemetry_mcp_server.services.kubernetes_service import KubernetesService

# ──────────────────────────────────────────────
# Fixture Loading Helpers
# ──────────────────────────────────────────────


def _load_fixture(name: str) -> Any:
    """Load a JSON fixture from the tests/fixtures/otel directory."""
    fixture_path = os.path.join(
        os.path.dirname(__file__), "fixtures", "otel", f"{name}.json"
    )
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ──────────────────────────────────────────────
# Test Assert Helpers
# ──────────────────────────────────────────────


def get_text(result: Any) -> str:
    """Helper to extract text from a CallToolResult."""
    if hasattr(result, "content") and result.content:
        return result.content[0].text
    if isinstance(result, list) and len(result) > 0 and hasattr(result[0], "text"):
        return result[0].text
    return str(result)


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def server_config() -> ServerConfig:
    """Provide a test ServerConfig with write enabled for full tool surface tests."""
    return ServerConfig(
        name="test-otel-mcp-server",
        version="0.0.1-test",
        allow_write=True,
        read_only=False,
        toolsets=["all"],
        kubernetes=KubernetesConfig(enabled=False),
    )


@pytest.fixture
def collector_config_service() -> CollectorConfigService:
    """Provide a real CollectorConfigService (stateless, no mocks needed)."""
    return CollectorConfigService()


@pytest.fixture
def sample_collector_cr() -> Dict[str, Any]:
    """Provide a sample collector CRD dict."""
    return _load_fixture("collector_cr")


@pytest.fixture
def sample_instrumentation_cr() -> Dict[str, Any]:
    """Provide a sample instrumentation CRD dict."""
    return _load_fixture("instrumentation_cr")


@pytest.fixture
def mock_kubernetes_service() -> KubernetesService:
    """Provide a mocked KubernetesService."""
    service = MagicMock(spec=KubernetesService)
    service.is_available = True

    deployments = _load_fixture("deployments_response")
    # Default mock responses
    service.list_otel_collectors = AsyncMock(
        return_value={"items": [_load_fixture("collector_cr")]}
    )
    service.get_otel_collector = AsyncMock(
        return_value=_load_fixture("collector_cr")
    )
    service.list_instrumentations = AsyncMock(
        return_value={"items": [_load_fixture("instrumentation_cr")]}
    )
    service.get_instrumentation = AsyncMock(
        return_value=_load_fixture("instrumentation_cr")
    )
    service.list_deployments = AsyncMock(return_value=deployments)
    service.list_workloads = AsyncMock(return_value=deployments)
    service.get_workload = AsyncMock(
        return_value=deployments[0] if deployments else {"name": "checkout", "namespace": "otel-demo", "kind": "Deployment", "annotations": {}, "labels": {}, "containers": []}
    )
    service.get_deployment = AsyncMock(
        return_value=deployments[0] if deployments else {"name": "checkout", "namespace": "otel-demo", "annotations": {}, "labels": {}, "containers": []}
    )
    service.patch_workload_annotations = AsyncMock(
        return_value=deployments[0] if deployments else {"name": "checkout", "namespace": "otel-demo"}
    )
    service.restart_workload = AsyncMock(
        return_value=deployments[0] if deployments else {"name": "checkout", "namespace": "otel-demo"}
    )
    service.strip_otel_env_vars = AsyncMock(
        return_value={"action": "no_change", "removed": {}, "would_remove": {}}
    )
    service.list_pods = AsyncMock(return_value=_load_fixture("pods_ebpf_response"))
    service.health_check = AsyncMock(return_value=_load_fixture("k8s_health_response"))
    service.list_available_contexts = AsyncMock(
        return_value=[{"name": "test-context", "cluster": "test-cluster", "user": "admin", "namespace": "default", "is_current": True}]
    )
    service.get_operator_diagnostics = AsyncMock(
        return_value={
            "operator_found": True,
            "operator_pod": "opentelemetry-operator-controller-manager-xyz",
            "operator_namespace": "opentelemetry-operator-system",
            "operator_status": "Running",
            "recent_errors": [],
            "instrumentation_cr_counts": {"otel-demo": 1},
            "warnings": [],
        }
    )
    service.list_target_allocators = AsyncMock(return_value={"items": []})
    service.list_opamp_bridges = AsyncMock(return_value={"items": []})
    service.list_services = AsyncMock(return_value=[])
    service.list_namespaces = AsyncMock(return_value=["default", "observability"])
    service.get_node_count = AsyncMock(return_value=3)
    service.count_nodes = AsyncMock(return_value=3)
    service.list_namespace_events = AsyncMock(return_value=[])
    service.get_collector_pod_logs = AsyncMock(
        return_value={
            "pod_name": "otel-collector-0",
            "lines": [],
            "error_lines": [],
            "auth_errors": [],
            "tls_errors": [],
            "dns_errors": [],
        }
    )
    service.check_cluster_role_binding_exists = AsyncMock(return_value=True)
    service.list_otel_cluster_roles = AsyncMock(return_value=[])
    service.check_secret_key_exists = AsyncMock(return_value={"exists": True, "has_key": True})
    service.create_or_patch_collector = AsyncMock(return_value=_load_fixture("collector_cr"))
    service.create_or_patch_instrumentation = AsyncMock(return_value=_load_fixture("instrumentation_cr"))
    service.delete_custom_resource = AsyncMock(
        return_value={"deleted": True, "kind": "OpenTelemetryCollector", "name": "otel-collector", "namespace": "otel-demo"}
    )
    service.create_receiver_rbac = AsyncMock(
        return_value={"cluster_role_action": "created", "cluster_role_binding_action": "created"}
    )
    service.build_receiver_rbac_manifests = KubernetesService.build_receiver_rbac_manifests
    service.build_k8sattributes_rbac_manifests = KubernetesService.build_k8sattributes_rbac_manifests
    service.get_config_snapshot = AsyncMock(
        return_value={
            "has_snapshot": True,
            "collector_name": "otel-collector",
            "namespace": "otel-demo",
            "last_mutation_timestamp": "2026-01-01T00:00:00Z",
            "last_mutation_tool": "otel_patch_collector",
            "snapshot_config": "receivers:\n  otlp:\n",
        }
    )
    service.rollback_collector_config = AsyncMock(
        return_value={
            "action": "rolled_back",
            "collector": "otel-demo/otel-collector",
            "dry_run": False,
            "restored_from_timestamp": "2026-01-01T00:00:00Z",
            "restored_config_preview": "receivers:\n  otlp:\n",
        }
    )

    return service


@pytest.fixture
def service_locator(
    mock_kubernetes_service: KubernetesService,
    collector_config_service: CollectorConfigService,
    server_config: ServerConfig,
) -> Dict[str, Any]:
    """Provide a complete service locator with mocked services."""
    return {
        "kubernetes_service": mock_kubernetes_service,
        "collector_config_service": collector_config_service,
        "config": server_config,
    }


@pytest.fixture
def bootstrapped_mcp(
    mock_kubernetes_service: KubernetesService, server_config: ServerConfig
) -> FastMCP:
    """Provide a fully bootstrapped MCP server with mocked services."""
    os.environ["K8S_ENABLED"] = "false"

    from opentelemetry_mcp_server.resources import initialize_resources
    from opentelemetry_mcp_server.server.core import create_mcp_server
    from opentelemetry_mcp_server.tools import initialize_tools

    mcp = create_mcp_server(server_config)

    locator = {
        "kubernetes_service": mock_kubernetes_service,
        "collector_config_service": CollectorConfigService(),
        "config": server_config,
    }

    tool_registry = initialize_tools(locator)
    tool_registry.register_all_tools(mcp)

    resource_registry = initialize_resources(locator)
    resource_registry.register_all_resources(mcp)

    return mcp
