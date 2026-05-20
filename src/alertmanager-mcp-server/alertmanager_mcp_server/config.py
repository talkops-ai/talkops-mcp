"""Application configuration management for Alertmanager MCP server."""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class BackendConfig:
    """Configuration for a single Alertmanager backend."""
    id: str = "default"
    base_url: str = "http://localhost:9093"
    display_name: Optional[str] = None
    labels: Dict[str, str] = field(default_factory=dict)
    auth_header: Optional[str] = None
    verify_ssl: bool = True
    timeout: int = 30
    is_default: bool = True


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = 'INFO'
    format: str = 'json'


@dataclass
class ServerConfig:
    """MCP server configuration."""
    name: str = 'alertmanager-mcp-server'
    version: str = '0.1.0'
    transport: str = 'stdio'
    host: str = '0.0.0.0'
    port: int = 8768
    path: str = '/mcp'

    backends: List[BackendConfig] = field(default_factory=lambda: [BackendConfig()])
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Silence safety defaults
    max_silence_duration_minutes: int = 1440  # 24h cap
    silence_warning_threshold: int = 50  # warn if silence affects >= N alerts


class Config:
    """Configuration loader."""

    @staticmethod
    def from_env() -> ServerConfig:
        """Load configuration from environment variables."""
        backends_json = os.getenv('ALERTMANAGER_BACKENDS')
        if backends_json:
            try:
                raw_backends = json.loads(backends_json)
                backends = [
                    BackendConfig(
                        id=b.get('id', f'backend-{i}'),
                        base_url=b.get('base_url', 'http://localhost:9093'),
                        display_name=b.get('display_name'),
                        labels=b.get('labels', {}),
                        auth_header=b.get('auth_header'),
                        verify_ssl=b.get('verify_ssl', True),
                        timeout=b.get('timeout', 30),
                        is_default=b.get('is_default', i == 0),
                    )
                    for i, b in enumerate(raw_backends)
                ]
            except (json.JSONDecodeError, TypeError):
                backends = [BackendConfig()]
        else:
            backends = [
                BackendConfig(
                    id=os.getenv('ALERTMANAGER_BACKEND_ID', 'default'),
                    base_url=os.getenv('ALERTMANAGER_BASE_URL', 'http://localhost:9093'),
                    display_name=os.getenv('ALERTMANAGER_DISPLAY_NAME'),
                    auth_header=os.getenv('ALERTMANAGER_AUTH_HEADER'),
                    verify_ssl=os.getenv('ALERTMANAGER_VERIFY_SSL', 'true').lower() == 'true',
                    timeout=int(os.getenv('ALERTMANAGER_TIMEOUT', '30')),
                    is_default=True,
                )
            ]

        return ServerConfig(
            name=os.getenv('MCP_SERVER_NAME', 'alertmanager-mcp-server'),
            version=os.getenv('MCP_SERVER_VERSION', '0.1.0'),
            transport=os.getenv('MCP_TRANSPORT', 'stdio'),
            host=os.getenv('MCP_HOST', '0.0.0.0'),
            port=int(os.getenv('MCP_PORT', '8768')),
            path=os.getenv('MCP_PATH', '/mcp'),
            backends=backends,
            logging=LoggingConfig(
                level=os.getenv('MCP_LOG_LEVEL', 'INFO'),
                format=os.getenv('MCP_LOG_FORMAT', 'json'),
            ),
            max_silence_duration_minutes=int(os.getenv('AM_MAX_SILENCE_MINUTES', '1440')),
            silence_warning_threshold=int(os.getenv('AM_SILENCE_WARNING_THRESHOLD', '50')),
        )
