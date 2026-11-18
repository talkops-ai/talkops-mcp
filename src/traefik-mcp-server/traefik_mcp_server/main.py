"""Application entry point for Traefik MCP Server."""

import sys
from pathlib import Path
from typing import Optional

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from traefik_mcp_server.server.bootstrap import ServerBootstrap


def main(argv: Optional[list[str]] = None) -> None:
    """Run the Traefik MCP server in local stdio mode."""
    try:
        mcp, _config = ServerBootstrap.initialize(argv if argv is not None else sys.argv[1:])
        mcp.run()
    except KeyboardInterrupt:
        pass


def cli() -> None:
    """CLI entry point for the traefik-mcp-server command."""
    main()


if __name__ == "__main__":
    cli()
