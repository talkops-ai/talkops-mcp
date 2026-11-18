"""Silence lifecycle, preview, and safety-gated mutation tools (`silences` toolset)."""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from alertmanager_mcp_server.domain.matchers import (
    MatcherValidationError,
    match_all,
    parse_matcher_set,
)
from alertmanager_mcp_server.domain.timeparse import (
    format_rfc3339_utc,
    parse_rfc3339,
)
from alertmanager_mcp_server.exceptions import (
    AlertmanagerValidationError,
    SilenceSafetyError,
)
from alertmanager_mcp_server.models.alert import AlertMatcher
from alertmanager_mcp_server.models.responses import (
    ExpireSilenceResponse,
    SilenceListResponse,
    SilenceMutationResponse,
    SilencePreviewResponse,
)
from alertmanager_mcp_server.models.silence import PostableSilence
from alertmanager_mcp_server.tools._confirmation import (
    confirm_or_elicit,
    ensure_write_allowed,
    safe_ctx_info,
)
from alertmanager_mcp_server.tools.base import BaseTool
from alertmanager_mcp_server.utils.audit import add_audit_entry

SilenceStateFilter = Literal["active", "pending", "expired", "all"]
SilenceScope = Literal["instance", "service"]


class SilenceTools(BaseTool):
    """Tools for querying, previewing, creating, updating, and expiring Alertmanager silences."""

    def register(self, mcp_instance: object) -> None:
        if not self.config.is_toolset_enabled("silences"):
            return

        mcp: Any = mcp_instance

        @mcp.tool(
            annotations=ToolAnnotations(
                title="List Silences",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def am_list_silences(
            backend_id: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Alertmanager backend ID (defaults to primary backend)",
                ),
            ] = None,
            state: Annotated[
                SilenceStateFilter,
                Field(
                    default="active",
                    description="Filter silences by state: active, pending, expired, or all",
                ),
            ] = "active",
            matchers: Annotated[
                Optional[List[str] | Dict[str, str] | str],
                Field(
                    default=None,
                    description="Optional matcher filter (e.g. 'service=\"checkout\"' or {'env': 'prod'})",
                ),
            ] = None,
            created_by: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Substring filter on silence creator (createdBy)",
                ),
            ] = None,
            comment_search: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Substring filter on silence comment or ticket ID",
                ),
            ] = None,
            limit: Annotated[
                int,
                Field(
                    default=50,
                    ge=1,
                    le=500,
                    description="Maximum silences per page (1..500)",
                ),
            ] = 50,
            offset: Annotated[
                int,
                Field(default=0, ge=0, description="Pagination offset"),
            ] = 0,
            ctx: Optional[Context] = None,
        ) -> SilenceListResponse:
            """List silences with state, matcher, author, and comment filtering."""
            bid = self.alertmanager_service.resolve_backend_id(backend_id)
            await safe_ctx_info(
                ctx, f"Listing silences on backend '{bid}' (state={state})"
            )

            compiled_filter = None
            if matchers is not None:
                try:
                    compiled_filter = parse_matcher_set(matchers)
                except MatcherValidationError as exc:
                    raise AlertmanagerValidationError(
                        f"Invalid matchers filter: {exc}"
                    ) from exc

            silences, total, has_more, _ = (
                await self.alertmanager_service.list_silences_with_total(
                    bid,
                    state=state,
                    filter_matchers=compiled_filter,
                    created_by=created_by,
                    comment_search=comment_search,
                    limit=limit,
                    offset=offset,
                )
            )
            return SilenceListResponse(
                backend_id=bid,
                total=total,
                offset=offset,
                limit=limit,
                has_more=has_more,
                silences=[s.model_dump(mode="json") for s in silences],
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                title="Preview Silence Blast Radius & Policy",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def am_preview_silence(
            matchers: Annotated[
                List[Dict[str, Any] | str] | Dict[str, str] | str,
                Field(
                    description=(
                        "Matchers to preview as API matcher objects, matcher strings "
                        "(['alertname=\"HighLatency\"', 'service=\"checkout\"']), or label dict"
                    )
                ),
            ],
            backend_id: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Alertmanager backend ID (defaults to primary backend)",
                ),
            ] = None,
            duration_minutes: Annotated[
                Optional[int],
                Field(
                    default=120,
                    ge=1,
                    description="Proposed silence duration in minutes",
                ),
            ] = 120,
            starts_at: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Optional RFC3339 start timestamp with timezone offset (e.g. '2026-03-29T10:00:00Z')",
                ),
            ] = None,
            ends_at: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Optional RFC3339 end timestamp with timezone offset",
                ),
            ] = None,
            created_by: Annotated[
                Optional[str],
                Field(
                    default="preview-operator",
                    description="Proposed creator attribution to validate against SP008",
                ),
            ] = "preview-operator",
            comment: Annotated[
                Optional[str],
                Field(
                    default="CHG-000: Dry-run silence preview",
                    description="Proposed comment/ticket justification to validate against SP009",
                ),
            ] = "CHG-000: Dry-run silence preview",
            ctx: Optional[Context] = None,
        ) -> SilencePreviewResponse:
            """Dry-run a silence against active alerts, routing receivers, overlapping silences, and `SilencePolicy` (`SP001`–`SP010`)."""
            bid = self.alertmanager_service.resolve_backend_id(backend_id)
            await safe_ctx_info(ctx, f"Previewing silence on backend '{bid}'")

            preview = await self.alertmanager_service.preview_silence(
                bid,
                matchers=matchers,
                starts_at=starts_at,
                ends_at=ends_at,
                duration_minutes=duration_minutes,
                created_by=created_by,
                comment=comment,
            )
            return SilencePreviewResponse(**preview)

        if self.config.allow_write:

            @mcp.tool(
                annotations=ToolAnnotations(
                    title="Create Silence",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                )
            )
            async def am_create_silence(
                matchers: Annotated[
                    List[Dict[str, Any] | str] | Dict[str, str] | str,
                    Field(
                        description=(
                            "Silence matchers as API matcher dicts, matcher strings "
                            "(['alertname=\"HighLatency\"', 'service=\"checkout\"']), or label dict"
                        )
                    ),
                ],
                created_by: Annotated[
                    str,
                    Field(
                        min_length=1,
                        description="Operator identity or email creating the silence (required by SP008)",
                    ),
                ],
                comment: Annotated[
                    str,
                    Field(
                        min_length=3,
                        description="Maintenance ticket ID, incident link, or justification (required by SP009)",
                    ),
                ],
                backend_id: Annotated[
                    Optional[str],
                    Field(
                        default=None,
                        description="Alertmanager backend ID (defaults to primary backend)",
                    ),
                ] = None,
                duration_minutes: Annotated[
                    Optional[int],
                    Field(
                        default=None,
                        ge=1,
                        description="Silence duration in minutes (defaults to 120 if ends_at is omitted)",
                    ),
                ] = None,
                starts_at: Annotated[
                    Optional[str],
                    Field(
                        default=None,
                        description="Explicit RFC3339 start timestamp with timezone offset (e.g. '2026-03-29T10:00:00Z')",
                    ),
                ] = None,
                ends_at: Annotated[
                    Optional[str],
                    Field(
                        default=None,
                        description="Explicit RFC3339 end timestamp with timezone offset",
                    ),
                ] = None,
                confirm: Annotated[
                    bool,
                    Field(
                        default=False,
                        description="Set True to confirm high-blast-radius or broad critical silences",
                    ),
                ] = False,
                ctx: Optional[Context] = None,
            ) -> SilenceMutationResponse:
                """Create an Alertmanager silence after enforcing `SilencePolicy` (`SP001`–`SP010`), deduplication, and blast-radius confirmation."""
                bid = self.alertmanager_service.resolve_backend_id(backend_id)
                ensure_write_allowed(
                    self.config,
                    backend_id=bid,
                    operation="create_silence",
                    principal=created_by,
                )

                preview = await self.alertmanager_service.preview_silence(
                    bid,
                    matchers=matchers,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    duration_minutes=duration_minutes,
                    created_by=created_by,
                    comment=comment,
                )
                policy_dict = preview["policy"]
                if not preview["valid"]:
                    violations = policy_dict.get("violations") or []
                    msg = "; ".join(
                        f"[{v['rule_id']}] {v['message']} Remediation: {v['remediation']}"
                        for v in violations
                    )
                    add_audit_entry(
                        backend_id=bid,
                        operation="create_silence",
                        principal=created_by,
                        summary=f"Policy violation: {msg}",
                        outcome="denied",
                        audit_log_path=self.config.audit_log_path,
                    )
                    raise SilenceSafetyError(
                        f"Silence rejected by safety policy: {msg}"
                    )

                if preview["requires_confirmation"]:
                    await confirm_or_elicit(
                        ctx,
                        confirm=confirm,
                        prompt_message=(
                            f"Silence on '{bid}' triggers safety confirmation: "
                            f"{preview.get('warning_message') or 'High blast radius'}."
                        ),
                        backend_id=bid,
                        operation="create_silence",
                        principal=created_by,
                        audit_log_path=self.config.audit_log_path,
                        details={"matchers": policy_dict.get("matchers")},
                    )

                model_matchers = [
                    AlertMatcher(**m) for m in policy_dict["matchers"]
                ]
                dup = await self.alertmanager_service.find_duplicate_silence(
                    bid, model_matchers
                )
                if dup is not None:
                    dup_start = parse_rfc3339(dup.startsAt, require_tz=False)
                    dup_end = parse_rfc3339(dup.endsAt, require_tz=False)
                    dup_dur = round(
                        (dup_end - dup_start).total_seconds() / 60.0, 2
                    )
                    return SilenceMutationResponse(
                        backend_id=bid,
                        silence_id=dup.id,
                        deduped=True,
                        matchers=[m.model_dump() for m in dup.matchers],
                        starts_at=format_rfc3339_utc(dup_start),
                        ends_at=format_rfc3339_utc(dup_end),
                        duration_minutes=dup_dur,
                        created_by=dup.createdBy,
                        comment=dup.comment,
                        affected_alert_count=preview["affected_alert_count"],
                        policy_warnings=policy_dict.get("warnings") or [],
                        message=(
                            f"Equivalent active silence '{dup.id}' already exists on '{bid}'; "
                            "reusing existing silence."
                        ),
                    )

                start_dt = parse_rfc3339(
                    policy_dict["starts_at"], require_tz=True
                )
                end_dt = parse_rfc3339(policy_dict["ends_at"], require_tz=True)
                postable = PostableSilence(
                    matchers=model_matchers,
                    startsAt=start_dt,
                    endsAt=end_dt,
                    createdBy=created_by.strip(),
                    comment=comment.strip(),
                )
                created = await self.alertmanager_service.create_silence(
                    bid, postable
                )
                add_audit_entry(
                    backend_id=bid,
                    operation="create_silence",
                    principal=created_by.strip(),
                    summary=(
                        f"id={created.id} matchers={[m.model_dump() for m in model_matchers]} "
                        f"affected={preview['affected_alert_count']}"
                    ),
                    outcome="succeeded",
                    details={
                        "silence_id": created.id,
                        "starts_at": policy_dict["starts_at"],
                        "ends_at": policy_dict["ends_at"],
                    },
                    audit_log_path=self.config.audit_log_path,
                )
                return SilenceMutationResponse(
                    backend_id=bid,
                    silence_id=created.id,
                    deduped=False,
                    matchers=[m.model_dump() for m in created.matchers],
                    starts_at=policy_dict["starts_at"],
                    ends_at=policy_dict["ends_at"],
                    duration_minutes=float(policy_dict["duration_minutes"]),
                    created_by=created.createdBy,
                    comment=created.comment,
                    affected_alert_count=preview["affected_alert_count"],
                    policy_warnings=policy_dict.get("warnings") or [],
                    message=(
                        f"Created silence '{created.id}' on '{bid}' until {policy_dict['ends_at']} "
                        f"(affecting {preview['affected_alert_count']} active alert(s))."
                    ),
                )

            @mcp.tool(
                annotations=ToolAnnotations(
                    title="Silence Specific Alert by Fingerprint or Labels",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                )
            )
            async def am_silence_alert(
                created_by: Annotated[
                    str,
                    Field(
                        min_length=1,
                        description="Operator identity or email creating the silence (required by SP008)",
                    ),
                ],
                comment: Annotated[
                    str,
                    Field(
                        min_length=3,
                        description="Ticket ID, incident link, or justification (required by SP009)",
                    ),
                ],
                backend_id: Annotated[
                    Optional[str],
                    Field(
                        default=None,
                        description="Alertmanager backend ID (defaults to primary backend)",
                    ),
                ] = None,
                fingerprint: Annotated[
                    Optional[str],
                    Field(
                        default=None,
                        description="Target alert fingerprint to derive matchers from",
                    ),
                ] = None,
                labels: Annotated[
                    Optional[Dict[str, str]],
                    Field(
                        default=None,
                        description="Alert labels dictionary if fingerprint is not provided",
                    ),
                ] = None,
                scope: Annotated[
                    SilenceScope,
                    Field(
                        default="service",
                        description=(
                            "Matcher derivation scope: 'instance' (all alert labels) or "
                            "'service' (alertname + service + env)"
                        ),
                    ),
                ] = "service",
                duration_minutes: Annotated[
                    int,
                    Field(
                        default=60,
                        ge=1,
                        description="Silence duration in minutes (default 60)",
                    ),
                ] = 60,
                confirm: Annotated[
                    bool,
                    Field(
                        default=False,
                        description="Set True to confirm high-blast-radius silences",
                    ),
                ] = False,
                ctx: Optional[Context] = None,
            ) -> SilenceMutationResponse:
                """Derive scoped matchers (`instance` or `service`) from a firing alert and create a policy-validated silence."""
                bid = self.alertmanager_service.resolve_backend_id(backend_id)
                ensure_write_allowed(
                    self.config,
                    backend_id=bid,
                    operation="silence_alert",
                    principal=created_by,
                )

                resolved_labels: Dict[str, str] = {}
                if fingerprint:
                    target_alert = (
                        await self.alertmanager_service.get_alert_by_fingerprint(
                            bid, fingerprint
                        )
                    )
                    resolved_labels = dict(target_alert.labels)
                elif labels and isinstance(labels, dict):
                    resolved_labels = {str(k): str(v) for k, v in labels.items()}
                else:
                    raise AlertmanagerValidationError(
                        "Either 'fingerprint' or non-empty 'labels' must be provided to am_silence_alert."
                    )

                if scope == "instance":
                    derived_dict = dict(resolved_labels)
                elif scope == "service":
                    candidate_keys = (
                        "alertname",
                        self.config.label_service,
                        self.config.label_env,
                        "instance",
                        "job",
                        "namespace",
                    )
                    derived_dict = {}
                    for k in ("alertname", self.config.label_service, self.config.label_env):
                        if k in resolved_labels:
                            derived_dict[k] = resolved_labels[k]
                    # Ensure we have more than just broad env/severity labels
                    if "alertname" not in derived_dict and "service" not in derived_dict:
                        for k in candidate_keys:
                            if k in resolved_labels:
                                derived_dict[k] = resolved_labels[k]
                    if not derived_dict:
                        derived_dict = dict(resolved_labels)
                else:
                    raise SilenceSafetyError(
                        f"Unsupported silence scope '{scope}'. Only 'instance' and 'service' "
                        "scopes are allowed (environment-wide 'env' scope is prohibited by SP004)."
                    )

                return await am_create_silence(
                    matchers=derived_dict,
                    created_by=created_by,
                    comment=comment,
                    backend_id=bid,
                    duration_minutes=duration_minutes,
                    starts_at=None,
                    ends_at=None,
                    confirm=confirm,
                    ctx=ctx,
                )

            @mcp.tool(
                annotations=ToolAnnotations(
                    title="Update Silence in Place",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def am_update_silence(
                silence_id: Annotated[
                    str,
                    Field(
                        min_length=1,
                        description="Existing active silence ID to update",
                    ),
                ],
                updated_by: Annotated[
                    str,
                    Field(
                        min_length=1,
                        description="Operator identity performing the update (required by SP008)",
                    ),
                ],
                backend_id: Annotated[
                    Optional[str],
                    Field(
                        default=None,
                        description="Alertmanager backend ID (defaults to primary backend)",
                    ),
                ] = None,
                duration_minutes: Annotated[
                    Optional[int],
                    Field(
                        default=None,
                        ge=1,
                        description="New duration in minutes from current time (or original start)",
                    ),
                ] = None,
                new_ends_at: Annotated[
                    Optional[str],
                    Field(
                        default=None,
                        description="Explicit new RFC3339 end timestamp with timezone offset",
                    ),
                ] = None,
                comment: Annotated[
                    Optional[str],
                    Field(
                        default=None,
                        description="Updated comment/justification",
                    ),
                ] = None,
                confirm: Annotated[
                    bool,
                    Field(
                        default=False,
                        description="Set True to confirm high-blast-radius updates",
                    ),
                ] = False,
                ctx: Optional[Context] = None,
            ) -> SilenceMutationResponse:
                """Atomically update an active silence via `POST /api/v2/silences` with `id`, enforcing the total lifetime cap (`SP007`)."""
                bid = self.alertmanager_service.resolve_backend_id(backend_id)
                ensure_write_allowed(
                    self.config,
                    backend_id=bid,
                    operation="update_silence",
                    principal=updated_by,
                )
                if duration_minutes is None and new_ends_at is None and comment is None:
                    raise AlertmanagerValidationError(
                        "Provide at least one of 'duration_minutes', 'new_ends_at', or 'comment' to update the silence."
                    )

                try:
                    updated, policy_res = (
                        await self.alertmanager_service.update_silence(
                            bid,
                            silence_id,
                            new_ends_at=new_ends_at,
                            duration_minutes=duration_minutes,
                            new_comment=comment,
                            updated_by=updated_by,
                        )
                    )
                except SilenceSafetyError as exc:
                    add_audit_entry(
                        backend_id=bid,
                        operation="update_silence",
                        principal=updated_by.strip(),
                        summary=f"Policy violation on id={silence_id}: {exc}",
                        outcome="denied",
                        details={"silence_id": silence_id},
                        audit_log_path=self.config.audit_log_path,
                    )
                    raise
                add_audit_entry(
                    backend_id=bid,
                    operation="update_silence",
                    principal=updated_by.strip(),
                    summary=(
                        f"id={updated.id} prev_id={silence_id} "
                        f"ends_at={policy_res.ends_at_utc}"
                    ),
                    outcome="succeeded",
                    details={
                        "silence_id": updated.id,
                        "previous_silence_id": silence_id,
                        "ends_at": policy_res.ends_at_utc,
                    },
                    audit_log_path=self.config.audit_log_path,
                )
                return SilenceMutationResponse(
                    backend_id=bid,
                    silence_id=updated.id,
                    deduped=False,
                    previous_silence_id=silence_id,
                    matchers=[m.model_dump() for m in updated.matchers],
                    starts_at=policy_res.starts_at_utc or "",
                    ends_at=policy_res.ends_at_utc or "",
                    duration_minutes=float(policy_res.duration_minutes or 0.0),
                    created_by=updated.createdBy,
                    comment=updated.comment,
                    policy_warnings=[w.to_dict() for w in policy_res.warnings],
                    message=(
                        f"Updated silence '{updated.id}' on '{bid}' "
                        f"(new ends_at: {policy_res.ends_at_utc})."
                    ),
                )

            @mcp.tool(
                annotations=ToolAnnotations(
                    title="Expire Silence",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def am_expire_silence(
                silence_id: Annotated[
                    str,
                    Field(
                        min_length=1,
                        description="Active silence ID to expire",
                    ),
                ],
                expired_by: Annotated[
                    str,
                    Field(
                        min_length=1,
                        description="Operator identity expiring the silence",
                    ),
                ],
                reason: Annotated[
                    str,
                    Field(
                        min_length=3,
                        description="Audit reason for expiring the silence (e.g. 'CHG-1042 completed early')",
                    ),
                ],
                backend_id: Annotated[
                    Optional[str],
                    Field(
                        default=None,
                        description="Alertmanager backend ID (defaults to primary backend)",
                    ),
                ] = None,
                confirm: Annotated[
                    bool,
                    Field(
                        default=False,
                        description="Set True to confirm expiring the silence and reactivating notifications",
                    ),
                ] = False,
                ctx: Optional[Context] = None,
            ) -> ExpireSilenceResponse:
                """Expire an active silence after previewing how many suppressed alerts will immediately resume paging."""
                bid = self.alertmanager_service.resolve_backend_id(backend_id)
                ensure_write_allowed(
                    self.config,
                    backend_id=bid,
                    operation="expire_silence",
                    principal=expired_by,
                )

                existing = await self.alertmanager_service.get_silence(
                    bid, silence_id
                )
                compiled_s = parse_matcher_set(existing.matchers)

                # Inspect silenced alerts that will reactivate when this silence expires
                silenced_alerts, _, _ = (
                    await self.alertmanager_service.list_alerts(
                        bid,
                        active=False,
                        silenced=True,
                        inhibited=False,
                        limit=500,
                        offset=0,
                    )
                )
                reactivated = []
                for a in silenced_alerts:
                    s_by = (a.status or {}).get("silencedBy") or []
                    if silence_id in s_by or (
                        compiled_s and match_all(compiled_s, a.labels)
                    ):
                        reactivated.append(
                            {
                                "fingerprint": a.fingerprint,
                                "alertname": a.labels.get(
                                    "alertname", "unknown"
                                ),
                                "labels": a.labels,
                            }
                        )

                await confirm_or_elicit(
                    ctx,
                    confirm=confirm,
                    prompt_message=(
                        f"Expiring silence '{silence_id}' on '{bid}' will immediately "
                        f"reactivate notifications for {len(reactivated)} suppressed alert(s)."
                    ),
                    backend_id=bid,
                    operation="expire_silence",
                    principal=expired_by,
                    audit_log_path=self.config.audit_log_path,
                    details={
                        "silence_id": silence_id,
                        "reactivated_alert_count": len(reactivated),
                        "reason": reason,
                    },
                )

                await self.alertmanager_service.delete_silence(bid, silence_id)
                add_audit_entry(
                    backend_id=bid,
                    operation="expire_silence",
                    principal=expired_by.strip(),
                    summary=(
                        f"id={silence_id} reason='{reason.strip()}' "
                        f"reactivated={len(reactivated)}"
                    ),
                    outcome="succeeded",
                    details={
                        "silence_id": silence_id,
                        "reason": reason.strip(),
                        "reactivated_alert_count": len(reactivated),
                    },
                    audit_log_path=self.config.audit_log_path,
                )
                return ExpireSilenceResponse(
                    backend_id=bid,
                    silence_id=silence_id,
                    status="expired",
                    expired_by=expired_by.strip(),
                    reason=reason.strip(),
                    reactivated_alert_count=len(reactivated),
                    reactivated_alerts_preview=reactivated[:20],
                    message=(
                        f"Silence '{silence_id}' expired on '{bid}' by {expired_by.strip()} "
                        f"({len(reactivated)} alert(s) reactivated)."
                    ),
                )
