"""Tools module initialization."""

from typing import Any, Dict

from kargo_mcp_server.tools.credentials.credentials_tools import CredentialsTools
from kargo_mcp_server.tools.diagnostics.diagnostics_tools import DiagnosticsTools
from kargo_mcp_server.tools.pipeline.pipeline_tools import PipelineTools
from kargo_mcp_server.tools.promotion.promotion_tools import PromotionTools
from kargo_mcp_server.tools.rbac.rbac_tools import RbacTools
from kargo_mcp_server.tools.registry import ToolRegistry
from kargo_mcp_server.tools.verification.verification_tools import VerificationTools


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    """Initialize all 6 toolset modules (20 tools max)."""
    registry = ToolRegistry(service_locator)

    registry.register_tool(DiagnosticsTools(service_locator))
    registry.register_tool(PipelineTools(service_locator))
    registry.register_tool(PromotionTools(service_locator))
    registry.register_tool(VerificationTools(service_locator))
    registry.register_tool(CredentialsTools(service_locator))
    registry.register_tool(RbacTools(service_locator))

    return registry
