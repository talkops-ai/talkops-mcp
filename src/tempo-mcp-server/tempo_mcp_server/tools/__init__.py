"""Tools module initialization."""

from typing import Any, Dict
from tempo_mcp_server.tools.registry import ToolRegistry
from tempo_mcp_server.tools.discovery.discovery_tools import DiscoveryTools
from tempo_mcp_server.tools.schema.schema_tools import SchemaTools
from tempo_mcp_server.tools.search.search_tools import SearchTools
from tempo_mcp_server.tools.metrics.metrics_tools import MetricsTools
from tempo_mcp_server.tools.pivot.pivot_tools import PivotTools
from tempo_mcp_server.tools.diagnostics.diagnostics_tools import DiagnosticsTools
from tempo_mcp_server.tools.topology.topology_tools import TopologyTools
from tempo_mcp_server.tools.operator.operator_tools import OperatorTools
from tempo_mcp_server.tools.comparison.comparison_tools import ComparisonTools
from tempo_mcp_server.tools.alerting.alerting_tools import AlertingTools


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    """Initialize all tool modules.

    Args:
        service_locator: Dictionary of services

    Returns:
        Tool registry with all tools registered
    """
    registry = ToolRegistry(service_locator)

    # Backend discovery (3 tools)
    registry.register_tool(DiscoveryTools(service_locator))

    # Schema discovery (3 tools)
    registry.register_tool(SchemaTools(service_locator))

    # Trace search & retrieval (4 tools)
    registry.register_tool(SearchTools(service_locator))

    # TraceQL metrics (2 tools)
    registry.register_tool(MetricsTools(service_locator))

    # Cross-pillar pivots (2 tools)
    registry.register_tool(PivotTools(service_locator))

    # Diagnostics (1 tool)
    registry.register_tool(DiagnosticsTools(service_locator))

    # Topology (1 tool)
    registry.register_tool(TopologyTools(service_locator))

    # Operator CRD management (4 tools)
    registry.register_tool(OperatorTools(service_locator))

    # Trace comparison (1 tool)
    registry.register_tool(ComparisonTools(service_locator))

    # Alerting expression generator (1 tool)
    registry.register_tool(AlertingTools(service_locator))

    return registry
