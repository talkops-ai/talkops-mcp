"""Application configuration management.

Loads all configuration from environment variables following the 12-Factor
methodology. Uses dataclasses for type-safe, immutable configuration objects.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Literal, Optional


def _strip_env(value: Optional[str]) -> Optional[str]:
    """Strip inline comments and surrounding whitespace from a .env value.

    python-dotenv does not strip unquoted inline comments, so a line
    like ``LOKI_AUTH_TOKEN=my-token  # bearer token`` is parsed as the
    literal string ``my-token  # bearer token`` and injected verbatim
    into HTTP headers.

    This helper removes everything from the first bare ``#`` character
    (preceded by whitespace) and strips surrounding whitespace.  Returns
    ``None`` when the result is empty so callers can use ``or`` defaulting.
    """
    if value is None:
        return None
    cleaned = re.sub(r"\s*#.*$", "", value).strip()
    return cleaned if cleaned else None


@dataclass(frozen=True)
class LokiConfig:
    """Loki HTTP API connection configuration."""

    base_url: str = "http://loki:3100"
    timeout: int = 30
    verify_ssl: bool = True


@dataclass(frozen=True)
class AuthConfig:
    """Authentication configuration for Loki.

    Supports Bearer token, Basic Auth, and multi-tenant
    X-Scope-OrgID headers.
    """

    auth_token: Optional[str] = None
    basic_auth_user: Optional[str] = None
    basic_auth_password: Optional[str] = None
    org_id: Optional[str] = None


@dataclass(frozen=True)
class GuardrailConfig:
    """Query safety guardrails.

    Enforces limits on query cost, time windows, result size,
    and label cardinality to prevent dangerous queries.
    """

    max_query_bytes: int = 5_000_000_000  # 5 GB
    max_time_window_hours: int = 336  # 14 days
    max_log_limit: int = 200           # max log lines per response (was 5000)
    max_series: int = 100              # max metric series (matrix) per response
    max_points_per_series: int = 200   # max data points per metric series
    high_cardinality_threshold: int = 10_000


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: Literal["json", "text"] = "json"


@dataclass(frozen=True)
class ServerConfig:
    """Top-level MCP server configuration.

    Aggregates all sub-configurations and provides server transport settings.
    """

    name: str = "loki-mcp-server"
    version: str = "0.1.0"
    transport: str = "stdio"
    host: str = "0.0.0.0"
    port: int = 8769
    path: str = "/mcp"

    # Timeout settings (seconds)
    http_timeout: int = 300
    http_keepalive_timeout: int = 5
    http_connect_timeout: int = 60

    # Response size limits (bytes)
    # Soft limit: Primary defense. Tools compact and truncate their own results
    # to fit within this budget. Set conservatively because FastMCP serializes
    # results twice (TextContent + structured_content), roughly doubling the
    # wire payload (~2.2x).
    response_size_soft_limit: int = 40_000
    # Hard limit: Safety net only. The ResponseLimitingMiddleware uses this
    # as a last resort. Set generously high to avoid triggering on normally
    # truncated results.
    response_size_hard_limit: int = 200_000

    # Sub-configurations
    loki: LokiConfig = field(default_factory=LokiConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    guardrails: GuardrailConfig = field(default_factory=GuardrailConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


class Config:
    """Configuration loader.

    Loads all settings from environment variables with sensible defaults.
    Supports dotenv files for local development.
    """

    @staticmethod
    def from_env() -> ServerConfig:
        """Load configuration from environment variables.

        Returns:
            Fully populated ServerConfig instance.
        """
        from dotenv import load_dotenv

        load_dotenv()

        return ServerConfig(
            name=_strip_env(os.getenv("MCP_SERVER_NAME")) or "loki-mcp-server",
            version=_strip_env(os.getenv("MCP_SERVER_VERSION")) or "0.1.0",
            transport=_strip_env(os.getenv("MCP_TRANSPORT")) or "stdio",
            host=_strip_env(os.getenv("MCP_HOST")) or "0.0.0.0",
            port=int(_strip_env(os.getenv("MCP_PORT")) or "8769"),
            path=_strip_env(os.getenv("MCP_PATH")) or "/mcp",
            http_timeout=int(_strip_env(os.getenv("MCP_HTTP_TIMEOUT")) or "300"),
            http_keepalive_timeout=int(
                _strip_env(os.getenv("MCP_HTTP_KEEPALIVE_TIMEOUT")) or "5"
            ),
            http_connect_timeout=int(
                _strip_env(os.getenv("MCP_HTTP_CONNECT_TIMEOUT")) or "60"
            ),
            response_size_soft_limit=int(
                _strip_env(os.getenv("MCP_RESPONSE_SIZE_SOFT_LIMIT")) or "40000"
            ),
            response_size_hard_limit=int(
                _strip_env(os.getenv("MCP_RESPONSE_SIZE_HARD_LIMIT")) or "200000"
            ),
            loki=LokiConfig(
                base_url=_strip_env(os.getenv("LOKI_URL")) or "http://loki:3100",
                timeout=int(_strip_env(os.getenv("LOKI_TIMEOUT")) or "30"),
                verify_ssl=(_strip_env(os.getenv("LOKI_VERIFY_SSL")) or "true").lower()
                == "true",
            ),
            auth=AuthConfig(
                auth_token=_strip_env(os.getenv("LOKI_AUTH_TOKEN")),
                basic_auth_user=_strip_env(os.getenv("LOKI_BASIC_AUTH_USER")),
                basic_auth_password=_strip_env(os.getenv("LOKI_BASIC_AUTH_PASSWORD")),
                org_id=_strip_env(os.getenv("LOKI_ORG_ID")),
            ),
            guardrails=GuardrailConfig(
                max_query_bytes=int(
                    _strip_env(os.getenv("LOKI_MAX_QUERY_BYTES")) or "5000000000"
                ),
                max_time_window_hours=int(
                    _strip_env(os.getenv("LOKI_MAX_TIME_WINDOW_HOURS")) or "336"
                ),
                max_log_limit=int(
                    _strip_env(os.getenv("LOKI_MAX_LOG_LIMIT")) or "200"
                ),
                max_series=int(
                    _strip_env(os.getenv("LOKI_MAX_SERIES")) or "100"
                ),
                max_points_per_series=int(
                    _strip_env(os.getenv("LOKI_MAX_POINTS_PER_SERIES")) or "200"
                ),
                high_cardinality_threshold=int(
                    _strip_env(os.getenv("LOKI_HIGH_CARDINALITY_THRESHOLD")) or "10000"
                ),
            ),
            logging=LoggingConfig(
                level=_strip_env(os.getenv("MCP_LOG_LEVEL")) or "INFO",
                format=_strip_env(os.getenv("MCP_LOG_FORMAT")) or "json",  # type: ignore[arg-type]
            ),
        )
