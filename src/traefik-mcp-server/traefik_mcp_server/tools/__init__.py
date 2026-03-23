"""Tools module initialization for Traefik MCP Server.

Tool Categories:
1. Traefik Routing: Manage routes and weights
2. Traefik Middleware: Manage rate limits, circuit breakers, mirroring, route middleware attachment
3. Generators: Traefik CRD generators
4. Migration: NGINX to Traefik migration (apply / generate / revert)
"""

from typing import Dict, Any, List

from traefik_mcp_server.tools.registry import ToolRegistry
from traefik_mcp_server.tools.base import BaseTool

# Traefik Tools
from traefik_mcp_server.tools.traefik.traffic_routing import TrafficRoutingTools
from traefik_mcp_server.tools.traefik.middleware_management import MiddlewareTools
from traefik_mcp_server.tools.traefik.tcp_tools import TraefikTCPTools

# Generator Tools
from traefik_mcp_server.tools.generators.traefik_generators import TraefikGeneratorTools

# Migration Tools
from traefik_mcp_server.tools.migration.nginx_migration_tools import NginxMigrationTools

__all__ = [
    'initialize_tools',
    'ToolRegistry',
    'BaseTool',
    'TrafficRoutingTools',
    'MiddlewareTools',
    'TraefikTCPTools',
    'TraefikGeneratorTools',
    'NginxMigrationTools',
]


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    """Initialize all tools and register them with the registry.
    
    Args:
        service_locator: Dictionary containing service instances
        
    Returns:
        Configured ToolRegistry
    """
    registry = ToolRegistry(service_locator)
    
    # Initialize tool categories
    tools: List[BaseTool] = [
        TrafficRoutingTools(service_locator),
        MiddlewareTools(service_locator),
        TraefikTCPTools(service_locator),
        TraefikGeneratorTools(service_locator),
        NginxMigrationTools(service_locator),
    ]
    
    # Add to registry
    for tool in tools:
        registry.register_tool(tool)
        
    return registry

