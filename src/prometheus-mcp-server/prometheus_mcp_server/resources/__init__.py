"""Resources module initialization."""

from typing import Any, Dict
from prometheus_mcp_server.resources.registry import ResourceRegistry
from prometheus_mcp_server.resources.backend_resources import BackendResources
from prometheus_mcp_server.resources.config_resources import ConfigResources
from prometheus_mcp_server.resources.topology_resources import TopologyResources
from prometheus_mcp_server.resources.metadata_resources import MetadataResources
from prometheus_mcp_server.resources.tsdb_resources import TsdbResources
from prometheus_mcp_server.resources.static_resources import StaticResources
from prometheus_mcp_server.resources.rules_resources import RulesResources
from prometheus_mcp_server.resources.exporter_resources import ExporterResources
from prometheus_mcp_server.resources.kubernetes_resources import KubernetesResources


def initialize_resources(service_locator: Dict[str, Any]) -> ResourceRegistry:
    """Initialize all resource modules."""
    registry = ResourceRegistry(service_locator)

    registry.register_resource(BackendResources(service_locator))
    registry.register_resource(ConfigResources(service_locator))
    registry.register_resource(TopologyResources(service_locator))
    registry.register_resource(MetadataResources(service_locator))
    registry.register_resource(TsdbResources(service_locator))
    registry.register_resource(StaticResources(service_locator))
    registry.register_resource(RulesResources(service_locator))
    registry.register_resource(ExporterResources(service_locator))
    registry.register_resource(KubernetesResources(service_locator))

    return registry

