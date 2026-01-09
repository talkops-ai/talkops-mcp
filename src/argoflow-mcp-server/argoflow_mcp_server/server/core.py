"""FastMCP server core setup."""

from pathlib import Path
from fastmcp import FastMCP
from argoflow_mcp_server.config import ServerConfig
from argoflow_mcp_server.server.middleware import setup_middleware


def _load_instructions() -> str:
    """Load MCP instructions from static file.
    
    Returns:
        Instructions content as string
    """
    static_dir = Path(__file__).parent.parent / 'static'
    instructions_path = static_dir / 'ARGOFLOW_MCP_INSTRUCTIONS.md'
    
    try:
        return instructions_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return (
            "ArgoFlow MCP Server - Progressive delivery and traffic management "
            "for Kubernetes using Argo Rollouts and Traefik."
        )


def create_mcp_server(config: ServerConfig) -> FastMCP:
    """Create and configure FastMCP server.
    
    Args:
        config: Server configuration
    
    Returns:
        Configured FastMCP instance
    """
    # Load instructions from static file
    instructions = _load_instructions()
    
    # Create FastMCP instance
    # Note: FastMCP handles timeouts internally via uvicorn
    # HTTP timeout settings are configured via environment variables
    mcp = FastMCP(
        name=config.name,
        version=config.version,
        instructions=instructions
    )
    
    # Setup middleware
    setup_middleware(mcp, config)
    
    return mcp
