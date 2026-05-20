"""Silence lifecycle management tools — granular pattern."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Annotated
from pydantic import Field
from fastmcp import Context
from mcp.types import ToolAnnotations
from alertmanager_mcp_server.models.alert import AlertMatcher
from alertmanager_mcp_server.models.silence import PostableSilence
from alertmanager_mcp_server.utils import compute_silence_window
from alertmanager_mcp_server.utils.audit import add_audit_entry
from alertmanager_mcp_server.tools.base import BaseTool


class SilenceTools(BaseTool):
    """Tools for managing the full silence lifecycle in Alertmanager."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="List Silences",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def am_list_silences(
            backend_id: Annotated[str, Field(min_length=1, description="Alertmanager backend ID")],
            state: Annotated[Optional[str], Field(description="Filter: active, pending, or expired")] = None,
            limit: Annotated[Optional[int], Field(description="Max results (default 50)")] = 50,
            offset: Annotated[Optional[int], Field(description="Pagination offset")] = 0,
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Any:
            """List silences with optional state filter and pagination.

            Use this to inspect current and historical silences. Read-only.

            Returns:
            - {\"silences\": [{...}], \"has_more\": bool, \"next_offset\": int|null}

            When NOT to use: For creating or modifying silences, use am_create_silence
            or am_update_silence.
            """
            await ctx.info("Listing silences")
            try:
                silences, has_more, next_offset = await self.alertmanager_service.list_silences(
                    backend_id, state=state, limit=limit or 50, offset=offset or 0,
                )
                return {
                    "silences": [s.model_dump(mode="json") for s in silences],
                    "has_more": has_more,
                    "next_offset": next_offset,
                }
            except Exception as e:
                await ctx.error(str(e))
                return {"error": str(e), "isError": True}

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Create Silence",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def am_create_silence(
            backend_id: Annotated[str, Field(min_length=1, description="Alertmanager backend ID")],
            matchers: Annotated[List[Dict[str, Any]], Field(description="Matchers: [{name, value, isRegex, isEqual}] (must be a JSON array of objects)")],
            duration_minutes: Annotated[Optional[int], Field(description="Silence duration in minutes")] = None,
            starts_at: Annotated[Optional[str], Field(description="Explicit start (ISO 8601)")] = None,
            ends_at: Annotated[Optional[str], Field(description="Explicit end (ISO 8601)")] = None,
            created_by: Annotated[Optional[str], Field(description="Who is creating the silence (required)")] = "mcp",
            comment: Annotated[Optional[str], Field(description="Reason/justification (required)")] = "Silence created via Alertmanager MCP",
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Any:
            """Create a silence to suppress matching alerts.

            Use this for planned maintenance windows or to temporarily mute known
            alerts. MUTATES STATE. Checks for duplicate silences before creating.

            Safety: Max duration is capped at 24h by default. Use am_preview_silence
            before creating broad silences.

            Returns:
            - {\"silence_id\": str, \"silence\": {...}}

            When NOT to use: For quickly silencing a specific alert by fingerprint,
            use am_silence_alert instead.

            Common errors:
            - Duration cap exceeded: Cannot exceed the configured max (default 24h/1440m).
            - Duplicate silence: If an equivalent active silence exists, creation is blocked.
            """
            await ctx.info("Creating silence")
            try:
                max_dur = self.config.max_silence_duration_minutes
                if duration_minutes and duration_minutes > max_dur:
                    return {"error": f"Duration {duration_minutes}m exceeds {max_dur}m cap.", "isError": True}
                parsed_matchers = [AlertMatcher(**m) for m in matchers]
                dup = await self.alertmanager_service.find_duplicate_silence(backend_id, parsed_matchers)
                if dup:
                    return {
                        "warning": "An equivalent active silence already exists.",
                        "existing_silence_id": dup.id,
                        "silence": dup.model_dump(mode="json"),
                    }
                now = datetime.now(timezone.utc)
                sa = datetime.fromisoformat(starts_at) if starts_at else None
                ea = datetime.fromisoformat(ends_at) if ends_at else None
                start, end = compute_silence_window(duration_minutes, sa, ea, now)
                silence = PostableSilence(
                    matchers=parsed_matchers, startsAt=start, endsAt=end,
                    createdBy=created_by or "mcp", comment=comment or "Silence via MCP",
                )
                created = await self.alertmanager_service.create_silence(backend_id, silence)
                add_audit_entry(
                    backend_id=backend_id, operation="create_silence",
                    principal=created_by or "mcp",
                    summary=f"id={created.id} matchers={[m.name + '=' + m.value for m in parsed_matchers]}",
                )
                return {"silence_id": created.id, "silence": created.model_dump(mode="json")}
            except Exception as e:
                await ctx.error(str(e))
                return {"error": str(e), "isError": True}

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Update Silence",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def am_update_silence(
            backend_id: Annotated[str, Field(min_length=1, description="Alertmanager backend ID")],
            silence_id: Annotated[str, Field(min_length=1, description="ID of the silence to update")],
            add_minutes: Annotated[Optional[int], Field(description="Minutes to add to the silence window")] = None,
            new_ends_at: Annotated[Optional[str], Field(description="New end time (ISO 8601)")] = None,
            comment: Annotated[Optional[str], Field(description="Updated comment/reason")] = None,
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Any:
            """Update an existing silence (extend duration or modify end time).

            Use this to extend a maintenance window or adjust the silence duration.
            The old silence is expired and a new one is created with the updated
            parameters. MUTATES STATE.

            Returns:
            - {\"new_silence_id\": str, \"silence\": {...}}

            Common errors:
            - Extension exceeds cap: Cannot exceed the configured max (default 24h/1440m).
            - Silence not found: Verify the silence_id is valid via am_list_silences.
            """
            await ctx.info(f"Updating silence: {silence_id}")
            try:
                existing = await self.alertmanager_service.get_silence(backend_id, silence_id)
                now = datetime.now(timezone.utc)

                # Determine new end time
                if new_ends_at:
                    new_end = datetime.fromisoformat(new_ends_at)
                elif add_minutes:
                    max_dur = self.config.max_silence_duration_minutes
                    if add_minutes > max_dur:
                        return {"error": f"Extension {add_minutes}m exceeds {max_dur}m cap.", "isError": True}
                    base = existing.endsAt if existing.endsAt > now else now
                    new_end = base + timedelta(minutes=add_minutes)
                else:
                    return {"error": "Provide 'add_minutes' or 'new_ends_at'.", "isError": True}

                updated_comment = comment or f"{existing.comment} (extended via MCP)"
                new_silence = PostableSilence(
                    matchers=existing.matchers, startsAt=existing.startsAt, endsAt=new_end,
                    createdBy=existing.createdBy, comment=updated_comment,
                )
                created = await self.alertmanager_service.create_silence(backend_id, new_silence)
                await self.alertmanager_service.delete_silence(backend_id, existing.id)
                add_audit_entry(
                    backend_id=backend_id, operation="update_silence",
                    principal=existing.createdBy,
                    summary=f"old_id={existing.id} new_id={created.id} add_minutes={add_minutes}",
                )
                return {"new_silence_id": created.id, "silence": created.model_dump(mode="json")}
            except Exception as e:
                await ctx.error(str(e))
                return {"error": str(e), "isError": True}

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Expire Silence",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def am_expire_silence(
            backend_id: Annotated[str, Field(min_length=1, description="Alertmanager backend ID")],
            silence_id: Annotated[str, Field(min_length=1, description="ID of the silence to expire")],
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Any:
            """Expire a silence to reactivate alert notifications.

            Use this when a maintenance window ends early or when alerts need to
            be re-enabled. MUTATES STATE.

            Returns:
            - {\"success\": true, \"message\": str}

            Common errors:
            - Silence not found: Verify the silence_id via am_list_silences.
            """
            await ctx.info(f"Expiring silence: {silence_id}")
            try:
                await self.alertmanager_service.delete_silence(backend_id, silence_id)
                add_audit_entry(
                    backend_id=backend_id, operation="expire_silence",
                    principal="mcp", summary=f"id={silence_id}",
                )
                return {"success": True, "message": f"Silence {silence_id} expired."}
            except Exception as e:
                await ctx.error(str(e))
                return {"error": str(e), "isError": True}
