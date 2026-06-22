"""Resources module initialization."""

from typing import Any, Dict
from tempo_mcp_server.resources.registry import ResourceRegistry
from tempo_mcp_server.resources.backend_resources import BackendResources
from tempo_mcp_server.resources.deployment_resources import DeploymentResources
from tempo_mcp_server.resources.reference_resources import ReferenceResources
from tempo_mcp_server.resources.runbook_resources import RunbookResources
from tempo_mcp_server.resources.examples_resources import ExamplesResources


def initialize_resources(service_locator: Dict[str, Any]) -> ResourceRegistry:
    """Initialize all resource modules."""
    registry = ResourceRegistry(service_locator)

    registry.register_resource(BackendResources(service_locator))
    registry.register_resource(DeploymentResources(service_locator))
    registry.register_resource(ReferenceResources(service_locator))
    registry.register_resource(RunbookResources(service_locator))
    registry.register_resource(ExamplesResources(service_locator))

    return registry
