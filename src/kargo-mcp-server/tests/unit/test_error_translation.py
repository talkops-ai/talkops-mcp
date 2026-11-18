"""Unit tests for translating Kargo API and domain exceptions to FastMCP ToolError."""

from __future__ import annotations

from fastmcp.exceptions import ToolError

from kargo_mcp_server.exceptions import (
    KargoApiError,
    KargoConflictError,
    KargoPermissionError,
    KargoPromotionError,
    KargoResourceNotFoundError,
    KargoValidationError,
)
from kargo_mcp_server.tools.base import translate_error


def test_translate_404_includes_resource_uri_and_tool_guidance() -> None:
    err = KargoApiError(404, "stage not found")
    tool_err = translate_error(
        err, tool_name="kargo_promote", project="guestbook", resource_name="prod"
    )
    assert isinstance(tool_err, ToolError)
    msg = str(tool_err)
    assert "not found" in msg
    assert "kargo://projects/guestbook/pipeline" in msg


def test_translate_403_includes_capabilities_and_roles_guidance() -> None:
    err = KargoApiError(403, "forbidden")
    tool_err = translate_error(
        err, tool_name="kargo_promote", project="guestbook", resource_name="prod"
    )
    msg = str(tool_err)
    assert "permission denied" in msg.lower()
    assert "kargo://server/capabilities" in msg
    assert "kargo://projects/guestbook/roles" in msg


def test_translate_409_conflict_error() -> None:
    err = KargoConflictError("Promotion already in progress")
    tool_err = translate_error(
        err, tool_name="kargo_promote", project="guestbook", resource_name="dev"
    )
    msg = str(tool_err)
    assert "conflict" in msg.lower()
    assert "kargo://projects/guestbook/pipeline" in msg


def test_translate_validation_and_permission_errors() -> None:
    val_err = KargoValidationError("Stage DAG cycle detected: dev -> prod -> dev")
    assert "Validation error" in str(translate_error(val_err, tool_name="kargo_apply_stage"))

    perm_err = KargoPermissionError("Write operations disabled")
    assert "kargo://projects/guestbook/roles" in str(
        translate_error(perm_err, tool_name="kargo_promote", project="guestbook")
    )

    not_found = KargoResourceNotFoundError("Freight 'x' not found")
    assert "kargo://projects/guestbook/pipeline" in str(
        translate_error(not_found, tool_name="kargo_promote", project="guestbook")
    )

    promo_err = KargoPromotionError("Step yaml-update failed")
    assert "kargo_diagnose_stage" in str(
        translate_error(promo_err, tool_name="kargo_promote", project="guestbook", resource_name="dev")
    )
