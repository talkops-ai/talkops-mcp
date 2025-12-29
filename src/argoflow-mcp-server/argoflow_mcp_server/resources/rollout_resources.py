"""Rollout status resources.

Provides real-time rollout status information including phase, steps,
canary/stable weights, and progress tracking.
"""

import json
import logging
from typing import List, Optional
from mcp.types import Resource, TextContent
from argoflow_mcp_server.resources.base import BaseResource

logger = logging.getLogger(__name__)


class RolloutResources(BaseResource):
    """Rollout status resources.
    
    Provides live rollout progress, phase, canary/stable weights.
    Update frequency: Every 2 seconds (real-time).
    """
    
    def register(self, mcp_instance) -> None:
        """Register rollout resources with FastMCP.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        
        @mcp_instance.resource("argoflow://rollouts/list")
        async def list_rollouts() -> List[Resource]:
            """List all rollouts across namespaces.
            
            Returns:
                List of rollout summary resources
            """
            try:
                if not self.argo_service:
                    logger.warning("Argo service not available")
                    return []
                
                # Get default namespace from config
                namespace = getattr(self.config, 'namespace', 'default') if self.config else 'default'
                
                rollouts = await self.argo_service.list_rollouts(namespace=namespace)
                
                resources = []
                for rollout in rollouts:
                    name = rollout.get('name', 'unknown')
                    ns = rollout.get('namespace', namespace)
                    
                    resource_data = {
                        "name": name,
                        "namespace": ns,
                        "phase": rollout.get('phase', 'Unknown'),
                        "replicas": rollout.get('replicas', {}),
                        "strategy": rollout.get('strategy', 'unknown')
                    }
                    
                    resources.append(
                        Resource(
                            uri=f"argoflow://rollouts/{ns}/{name}/summary",
                            name=f"Rollout: {name}",
                            description=f"Summary of rollout {name} in {ns} namespace",
                            mimeType="application/json",
                            contents=[
                                TextContent(
                                    text=json.dumps(resource_data, indent=2),
                                    mimeType="application/json"
                                )
                            ]
                        )
                    )
                
                return resources
                
            except Exception as e:
                logger.error(f"Error listing rollouts: {e}")
                return []
        
        @mcp_instance.resource("argoflow://rollouts/{namespace}/{name}/status")
        async def rollout_status(namespace: str, name: str) -> str:
            """Get detailed rollout status.
            
            Args:
                namespace: Kubernetes namespace
                name: Rollout name
            
            Returns:
                JSON string with detailed rollout status
            """
            try:
                if not self.argo_service:
                    return json.dumps({"error": "Argo service not available"}, indent=2)
                
                # Get detailed rollout status
                status_data = await self.argo_service.get_rollout_status(
                    name=name,
                    namespace=namespace
                )
                
                # Extract key information
                spec = status_data.get('spec', {})
                status = status_data.get('status', {})
                
                # Parse canary steps
                strategy = spec.get('strategy', {})
                canary_strategy = strategy.get('canary', {})
                steps = canary_strategy.get('steps', [])
                
                current_step_index = status.get('currentStepIndex', 0)
                total_steps = len(steps)
                
                # Calculate progress
                progress = 0
                if total_steps > 0:
                    progress = int((current_step_index / total_steps) * 100)
                
                # Get canary/stable weights
                canary_weight = 0
                stable_weight = 100
                
                if current_step_index < len(steps):
                    current_step = steps[current_step_index]
                    if 'setWeight' in current_step:
                        canary_weight = current_step['setWeight']
                        stable_weight = 100 - canary_weight
                
                # Get replica counts
                replicas = status.get('replicas', 0)
                updated_replicas = status.get('updatedReplicas', 0)
                ready_replicas = status.get('readyReplicas', 0)
                available_replicas = status.get('availableReplicas', 0)
                
                canary_replicas = updated_replicas
                stable_replicas = replicas - updated_replicas
                
                resource_data = {
                    "name": name,
                    "namespace": namespace,
                    "phase": status.get('phase', 'Unknown'),
                    "message": status.get('message', ''),
                    "currentStep": current_step_index,
                    "totalSteps": total_steps,
                    "canary": {
                        "weight": canary_weight,
                        "replicas": canary_replicas
                    },
                    "stable": {
                        "weight": stable_weight,
                        "replicas": stable_replicas
                    },
                    "progress": progress,
                    "replicas": {
                        "total": replicas,
                        "updated": updated_replicas,
                        "ready": ready_replicas,
                        "available": available_replicas
                    },
                    "paused": status.get('paused', False),
                    "aborted": status.get('abort', False)
                }
                
                return json.dumps(resource_data, indent=2)
                
            except Exception as e:
                logger.error(f"Error getting rollout status: {e}")
                return json.dumps({"error": str(e)}, indent=2)
