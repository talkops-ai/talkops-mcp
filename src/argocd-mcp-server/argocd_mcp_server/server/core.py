"""FastMCP server core setup."""

from pathlib import Path
from fastmcp import FastMCP
from argocd_mcp_server.config import ServerConfig
from argocd_mcp_server.server.middleware import setup_middleware


def _load_instructions() -> str:
    """Load MCP instructions from static file.
    
    Returns:
        Instructions content as string
    """
    static_dir = Path(__file__).parent.parent / 'static'
    instructions_path = static_dir / 'ARGOCD_MCP_INSTRUCTIONS.md'
    
    try:
        return instructions_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return "ArgoCD MCP Server for managing Kubernetes applications via ArgoCD using GitOps principles."


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
