"""Resources module initialization."""

from typing import Any, Dict

from prometheus_mcp_server.resources.audit_resources import AuditResources
from prometheus_mcp_server.resources.backend_resources import BackendResources
from prometheus_mcp_server.resources.config_resources import ConfigResources
from prometheus_mcp_server.resources.kubernetes_resources import KubernetesResources
from prometheus_mcp_server.resources.metadata_resources import MetadataResources
from prometheus_mcp_server.resources.registry import ResourceRegistry
from prometheus_mcp_server.resources.rules_resources import RulesResources
from prometheus_mcp_server.resources.topology_resources import TopologyResources
from prometheus_mcp_server.resources.tsdb_resources import TsdbResources


def initialize_resources(service_locator: Dict[str, Any]) -> ResourceRegistry:
    """Initialize all 11 dynamic `prom://` resource modules."""
    registry = ResourceRegistry(service_locator)

    registry.register_resource(BackendResources(service_locator))
    registry.register_resource(ConfigResources(service_locator))
    registry.register_resource(TopologyResources(service_locator))
    registry.register_resource(MetadataResources(service_locator))
    registry.register_resource(TsdbResources(service_locator))
    registry.register_resource(RulesResources(service_locator))
    registry.register_resource(KubernetesResources(service_locator))
    registry.register_resource(AuditResources(service_locator))

    return registry
