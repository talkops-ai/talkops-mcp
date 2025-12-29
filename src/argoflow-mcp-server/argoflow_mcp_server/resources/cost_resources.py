"""Cost analytics resources.

Provides cost tracking and optimization insights for deployments.
"""

import json
import logging
from mcp.types import Resource, TextContent
from argoflow_mcp_server.resources.base import BaseResource

logger = logging.getLogger(__name__)


class CostResources(BaseResource):
    """Cost analytics resources.
    
    Provides cost tracking and optimization insights.
    Update frequency: Every 60 seconds.
    """
    
    def register(self, mcp_instance) -> None:
        """Register cost resources with FastMCP.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        
        @mcp_instance.resource("argoflow://cost/analytics")
        async def cost_analytics() -> str:
            """Get cost analytics for all deployments.
            
            Returns:
                JSON string with cost information
            
            Note:
                This is a placeholder implementation. Full cost analytics requires:
                1. Cloud provider cost APIs (AWS Cost Explorer, GCP Billing, etc.)
                2. Resource metrics from Kubernetes metrics-server
                3. Cost allocation models and pricing data
            """
            try:
                if not self.argo_service:
                    return json.dumps({
                        "error": "Services not available",
                        "totalCostPerHour": 0.0,
                        "costByDeployment": []
                    }, indent=2)
                
                # Get namespace from config
                namespace = getattr(self.config, 'namespace', 'default') if self.config else 'default'
                
                # List all rollouts
                rollouts = await self.argo_service.list_rollouts(namespace=namespace)
                
                cost_by_deployment = []
                total_cost = 0.0
                
                # Placeholder cost model: $0.05 per replica per hour
                # In production, this would use actual cloud costs
                COST_PER_REPLICA_HOUR = 0.05
                
                for rollout in rollouts:
                    name = rollout.get('name', 'unknown')
                    ns = rollout.get('namespace', namespace)
                    replicas = rollout.get('replicas', {})
                    
                    # Get total replicas
                    total_replicas = replicas.get('total', 0)
                    
                    # Calculate estimated cost
                    deployment_cost = total_replicas * COST_PER_REPLICA_HOUR
                    total_cost += deployment_cost
                    
                    cost_by_deployment.append({
                        "deployment": name,
                        "namespace": ns,
                        "replicas": total_replicas,
                        "costPerHour": round(deployment_cost, 2),
                        "estimatedDailyCost": round(deployment_cost * 24, 2),
                        "estimatedMonthlyCost": round(deployment_cost * 24 * 30, 2)
                    })
                
                # Sort by cost (highest first)
                cost_by_deployment.sort(key=lambda x: x['costPerHour'], reverse=True)
                
                resource_data = {
                    "totalCostPerHour": round(total_cost, 2),
                    "estimatedDailyCost": round(total_cost * 24, 2),
                    "projectedMonthlyCost": round(total_cost * 24 * 30, 2),
                    "costByDeployment": cost_by_deployment,
                    "totalDeployments": len(cost_by_deployment),
                    "note": "Costs are estimated. Integrate with cloud provider APIs for actual costs.",
                    "costModel": f"${COST_PER_REPLICA_HOUR} per replica per hour"
                }
                
                return json.dumps(resource_data, indent=2)
                
            except Exception as e:
                logger.error(f"Error calculating cost analytics: {e}")
                return json.dumps({
                    "error": str(e),
                    "totalCostPerHour": 0.0,
                    "costByDeployment": []
                }, indent=2)
        
        @mcp_instance.resource("argoflow://costs/{namespace}/{deployment}")
        async def deployment_cost_details(namespace: str, deployment: str) -> str:
            """Get detailed cost information for a specific deployment.
            
            Args:
                namespace: Kubernetes namespace
                deployment: Deployment/rollout name
            
            Returns:
                JSON string with detailed cost breakdown
            """
            try:
                if not self.argo_service:
                    return json.dumps({
                        "error": "Argo service not available",
                        "deployment": deployment,
                        "namespace": namespace
                    }, indent=2)
                
                # Get rollout status
                status_data = await self.argo_service.get_rollout_status(
                    name=deployment,
                    namespace=namespace
                )
                
                status = status_data.get('status', {})
                
                # Get replica counts
                replicas_total = status.get('replicas', 0)
                replicas_ready = status.get('readyReplicas', 0)
                replicas_updated = status.get('updatedReplicas', 0)
                
                # Placeholder cost model
                COST_PER_REPLICA_HOUR = 0.05
                
                # Calculate costs
                total_cost_hour = replicas_total * COST_PER_REPLICA_HOUR
                
                # Calculate waste (unhealthy replicas still cost money)
                unhealthy_replicas = replicas_total - replicas_ready
                wasted_cost_hour = unhealthy_replicas * COST_PER_REPLICA_HOUR
                
                resource_data = {
                    "deployment": deployment,
                    "namespace": namespace,
                    "replicas": {
                        "total": replicas_total,
                        "ready": replicas_ready,
                        "updated": replicas_updated,
                        "unhealthy": unhealthy_replicas
                    },
                    "costs": {
                        "perHour": round(total_cost_hour, 2),
                        "perDay": round(total_cost_hour * 24, 2),
                        "perMonth": round(total_cost_hour * 24 * 30, 2),
                        "perYear": round(total_cost_hour * 24 * 365, 2)
                    },
                    "waste": {
                        "unhealthyReplicas": unhealthy_replicas,
                        "wastedCostPerHour": round(wasted_cost_hour, 2),
                        "wastedCostPerDay": round(wasted_cost_hour * 24, 2),
                        "wastedCostPerMonth": round(wasted_cost_hour * 24 * 30, 2)
                    },
                    "optimization": {
                        "suggestion": "Scale down unhealthy replicas" if unhealthy_replicas > 0 else "No immediate optimization needed",
                        "potentialSavings": round(wasted_cost_hour * 24 * 30, 2) if unhealthy_replicas > 0 else 0.0
                    },
                    "note": "Costs are estimated. Integrate with cloud provider APIs for actual costs.",
                    "costModel": f"${COST_PER_REPLICA_HOUR} per replica per hour"
                }
                
                return json.dumps(resource_data, indent=2)
                
            except Exception as e:
                logger.error(f"Error getting deployment cost details: {e}")
                return json.dumps({
                    "error": str(e),
                    "deployment": deployment if 'deployment' in locals() else 'unknown',
                    "namespace": namespace if 'namespace' in locals() else 'unknown'
                }, indent=2)
