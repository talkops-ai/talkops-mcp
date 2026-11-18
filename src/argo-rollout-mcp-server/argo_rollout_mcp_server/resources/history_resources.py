"""Deployment and Rollout revision history resources."""

import json
import logging

from argo_rollout_mcp_server.resources.base import BaseResource

logger = logging.getLogger(__name__)


class HistoryResources(BaseResource):
    """Rollout ReplicaSet revision history and status conditions resource."""

    def register(self, mcp_instance) -> None:
        """Register history resource with FastMCP."""

        @mcp_instance.resource("argorollout://history/{namespace}/{deployment}")
        async def deployment_history(namespace: str, deployment: str) -> str:
            """Get ReplicaSet revision history and status conditions for a Rollout."""
            try:
                if not self.argo_service:
                    return json.dumps(
                        {
                            "error": "Argo service not available",
                            "deployment": deployment,
                            "namespace": namespace,
                            "currentRevision": 0,
                            "revisions": [],
                            "conditions": [],
                        },
                        indent=2,
                    )

                history = await self.argo_service.get_rollout_history(
                    name=deployment,
                    namespace=namespace,
                    limit=20,
                )
                # Fix B3: keep status conditions explicitly labeled as conditions, not fake revisions
                conditions = [
                    {
                        "type": entry.get("type", "Unknown"),
                        "status": entry.get("status", ""),
                        "reason": entry.get("reason", ""),
                        "message": entry.get("message", ""),
                        "lastTransitionTime": entry.get(
                            "lastTransitionTime", entry.get("lastUpdateTime", "")
                        ),
                    }
                    for entry in history.get("history", [])
                ]

                try:
                    rev_history = await self.argo_service.get_rollout_revision_history(
                        name=deployment,
                        namespace=namespace,
                        limit=20,
                    )
                    revisions = rev_history.get("revisions", [])
                    current_revision = rev_history.get("currentRevision", 0)
                except Exception as rev_err:
                    logger.warning(f"Failed to get revision history: {rev_err}")
                    revisions = []
                    current_revision = 0

                resource_data = {
                    "deployment": deployment,
                    "namespace": namespace,
                    "currentRevision": current_revision,
                    "revisions": revisions,
                    "conditions": conditions,
                    "totalRevisions": len(revisions),
                }
                return json.dumps(resource_data, indent=2)
            except Exception as e:
                logger.error(f"Error getting deployment history: {e}")
                return json.dumps(
                    {
                        "error": str(e),
                        "deployment": deployment,
                        "namespace": namespace,
                        "currentRevision": 0,
                        "revisions": [],
                        "conditions": [],
                    },
                    indent=2,
                )
