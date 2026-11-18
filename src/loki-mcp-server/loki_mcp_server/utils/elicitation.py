"""Human-in-the-loop MCP Elicitation gates and unified YAML diff utilities."""

from __future__ import annotations

import difflib
from typing import Any, Literal, Tuple


def compute_unified_diff(
    before_text: str,
    after_text: str,
    fromfile: str = "before",
    tofile: str = "after",
) -> str:
    """Compute a unified diff string between two YAML/text documents."""
    before_lines = before_text.splitlines(keepends=True)
    after_lines = after_text.splitlines(keepends=True)
    diff = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=fromfile,
            tofile=tofile,
        )
    )
    if not diff:
        return "(no changes)"
    return "".join(diff)


async def confirm_mutation_or_elicit(
    ctx: Any,
    confirm: bool,
    prompt_message: str,
) -> Tuple[bool, str]:
    """Gate a state-changing or destructive operation behind confirm=True or MCP Elicitation.

    Returns:
        Tuple of (approved: bool, status_reason: str).
    """
    if confirm:
        return True, "confirmed_via_parameter"

    if ctx is None or not hasattr(ctx, "elicit"):
        return (
            False,
            "Confirmation required: re-run with dry_run=True to preview or pass confirm=True "
            "after operator approval (client does not support interactive MCP elicitation).",
        )

    try:
        response = await ctx.elicit(
            prompt_message,
            response_type=Literal["confirm", "abort"],
        )
        action = getattr(response, "action", None)
        data = getattr(response, "data", None)

        if action == "accept" or response.__class__.__name__ == "AcceptedElicitation":
            if data in ("confirm", True, {"decision": "confirm"}):
                return True, "confirmed_via_elicitation"
            return False, "Operation aborted by operator via elicitation."
        if action in ("decline", "cancel") or response.__class__.__name__ in (
            "DeclinedElicitation",
            "CancelledElicitation",
        ):
            return False, f"Operation {action or 'cancelled'} by operator."
    except Exception as exc:
        return (
            False,
            f"Interactive elicitation unavailable ({exc}). "
            "Pass confirm=True after reviewing the dry_run=True preview.",
        )

    return (
        False,
        "Operation not confirmed. Review the dry_run=True preview and pass confirm=True to execute.",
    )
