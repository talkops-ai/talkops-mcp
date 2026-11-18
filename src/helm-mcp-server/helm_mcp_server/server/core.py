"""FastMCP server core setup — execution layer only."""

from __future__ import annotations

from typing import Set
from fastmcp import FastMCP
from helm_mcp_server.config import ServerConfig
from helm_mcp_server.server.middleware import setup_middleware

SERVER_INSTRUCTIONS = (
    "TalkOps Helm MCP Execution Server for Kubernetes workload and release management.\n"
    "- Capabilities: Chart repository search/registration, offline manifest rendering, "
    "N-to-1 release planning and live diffing (helm_plan_release), release lifecycle mutations "
    "(install, upgrade, rollback, uninstall), multi-layer rollout health monitoring "
    "(helm_monitor_deployment), cluster prerequisite verification, and per-session kubeconfig context switching.\n"
    "- Read-Only Resources: 'helm://repositories', 'helm://charts/{repository}/{chart_name}', "
    "'helm://charts/{repository}/{chart_name}/values', 'helm://charts/{repository}/{chart_name}/readme', "
    "'helm://releases/{namespace}/{release_name}/history', 'helm://releases/{namespace}/{release_name}/values', "
    "'helm://releases/{namespace}/{release_name}/manifest', 'kubernetes://cluster-info', "
    "'kubernetes://namespaces', and 'kubernetes://contexts'.\n"
    "- Safety: Secret data and sensitive values are automatically redacted. Mutating tools require "
    "MCP_ALLOW_WRITE=true."
)


def create_mcp_server(config: ServerConfig) -> FastMCP:
    """Create and configure the FastMCP execution server."""
    exclude_tags: Set[str] = set()
    include_tags: Set[str] | None = None

    if not config.is_mutate_enabled:
        exclude_tags.add("mutate")
    elif not config.is_read_enabled:
        include_tags = {"mutate", "session"}

    mcp = FastMCP(
        name=config.name,
        version=config.version,
        instructions=SERVER_INSTRUCTIONS,
        include_tags=include_tags,
        exclude_tags=exclude_tags if exclude_tags else None,
    )

    setup_middleware(mcp, config)
    return mcp
