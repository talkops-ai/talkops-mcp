"""Tool 23: Validate Deployment Policy.

Policy enforcement and compliance validation.
"""

import json
from typing import Any, Optional
from fastmcp import Context
from argoflow_mcp_server.tools.base import BaseTool


class PolicyValidationTools(BaseTool):
    """Tools for deployment policy validation."""
    
    def register(self, mcp_instance) -> None:
        """Register policy validation tools with FastMCP."""
        
        @mcp_instance.tool()
        async def orch_validate_deployment_policy(
            app_name: str,
            namespace: str = "default",
            custom_policies: Optional[str] = None,
            ctx: Context = None
        ) -> str:
            """Validate deployment against governance policies.
            
            Validates deployment configuration against security, compliance,
            and custom policies before deployment.
            
            Args:
                app_name: Application/rollout name to validate
                namespace: Kubernetes namespace (default: 'default')
                custom_policies: Optional JSON string of custom policies
            
            Returns:
                JSON string with validation result and violations
            
            Policies Checked:
                - Security: No privileged containers, resource limits set
                - Compliance: Required labels, minimum replicas, namespace rules
                - Strategy: Proper deployment strategy configured
                - Custom: User-defined policies (if provided)
            
            Custom Policy Format:
                {
                    "policy-name": {
                        "severity": "high|medium|low",
                        "description": "Policy description"
                    }
                }
            
            Example:
                orch_validate_deployment_policy(
                    app_name="api-service",
                    namespace="production"
                )
            """
            await ctx.info(
                f"Validating deployment policy for '{app_name}'",
                extra={'app_name': app_name, 'namespace': namespace}
            )
            
            try:
                # Parse custom policies if provided
                custom_policies_dict = None
                if custom_policies:
                    try:
                        custom_policies_dict = json.loads(custom_policies)
                    except json.JSONDecodeError:
                        await ctx.error("Invalid custom_policies JSON format")
                        return json.dumps({
                            "success": False,
                            "error": "Invalid custom_policies JSON format"
                        }, indent=2)
                
                orch_service = self.service_locator.get('orch_service')
                if not orch_service:
                    await ctx.error("Orchestration service not available")
                    return json.dumps({
                        "success": False,
                        "error": "Orchestration service not available"
                    }, indent=2)
                
                result = await orch_service.validate_deployment_policy(
                    app_name=app_name,
                    namespace=namespace,
                    custom_policies=custom_policies_dict
                )
                
                if result.get("status") == "success":
                    validation_passed = result.get("validation_result") == "passed"
                    if validation_passed:
                        await ctx.info(
                            f"Policy validation passed for '{app_name}'",
                            extra={'app_name': app_name}
                        )
                    else:
                        await ctx.warning(
                            f"Policy validation failed for '{app_name}': {result.get('violations_count')} violations",
                            extra={'app_name': app_name, 'violations': result.get('violations_count')}
                        )
                    
                    return json.dumps({
                        "success": True,
                        "validation_passed": validation_passed,
                        **{k: v for k, v in result.items() if k != "status"}
                    }, indent=2)
                else:
                    await ctx.error(
                        f"Policy validation error: {result.get('message')}",
                        extra={'app_name': app_name}
                    )
                    return json.dumps({
                        "success": False,
                        "error": result.get("message", "Unknown error")
                    }, indent=2)
                    
            except Exception as e:
                await ctx.error(f"Policy validation failed: {str(e)}", extra={'error': str(e)})
                return json.dumps({
                    "success": False,
                    "error": str(e)
                }, indent=2)
