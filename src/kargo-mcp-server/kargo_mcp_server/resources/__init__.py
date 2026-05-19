"""Resources module initialization."""

from typing import Dict, Any
from kargo_mcp_server.resources.registry import ResourceRegistry
from kargo_mcp_server.resources.project_resources import ProjectResources
from kargo_mcp_server.resources.stage_resources import StageResources
from kargo_mcp_server.resources.warehouse_resources import WarehouseResources
from kargo_mcp_server.resources.freight_resources import FreightResources
from kargo_mcp_server.resources.promotion_resources import PromotionResources
from kargo_mcp_server.resources.promotion_task_resources import PromotionTaskResources
from kargo_mcp_server.resources.credentials_resources import CredentialsResources
from kargo_mcp_server.resources.static_resources import StaticResources


def initialize_resources(service_locator: Dict[str, Any]) -> ResourceRegistry:
    """Initialize all resource modules."""
    registry = ResourceRegistry(service_locator)

    registry.register_resource(ProjectResources(service_locator))
    registry.register_resource(StageResources(service_locator))
    registry.register_resource(WarehouseResources(service_locator))
    registry.register_resource(FreightResources(service_locator))
    registry.register_resource(PromotionResources(service_locator))
    registry.register_resource(PromotionTaskResources(service_locator))
    registry.register_resource(CredentialsResources(service_locator))
    registry.register_resource(StaticResources(service_locator))

    return registry
