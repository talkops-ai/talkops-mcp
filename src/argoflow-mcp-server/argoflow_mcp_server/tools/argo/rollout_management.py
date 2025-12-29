"""Argo Rollouts management tools - CRUD operations for rollouts."""

import json
from typing import Dict, Any, Optional, List
from pydantic import Field
from fastmcp import Context

from argoflow_mcp_server.tools.base import BaseTool
from argoflow_mcp_server.exceptions.custom import (
    ArgoRolloutError,
    RolloutNotFoundError,
    RolloutStrategyError,
)


class RolloutManagementTools(BaseTool):
    """Tools for creating, reading, updating, and deleting Argo Rollouts."""
    
    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""
        
        @mcp_instance.tool()
        async def argo_create_rollout(
            name: str = Field(..., min_length=1, description='Rollout name'),
            image: str = Field(..., min_length=1, description='Container image (e.g., nginx:1.19.0)'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            replicas: int = Field(default=3, ge=1, le=100, description='Number of replicas'),
            strategy: str = Field(default='canary', description='Deployment strategy: canary, bluegreen, or rolling'),
            canary_steps: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description='Canary steps configuration (list of {setWeight: int, pause: {duration: str}})'
           ),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Create a new Argo Rollout for progressive delivery.
            
            Creates a Rollout resource with the specified strategy (canary, blue-green, or rolling).
            For canary deployments, you can customize the rollout steps.
            
            Args:
                name: Name of the rollout
                image: Container image to deploy
                namespace: Kubernetes namespace
                replicas: Number of pod replicas
                strategy: Deployment strategy (canary, bluegreen, rolling)
                canary_steps: Optional custom canary steps
            
            Returns:
                Creation result with rollout details
            
            Raises:
                RolloutStrategyError: If strategy configuration is invalid
                ArgoRolloutError: If creation fails
            
            Example canary_steps:
                [
                    {"setWeight": 10}, {"pause": {"duration": "5m"}},
                    {"setWeight": 25}, {"pause": {"duration": "5m"}},
                    {"setWeight": 50}, {"pause": {"duration": "5m"}},
                    {"setWeight": 100}
                ]
            """
            await ctx.info(
                f"Creating Argo Rollout '{name}' with {strategy} strategy",
                extra={
                    'rollout_name': name,
                    'namespace': namespace,
                    'image': image,
                    'replicas': replicas,
                    'strategy': strategy
                }
            )
            
            # Validate strategy
            valid_strategies = ['canary', 'bluegreen', 'rolling']
            if strategy not in valid_strategies:
                error_msg = f"Invalid strategy '{strategy}'. Must be one of: {', '.join(valid_strategies)}"
                await ctx.error(error_msg)
                raise RolloutStrategyError(error_msg)
            
            if strategy == 'canary' and canary_steps:
                await ctx.debug(f"Using custom canary steps: {len(canary_steps)} steps defined")
            
            try:
                result = await self.argo_service.create_rollout(
                    name=name,
                    namespace=namespace,
                    image=image,
                    replicas=replicas,
                    strategy=strategy,
                    canary_steps=canary_steps
                )
                
                await ctx.info(
                    f"Successfully created rollout '{name}'",
                    extra={
                        'rollout_name': name,
                        'namespace': namespace,
                        'strategy': strategy
                    }
                )
                
                return result
            
            except RolloutStrategyError as e:
                await ctx.error(f"Strategy validation failed: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(
                    f"Failed to create rollout: {str(e)}",
                    extra={'rollout_name': name, 'error': str(e)}
                )
                raise ArgoRolloutError(f'Rollout creation failed: {str(e)}')
        
        @mcp_instance.tool()
        async def argo_get_rollout_status(
            name: str = Field(..., min_length=1, description='Rollout name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            ctx: Context = None
        ) -> str:
            """Get detailed status of an Argo Rollout.
            
            Returns current phase, replica state, strategy type, and conditions.
            
            Args:
                name: Rollout name
                namespace: Kubernetes namespace
            
            Returns:
                JSON string with rollout status, replica counts, phase, and conditions
            
            Raises:
                RolloutNotFoundError: If rollout doesn't exist
            """
            await ctx.info(
                f"Retrieving status for rollout '{name}'",
                extra={'rollout_name': name, 'namespace': namespace}
            )
            
            try:
                result = await self.argo_service.get_rollout_status(
                    name=name,
                    namespace=namespace
                )
                
                phase = result.get('phase', 'Unknown')
                replicas = result.get('replicas', {})
                
                await ctx.info(
                    f"Rollout '{name}' is in phase: {phase}",
                    extra={
                        'rollout_name': name,
                        'phase': phase,
                        'ready_replicas': replicas.get('ready', 0),
                        'total_replicas': replicas.get('total', 0)
                    }
                )
                
                return json.dumps(result, indent=2)
            
            except RolloutNotFoundError as e:
                await ctx.error(f"Rollout not found: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(f"Failed to get status: {str(e)}")
                raise ArgoRolloutError(f'Status retrieval failed: {str(e)}')
        
        @mcp_instance.tool()
        async def argo_list_rollouts(
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """List all Argo Rollouts in a namespace.
            
            Args:
                namespace: Kubernetes namespace
            
            Returns:
                List of rollouts with basic information
            """
            await ctx.info(
                f"Listing rollouts in namespace '{namespace}'",
                extra={'namespace': namespace}
            )
            
            try:
                result = await self.argo_service.list_rollouts(
                    namespace=namespace
                )
                
                count = result.get('count', 0)
                await ctx.info(
                    f"Found {count} rollout(s) in namespace '{namespace}'",
                    extra={'namespace': namespace, 'count': count}
                )
                
                return result
            
            except Exception as e:
                await ctx.error(f"Failed to list rollouts: {str(e)}")
                raise ArgoRolloutError(f'List operation failed: {str(e)}')
        
        @mcp_instance.tool()
        async def argo_delete_rollout(
            name: str = Field(..., min_length=1, description='Rollout name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Delete an Argo Rollout.
            
            Permanently deletes a rollout and all associated resources.
            
            Args:
                name: Rollout name
                namespace: Kubernetes namespace
            
            Returns:
                Deletion result
            
            Raises:
                RolloutNotFoundError: If rollout doesn't exist
            """
            await ctx.warning(
                f"Deleting rollout '{name}' from namespace '{namespace}'",
                extra={'rollout_name': name, 'namespace': namespace}
            )
            
            try:
                result = await self.argo_service.delete_rollout(
                    name=name,
                    namespace=namespace
                )
                
                await ctx.info(
                    f"Successfully deleted rollout '{name}'",
                    extra={'rollout_name': name, 'namespace': namespace}
                )
                
                return result
            
            except RolloutNotFoundError as e:
                await ctx.error(f"Rollout not found: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(f"Failed to delete rollout: {str(e)}")
                raise ArgoRolloutError(f'Deletion failed: {str(e)}')
        
        @mcp_instance.tool()
        async def argo_update_rollout_image(
            name: str = Field(..., min_length=1, description='Rollout name'),
            new_image: str = Field(..., min_length=1, description='New container image'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            container_name: Optional[str] = Field(default=None, description='Container name (defaults to rollout name)'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Update the container image for a rollout.
            
            Triggers a new rollout with the updated image.
            
            Args:
                name: Rollout name
                new_image: New container image
                namespace: Kubernetes namespace
                container_name: Container name (optional)
            
            Returns:
                Update result
            
            Raises:
                RolloutNotFoundError: If rollout doesn't exist
            """
            await ctx.info(
                f"Updating rollout '{name}' image to '{new_image}'",
                extra={
                    'rollout_name': name,
                    'namespace': namespace,
                    'new_image': new_image
                }
            )
            
            try:
                result = await self.argo_service.update_rollout_image(
                    name=name,
                    new_image=new_image,
                    namespace=namespace,
                    container_name=container_name
                )
                
                await ctx.info(
                    f"Successfully updated rollout '{name}' image",
                    extra={'rollout_name': name, 'new_image': new_image}
                )
                
                return result
            
            except RolloutNotFoundError as e:
                await ctx.error(f"Rollout not found: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(f"Failed to update image: {str(e)}")
                raise ArgoRolloutError(f'Image update failed: {str(e)}')
        
        @mcp_instance.tool()
        async def argo_get_rollout_history(
            name: str = Field(..., min_length=1, description='Rollout name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            limit: int = Field(default=10, ge=1, le=50, description='Maximum number of history entries'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Get rollout history and audit trail.
            
            Returns historical state changes and transitions.
            
            Args:
                name: Rollout name
                namespace: Kubernetes namespace
                limit: Maximum history entries to return
            
            Returns:
                Rollout history with conditions and transitions
            
            Raises:
                RolloutNotFoundError: If rollout doesn't exist
            """
            await ctx.info(
                f"Retrieving history for rollout '{name}'",
                extra={'rollout_name': name, 'namespace': namespace, 'limit': limit}
            )
            
            try:
                result = await self.argo_service.get_rollout_history(
                    name=name,
                    namespace=namespace,
                    limit=limit
                )
                
                history_count = result.get('history_count', 0)
                await ctx.info(
                    f"Retrieved {history_count} history entry(ies) for rollout '{name}'",
                    extra={'rollout_name': name, 'history_count': history_count}
                )
                
                return result
            
            except RolloutNotFoundError as e:
                await ctx.error(f"Rollout not found: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(f"Failed to get history: {str(e)}")
                raise ArgoRolloutError(f'History retrieval failed: {str(e)}')
