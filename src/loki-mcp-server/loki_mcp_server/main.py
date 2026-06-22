"""Application entry point."""

import atexit
import asyncio
import sys
from pathlib import Path

# Add project root to Python path for direct execution with uv run
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from loki_mcp_server.server.bootstrap import ServerBootstrap


def main():
    """Run the MCP server."""
    try:
        mcp, config, loki_service = ServerBootstrap.initialize()

        # Register graceful shutdown so HTTP clients are closed cleanly.
        # This ensures connection pools are flushed and file descriptors
        # released — critical in containerized environments with frequent
        # restarts.
        def _shutdown_handler():
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(loki_service.close())
                else:
                    loop.run_until_complete(loki_service.close())
            except Exception:
                pass

        atexit.register(_shutdown_handler)

        # Run FastMCP server with the configured transport
        if config.transport in ("http", "sse", "streamable-http"):
            mcp.run(
                transport=config.transport,
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


def cli():
    """CLI entry point for the loki-mcp-server command."""
    main()


if __name__ == "__main__":
    cli()
