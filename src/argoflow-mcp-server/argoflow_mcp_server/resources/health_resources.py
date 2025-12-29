"""Deployment health resources.

Provides health scores and status for all deployments in the cluster.
"""

import json
import logging
from typing import List
from mcp.types import Resource, TextContent
from argoflow_mcp_server.resources.base import BaseResource

logger = logging.getLogger(__name__)


class HealthResources(BaseResource):
    """Deployment health resources.
    
    Provides health scores for all deployments.
    Update frequency: Every 10 seconds.
    """
    
    def register(self, mcp_instance) -> None:
        """Register health resources with FastMCP.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        
        @mcp_instance.resource("argoflow://health/summary")
        async def health_summary() -> str:
            """Get health summary for all deployments.
            
            Returns:
                JSON string with health scores for all deployments
            """
            try:
                if not self.argo_service:
                    return json.dumps({
                        "error": "Argo service not available",
                        "deployments": [],
                        "overallHealth": 0
                    }, indent=2)
                
                # Get namespace from config
                namespace = getattr(self.config, 'namespace', 'default') if self.config else 'default'
                
                # List all rollouts
                rollouts = await self.argo_service.list_rollouts(namespace=namespace)
                
                deployments = []
                total_health = 0
                
                for rollout in rollouts:
                    name = rollout.get('name', 'unknown')
                    ns = rollout.get('namespace', namespace)
                    
                    # Get detailed status
                    try:
                        status_data = await self.argo_service.get_rollout_status(
                            name=name,
                            namespace=ns
                        )
                        
                        status = status_data.get('status', {})
                        phase = status.get('phase', 'Unknown')
                        
                        # Get replica counts
                        replicas_desired = status.get('replicas', 0)
                        replicas_ready = status.get('readyReplicas', 0)
                        replicas_available = status.get('availableReplicas', 0)
                        
                        # Calculate health score
                        health_score = 0
                        deployment_status = 'unhealthy'
                        
                        if replicas_desired > 0:
                            # Base score on ready replicas
                            ready_ratio = replicas_ready / replicas_desired
                            health_score = int(ready_ratio * 100)
                            
                            # Adjust based on phase
                            if phase in ['Healthy', 'Running']:
                                deployment_status = 'healthy'
                            elif phase == 'Progressing':
                                deployment_status = 'progressing'
                                health_score = max(health_score - 10, 0)
                            elif phase == 'Degraded':
                                deployment_status = 'degraded'
                                health_score = max(health_score - 30, 0)
                            elif phase == 'Paused':
                                deployment_status = 'paused'
                                health_score = max(health_score - 5, 0)
                            else:
                                deployment_status = 'unhealthy'
                                health_score = 0
                            
                            # Bonus for availability
                            if replicas_available == replicas_desired:
                                health_score = min(health_score + 5, 100)
                        
                        deployments.append({
                            "name": name,
                            "namespace": ns,
                            "healthScore": health_score,
                            "replicas": {
                                "desired": replicas_desired,
                                "ready": replicas_ready,
                                "available": replicas_available
                            },
                            "status": deployment_status,
                            "phase": phase
                        })
                        
                        total_health += health_score
                        
                    except Exception as e:
                        logger.warning(f"Error getting status for rollout {name}: {e}")
                        # Add with unknown health
                        deployments.append({
                            "name": name,
                            "namespace": ns,
                            "healthScore": 0,
                            "replicas": {"desired": 0, "ready": 0, "available": 0},
                            "status": "unknown",
                            "phase": "Unknown"
                        })
                
                # Calculate overall health
                overall_health = 0
                if deployments:
                    overall_health = int(total_health / len(deployments))
                
                resource_data = {
                    "deployments": deployments,
                    "overallHealth": overall_health,
                    "totalDeployments": len(deployments)
                }
                
                return json.dumps(resource_data, indent=2)
                
            except Exception as e:
                logger.error(f"Error getting health summary: {e}")
                return json.dumps({
                    "error": str(e),
                    "deployments": [],
                    "overallHealth": 0
                }, indent=2)
        
        @mcp_instance.resource("argoflow://health/{namespace}/{name}/details")
        async def deployment_health_details(namespace: str, name: str) -> str:
            """Get detailed health information for a specific deployment.
            
            Args:
                uri: Resource URI in format argoflow://health/{namespace}/{name}/details
            
            Returns:
                JSON string with detailed health information
            """
            try:
                if not self.argo_service:
                    return json.dumps({"error": "Argo service not available"}, indent=2)
                
                # Get detailed rollout status
                status_data = await self.argo_service.get_rollout_status(
                    name=name,
                    namespace=namespace
                )
                
                status = status_data.get('status', {})
                spec = status_data.get('spec', {})
                
                # Calculate health metrics
                replicas_desired = status.get('replicas', 0)
                replicas_ready = status.get('readyReplicas', 0)
                replicas_available = status.get('availableReplicas', 0)
                replicas_updated = status.get('updatedReplicas', 0)
                
                health_score = 0
                if replicas_desired > 0:
                    health_score = int((replicas_ready / replicas_desired) * 100)
                
                resource_data = {
                    "name": name,
                    "namespace": namespace,
                    "healthScore": health_score,
                    "phase": status.get('phase', 'Unknown'),
                    "message": status.get('message', ''),
                    "replicas": {
                        "desired": replicas_desired,
                        "ready": replicas_ready,
                        "available": replicas_available,
                        "updated": replicas_updated
                    },
                    "conditions": status.get('conditions', []),
                    "paused": status.get('paused', False),
                    "aborted": status.get('abort', False)
                }
                
                return json.dumps(resource_data, indent=2)
                
            except Exception as e:
                logger.error(f"Error getting deployment health details: {e}")
                return json.dumps({"error": str(e)}, indent=2)
