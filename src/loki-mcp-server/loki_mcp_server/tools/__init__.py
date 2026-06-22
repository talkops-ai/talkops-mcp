"""Tool module initialization — v4 architecture.

Registers the 8 v4 tools across 4 categories:
  Discovery (3): get_cluster_labels, get_label_values, get_active_series
  Structure (2): get_log_patterns, get_detected_fields
  Safety    (1): get_query_stats
  Execution (2): execute_logql_instant, execute_logql_query
"""

from typing import Any, Dict

from loki_mcp_server.tools.registry import ToolRegistry
from loki_mcp_server.tools.discovery.discovery_tools import DiscoveryTools
from loki_mcp_server.tools.structure.structure_tools import StructureTools
from loki_mcp_server.tools.safety.safety_tools import SafetyTools
from loki_mcp_server.tools.execution.execution_tools import ExecutionTools


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    """Create and populate the tool registry with all v4 tools.

    Args:
        service_locator: Dependency injection container with
            'loki_service' and 'config' keys.

    Returns:
        Populated ToolRegistry ready for registration.
    """
    registry = ToolRegistry(service_locator)

    registry.register_tool(DiscoveryTools(service_locator))
    registry.register_tool(StructureTools(service_locator))
    registry.register_tool(SafetyTools(service_locator))
    registry.register_tool(ExecutionTools(service_locator))

    return registry

