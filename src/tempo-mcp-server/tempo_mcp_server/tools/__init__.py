"""Tools module initialization."""

from typing import Any, Dict

from tempo_mcp_server.tools.comparison.comparison_tools import ComparisonTools
from tempo_mcp_server.tools.diagnostics.diagnostics_tools import DiagnosticsTools
from tempo_mcp_server.tools.metrics.metrics_tools import MetricsTools
from tempo_mcp_server.tools.operator.operator_tools import OperatorTools
from tempo_mcp_server.tools.pivot.pivot_tools import PivotTools
from tempo_mcp_server.tools.registry import ToolRegistry
from tempo_mcp_server.tools.schema.schema_tools import SchemaTools
from tempo_mcp_server.tools.search.search_tools import SearchTools
from tempo_mcp_server.tools.topology.topology_tools import TopologyTools


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    """Initialize all tool modules."""
    registry = ToolRegistry(service_locator)

    # Search & schema toolset (8 read-only tools)
    registry.register_tool(SchemaTools(service_locator))
    registry.register_tool(SearchTools(service_locator))
    registry.register_tool(ComparisonTools(service_locator))

    # Metrics toolset (4 read-only tools)
    registry.register_tool(MetricsTools(service_locator))

    # Diagnostics, pivot & topology toolset (4 read-only tools)
    registry.register_tool(PivotTools(service_locator))
    registry.register_tool(DiagnosticsTools(service_locator))
    registry.register_tool(TopologyTools(service_locator))

    # Write-gated overrides & operator toolsets (2 write tools)
    registry.register_tool(OperatorTools(service_locator))

    return registry
