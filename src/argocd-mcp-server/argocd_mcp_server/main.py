"""Application entry point."""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

# Add project root to Python path for direct execution with uv run
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from argocd_mcp_server.config import Config
from argocd_mcp_server.server.bootstrap import ServerBootstrap


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for the ArgoCD MCP server."""
    parser = argparse.ArgumentParser(
        prog="argocd-mcp-server",
        description="ArgoCD MCP Execution Server for Kubernetes GitOps operations.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=None,
        help="Override MCP transport mode ('stdio' or 'http').",
    )
    parser.add_argument(
        "--toolsets",
        default=None,
        help="Comma-separated list of active toolset profiles (all,readonly,applications,deployments,repositories,projects).",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        default=False,
        help="Force read-only mode (disables all cluster-mutating tools regardless of MCP_ALLOW_WRITE).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    """Run the MCP server."""
    args = parse_args(argv)
    try:
        config = Config.from_env()
        if args.transport:
            config.transport = args.transport
        if args.toolsets:
            config.toolsets = [
                item.strip().lower() for item in args.toolsets.split(",") if item.strip()
            ]
            if "readonly" in config.toolsets and "all" not in config.toolsets:
                config.allow_write = False
        if args.read_only:
            config.allow_write = False

        mcp, config = ServerBootstrap.initialize(config)

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


def cli() -> None:
    """CLI entry point for the argocd-mcp-server command."""
    main()


if __name__ == "__main__":
    cli()
