"""Application entry point with CLI flags for transport, toolsets, and write-access control."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from helm_mcp_server.config import Config, ServerConfig, _parse_toolsets
from helm_mcp_server.server.bootstrap import ServerBootstrap


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser for helm-mcp-server."""
    parser = argparse.ArgumentParser(
        prog="helm-mcp-server",
        description="TalkOps Helm MCP Execution Server",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "streamable-http"],
        default=None,
        help="MCP transport mode (default: from MCP_TRANSPORT or 'stdio')",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="HTTP bind host (default: from MCP_HOST or '0.0.0.0')",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="HTTP bind port (default: from MCP_PORT or 8765)",
    )
    parser.add_argument(
        "--path",
        default=None,
        help="Streamable HTTP endpoint path (default: from MCP_PATH or '/mcp')",
    )
    parser.add_argument(
        "--toolsets",
        default=None,
        help="Comma-separated toolsets to enable: read, mutate, all (default: from MCP_TOOLSETS or 'all')",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Force read-only mode (disables and hides all mutating tools)",
    )
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="Enable mutating Helm tools (overrides MCP_ALLOW_WRITE=false)",
    )
    return parser


def apply_cli_overrides(config: ServerConfig, argv: Optional[List[str]] = None) -> ServerConfig:
    """Apply CLI argument overrides onto a ServerConfig instance."""
    parser = build_arg_parser()
    args, _ = parser.parse_known_args(argv)

    if args.transport:
        config.transport = "http" if args.transport == "streamable-http" else args.transport
    if args.host:
        config.host = args.host
    if args.port is not None:
        config.port = args.port
    if args.path:
        config.path = args.path
    if args.toolsets:
        config.toolsets = _parse_toolsets(args.toolsets)
    if args.allow_write:
        config.allow_write = True
    if args.read_only:
        config.allow_write = False
        config.toolsets = ["read"]

    return config


def main(argv: Optional[List[str]] = None) -> None:
    """Run the Helm MCP execution server."""
    try:
        config = apply_cli_overrides(Config.from_env(), argv)
        mcp, resolved_config = ServerBootstrap.initialize(config)

        if resolved_config.transport in ("http", "streamable-http"):
            mcp.run(
                transport="streamable-http",
                host=resolved_config.host,
                port=resolved_config.port,
                path=resolved_config.path,
            )
        else:
            mcp.run()
    except KeyboardInterrupt:
        pass


def cli() -> None:
    """CLI entry point for the helm-mcp-server script."""
    main(sys.argv[1:])


if __name__ == "__main__":
    cli()
