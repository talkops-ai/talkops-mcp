"""Tools module initialization.

v4 refactor: DiscoveryTools and DiagnosticsTools have been retired.
Their read-only capabilities are now served by resources:
  - prom://system/backends, prom://system/backends/{backend_id}
  - prom://tsdb/cardinality, prom://config/runtime
"""

from typing import Any, Dict
from prometheus_mcp_server.tools.registry import ToolRegistry
from prometheus_mcp_server.tools.query.query_tools import QueryTools
from prometheus_mcp_server.tools.onboarding.onboarding_tools import OnboardingTools
from prometheus_mcp_server.tools.exporter.exporter_tools import ExporterTools
from prometheus_mcp_server.tools.scrape_config.scrape_config_tools import ScrapeConfigTools
from prometheus_mcp_server.tools.tsdb_finops.tsdb_finops_tools import TsdbFinOpsTools
from prometheus_mcp_server.tools.rules.rules_tools import RulesTools
from prometheus_mcp_server.tools.promtool.promtool_tools import PromtoolTools
from prometheus_mcp_server.tools.simulation.simulation_tools import SimulationTools
from prometheus_mcp_server.tools.authoring.authoring_tools import AuthoringTools


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    """Initialize all tool modules.

    Args:
        service_locator: Dictionary of services

    Returns:
        Tool registry with all tools registered
    """
    registry = ToolRegistry(service_locator)

    # Query & Exploration
    registry.register_tool(QueryTools(service_locator))

    # Onboarding & Exporters
    registry.register_tool(OnboardingTools(service_locator))
    registry.register_tool(ExporterTools(service_locator))
    registry.register_tool(ScrapeConfigTools(service_locator))

    # FinOps (cardinality optimization, recording rules, remote-write)
    registry.register_tool(TsdbFinOpsTools(service_locator))

    # Rule management, promtool, simulation, authoring
    registry.register_tool(RulesTools(service_locator))
    registry.register_tool(PromtoolTools(service_locator))
    registry.register_tool(SimulationTools(service_locator))
    registry.register_tool(AuthoringTools(service_locator))

    return registry
