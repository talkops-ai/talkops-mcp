"""Application entry point."""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from alertmanager_mcp_server.server.bootstrap import ServerBootstrap


def main():
    service = None
    try:
        mcp, config, service = ServerBootstrap.initialize()
        # Run FastMCP server with the configured transport
        if config.transport in ('http', 'sse', 'streamable-http'):
            mcp.run(transport=config.transport, host=config.host, port=config.port, path=config.path)
        else:
            mcp.run()
    except KeyboardInterrupt:
        pass
    finally:
        # Graceful shutdown: close all HTTP clients
        if service is not None:
            asyncio.get_event_loop().run_until_complete(service.close())


def cli():
    main()


if __name__ == '__main__':
    cli()
