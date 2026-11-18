"""Write-access gate and interactive MCP elicitation / confirmation helper."""

from __future__ import annotations

from typing import Any, Optional

from fastmcp import Context

from alertmanager_mcp_server.config import ServerConfig
from alertmanager_mcp_server.exceptions import (
    ConfirmationRequiredError,
    WriteAccessDeniedError,
)
from alertmanager_mcp_server.utils.audit import add_audit_entry


async def safe_ctx_info(ctx: Optional[Context], message: str) -> None:
    """Emit an MCP info log message only when an active MCP request session exists."""
    if ctx is not None and getattr(ctx, "request_context", None) is not None:
        try:
            await ctx.info(message)
        except Exception:
            pass


def ensure_write_allowed(
    config: ServerConfig,
    *,
    backend_id: str,
    operation: str,
    principal: str = "unknown",
) -> None:
    """Ensure the server is configured with `allow_write=True`, else audit & raise."""
    if not config.allow_write:
        add_audit_entry(
            backend_id=backend_id,
            operation=operation,
            principal=principal,
            summary="Denied mutating operation while server is in read-only mode",
            outcome="denied",
            audit_log_path=config.audit_log_path,
        )
        raise WriteAccessDeniedError(
            f"Operation '{operation}' is disabled because the Alertmanager MCP server "
            "is running in read-only mode (MCP_ALLOW_WRITE=false). "
            "Start the server with '--allow-write' or set MCP_ALLOW_WRITE=true to enable mutations."
        )


async def confirm_or_elicit(
    ctx: Optional[Context],
    *,
    confirm: bool,
    prompt_message: str,
    backend_id: str,
    operation: str,
    principal: str,
    audit_log_path: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    """Confirm a high-impact or destructive mutation via `confirm=True` or `ctx.elicit()`."""
    if confirm:
        return

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
                principal=principal,
                summary=f"User declined confirmation for {operation}",
                outcome="aborted",
                details=details,
                audit_log_path=audit_log_path,
            )
            raise ConfirmationRequiredError(
                f"Operation '{operation}' was aborted because confirmation was declined."
            )
        except ConfirmationRequiredError:
            raise
        except Exception:
            # Client does not support interactive elicitation; fall through to confirm=True error
            pass

    add_audit_entry(
        backend_id=backend_id,
        operation=operation,
        principal=principal,
        summary=f"Confirmation required for {operation}: {prompt_message}",
        outcome="confirmation_required",
        details=details,
        audit_log_path=audit_log_path,
    )
    raise ConfirmationRequiredError(
        f"{prompt_message} "
        "Review the impact with the user and re-run this tool with confirm=True to proceed."
    )
