"""Application entry point."""

import sys
from pathlib import Path

# Add project root to Python path for direct execution with uv run
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from helm_mcp_server.server.bootstrap import ServerBootstrap


def main():
    """Run the MCP server."""
    try:
        mcp, config = ServerBootstrap.initialize()
        
        # Run FastMCP server with the configured transport
        if config.transport == 'http':
            # HTTP/SSE transport mode
            mcp.run(transport='sse', host=config.host, port=config.port, path=config.path)
        else:
            # STDIO transport mode (default for MCP)
            mcp.run()
    
    except KeyboardInterrupt:
        pass
    except Exception as e:
        raise


def cli():
    """CLI entry point for the helm-mcp-server command."""
    main()


if __name__ == '__main__':
    cli()

