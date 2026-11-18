"""Base class and safety gate helpers for all Prometheus MCP tools."""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastmcp import Context

from prometheus_mcp_server.config import ServerConfig
from prometheus_mcp_server.exceptions import (
    ConfirmationRequiredError,
    WriteAccessDeniedError,
)
from prometheus_mcp_server.services.kubernetes_service import KubernetesService
from prometheus_mcp_server.services.prometheus_service import PrometheusService
from prometheus_mcp_server.utils.audit import AuditOutcome, add_audit_entry
from prometheus_mcp_server.utils.promql_helpers import parse_duration_seconds

_REL_OFFSET_RE = re.compile(r"^(?:now)?\s*([+-])\s*(.+)$", re.IGNORECASE)


def parse_time_param(raw: Optional[str], default_ts: Optional[float] = None) -> float:
    """Parse an RFC3339 timestamp, Unix epoch float, or relative offset ('-15m', 'now-1h', '1h')."""
    now = time.time()
    if raw is None or not str(raw).strip():
        return default_ts if default_ts is not None else now

    s = str(raw).strip()
    if s.lower() == "now":
        return now

    try:
        return float(s)
    except ValueError:
        pass

    m = _REL_OFFSET_RE.match(s)
    if m:
        sign = -1.0 if m.group(1) == "-" else 1.0
        secs = parse_duration_seconds(m.group(2), default=0.0)
        if secs > 0:
            return now + sign * secs

    # Support shorthand duration like "15m" or "1h" as lookback before now
    if re.match(r"^\d+(?:\.\d+)?(?:ms|s|m|h|d|w|y)$", s):
        return now - parse_duration_seconds(s, default=300.0)

    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return default_ts if default_ts is not None else now


class BaseTool(ABC):
    """Abstract base class for all Prometheus MCP tool groups."""

    prometheus_service: PrometheusService
    kubernetes_service: KubernetesService
    config: ServerConfig

    def __init__(self, service_locator: Dict[str, Any]):
        self.prometheus_service = service_locator.get("prometheus_service")  # type: ignore[assignment]
        self.kubernetes_service = service_locator.get("kubernetes_service")  # type: ignore[assignment]
        self.config = service_locator.get("config") or ServerConfig()

    def should_register(self, toolset: str, is_write: bool = False) -> bool:
        """Check whether a tool in `toolset` should be registered on the FastMCP server."""
        if self.config is None:
            return True
        return self.config.should_register(toolset, is_write=is_write)

    def ensure_write_allowed(self, backend_id: str, operation: str) -> None:
        """Raise WriteAccessDeniedError if the server is running in read-only mode."""
        if self.config and not self.config.allow_write:
            add_audit_entry(
                backend_id=backend_id,
                operation=operation,
                summary=f"Denied mutating operation '{operation}' in read-only mode",
                outcome="denied",
                audit_log_path=self.config.audit_log_path,
            )
            raise WriteAccessDeniedError(
                f"Operation '{operation}' is disabled because the Prometheus MCP server "
                "is running in read-only mode (MCP_ALLOW_WRITE=false / --read-only). "
                "Start the server with '--allow-write' or set MCP_ALLOW_WRITE=true to enable mutations."
            )

    async def confirm_or_elicit(
        self,
        ctx: Optional[Context],
        *,
        confirm: bool,
        prompt_message: str,
        backend_id: str,
        operation: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Verify confirmation for state mutations via `confirm=True` or interactive `ctx.elicit()`."""
        if confirm:
            return

        audit_path = self.config.audit_log_path if self.config else None
        if ctx is not None and hasattr(ctx, "elicit"):
            try:
                elicit_result = await ctx.elicit(prompt_message, response_type=bool)
                action = getattr(elicit_result, "action", None)
                data = getattr(elicit_result, "data", None)
                if action == "accept" and data is not False:
                    return
                add_audit_entry(
                    backend_id=backend_id,
                    operation=operation,
                    summary=f"User declined confirmation for {operation}",
                    outcome="aborted",
                    details=details,
                    audit_log_path=audit_path,
                )
                raise ConfirmationRequiredError(
                    f"Operation '{operation}' was aborted because interactive confirmation was declined."
                )
            except ConfirmationRequiredError:
                raise
            except Exception:
                pass

        add_audit_entry(
            backend_id=backend_id,
            operation=operation,
            summary=f"Confirmation required for {operation}: {prompt_message}",
            outcome="confirmation_required",
            details=details,
            audit_log_path=audit_path,
        )
        raise ConfirmationRequiredError(
            f"{prompt_message} "
            "Run with dry_run=True to preview changes first, then re-run with dry_run=False and confirm=True."
        )

    def record_audit(
        self,
        backend_id: str,
        operation: str,
        summary: str,
        *,
        outcome: AuditOutcome = "succeeded",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an audit entry for a write or dry-run operation."""
        audit_path = self.config.audit_log_path if self.config else None
        add_audit_entry(
            backend_id=backend_id,
            operation=operation,
            summary=summary,
            outcome=outcome,
            details=details,
            audit_log_path=audit_path,
        )

    @abstractmethod
    def register(self, mcp_instance: Any) -> None:
        """Register tools with the FastMCP server instance."""
        pass
