"""Governance, audit, and policy tools.

v4 refactor: am_export_config has been moved to the am://system/config resource.
"""

from typing import Any, Dict, List, Optional, Annotated
from pydantic import Field
from fastmcp import Context
from mcp.types import ToolAnnotations
from alertmanager_mcp_server.models.alert import AlertMatcher
from alertmanager_mcp_server.tools.base import BaseTool


class GovernanceTools(BaseTool):
    """Tools for governance, audit trails, and silence policy validation."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="List Recent Silence Changes",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def am_list_recent_changes(
            backend_id: Annotated[str, Field(min_length=1, description="Alertmanager backend ID")],
            hours: Annotated[Optional[int], Field(description="Look-back window in hours (default 24)")] = 24,
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Any:
            """List recent silence changes (created, expired, updated) within a time window.

            Use this for governance reviews, auditing who created or expired silences,
            and tracking silence lifecycle activity. Read-only.

            Returns:
            - {\"changes\": [{\"silence_id\": str, \"action\": str, \"matchers_summary\": str,
               \"created_by\": str, \"comment\": str, \"timestamp\": str}, ...],
               \"summary_text\": str}
            """
            await ctx.info(f"Listing recent silence changes for backend: {backend_id}")
            try:
                changes = await self.alertmanager_service.get_recent_silence_changes(
                    backend_id, hours=hours or 24,
                )
                if not changes:
                    summary = f"No silence changes in the last {hours or 24} hours."
                else:
                    created = sum(1 for c in changes if c.action == "created")
                    expired = sum(1 for c in changes if c.action == "expired")
                    authors = set(c.created_by for c in changes if c.created_by)
                    summary = (
                        f"{len(changes)} silence change(s) in the last {hours or 24}h: "
                        f"{created} created, {expired} expired. "
                        f"Authors: {', '.join(sorted(authors)) or 'unknown'}."
                    )

                return {
                    "changes": [c.model_dump(mode="json") for c in changes],
                    "summary_text": summary,
                }
            except Exception as e:
                await ctx.error(str(e))
                return {"error": str(e), "isError": True}

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Validate Silence Policy",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def am_validate_silence_policy(
            backend_id: Annotated[str, Field(min_length=1, description="Alertmanager backend ID")],
            matchers: Annotated[List[Dict[str, Any]], Field(description="Proposed silence matchers")],
            duration_minutes: Annotated[Optional[int], Field(description="Proposed duration in minutes")] = None,
            comment: Annotated[Optional[str], Field(description="Proposed comment")] = None,
            created_by: Annotated[Optional[str], Field(description="Proposed creator")] = None,
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Any:
            """Validate a proposed silence against organizational policy before creation.

            Use this as a pre-flight check before am_create_silence to ensure
            compliance with duration caps, comment requirements, and forbidden
            matcher combinations. Read-only — does NOT create any silence.

            Returns:
            - {\"allowed\": bool, \"violations\": [str]}

            When NOT to use: For previewing which alerts would be affected, use
            am_preview_silence instead. This tool validates policy, not blast radius.
            """
            await ctx.info("Validating silence policy")
            try:
                violations: List[str] = []
                max_dur = self.config.max_silence_duration_minutes

                # Check duration
                if duration_minutes and duration_minutes > max_dur:
                    violations.append(f"Duration {duration_minutes}m exceeds maximum allowed {max_dur}m.")

                # Check comment requirement
                if not comment or comment.strip() == "":
                    violations.append("A non-empty comment/justification is required.")

                # Check created_by requirement
                if not created_by or created_by.strip() == "":
                    violations.append("A non-empty created_by identity is required.")

                # Check for overly broad matchers (e.g., only severity=critical)
                parsed = [AlertMatcher(**m) for m in matchers]
                if not parsed:
                    violations.append("At least one matcher is required.")
                else:
                    matcher_names = {m.name for m in parsed}
                    if matcher_names == {"severity"}:
                        violations.append(
                            "Silencing by 'severity' alone is too broad. "
                            "Add 'alertname', 'service', or 'env' matchers."
                        )
                    if len(parsed) == 1 and parsed[0].name == "env":
                        violations.append(
                            "Silencing an entire environment is extremely broad. "
                            "Add 'alertname' or 'service' matchers."
                        )

                # Check blast radius
                try:
                    from alertmanager_mcp_server.utils import all_matchers_match
                    alerts, _, _ = await self.alertmanager_service.list_alerts(
                        backend_id, active=True, limit=1000, offset=0,
                    )
                    affected = [a for a in alerts if all_matchers_match(a.labels, parsed)]
                    threshold = self.config.silence_warning_threshold
                    if len(affected) >= threshold:
                        violations.append(
                            f"Would affect {len(affected)} alerts (threshold: {threshold}). "
                            f"Consider narrowing matchers or getting approval."
                        )
                except Exception:
                    pass  # Best-effort blast radius check

                return {
                    "allowed": len(violations) == 0,
                    "violations": violations,
                }
            except Exception as e:
                await ctx.error(str(e))
                return {"error": str(e), "isError": True}
