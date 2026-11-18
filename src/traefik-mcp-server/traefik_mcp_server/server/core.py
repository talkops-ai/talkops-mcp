"""FastMCP server core setup."""

from pathlib import Path
from fastmcp import FastMCP
from traefik_mcp_server.config import ServerConfig
from traefik_mcp_server.server.middleware import setup_middleware


def _load_instructions() -> str:
    """Load MCP instructions from static file."""
    static_dir = Path(__file__).parent.parent / "static"
    instructions_path = static_dir / "TRAEFIK_MCP_INSTRUCTIONS.md"

    try:
        return instructions_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return (
            "Traefik MCP Server - Execution layer for Traefik v3 routing, "
            "weighted services, middlewares, TLS policies, TCP/UDP, and runtime diagnostics."
        )


def create_mcp_server(config: ServerConfig) -> FastMCP:
    """Create and configure FastMCP server."""
    instructions = _load_instructions()

    mcp = FastMCP(
        name=config.name,
        version=config.version,
        instructions=instructions,
    )

    setup_middleware(mcp, config)

    return mcp
