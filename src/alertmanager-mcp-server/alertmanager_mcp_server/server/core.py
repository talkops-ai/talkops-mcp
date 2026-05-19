"""FastMCP server core setup."""
from pathlib import Path
from fastmcp import FastMCP
from alertmanager_mcp_server.config import ServerConfig


def _load_instructions() -> str:
    static_dir = Path(__file__).parent.parent / 'static'
    path = static_dir / 'ALERTMANAGER_MCP_INSTRUCTIONS.md'
    try:
        return path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return "Alertmanager MCP Server for AI-native alert management."


def create_mcp_server(config: ServerConfig) -> FastMCP:
    return FastMCP(name=config.name, version=config.version, instructions=_load_instructions())
