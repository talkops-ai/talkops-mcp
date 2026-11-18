"""Application entry point and CLI argument parser for Alertmanager MCP server."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from alertmanager_mcp_server.config import (
    VALID_TRANSPORTS,
    Config,
    ServerConfig,
)
from alertmanager_mcp_server.server.bootstrap import ServerBootstrap


def build_arg_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser for `alertmanager-mcp-server`."""
    parser = argparse.ArgumentParser(
        prog="alertmanager-mcp-server",
        description="Alertmanager Model Context Protocol (MCP) Execution Server",
    )
    parser.add_argument(
        "--transport",
        choices=sorted(VALID_TRANSPORTS),
        default=None,
        help="MCP transport mode: stdio, http, sse, or streamable-http",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Bind host for HTTP/SSE transports (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port for HTTP/SSE transports (default: 8769)",
    )
    parser.add_argument(
        "--path",
        default=None,
        help="HTTP mount path (default: /mcp)",
    )
    parser.add_argument(
        "--toolsets",
        default=None,
        help="Comma-separated toolsets to enable: all,triage,routing,silences,governance",
    )

    write_group = parser.add_mutually_exclusive_group()
    write_group.add_argument(
        "--read-only",
        dest="read_only",
        action="store_true",
        default=None,
        help="Enforce read-only mode (disable all mutating tools)",
    )
    write_group.add_argument(
        "--allow-write",
        dest="allow_write",
        action="store_true",
        default=None,
        help="Enable mutating tools (silences and test alert pushing)",
    )
    return parser


def apply_cli_overrides(
    config: ServerConfig,
    args: argparse.Namespace,
) -> ServerConfig:
    """Apply parsed CLI arguments over environment-loaded `ServerConfig`."""
    if args.transport is not None:
        config.transport = args.transport
    if args.host is not None:
        config.host = args.host
    if args.port is not None:
        config.port = int(args.port)
    if args.path is not None:
        config.path = args.path
    if args.toolsets is not None:
        raw_ts = [t.strip().lower() for t in str(args.toolsets).split(",") if t.strip()]
        config.toolsets = raw_ts or ["all"]
        config.__post_init__()
    if args.read_only is True:
        config.allow_write = False
    elif args.allow_write is True:
        config.allow_write = True
    return config


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Initialize and run the Alertmanager MCP server."""
    parser = build_arg_parser()
    parsed_args = parser.parse_args(list(argv) if argv is not None else [])
    has_overrides = any(
        getattr(parsed_args, attr) is not None
        for attr in (
            "transport",
            "host",
            "port",
            "path",
            "toolsets",
            "read_only",
            "allow_write",
        )
    )
    try:
        if has_overrides:
            base_cfg = Config.from_env()
            apply_cli_overrides(base_cfg, parsed_args)
            mcp, config, _service = ServerBootstrap.initialize(config=base_cfg)
        else:
            mcp, config, _service = ServerBootstrap.initialize()

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


def cli() -> None:
    """Console script entry point."""
    main(sys.argv[1:])


if __name__ == "__main__":
    cli()
