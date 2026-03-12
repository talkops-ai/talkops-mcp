"""Deployment history resources.

Provides audit trail of deployment changes and events.
"""

import json
import logging
from typing import List
from mcp.types import Resource, TextContent
from argo_rollout_mcp_server.resources.base import BaseResource

logger = logging.getLogger(__name__)


class HistoryResources(BaseResource):
    """Deployment history resources.
    
    Provides audit trail of deployment changes.
    Update frequency: Per event.
    """
    
    def register(self, mcp_instance) -> None:
        """Register history resources with FastMCP.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        
        @mcp_instance.resource("argorollout://history/{namespace}/{deployment}")
        async def deployment_history(namespace: str, deployment: str) -> str:
            """Get deployment history for a rollout.
            
            Args:
                namespace: Kubernetes namespace
                deployment: Deployment/rollout name
            
            Returns:
                JSON string with deployment history events
            """
            try:
                if not self.argo_service:
                    return json.dumps({
                        "error": "Argo service not available",
                        "deployment": deployment,
                        "namespace": namespace,
                        "currentRevision": 0,
                        "revisions": [],
                        "events": []
                    }, indent=2)
                
                # Get rollout history using existing service method
                history = await self.argo_service.get_rollout_history(
                    name=deployment,
                    namespace=namespace,
                    limit=20  # Last 20 events
                )
                
                # Transform history into event format (service returns conditions in 'history' key)
                events = []
                for i, entry in enumerate(history.get('history', [])):
                    entry_type = entry.get('type', 'Unknown')
                    events.append({
                        "timestamp": entry.get('lastTransitionTime', entry.get('lastUpdateTime', '')),
                        "eventType": entry_type,
                        "revision": i + 1,
                        "details": {
                            "type": entry_type,
                            "status": entry.get('status', ''),
                            "reason": entry.get('reason', ''),
                            "message": entry.get('message', '')
                        }
                    })
                
                # Get rollout revision history
                try:
                    rev_history = await self.argo_service.get_rollout_revision_history(
                        name=deployment,
                        namespace=namespace,
                        limit=20
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
                    "events": events,
                    "totalEvents": len(events)
                }
                
                return json.dumps(resource_data, indent=2)
                
            except Exception as e:
                logger.error(f"Error getting deployment history: {e}")
                return json.dumps({
                    "error": str(e),
                    "deployment": deployment if 'deployment' in locals() else 'unknown',
                    "namespace": namespace if 'namespace' in locals() else 'unknown',
                    "currentRevision": 0,
                    "revisions": [],
                    "events": []
                }, indent=2)
        
        @mcp_instance.resource("argorollout://history/all")
        async def all_deployment_history() -> str:
            """Get recent deployment history across all rollouts.
            
            Returns:
                JSON string with recent deployment events
            """
            try:
                if not self.argo_service:
                    return json.dumps({
                        "error": "Argo service not available",
                        "events": []
                    }, indent=2)
                
                # List all rollouts cluster-wide
                result = await self.argo_service.list_rollouts(namespace=None)
                rollouts = result.get("rollouts", []) if isinstance(result, dict) else []
                
                all_events = []
                
                for rollout in rollouts:
                    name = rollout.get('name', 'unknown')
                    ns = rollout.get('namespace', 'default')
                    
                    try:
                        # Get history for each rollout
                        history = await self.argo_service.get_rollout_history(
                            name=name,
                            namespace=ns,
                            limit=5  # Last 5 events per rollout
                        )
                        
                        # Transform and add to events (service returns conditions in 'history' key)
                        for i, entry in enumerate(history.get('history', [])):
                            entry_type = entry.get('type', 'Unknown')
                            all_events.append({
                                "deployment": name,
                                "namespace": ns,
                                "timestamp": entry.get('lastTransitionTime', entry.get('lastUpdateTime', '')),
                                "eventType": entry_type,
                                "revision": i + 1,
                                "details": {
                                    "type": entry_type,
                                    "status": entry.get('status', ''),
                                    "reason": entry.get('reason', ''),
                                    "message": entry.get('message', '')
                                }
                            })
                    
                    except Exception as e:
                        logger.warning(f"Error getting history for rollout {name}: {e}")
                
                # Sort by timestamp (most recent first)
                all_events.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                
                resource_data = {
                    "events": all_events[:50],  # Limit to 50 most recent
                    "totalEvents": len(all_events),
                    "scope": "cluster-wide"
                }
                
                return json.dumps(resource_data, indent=2)
                
            except Exception as e:
                logger.error(f"Error getting all deployment history: {e}")
                return json.dumps({
                    "error": str(e),
                    "events": []
                }, indent=2)
