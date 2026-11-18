"""Application entry point."""

import asyncio
import atexit
import sys
from pathlib import Path
from typing import Optional, Sequence

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tempo_mcp_server.server.bootstrap import ServerBootstrap


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Run the MCP server."""
    try:
        cli_args = list(argv) if argv is not None else sys.argv[1:]
        mcp, config, tempo_service = ServerBootstrap.initialize(cli_args)

        def _shutdown_handler() -> None:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(tempo_service.close())
                else:
                    loop.run_until_complete(tempo_service.close())
            except Exception:
                pass

        atexit.register(_shutdown_handler)

        if config.transport in ("http", "sse", "streamable-http"):
            mcp.run(transport=config.transport, host=config.host, port=config.port, path=config.path)
        else:
            mcp.run()

    except KeyboardInterrupt:
        pass
    except Exception:
        raise


def cli() -> None:
    """CLI entry point for the tempo-mcp-server command."""
    main()


if __name__ == "__main__":
    cli()
