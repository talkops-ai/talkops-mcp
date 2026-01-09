"""Tool 20: Deploy with Intelligent Promotion.

Master orchestrator for intelligent canary deployment with ML-based decisions.
"""

import json
from typing import Any, Dict
from fastmcp import Context
from argoflow_mcp_server.tools.base import BaseTool


class IntelligentPromotionTools(BaseTool):
    """Tools for intelligent deployment promotion."""
    
    def register(self, mcp_instance) -> None:
        """Register intelligent promotion tools with FastMCP.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        
        @mcp_instance.tool()
        async def orch_deploy_intelligent_promotion(
            app_name: str,
            image: str,
            namespace: str = "default",
            strategy: str = "canary",
            ml_model: str = "gradient_boosting",
            health_threshold: float = 0.95,
            max_iterations: int = 10,
            ctx: Context = None
        ) -> str:
            """Deploy with ML-based intelligent promotion.
            
            This is the master orchestrator that automatically promotes
            canary deployments using machine learning to predict optimal
            traffic weights based on health metrics.
            
            Args:
                app_name: Application/rollout name to deploy
                image: Container image to deploy (e.g., 'myapp:v2.0')
                namespace: Kubernetes namespace (default: 'default')
                strategy: Deployment strategy - 'canary', 'bluegreen', or 'rolling'
                ml_model: ML model to use - 'gradient_boosting' or 'random_forest'
                health_threshold: Minimum health score (0.0-1.0) to continue promotion
                max_iterations: Maximum promotion iterations before stopping
            
            Returns:
                JSON string with deployment result and promotion history
            
            Example:
                orch_deploy_intelligent_promotion(
                    app_name="api-service",
                    image="api:v2.0",
                    namespace="production",
                    strategy="canary",
                    ml_model="gradient_boosting",
                    health_threshold=0.95
                )
            """
            await ctx.info(
                f"Starting intelligent promotion for '{app_name}'",
                extra={
                    'app_name': app_name,
                    'image': image,
                    'namespace': namespace,
                    'strategy': strategy,
                    'ml_model': ml_model
                }
            )
            
            try:
                # Get orchestration service
                orch_service = self.service_locator.get('orch_service')
                if not orch_service:
                    await ctx.error("Orchestration service not available")
                    return json.dumps({
                        "success": False,
                        "error": "Orchestration service not available"
                    }, indent=2)
                
                # Call service method
                result = await orch_service.deploy_with_intelligent_promotion(
                    app_name=app_name,
                    image=image,
                    namespace=namespace,
                    strategy=strategy,
                    ml_model=ml_model,
                    health_threshold=health_threshold,
                    max_iterations=max_iterations
                )
                
                # Format response
                if result.get("status") == "success":
                    await ctx.info(
                        f"Successfully deployed '{app_name}' after {result.get('iterations')} iterations",
                        extra={
                            'app_name': app_name,
                            'iterations': result.get('iterations'),
                            'final_weight': result.get('final_weight')
                        }
                    )
                    
                    summary = {
                        "success": True,
                        "app_name": app_name,
                        "namespace": namespace,
                        "image": image,
                        "strategy": strategy,
                        "ml_model": ml_model,
                        "iterations": result.get("iterations"),
                        "final_weight": result.get("final_weight"),
                        "message": result.get("message"),
                        "promotion_history": result.get("promotion_history", [])
                    }
                    return json.dumps(summary, indent=2)
                
                elif result.get("status") == "aborted":
                    await ctx.warning(
                        f"Deployment aborted for '{app_name}': {result.get('reason')}",
                        extra={'app_name': app_name, 'reason': result.get('reason')}
                    )
                    return json.dumps({
                        "success": False,
                        "aborted": True,
                        "reason": result.get("reason"),
                        "health_score": result.get("health_score"),
                        "iterations": result.get("iterations"),
                        "message": result.get("message")
                    }, indent=2)
                
                else:
                    await ctx.error(
                        f"Deployment failed for '{app_name}': {result.get('message')}",
                        extra={'app_name': app_name, 'error': result.get('message')}
                    )
                    return json.dumps({
                        "success": False,
                        "error": result.get("message", "Unknown error")
                    }, indent=2)
                    
            except Exception as e:
                await ctx.error(
                    f"Intelligent promotion failed: {str(e)}",
                    extra={'app_name': app_name, 'error': str(e)}
                )
                return json.dumps({
                    "success": False,
                    "error": str(e)
                }, indent=2)
