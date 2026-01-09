"""Tool 24: Get Deployment Insights.

AI-driven insights and recommendations for deployments.
"""

import json
from typing import Any
from fastmcp import Context
from argoflow_mcp_server.tools.base import BaseTool


class DeploymentInsightsTools(BaseTool):
    """Tools for AI-driven deployment insights."""
    
    def register(self, mcp_instance) -> None:
        """Register deployment insights tools with FastMCP."""
        
        @mcp_instance.tool()
        async def orch_get_deployment_insights(
            app_name: str,
            namespace: str = "default",
            insight_type: str = "full",
            ctx: Context = None
        ) -> str:
            """Get AI-driven deployment insights and recommendations.
            
            Analyzes deployment metrics and provides actionable insights
            for performance, cost, risk, and scaling optimization.
            
            Args:
                app_name: Application/rollout name
                namespace: Kubernetes namespace (default: 'default')
                insight_type: Type of insights - 'full', 'performance', 'cost', 'risk', or 'scaling'
            
            Returns:
                JSON string with insights and recommendations
            
            Insight Types:
                - full: All insights (performance, cost, risk, scaling)
                - performance: Latency, throughput, error rate analysis
                - cost: Cost analysis and savings opportunities
                - risk: Risk assessment and mitigations
                - scaling: Scaling recommendations and HPA suggestions
            
            Returns:
                Insights object with:
                - Performance metrics and analysis
                - Cost breakdown and optimization opportunities
                - Risk score and mitigation strategies
                - Scaling recommendations
                - Prioritized actionable recommendations
            
            Example:
                orch_get_deployment_insights(
                    app_name="api-service",
                    namespace="production",
                    insight_type="full"
                )
            """
            await ctx.info(
                f"Generating deployment insights for '{app_name}'",
                extra={'app_name': app_name, 'namespace': namespace, 'insight_type': insight_type}
            )
            
            try:
                orch_service = self.service_locator.get('orch_service')
                if not orch_service:
                    await ctx.error("Orchestration service not available")
                    return json.dumps({
                        "success": False,
                        "error": "Orchestration service not available"
                    }, indent=2)
                
                result = await orch_service.get_deployment_insights(
                    app_name=app_name,
                    namespace=namespace,
                    insight_type=insight_type
                )
                
                if result.get("status") == "success":
                    insights = result.get("insights", {})
                    await ctx.info(
                        f"Generated {len(insights.get('recommendations', []))} recommendations for '{app_name}'",
                        extra={'app_name': app_name, 'insight_type': insight_type}
                    )
                    return json.dumps({
                        "success": True,
                        "insights": insights
                    }, indent=2)
                else:
                    await ctx.error(
                        f"Insights generation failed: {result.get('message')}",
                        extra={'app_name': app_name}
                    )
                    return json.dumps({
                        "success": False,
                        "error": result.get("message", "Unknown error")
                    }, indent=2)
                    
            except Exception as e:
                await ctx.error(f"Deployment insights failed: {str(e)}", extra={'error': str(e)})
                return json.dumps({
                    "success": False,
                    "error": str(e)
                }, indent=2)
