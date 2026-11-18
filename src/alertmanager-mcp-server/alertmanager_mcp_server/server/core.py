"""FastMCP server core setup and lifespan management."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastmcp import FastMCP

from alertmanager_mcp_server.config import ServerConfig


def _load_instructions() -> str:
    static_dir = Path(__file__).parent.parent / "static"
    path = static_dir / "ALERTMANAGER_MCP_INSTRUCTIONS.md"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "Alertmanager MCP Server for AI-native alert triage, routing diagnostics, silence safety, and governance."


def create_mcp_server(
    config: ServerConfig,
    service: Optional[Any] = None,
) -> FastMCP:
    """Create a FastMCP instance with graceful HTTP client lifespan cleanup."""

    @asynccontextmanager
    async def _lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        try:
            yield {}
        finally:
            svc = service or getattr(server, "_alertmanager_service", None)
            if svc is not None and hasattr(svc, "close"):
                await svc.close()

    mcp = FastMCP(
        name=config.name,
        version=config.version,
        instructions=_load_instructions(),
        lifespan=_lifespan,
    )
    if service is not None:
        setattr(mcp, "_alertmanager_service", service)
    return mcp
