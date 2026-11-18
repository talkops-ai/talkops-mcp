"""Tools module initialization for the 5 Prometheus MCP toolsets (19 granular tools)."""

from typing import Any, Dict

from prometheus_mcp_server.tools.diagnostics.diagnostics_tools import DiagnosticsTools
from prometheus_mcp_server.tools.exporter.exporter_tools import ExporterTools
from prometheus_mcp_server.tools.query.query_tools import QueryTools
from prometheus_mcp_server.tools.registry import ToolRegistry
from prometheus_mcp_server.tools.rules.rules_tools import RulesTools
from prometheus_mcp_server.tools.scrape_config.scrape_config_tools import (
    ScrapeConfigTools,
)


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    """Initialize all 5 toolset modules (`diagnostics`, `query`, `rules`, `scrape`, `exporter`)."""
    registry = ToolRegistry(service_locator)

    registry.register_tool(DiagnosticsTools(service_locator))
    registry.register_tool(QueryTools(service_locator))
    registry.register_tool(RulesTools(service_locator))
    registry.register_tool(ScrapeConfigTools(service_locator))
    registry.register_tool(ExporterTools(service_locator))

    return registry
