"""FastMCP server creation and configuration.

Creates the FastMCP instance with system-prompt instructions
and middleware stack.
"""

from pathlib import Path

from fastmcp import FastMCP

from loki_mcp_server.config import ServerConfig
from loki_mcp_server.server.middleware import setup_middleware

# Path to the static instructions file
_STATIC_DIR = Path(__file__).parent.parent / "static"


def _load_instructions() -> str:
    """Load the MCP system-prompt instructions from the static file.

    Returns:
        Instruction markdown string.
    """
    instructions_path = _STATIC_DIR / "LOKI_MCP_INSTRUCTIONS.md"
    try:
        return instructions_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return (
            "You are connected to a Loki MCP server. "
            "Use get_loki_schema before writing any LogQL queries. "
            "Never put high-cardinality labels (trace_id, user_id, ip) "
            "in {} stream selectors."
        )


def create_mcp_server(config: ServerConfig) -> FastMCP:
    """Create and configure the FastMCP server instance.

    Args:
        config: Server configuration.

    Returns:
        Configured FastMCP instance with middleware.
    """
    instructions = _load_instructions()

    mcp = FastMCP(
        name=config.name,
        version=config.version,
        instructions=instructions,
    )

    # Set up middleware stack
    setup_middleware(mcp, config)

    return mcp
