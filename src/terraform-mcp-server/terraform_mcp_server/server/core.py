"""FastMCP server core setup for Terraform MCP Server."""

from fastmcp import FastMCP
from terraform_mcp_server.server_config import ServerConfig
from terraform_mcp_server.server.middleware import setup_middleware


def _load_instructions() -> str:
    """Load MCP server instructions.
    
    Returns:
        Instructions content describing the server's capabilities.
    """
    return (
        "Terraform Knowledge Graph MCP Server — provides semantic vector "
        "search over Terraform documentation, document ingestion into a "
        "Neo4j-backed knowledge graph, and secure Terraform command execution. "
        "Tools: terraform_doc_search (vector similarity search), "
        "ingest_terraform_docs (document ingestion pipeline), "
        "terraform_execute (secure CLI execution). "
        "Resources: terraform://knowledge-graph/stats, "
        "terraform://server/config-summary."
    )


def create_mcp_server(server_config: ServerConfig) -> FastMCP:
    """Create and configure FastMCP server instance.
    
    Args:
        server_config: MCP server configuration
    
    Returns:
        Configured FastMCP instance with middleware attached
    """
    instructions = _load_instructions()
    
    mcp = FastMCP(
        name=server_config.name,
        version=server_config.version,
        instructions=instructions,
    )
    
    # Attach middleware stack
    setup_middleware(mcp, server_config)
    
    return mcp
