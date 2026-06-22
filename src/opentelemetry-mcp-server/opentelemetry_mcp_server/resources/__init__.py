"""Resources module initialization.

Creates and returns the ResourceRegistry with all resource groups registered.
"""

from typing import Any, Dict

from opentelemetry_mcp_server.resources.registry import ResourceRegistry
from opentelemetry_mcp_server.resources.otel_resources import (
    CollectorResources,
    EnrichmentResources,
    InstrumentationResources,
    LanguageResources,
    LogsResources,
    OperatorDiagnosticsResources,
    SpanMetricsResources,
    StaticResources,
    TargetAllocatorResources,
)


def initialize_resources(service_locator: Dict[str, Any]) -> ResourceRegistry:
    """Initialize all resources and return the registry.

    Args:
        service_locator: Service locator dict with dependencies.

    Returns:
        Populated ResourceRegistry.
    """
    registry = ResourceRegistry(service_locator)

    registry.register_resource(CollectorResources(service_locator))
    registry.register_resource(EnrichmentResources(service_locator))
    registry.register_resource(LogsResources(service_locator))
    registry.register_resource(SpanMetricsResources(service_locator))
    registry.register_resource(InstrumentationResources(service_locator))
    registry.register_resource(TargetAllocatorResources(service_locator))
    registry.register_resource(LanguageResources(service_locator))
    registry.register_resource(StaticResources(service_locator))
    registry.register_resource(OperatorDiagnosticsResources(service_locator))

    return registry
