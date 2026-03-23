"""Application entry point."""

import sys
from pathlib import Path
import urllib3

# Suppress unverified HTTPS request warnings (e.g. for local kubernetes.docker.internal clusters)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Add project root to Python path for direct execution with uv run
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from traefik_mcp_server.server.bootstrap import ServerBootstrap


def main() -> int:
    """Run the MCP server."""
    try:
        mcp, config = ServerBootstrap.initialize()
        
        # Run FastMCP server with the configured transport
        if config.transport == 'http':
            # HTTP/Streamable HTTP transport mode (single unified endpoint)
            mcp.run(transport='streamable-http', host=config.host, port=config.port, path=config.path)
        else:
            # STDIO transport mode (default for MCP)
            mcp.run()
            
        return 0
    
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
