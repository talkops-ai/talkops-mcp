"""Rollout status resources.

Provides rollout details including status, phase, steps, and full YAML manifest.
"""

import json
import logging
from typing import List, Optional
import yaml
from mcp.types import Resource, TextContent
from argo_rollout_mcp_server.resources.base import BaseResource

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
        
        @mcp_instance.resource("argorollout://rollouts/list")
        async def list_rollouts() -> str:
            """List all rollouts across namespaces.
            
            Returns:
                JSON string of rollout summaries
            """
            try:
                if not self.argo_service:
                    logger.warning("Argo service not available")
                    return "[]"
                
                # List cluster-wide (namespace=None) to match "all rollouts across namespaces"
                result = await self.argo_service.list_rollouts(namespace=None)
                rollouts = result.get("rollouts", []) if isinstance(result, dict) else []
                
                summary_data = []
                for rollout in rollouts:
                    name = rollout.get('name', 'unknown')
                    ns = rollout.get('namespace', 'default')
                    
                    replicas_info = {
                        "desired": rollout.get('desired_replicas', 0),
                        "current": rollout.get('current_replicas', 0),
                        "ready": rollout.get('ready_replicas', 0),
                    }
                    resource_data = {
                        "name": name,
                        "namespace": ns,
                        "phase": rollout.get('phase', 'Unknown'),
                        "replicas": replicas_info,
                        "strategy": rollout.get('strategy', 'unknown'),
                        "image": rollout.get('image', ''),
                        "created": rollout.get('created', ''),
                    }
                    
                    summary_data.append(resource_data)
                
                return json.dumps(summary_data, indent=2)
                
            except Exception as e:
                logger.error(f"Error listing rollouts: {e}")
                return "[]"
        
        @mcp_instance.resource("argorollout://rollouts/{namespace}/{name}/detail")
        async def rollout_status(namespace: str, name: str) -> str:
            """Get rollout details including status and full YAML manifest.
            
            Args:
                namespace: Kubernetes namespace
                name: Rollout name
            
            Returns:
                Rollout details (status, phase, replicas, conditions) plus full YAML manifest
            """
            try:
                if not self.argo_service:
                    return json.dumps({"error": "Argo service not available"}, indent=2)
                
                # Get detailed rollout status
                status_data = await self.argo_service.get_rollout_status(
                    name=name,
                    namespace=namespace
                )
                
                # Get full rollout manifest for YAML
                manifest = await self.argo_service.get_rollout_manifest(
                    name=name,
                    namespace=namespace
                )
                
                if not isinstance(status_data, dict):
                    return json.dumps({"error": "Invalid status response"}, indent=2)
                
                replicas_info = status_data.get('replicas', {})
                if not isinstance(replicas_info, dict):
                    replicas_info = {}
                
                # Build details section
                details = {
                    "name": status_data.get('name', name),
                    "namespace": status_data.get('namespace', namespace),
                    "phase": status_data.get('phase', 'Unknown'),
                    "message": status_data.get('message', ''),
                    "strategy": status_data.get('strategy', 'unknown'),
                    "currentStep": status_data.get('current_step'),
                    "replicas": {
                        "total": replicas_info.get('total', 0),
                        "updated": replicas_info.get('updated', 0),
                        "ready": replicas_info.get('ready', 0),
                        "available": replicas_info.get('available', 0),
                    },
                    "desired_replicas": status_data.get('desired_replicas', 0),
                    "conditions": status_data.get('conditions', []),
                    "timestamp": status_data.get('timestamp', ''),
                }
                
                # Serialize manifest to YAML (use default_flow_style=False for readable output)
                yaml_manifest = yaml.dump(
                    manifest,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )
                
                # Combine details + YAML into single output
                output_parts = [
                    "## Rollout Details",
                    "",
                    "```json",
                    json.dumps(details, indent=2),
                    "```",
                    "",
                    "## Full YAML Manifest",
                    "",
                    "```yaml",
                    yaml_manifest.rstrip(),
                    "```",
                ]
                return "\n".join(output_parts)
                
            except Exception as e:
                logger.error(f"Error getting rollout details: {e}")
                return json.dumps({"error": str(e)}, indent=2)
        
        @mcp_instance.resource("argorollout://experiments/{namespace}/{name}/status")
        async def experiment_status(namespace: str, name: str) -> str:
            """Get Argo Experiment status.
            
            Args:
                namespace: Kubernetes namespace
                name: Experiment name
            
            Returns:
                JSON string with experiment phase, template statuses, analysis results
            """
            try:
                if not self.argo_service:
                    return json.dumps({"error": "Argo service not available"}, indent=2)
                
                result = await self.argo_service.get_experiment_status(
                    name=name,
                    namespace=namespace
                )
                return json.dumps(result, indent=2)
                
            except Exception as e:
                logger.error(f"Error getting experiment status: {e}")
                return json.dumps({"error": str(e)}, indent=2)
