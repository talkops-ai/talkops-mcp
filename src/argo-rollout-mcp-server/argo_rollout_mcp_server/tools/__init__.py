"""Tools module initialization for Argo Rollout MCP Server.

Toolsets:
- rollouts: Rollout creation, image update, strategy config, lifecycle, deletion
- migration: Readiness validation, Deployment <-> Rollout conversion, legacy cleanup
- analysis: AnalysisTemplate, ClusterAnalysisTemplate, Experiment, Canary metrics comparison
- diagnostics: Single-call Rollout diagnosis
"""

from typing import Any, Dict
from argo_rollout_mcp_server.tools.argo.rollout_management import RolloutManagementTools
from argo_rollout_mcp_server.tools.argo.rollout_operations import RolloutOperationTools
from argo_rollout_mcp_server.tools.diagnostics.diagnostic_tools import DiagnosticTools
from argo_rollout_mcp_server.tools.migration.migration_tools import MigrationTools
from argo_rollout_mcp_server.tools.registry import ToolRegistry


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    """Initialize all tool modules."""
    registry = ToolRegistry(service_locator)
    registry.register_tool(RolloutManagementTools(service_locator))
    registry.register_tool(RolloutOperationTools(service_locator))
    registry.register_tool(MigrationTools(service_locator))
    registry.register_tool(DiagnosticTools(service_locator))
    return registry


__all__ = [
    "initialize_tools",
    "ToolRegistry",
]
