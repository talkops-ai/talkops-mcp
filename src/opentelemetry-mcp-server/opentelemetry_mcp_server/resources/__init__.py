"""Resources module initialization.

Creates and returns the ResourceRegistry with all live resource groups registered.
"""

from typing import Any, Dict

from opentelemetry_mcp_server.resources.otel_resources import (
    CollectorResources,
    EnrichmentResources,
    InstrumentationResources,
    LogsResources,
    SamplingResources,
    SpanMetricsResources,
    SystemCapabilitiesResources,
    TargetAllocatorResources,
)
from opentelemetry_mcp_server.resources.registry import ResourceRegistry


def initialize_resources(service_locator: Dict[str, Any]) -> ResourceRegistry:
    """Initialize all resources and return the registry."""
    registry = ResourceRegistry(service_locator)

    registry.register_resource(SystemCapabilitiesResources(service_locator))
    registry.register_resource(CollectorResources(service_locator))
    registry.register_resource(EnrichmentResources(service_locator))
    registry.register_resource(LogsResources(service_locator))
    registry.register_resource(SpanMetricsResources(service_locator))
    registry.register_resource(SamplingResources(service_locator))
    registry.register_resource(InstrumentationResources(service_locator))
    registry.register_resource(TargetAllocatorResources(service_locator))

    return registry
