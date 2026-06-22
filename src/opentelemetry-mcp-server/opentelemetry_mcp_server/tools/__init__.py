"""Tools module initialization.

Creates and returns the ToolRegistry with all tool groups registered.
"""

from typing import Any, Dict

from opentelemetry_mcp_server.tools.registry import ToolRegistry
from opentelemetry_mcp_server.tools.collector.collector_tools import CollectorTools
from opentelemetry_mcp_server.tools.collector.provision_tools import ProvisionTools
from opentelemetry_mcp_server.tools.collector.revert_tools import RevertTools
from opentelemetry_mcp_server.tools.discovery.discovery_tools import DiscoveryTools
from opentelemetry_mcp_server.tools.instrumentation.instrumentation_tools import (
    InstrumentationTools,
)
from opentelemetry_mcp_server.tools.logs.log_transform_tools import LogTransformTools
from opentelemetry_mcp_server.tools.validation.validation_tools import ValidationTools
from opentelemetry_mcp_server.tools.governance.governance_tools import GovernanceTools
from opentelemetry_mcp_server.tools.sampling.sampling_tools import SamplingTools
from opentelemetry_mcp_server.tools.spanmetrics.spanmetrics_tools import SpanMetricsTools


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    """Initialize all tools and return the registry.

    Args:
        service_locator: Service locator dict with dependencies.

    Returns:
        Populated ToolRegistry.
    """
    registry = ToolRegistry(service_locator)

    registry.register_tool(CollectorTools(service_locator))
    registry.register_tool(ProvisionTools(service_locator))
    registry.register_tool(RevertTools(service_locator))
    registry.register_tool(DiscoveryTools(service_locator))
    registry.register_tool(InstrumentationTools(service_locator))
    registry.register_tool(LogTransformTools(service_locator))
    registry.register_tool(ValidationTools(service_locator))
    registry.register_tool(GovernanceTools(service_locator))
    registry.register_tool(SamplingTools(service_locator))
    registry.register_tool(SpanMetricsTools(service_locator))

    return registry

