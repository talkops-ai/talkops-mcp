"""Routing and inhibition introspection tools.

v4 refactor: am_get_routing_tree and am_list_receivers have been moved to
resources (am://system/config and am://system/receivers).

Remaining tools provide reasoning/computation — not simple GET wrappers.
"""

from typing import Any, Dict, Optional, Annotated
from pydantic import Field
from fastmcp import Context
from mcp.types import ToolAnnotations
from alertmanager_mcp_server.tools.base import BaseTool


class RoutingTools(BaseTool):
    """Tools for routing simulation and default-route auditing."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Explain Routing for Alert",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def am_explain_routing(
            backend_id: Annotated[str, Field(min_length=1, description="Alertmanager backend ID")],
            labels: Annotated[Any, Field(description="Alert label set to simulate routing for (must be a JSON object/dictionary, e.g. {\"env\": \"prod\"})")],
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Any:
            """Simulate routing and inhibition for a given label set with explanation.

            Use this to answer questions like "Who gets paged for this alert?" or
            "Why didn't I get notified?". Provides a human-readable explanation of
            the routing path, matched receivers, grouping, and inhibition rules.
            Similar to `amtool config routes test`. Read-only.

            Returns:
            - {\"matched_route\": str, \"receivers\": [str], \"group_labels\": [str],
               \"inhibited_by\": [str], \"explanation\": str}

            When NOT to use: For a structural view of the routing tree, read the
            am://system/config resource instead.
            """
            await ctx.info(f"Explaining routing for labels: {labels}")
            try:
                import json
                if isinstance(labels, str):
                    labels = json.loads(labels)
                result = await self.alertmanager_service.explain_routing_for_alert(backend_id, labels)
                return result.model_dump()
            except Exception as e:
                await ctx.error(str(e))
                return {"error": str(e), "isError": True}

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Audit Default Route Usage",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def am_audit_default_route(
            backend_id: Annotated[str, Field(min_length=1, description="Alertmanager backend ID")],
            limit: Annotated[Optional[int], Field(description="Max alerts to return")] = 20,
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Any:
            """Show alerts falling into the default route, highlighting potential misconfigurations.

            Use this to identify alerts that are not matched by any specific route
            and are falling through to the default receiver. This often indicates
            missing routing rules or incorrect label taxonomies. Read-only.

            Returns:
            - {\"default_receiver\": str, \"alert_count\": int, \"alerts\": [{...}],
               \"summary_text\": str}
            """
            await ctx.info(f"Auditing default route for backend: {backend_id}")
            try:
                default_alerts = await self.alertmanager_service.get_default_route_alerts(backend_id)
                config = await self.alertmanager_service.get_config_snapshot(backend_id)
                default_receiver = config.routes[0].receiver if config.routes else "<none>"

                limited = default_alerts[:limit or 20]
                if not default_alerts:
                    summary = "No active alerts are hitting the default route. Routing looks well configured."
                else:
                    alertnames = set(a.labels.get("alertname", "?") for a in default_alerts)
                    summary = (
                        f"{len(default_alerts)} alert(s) are routing to the default receiver "
                        f"'{default_receiver}'. Alert names: {', '.join(sorted(alertnames))}. "
                        f"Consider adding specific routes for these alerts."
                    )

                return {
                    "default_receiver": default_receiver,
                    "alert_count": len(default_alerts),
                    "alerts": [a.model_dump(mode="json") for a in limited],
                    "summary_text": summary,
                }
            except Exception as e:
                await ctx.error(str(e))
                return {"error": str(e), "isError": True}
