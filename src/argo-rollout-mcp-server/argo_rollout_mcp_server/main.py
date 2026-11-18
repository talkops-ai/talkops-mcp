"""Application entry point."""

import sys
from pathlib import Path
from typing import Optional

# Suppress InsecureRequestWarning when connecting to clusters with self-signed certs
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from argo_rollout_mcp_server.server.bootstrap import ServerBootstrap


def main(argv: Optional[list[str]] = None):
    """Run the Argo Rollouts MCP server."""
    try:
        mcp, config = ServerBootstrap.initialize(argv if argv is not None else sys.argv[1:])

        if config.transport == "http":
            mcp.run(
                transport="streamable-http",
                host=config.host,
                port=config.port,
                path=config.path,
            )
        else:
            mcp.run()
    except KeyboardInterrupt:
        pass


def cli():
    """CLI entry point for the argo-rollout-mcp-server command."""
    main()


if __name__ == "__main__":
    cli()
