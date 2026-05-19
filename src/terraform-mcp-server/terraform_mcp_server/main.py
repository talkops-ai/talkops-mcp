"""Application entry point for Terraform MCP Server."""

import sys
from pathlib import Path

# Add project root to Python path for direct execution with uv run
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from terraform_mcp_server.server.bootstrap import ServerBootstrap


def main() -> int:
    """Run the Terraform MCP Server.
    
    Initializes all components via bootstrap and starts the FastMCP
    server with the configured transport (stdio or streamable-http).
    
    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        mcp, server_config = ServerBootstrap.initialize()
        
        # Start server with configured transport
        if server_config.transport == 'http':
            mcp.run(
                transport='streamable-http',
                host=server_config.host,
                port=server_config.port,
                path=server_config.path,
            )
        else:
            # Default: STDIO transport
            mcp.run()
        
        return 0
    
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
