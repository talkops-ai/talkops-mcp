"""Application configuration management for Alertmanager MCP server."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

VALID_TOOLSETS = frozenset({"all", "triage", "routing", "silences", "governance"})
VALID_TRANSPORTS = frozenset({"stdio", "http", "sse", "streamable-http"})


def _env_or_none(name: str) -> Optional[str]:
    val = os.getenv(name)
    if val is None:
        return None
    stripped = val.strip()
    return stripped if stripped else None


def _parse_bool_env(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    norm = value.strip().lower()
    if norm in ("1", "true", "yes", "on"):
        return True
    if norm in ("0", "false", "no", "off"):
        return False
    return default


def _parse_csv_env(value: Optional[str], default: List[str]) -> List[str]:
    if value is None or not value.strip():
        return list(default)
    return [tok.strip() for tok in value.split(",") if tok.strip()]


@dataclass
class BackendConfig:
    """Configuration for a single Alertmanager backend."""

    id: str = "default"
    base_url: str = "http://localhost:9093"
    display_name: Optional[str] = None
    labels: Dict[str, str] = field(default_factory=dict)
    auth_header: Optional[str] = None
    basic_auth_username: Optional[str] = None
    basic_auth_password_env: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    path_prefix: str = ""
    metrics_path: str = "/metrics"
    verify_ssl: bool = True
    timeout: int = 30
    is_default: bool = True

    def __post_init__(self) -> None:
        self.id = self.id.strip()
        if not self.id:
            raise ValueError("Backend 'id' cannot be empty.")
        self.base_url = self.base_url.strip().rstrip("/")
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError(
                f"Backend '{self.id}' has invalid base_url '{self.base_url}'. "
                "Must start with http:// or https://."
            )
        if self.path_prefix:
            self.path_prefix = "/" + self.path_prefix.strip("/")
        if not self.metrics_path.startswith("/"):
            self.metrics_path = "/" + self.metrics_path
        if self.timeout <= 0:
            raise ValueError(
                f"Backend '{self.id}' timeout must be positive (got {self.timeout})."
            )

    @property
    def api_base_url(self) -> str:
        """Return base URL including optional reverse-proxy path prefix."""
        if self.path_prefix:
            return f"{self.base_url}{self.path_prefix}"
        return self.base_url

    def build_request_headers(self) -> Dict[str, str]:
        """Construct HTTP request headers including configured auth and custom headers."""
        req_headers: Dict[str, str] = dict(self.headers)
        if self.auth_header:
            req_headers["Authorization"] = self.auth_header
        return req_headers

    def resolve_basic_auth(self) -> Optional[tuple[str, str]]:
        """Resolve optional HTTP Basic Auth `(username, password)` from env var."""
        if not self.basic_auth_username:
            return None
        password = ""
        if self.basic_auth_password_env:
            password = os.getenv(self.basic_auth_password_env, "")
        return (self.basic_auth_username, password)


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"


@dataclass
class ServerConfig:
    """MCP server configuration."""

    name: str = "alertmanager-mcp-server"
    version: str = "0.2.1"
    transport: str = "stdio"
    host: str = "0.0.0.0"
    port: int = 8769
    path: str = "/mcp"

    allow_write: bool = False
    toolsets: List[str] = field(default_factory=lambda: ["all"])
    log_payloads: bool = False
    audit_log_path: Optional[str] = None

    backends: List[BackendConfig] = field(default_factory=lambda: [BackendConfig()])
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Silence safety & governance policy settings
    max_silence_duration_minutes: int = 1440  # 24h cap
    silence_confirm_threshold: int = 50
    silence_warning_threshold: int = 50
    silence_forbidden_sole_labels: List[str] = field(
        default_factory=lambda: [
            "severity",
            "env",
            "environment",
            "cluster",
            "region",
            "datacenter",
        ]
    )
    silence_comment_pattern: Optional[str] = None

    # Configurable Alertmanager label & annotation taxonomy
    label_env: str = "env"
    label_service: str = "service"
    label_team: str = "team"
    label_severity: str = "severity"
    severity_values: List[str] = field(
        default_factory=lambda: ["critical", "warning", "info"]
    )
    required_annotations: List[str] = field(
        default_factory=lambda: ["summary", "runbook_url"]
    )
    watchdog_alertname: str = "Watchdog"
    test_alert_label: str = "mcp_test"

    def __post_init__(self) -> None:
        if not self.backends:
            raise ValueError("At least one Alertmanager backend must be configured.")

        seen_ids: set[str] = set()
        default_count = 0
        for b in self.backends:
            if b.id in seen_ids:
                raise ValueError(
                    f"Duplicate Alertmanager backend ID '{b.id}' in configuration."
                )
            seen_ids.add(b.id)
            if b.is_default:
                default_count += 1

        if default_count > 1:
            raise ValueError(
                f"Multiple backends ({default_count}) are marked is_default=True; "
                "at most one default backend is allowed."
            )
        if default_count == 0:
            self.backends[0].is_default = True

        normalized_toolsets = [t.strip().lower() for t in self.toolsets if t.strip()]
        if not normalized_toolsets:
            normalized_toolsets = ["all"]
        unknown_toolsets = set(normalized_toolsets) - VALID_TOOLSETS
        if unknown_toolsets:
            raise ValueError(
                f"Unknown toolset(s) {sorted(unknown_toolsets)}. "
                f"Valid toolsets are: {sorted(VALID_TOOLSETS)}."
            )
        self.toolsets = normalized_toolsets

        # Keep silence_warning_threshold and silence_confirm_threshold synchronized
        if (
            self.silence_confirm_threshold == 50
            and self.silence_warning_threshold != 50
        ):
            self.silence_confirm_threshold = self.silence_warning_threshold
        else:
            self.silence_warning_threshold = self.silence_confirm_threshold

    def is_toolset_enabled(self, toolset: str) -> bool:
        """Return True if `toolset` ('triage', 'routing', 'silences', 'governance') is active."""
        ts = toolset.strip().lower()
        return "all" in self.toolsets or ts in self.toolsets


class Config:
    """Configuration loader."""

    @staticmethod
    def from_env() -> ServerConfig:
        """Load and validate configuration from environment variables."""
        backends_json = os.getenv("ALERTMANAGER_BACKENDS")
        if backends_json is not None and backends_json.strip():
            try:
                raw_backends = json.loads(backends_json)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Malformed JSON in ALERTMANAGER_BACKENDS environment variable: {exc}"
                ) from exc

            if not isinstance(raw_backends, list) or not raw_backends:
                raise ValueError(
                    "ALERTMANAGER_BACKENDS must be a non-empty JSON array of backend objects."
                )

            explicit_defaults = sum(
                1
                for item in raw_backends
                if isinstance(item, dict) and bool(item.get("is_default"))
            )
            backends: List[BackendConfig] = []
            for i, b in enumerate(raw_backends):
                if not isinstance(b, dict):
                    raise ValueError(
                        f"ALERTMANAGER_BACKENDS[{i}] must be a JSON object, got {type(b).__name__}."
                    )
                is_def = (
                    bool(b["is_default"])
                    if "is_default" in b
                    else (explicit_defaults == 0 and i == 0)
                )
                backends.append(
                    BackendConfig(
                        id=str(b.get("id", f"backend-{i}")),
                        base_url=str(b.get("base_url", "http://localhost:9093")),
                        display_name=b.get("display_name"),
                        labels=dict(b.get("labels") or {}),
                        auth_header=b.get("auth_header"),
                        basic_auth_username=b.get("basic_auth_username"),
                        basic_auth_password_env=b.get("basic_auth_password_env"),
                        headers=dict(b.get("headers") or {}),
                        path_prefix=str(b.get("path_prefix") or ""),
                        metrics_path=str(b.get("metrics_path") or "/metrics"),
                        verify_ssl=bool(b.get("verify_ssl", True)),
                        timeout=int(b.get("timeout", 30)),
                        is_default=is_def,
                    )
                )
        else:
            backends = [
                BackendConfig(
                    id=_env_or_none("ALERTMANAGER_BACKEND_ID") or "default",
                    base_url=(
                        _env_or_none("ALERTMANAGER_BASE_URL")
                        or _env_or_none("ALERTMANAGER_URL")
                        or "http://localhost:9093"
                    ),
                    display_name=_env_or_none("ALERTMANAGER_DISPLAY_NAME"),
                    auth_header=_env_or_none("ALERTMANAGER_AUTH_HEADER"),
                    basic_auth_username=_env_or_none("ALERTMANAGER_BASIC_AUTH_USERNAME"),
                    basic_auth_password_env=_env_or_none(
                        "ALERTMANAGER_BASIC_AUTH_PASSWORD_ENV"
                    ),
                    path_prefix=_env_or_none("ALERTMANAGER_PATH_PREFIX") or "",
                    metrics_path=_env_or_none("ALERTMANAGER_METRICS_PATH") or "/metrics",
                    verify_ssl=_parse_bool_env(
                        _env_or_none("ALERTMANAGER_VERIFY_SSL"), default=True
                    ),
                    timeout=int(_env_or_none("ALERTMANAGER_TIMEOUT") or "30"),
                    is_default=True,
                )
            ]

        # Read-only by default (allow_write=False).
        # MCP_ALLOW_WRITE=true enables mutations unless MCP_READ_ONLY=true overrides it.
        allow_write = _parse_bool_env(os.getenv("MCP_ALLOW_WRITE"), default=False)
        read_only_env = os.getenv("MCP_READ_ONLY")
        if read_only_env is not None:
            is_read_only = _parse_bool_env(read_only_env, default=True)
            allow_write = not is_read_only

        confirm_threshold_str = os.getenv(
            "AM_SILENCE_CONFIRM_THRESHOLD",
            os.getenv("AM_SILENCE_WARNING_THRESHOLD", "50"),
        )
        confirm_threshold = int(confirm_threshold_str)

        return ServerConfig(
            name=os.getenv("MCP_SERVER_NAME", "alertmanager-mcp-server"),
            version=os.getenv("MCP_SERVER_VERSION", "0.2.1"),
            transport=os.getenv("MCP_TRANSPORT", "stdio"),
            host=os.getenv("MCP_HOST", "0.0.0.0"),
            port=int(os.getenv("MCP_PORT", "8769")),
            path=os.getenv("MCP_PATH", "/mcp"),
            allow_write=allow_write,
            toolsets=_parse_csv_env(os.getenv("MCP_TOOLSETS"), ["all"]),
            log_payloads=_parse_bool_env(os.getenv("MCP_LOG_PAYLOADS"), default=False),
            audit_log_path=os.getenv("AM_AUDIT_LOG_PATH") or None,
            backends=backends,
            logging=LoggingConfig(
                level=os.getenv("MCP_LOG_LEVEL", "INFO"),
                format=os.getenv("MCP_LOG_FORMAT", "json"),
            ),
            max_silence_duration_minutes=int(
                os.getenv("AM_MAX_SILENCE_MINUTES", "1440")
            ),
            silence_confirm_threshold=confirm_threshold,
            silence_warning_threshold=confirm_threshold,
            silence_forbidden_sole_labels=_parse_csv_env(
                os.getenv("AM_SILENCE_FORBIDDEN_SOLE_LABELS"),
                ["severity", "env", "environment", "cluster", "region", "datacenter"],
            ),
            silence_comment_pattern=os.getenv("AM_SILENCE_COMMENT_PATTERN") or None,
            label_env=os.getenv("AM_LABEL_ENV", "env"),
            label_service=os.getenv("AM_LABEL_SERVICE", "service"),
            label_team=os.getenv("AM_LABEL_TEAM", "team"),
            label_severity=os.getenv("AM_LABEL_SEVERITY", "severity"),
            severity_values=_parse_csv_env(
                os.getenv("AM_SEVERITY_VALUES"), ["critical", "warning", "info"]
            ),
            required_annotations=_parse_csv_env(
                os.getenv("AM_REQUIRED_ANNOTATIONS"), ["summary", "runbook_url"]
            ),
            watchdog_alertname=os.getenv("AM_WATCHDOG_ALERTNAME", "Watchdog"),
            test_alert_label=os.getenv("AM_TEST_ALERT_LABEL", "mcp_test"),
        )
