"""Deployment history resources.

Provides audit trail of deployment changes and events.
"""

import json
import logging
from typing import List
from mcp.types import Resource, TextContent
from argoflow_mcp_server.resources.base import BaseResource

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
        
        @mcp_instance.resource("argoflow://history/{namespace}/{deployment}")
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
                        "events": []
                    }, indent=2)
                
                # Get rollout history using existing service method
                history = await self.argo_service.get_rollout_history(
                    name=deployment,
                    namespace=namespace,
                    limit=20  # Last 20 events
                )
                
                # Transform history into event format
                events = []
                for entry in history.get('revisions', []):
                    # Extract revision info
                    revision = entry.get('revision', 0)
                    status = entry.get('status', {})
                    
                    # Parse image changes
                    old_image = entry.get('oldImage', 'unknown')
                    new_image = entry.get('newImage', 'unknown')
                    
                    event_type = "REVISION_CHANGE"
                    if old_image != new_image:
                        event_type = "IMAGE_UPDATE"
                    
                    events.append({
                        "timestamp": entry.get('timestamp', ''),
                        "eventType": event_type,
                        "revision": revision,
                        "details": {
                            "oldImage": old_image,
                            "newImage": new_image,
                            "phase": status.get('phase', 'Unknown'),
                            "message": status.get('message', '')
                        }
                    })
                
                resource_data = {
                    "deployment": deployment,
                    "namespace": namespace,
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
                    "events": []
                }, indent=2)
        
        @mcp_instance.resource("argoflow://history/all")
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
                
                # Get namespace from config
                namespace = getattr(self.config, 'namespace', 'default') if self.config else 'default'
                
                # List all rollouts
                rollouts = await self.argo_service.list_rollouts(namespace=namespace)
                
                all_events = []
                
                for rollout in rollouts:
                    name = rollout.get('name', 'unknown')
                    ns = rollout.get('namespace', namespace)
                    
                    try:
                        # Get history for each rollout
                        history = await self.argo_service.get_rollout_history(
                            name=name,
                            namespace=ns,
                            limit=5  # Last 5 events per rollout
                        )
                        
                        # Transform and add to events
                        for entry in history.get('revisions', []):
                            revision = entry.get('revision', 0)
                            status = entry.get('status', {})
                            
                            old_image = entry.get('oldImage', 'unknown')
                            new_image = entry.get('newImage', 'unknown')
                            
                            event_type = "REVISION_CHANGE"
                            if old_image != new_image:
                                event_type = "IMAGE_UPDATE"
                            
                            all_events.append({
                                "deployment": name,
                                "namespace": ns,
                                "timestamp": entry.get('timestamp', ''),
                                "eventType": event_type,
                                "revision": revision,
                                "details": {
                                    "oldImage": old_image,
                                    "newImage": new_image,
                                    "phase": status.get('phase', 'Unknown'),
                                    "message": status.get('message', '')
                                }
                            })
                    
                    except Exception as e:
                        logger.warning(f"Error getting history for rollout {name}: {e}")
                
                # Sort by timestamp (most recent first)
                all_events.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                
                resource_data = {
                    "events": all_events[:50],  # Limit to 50 most recent
                    "totalEvents": len(all_events),
                    "namespace": namespace
                }
                
                return json.dumps(resource_data, indent=2)
                
            except Exception as e:
                logger.error(f"Error getting all deployment history: {e}")
                return json.dumps({
                    "error": str(e),
                    "events": []
                }, indent=2)
