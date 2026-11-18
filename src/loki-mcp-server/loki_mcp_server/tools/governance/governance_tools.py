"""Compactor log deletion (`/loki/api/v1/delete`) and Kubernetes Loki Operator CRD tools.

Tools:
- loki_manage_delete_requests (`governance` toolset, write/destructive-gated)
- loki_apply_operator_cr (`operator` toolset, write-gated)
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from loki_mcp_server.exceptions import LokiValidationError
from loki_mcp_server.tools.base import BaseTool
from loki_mcp_server.utils.elicitation import confirm_mutation_or_elicit
from loki_mcp_server.utils.error_handling import tool_error_boundary
from loki_mcp_server.utils.logql_helpers import (
    format_log_entries,
    validate_stream_selector,
)
from loki_mcp_server.utils.time_utils import parse_relative_time, validate_time_window


class GovernanceAndOperatorTools(BaseTool):
    """Compactor deletion (`governance`) and Kubernetes Loki Operator (`operator`) tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        loki = self.loki_service
        k8s = self.kubernetes_service
        config = self.config

        # ──────────────────────────────────────────
        # Tool 17: loki_manage_delete_requests
        # ──────────────────────────────────────────
        if config.should_register("governance", is_write=True):

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Manage Compactor Log Deletion Requests",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
                output_schema=None,
            )
            @tool_error_boundary
            async def loki_manage_delete_requests(
                action: Literal["list", "create", "cancel"] = Field(
                    ...,
                    description="Compactor deletion action: 'list' active/processed requests, 'create' a deletion request, or 'cancel' a pending request",
                ),
                query: Optional[str] = Field(
                    default=None,
                    description="LogQL stream selector + line/metadata filter for 'create' (e.g., '{app=\"auth\"} |= \"secret_token\"')",
                ),
                start: str = Field(
                    default="now-24h",
                    description="Start timestamp for 'create' (RFC3339 or relative like 'now-24h')",
                ),
                end: str = Field(
                    default="now",
                    description="End timestamp for 'create' (RFC3339 or relative like 'now')",
                ),
                request_id: Optional[str] = Field(
                    default=None,
                    description="Compactor delete request_id required when action='cancel'",
                ),
                dry_run: bool = Field(
                    default=True,
                    description="Preview blast radius (streams, bytes, sample matching lines) without executing (default: True)",
                ),
                confirm: bool = Field(
                    default=False,
                    description="Confirm destructive log deletion when dry_run=False",
                ),
                org_id: Optional[str] = Field(
                    default=None,
                    description="Optional tenant ID (X-Scope-OrgID)",
                ),
                ctx: Context = None,  # type: ignore[assignment]
            ) -> Dict[str, Any]:
                """List, preview (`dry_run=True`), create, or cancel a Loki Compactor log deletion request.

                On `action='create'`, enforces narrowing line/metadata filter guardrails (blocking
                unbounded whole-namespace deletions), estimates affected streams/bytes via
                `/loki/api/v1/index/stats`, and samples up to 5 matching log lines before executing
                `POST /loki/api/v1/delete` gated by `ctx.elicit()` or `confirm=True`.
                """
                if action == "list":
                    reqs = await loki.list_delete_requests(org_id=org_id)
                    return {
                        "status": "ok",
                        "action": "list",
                        "requests": reqs,
                        "count": len(reqs),
                    }

                if action == "cancel":
                    if not request_id or not request_id.strip():
                        raise LokiValidationError(
                            "request_id is required when action='cancel'. Read loki://compactor/delete-requests to list IDs."
                        )
                    if dry_run:
                        return {
                            "status": "dry_run_preview",
                            "dry_run": True,
                            "action": "cancel",
                            "request_id": request_id,
                            "next_step": "Call with dry_run=False and confirm=True to cancel this delete request.",
                        }
                    approved, reason = await confirm_mutation_or_elicit(
                        ctx,
                        confirm=confirm,
                        prompt_message=f"Cancel pending Loki Compactor delete request '{request_id}'?",
                    )
                    if not approved:
                        return {
                            "status": "confirmation_required",
                            "dry_run": False,
                            "approved": False,
                            "reason": reason,
                            "request_id": request_id,
                        }
                    res = await loki.cancel_delete_request(
                        request_id=request_id.strip(), org_id=org_id
                    )
                    return {**res, "dry_run": False}

                # action == "create"
                if not query or not query.strip():
                    raise LokiValidationError(
                        "query is required when action='create' (e.g., '{app=\"checkout\"} |= \"pii_email\"')."
                    )
                clean_query = validate_stream_selector(query)
                close_brace_idx = clean_query.find("}")
                pipeline_tail = (
                    clean_query[close_brace_idx + 1 :].strip()
                    if close_brace_idx != -1
                    else ""
                )
                if not pipeline_tail or not any(
                    op in pipeline_tail for op in ("|=", "|~", "!=", "!~", "| ")
                ):
                    raise LokiValidationError(
                        "Unbounded stream or whole-namespace Compactor deletion without a narrowing "
                        "line or structured-metadata filter (e.g., '|= \"leaked_pii\"' or '| user_id=\"...\"') "
                        "is blocked by safety guardrails: '/loki/api/v1/delete' rewrites every matching chunk "
                        "in object storage, causing severe Compactor I/O amplification and irreversible audit log "
                        "loss. Configure 'limits_config.retention_period' / 'retention_stream' to reclaim storage, "
                        "or add a specific line/metadata filter for targeted GDPR/PII scrubbing."
                    )
                s = parse_relative_time(start)
                e = parse_relative_time(end)
                validate_time_window(
                    s, e, max_hours=config.guardrails.max_time_window_hours
                )

                # Estimate blast radius
                stats: Dict[str, Any] = {}
                try:
                    stats = await loki.get_index_stats(
                        query=clean_query, start=s, end=e, org_id=org_id
                    )
                except Exception:
                    stats = {"streams": 0, "chunks": 0, "entries": 0, "bytes": 0}

                sample_data = await loki.query_range(
                    query=clean_query, start=s, end=e, limit=5, org_id=org_id
                )
                sample_streams = format_log_entries(
                    sample_data.get("result", []), max_lines=5
                )

                if dry_run:
                    return {
                        "status": "dry_run_preview",
                        "dry_run": True,
                        "action": "create",
                        "query": clean_query,
                        "window": {"start": start, "end": end},
                        "blast_radius_estimate": stats,
                        "sample_matching_streams": sample_streams,
                        "next_step": (
                            "Verify the blast_radius_estimate and sample_matching_streams. "
                            "To submit the deletion request to the Loki Compactor, call with "
                            "dry_run=False and confirm=True."
                        ),
                    }

                approved, reason = await confirm_mutation_or_elicit(
                    ctx,
                    confirm=confirm,
                    prompt_message=(
                        f"Submit permanent Loki Compactor log deletion for query '{clean_query}' "
                        f"({start} -> {end}, estimated entries={stats.get('entries', 'unknown')})?"
                    ),
                )
                if not approved:
                    return {
                        "status": "confirmation_required",
                        "dry_run": False,
                        "approved": False,
                        "reason": reason,
                        "query": clean_query,
                        "blast_radius_estimate": stats,
                    }

                res = await loki.create_delete_request(
                    query=clean_query, start=s, end=e, org_id=org_id
                )
                return {
                    **res,
                    "dry_run": False,
                    "blast_radius_estimate": stats,
                }

        # ──────────────────────────────────────────
        # Tool 18: loki_apply_operator_cr
        # ──────────────────────────────────────────
        if config.should_register("operator", is_write=True):

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Apply Kubernetes Loki Operator CR",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                ),
                output_schema=None,
            )
            @tool_error_boundary
            async def loki_apply_operator_cr(
                manifest_yaml: str = Field(
                    ...,
                    min_length=1,
                    description=(
                        "YAML manifest for a Loki Operator custom resource "
                        "(LokiStack, RulerConfig, AlertingRule, or RecordingRule)"
                    ),
                ),
                namespace: str = Field(
                    default="default",
                    description="Target Kubernetes namespace (used if metadata.namespace is omitted)",
                ),
                dry_run: bool = Field(
                    default=True,
                    description="Validate schema and return unified YAML diff without mutating the cluster (default: True)",
                ),
                confirm: bool = Field(
                    default=False,
                    description="Confirm Server-Side Apply when dry_run=False",
                ),
                force_conflicts: bool = Field(
                    default=False,
                    description="Force field ownership conflicts during Kubernetes Server-Side Apply",
                ),
                ctx: Context = None,  # type: ignore[assignment]
            ) -> Dict[str, Any]:
                """Validate, preview (`dry_run=True`), or Server-Side Apply a Loki Operator CR.

                Supports `LokiStack` (`loki.grafana.com/v1`), `RulerConfig`, `AlertingRule`,
                and `RecordingRule` (`loki.grafana.com/v1beta1`). Redacts secret references
                and requires `confirm=True` or MCP elicitation before applying changes.
                """
                preview = await k8s.apply_loki_operator_cr(
                    manifest_yaml=manifest_yaml,
                    namespace=namespace,
                    dry_run=True,
                    force_conflicts=force_conflicts,
                )
                if dry_run:
                    return {
                        **preview,
                        "next_step": (
                            "Review the sanitized manifest and unified diff. To apply via "
                            "Server-Side Apply, call loki_apply_operator_cr with dry_run=False and confirm=True."
                        ),
                    }

                approved, reason = await confirm_mutation_or_elicit(
                    ctx,
                    confirm=confirm,
                    prompt_message=(
                        f"Apply {preview['kind']} '{preview['namespace']}/{preview['name']}' "
                        f"to Kubernetes cluster (fieldManager={config.field_manager})?"
                    ),
                )
                if not approved:
                    return {
                        "status": "confirmation_required",
                        "dry_run": False,
                        "approved": False,
                        "reason": reason,
                        "kind": preview["kind"],
                        "namespace": preview["namespace"],
                        "name": preview["name"],
                        "diff": preview["diff"],
                    }

                applied = await k8s.apply_loki_operator_cr(
                    manifest_yaml=manifest_yaml,
                    namespace=namespace,
                    dry_run=False,
                    force_conflicts=force_conflicts,
                )
                return applied
