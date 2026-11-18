"""Application entry point."""

import sys
from pathlib import Path
from typing import Optional, Sequence

# Add project root to Python path for direct execution with uv run
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

from opentelemetry_mcp_server.config import Config
from opentelemetry_mcp_server.server.bootstrap import ServerBootstrap


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Run the MCP server."""
    try:
        load_dotenv()
        config = Config.from_cli_and_env(
            argv if argv is not None else sys.argv[1:]
        )
        mcp, config = ServerBootstrap.initialize(config)

        # Run FastMCP server with the configured transport
        if config.transport in ("http", "sse", "streamable-http"):
            mcp.run(
                transport="http" if config.transport == "streamable-http" else config.transport,
                host=config.host,
                port=config.port,
                path=config.path,
            )
        else:
            mcp.run()

    except KeyboardInterrupt:
        pass
    except Exception:
        raise


def cli() -> None:
    """CLI entry point for the opentelemetry-mcp-server command."""
    main()


if __name__ == "__main__":
    cli()
