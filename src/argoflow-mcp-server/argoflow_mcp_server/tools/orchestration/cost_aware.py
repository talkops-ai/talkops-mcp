"""Tool 21: Configure Cost-Aware Deployment.

Cost tracking and optimization for deployments.
"""

import json
from typing import Any
from fastmcp import Context
from argoflow_mcp_server.tools.base import BaseTool


class CostAwareTools(BaseTool):
    """Tools for cost-aware deployment management."""
    
    def register(self, mcp_instance) -> None:
        """Register cost-aware tools with FastMCP."""
        
        @mcp_instance.tool()
        async def orch_configure_cost_aware_deployment(
            app_name: str,
            namespace: str = "default",
            max_daily_cost: float = 100.0,
            mode: str = "optimize",
            cost_per_pod_hour: float = 0.05,
            ctx: Context = None
        ) -> str:
            """Configure cost-aware deployment with budget tracking.
            
            Tracks costs and provides optimization recommendations to stay
           within budget while maintaining performance.
            
            Args:
                app_name: Application/rollout name
                namespace: Kubernetes namespace (default: 'default')
                max_daily_cost: Maximum daily cost budget in USD
                mode: Operation mode - 'validate', 'optimize', or 'report'
                cost_per_pod_hour: Cost per pod per hour in USD
            
            Returns:
                JSON string with cost analysis and recommendations
            
            Modes:
                - validate: Check if deployment is within budget
                - optimize: Apply cost optimizations (HPA, replica adjustment)
                - report: Generate detailed cost report
            
            Example:
                orch_configure_cost_aware_deployment(
                    app_name="api-service",
                    namespace="production",
                    max_daily_cost=200.0,
                    mode="validate"
                )
            """
            await ctx.info(
                f"Configuring cost-aware deployment for '{app_name}'",
                extra={'app_name': app_name, 'namespace': namespace, 'mode': mode}
            )
            
            try:
                orch_service = self.service_locator.get('orch_service')
                if not orch_service:
                    await ctx.error("Orchestration service not available")
                    return json.dumps({
                        "success": False,
                        "error": "Orchestration service not available"
                    }, indent=2)
                
                result = await orch_service.configure_cost_aware_deployment(
                    app_name=app_name,
                    namespace=namespace,
                    max_daily_cost=max_daily_cost,
                    mode=mode,
                    cost_per_pod_hour=cost_per_pod_hour
                )
                
                if result.get("status") == "success":
                    await ctx.info(
                        f"Cost-aware configuration complete for '{app_name}'",
                        extra={'app_name': app_name, 'mode': result.get('mode')}
                    )
                    return json.dumps({
                        "success": True,
                        **{k: v for k, v in result.items() if k != "status"}
                    }, indent=2)
                else:
                    await ctx.error(
                        f"Cost configuration failed: {result.get('message')}",
                        extra={'app_name': app_name}
                    )
                    return json.dumps({
                        "success": False,
                        "error": result.get("message", "Unknown error")
                    }, indent=2)
                    
            except Exception as e:
                await ctx.error(f"Cost-aware deployment failed: {str(e)}", extra={'error': str(e)})
                return json.dumps({
                    "success": False,
                    "error": str(e)
                }, indent=2)
