"""Traefik MCP resources package."""

from traefik_mcp_server.resources.base import BaseResource
from traefik_mcp_server.resources.registry import ResourceRegistry, initialize_resources
from traefik_mcp_server.resources.traefik_resources import TraefikResources

__all__ = [
    "BaseResource",
    "TraefikResources",
    "ResourceRegistry",
    "initialize_resources",
]
