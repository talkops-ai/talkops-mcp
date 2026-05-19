"""Tools module initialization."""

from typing import Dict, Any
from kargo_mcp_server.tools.registry import ToolRegistry
from kargo_mcp_server.tools.project.project_tools import ProjectTools
from kargo_mcp_server.tools.stage.stage_tools import StageTools
from kargo_mcp_server.tools.warehouse.warehouse_tools import WarehouseTools
from kargo_mcp_server.tools.freight.freight_tools import FreightTools
from kargo_mcp_server.tools.promotion.promotion_tools import PromotionTools
from kargo_mcp_server.tools.promotion_task.promotion_task_tools import PromotionTaskTools
from kargo_mcp_server.tools.credentials.credentials_tools import CredentialsTools
from kargo_mcp_server.tools.diagnostics.diagnostics_tools import DiagnosticsTools


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    """Initialize all tool modules.

    Args:
        service_locator: Dictionary of services

    Returns:
        Tool registry with all tools registered
    """
    registry = ToolRegistry(service_locator)

    # Register tool groups
    registry.register_tool(ProjectTools(service_locator))
    registry.register_tool(StageTools(service_locator))
    registry.register_tool(WarehouseTools(service_locator))
    registry.register_tool(FreightTools(service_locator))
    registry.register_tool(PromotionTools(service_locator))
    registry.register_tool(PromotionTaskTools(service_locator))
    registry.register_tool(CredentialsTools(service_locator))
    registry.register_tool(DiagnosticsTools(service_locator))

    return registry
