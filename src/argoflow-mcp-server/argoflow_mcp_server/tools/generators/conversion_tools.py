"""Generator tools for converting Deployments to Rollouts and creating supporting resources."""

import json
from typing import Dict, Any, List, Optional
from pydantic import Field
from fastmcp import Context

from argoflow_mcp_server.tools.base import BaseTool


class GeneratorTools(BaseTool):
    """Tools for generating Rollout resources from Deployments."""
    
    def register(self, mcp_instance) -> None:
        """Register generator tools with FastMCP."""
        
        @mcp_instance.tool()
        async def convert_deployment_to_rollout(
            deployment_yaml: str = Field(..., description="Kubernetes Deployment YAML as string"),
            strategy: str = Field(default="canary", description="Rollout strategy: canary or bluegreen"),
            ctx: Context = None
        ) -> str:
            """Convert a Kubernetes Deployment to an Argo Rollout.
            
            This tool bridges the gap between standard K8s Deployments (created by ArgoCD)
            and Argo Rollouts for progressive delivery.
            
            Args:
                deployment_yaml: Deployment YAML as string
                strategy: Deployment strategy ("canary" or "bluegreen")
            
            Returns:
                JSON string with converted Rollout YAML
            
            Example:
                Input: Deployment with replicas, containers, etc.
                Output: Rollout with canary strategy and default steps
            """
            await ctx.info(
                f"Converting Deployment to Rollout with {strategy} strategy",
                extra={'strategy': strategy}
            )
            
            try:
                result = await self.generator_service.convert_deployment_to_rollout(
                    deployment_yaml=deployment_yaml,
                    strategy=strategy
                )
                
                if result.get("status") == "success":
                    app_name = result.get("app_name")
                    await ctx.info(
                        f"Successfully converted Deployment '{app_name}' to Rollout",
                        extra={'app_name': app_name, 'strategy': strategy}
                    )
                else:
                    await ctx.error(f"Conversion failed: {result.get('error')}")
                
                return json.dumps(result, indent=2)
                
            except Exception as e:
                error_msg = f"Conversion failed: {str(e)}"
                await ctx.error(error_msg)
                return json.dumps({"error": error_msg}, indent=2)
        
        @mcp_instance.tool()
        async def create_traefik_service_for_rollout(
            app_name: str = Field(..., description="Application name"),
            stable_service: str = Field(..., description="K8s Service name for stable version"),
            canary_service: str = Field(..., description="K8s Service name for canary version"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            initial_canary_weight: int = Field(default=5, ge=0, le=100, description="Initial traffic % to canary"),
            port: int = Field(default=80, description="Service port"),
            ctx: Context = None
        ) -> str:
            """Create a Traefik WeightedService for canary traffic splitting.
            
            This bridges Argo Rollouts with Traefik for progressive traffic shifting.
            
            Args:
                app_name: Application name
                stable_service: K8s Service name for stable pods
                canary_service: K8s Service name for canary pods
                namespace: Kubernetes namespace
                initial_canary_weight: Initial canary traffic percentage (0-100)
                port: Service port number
            
            Returns:
                JSON string with TraefikService YAML
            
            Example:
                Creates a TraefikService that splits traffic 95% stable / 5% canary
            """
            await ctx.info(
                f"Creating Traefik WeightedService for {app_name}",
                extra={
                    'app_name': app_name,
                    'stable_service': stable_service,
                    'canary_service': canary_service,
                    'initial_canary_weight': initial_canary_weight
                }
            )
            
            try:
                result = await self.generator_service.create_traefik_service_for_rollout(
                    app_name=app_name,
                    stable_service=stable_service,
                    canary_service=canary_service,
                    namespace=namespace,
                    initial_canary_weight=initial_canary_weight,
                    port=port
                )
                
                if result.get("status") == "success":
                    stable_weight = result.get("stable_weight")
                    canary_weight = result.get("canary_weight")
                    await ctx.info(
                        f"Created TraefikService: {stable_weight}% stable, {canary_weight}% canary",
                        extra={
                            'app_name': app_name,
                            'stable_weight': stable_weight,
                            'canary_weight': canary_weight
                        }
                    )
                else:
                    await ctx.error(f"TraefikService creation failed: {result.get('error')}")
                
                return json.dumps(result, indent=2)
                
            except Exception as e:
                error_msg = f"Failed to create TraefikService: {str(e)}"
                await ctx.error(error_msg)
                return json.dumps({"error": error_msg}, indent=2)
        
        @mcp_instance.tool()
        async def create_analysis_template_for_rollout(
            service_name: str = Field(..., description="Service name to monitor"),
            prometheus_url: str = Field(..., description="Prometheus server URL"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            error_rate_threshold: float = Field(default=5.0, description="Max acceptable error rate (%)"),
            latency_p99_threshold: float = Field(default=2000.0, description="Max P99 latency (ms)"),
            latency_p95_threshold: float = Field(default=1000.0, description="Max P95 latency (ms)"),
            ctx: Context = None
        ) -> str:
            """Create an Argo AnalysisTemplate for automated canary health validation.
            
            Defines metrics, thresholds, and failure conditions for auto-rollback.
            
            Args:
                service_name: Service name to monitor
                prometheus_url: Prometheus server URL (e.g., http://prometheus:9090)
                namespace: Kubernetes namespace
                error_rate_threshold: Maximum acceptable error rate percentage
                latency_p99_threshold: Maximum acceptable P99 latency in milliseconds
                latency_p95_threshold: Maximum acceptable P95 latency in milliseconds
            
            Returns:
                JSON string with AnalysisTemplate YAML
            
            Example:
                Creates template that monitors error rate, P99, and P95 latency
                Auto-fails if error rate > 5% or latency too high
            """
            await ctx.info(
                f"Creating AnalysisTemplate for {service_name}",
                extra={
                    'service_name': service_name,
                    'prometheus_url': prometheus_url,
                    'error_threshold': error_rate_threshold,
                    'latency_p99': latency_p99_threshold
                }
            )
            
            try:
                result = await self.generator_service.create_analysis_template_for_rollout(
                    service_name=service_name,
                    prometheus_url=prometheus_url,
                    namespace=namespace,
                    error_rate_threshold=error_rate_threshold,
                    latency_p99_threshold=latency_p99_threshold,
                    latency_p95_threshold=latency_p95_threshold
                )
                
                if result.get("status") == "success":
                    metrics_count = len(result.get("metrics", []))
                    await ctx.info(
                        f"Created AnalysisTemplate with {metrics_count} metrics",
                        extra={
                            'service_name': service_name,
                            'metrics_count': metrics_count
                        }
                    )
                else:
                    await ctx.error(f"AnalysisTemplate creation failed: {result.get('error')}")
                
                return json.dumps(result, indent=2)
                
            except Exception as e:
                error_msg = f"Failed to create AnalysisTemplate: {str(e)}"
                await ctx.error(error_msg)
                return json.dumps({"error": error_msg}, indent=2)
        
        @mcp_instance.tool()
        async def validate_deployment_ready_for_rollout(
            deployment_yaml: str = Field(..., description="Kubernetes Deployment YAML as string"),
            ctx: Context = None
        ) -> str:
            """Validate if a Deployment is ready to be converted to a Rollout.
            
            Checks for:
            - Minimum replica count
            - Resource limits/requests
            - Readiness/liveness probes
            - Other best practices
            
            Args:
                deployment_yaml: Deployment YAML as string
            
            Returns:
                JSON string with validation report including:
                - ready: boolean
                - score: 0-100
                - issues: list of blocking problems
                - warnings: list of recommendations
                - recommendations: list of improvements
            
            Example:
                Checks if deployment has >=2 replicas, resource limits, probes, etc.
            """
            await ctx.info("Validating Deployment readiness for Rollout conversion")
            
            try:
                result = await self.generator_service.validate_deployment_ready_for_rollout(
                    deployment_yaml=deployment_yaml
                )
                
                if "error" not in result:
                    app_name = result.get("app_name")
                    ready = result.get("ready")
                    score = result.get("score")
                    issues_count = len(result.get("issues", []))
                    warnings_count = len(result.get("warnings", []))
                    
                    await ctx.info(
                        f"Validation complete: {'Ready' if ready else 'Not ready'} (score: {score}/100)",
                        extra={
                            'app_name': app_name,
                            'ready': ready,
                            'score': score,
                            'issues_count': issues_count,
                            'warnings_count': warnings_count
                        }
                    )
                else:
                    await ctx.error(f"Validation failed: {result.get('error')}")
                
                return json.dumps(result, indent=2)
                
            except Exception as e:
                error_msg = f"Validation failed: {str(e)}"
                await ctx.error(error_msg)
                return json.dumps({"error": error_msg}, indent=2)
