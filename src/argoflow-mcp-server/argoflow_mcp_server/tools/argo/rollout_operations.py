"""Argo Rollouts operation tools - Control rollout progression and lifecycle."""

from typing import Dict, Any, Optional, List
from pydantic import Field
from fastmcp import Context

from argoflow_mcp_server.tools.base import BaseTool
from argoflow_mcp_server.exceptions.custom import (
    ArgoRolloutError,
    RolloutNotFoundError,
    RolloutPromotionError,
    RolloutAbortError,
    AnalysisTemplateError,
)


class RolloutOperationTools(BaseTool):
    """Tools for controlling rollout progression: promote, abort, pause, resume."""
    
    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""
        
        @mcp_instance.tool()
        async def argo_promote_rollout(
            name: str = Field(..., min_length=1, description='Rollout name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
           full: bool = Field(default=False, description='If True, promote fully (skip all remaining steps)'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Promote a rollout to the next step or fully to 100%.
            
            For canary deployments, this advances the rollout to the next traffic weight step.
            Use full=True to skip all remaining steps and promote directly to 100%.
            
            Args:
                name: Rollout name
                namespace: Kubernetes namespace
                full: Skip all steps and promote to 100%
            
            Returns:
                Promotion result
            
            Raises:
                RolloutNotFoundError: If rollout doesn't exist
                RolloutPromotionError: If promotion fails or already at final step
            """
            promotion_type = "full" if full else "incremental"
            await ctx.info(
                f"Promoting rollout '{name}' ({promotion_type})",
                extra={
                    'name': name,
                    'namespace': namespace,
                    'full': full
                }
            )
            
            try:
                result = await self.argo_service.promote_rollout(
                    name=name,
                    namespace=namespace,
                    full=full
                )
                
                await ctx.info(
                    f"Successfully promoted rollout '{name}'",
                    extra={'app_name': name, 'full': full}
                )
                
                return result
            
            except RolloutPromotionError as e:
                await ctx.error(f"Promotion failed: {str(e)}")
                raise
            except RolloutNotFoundError as e:
                await ctx.error(f"Rollout not found: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(f"Failed to promote rollout: {str(e)}")
                raise ArgoRolloutError(f'Promotion failed: {str(e)}')
        
        @mcp_instance.tool()
        async def argo_abort_rollout(
            name: str = Field(..., min_length=1, description='Rollout name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Abort a rollout and roll back to stable version.
            
            Use this to immediately stop a rollout and revert to the previous stable version.
            This is typically used when errors are detected during a canary rollout.
            
            Args:
                name: Rollout name
                namespace: Kubernetes namespace
            
            Returns:
                Abort result
            
            Raises:
                RolloutNotFoundError: If rollout doesn't exist
                RolloutAbortError: If abort operation fails
            """
            await ctx.warning(
                f"Aborting rollout '{name}' - will rollback to stable",
                extra={'app_name': name, 'namespace': namespace}
            )
            
            try:
                result = await self.argo_service.abort_rollout(
                    name=name,
                    namespace=namespace
                )
                
                await ctx.info(
                    f"Successfully aborted rollout '{name}'",
                    extra={'app_name': name}
                )
                
                return result
            
            except RolloutAbortError as e:
                await ctx.error(f"Abort failed: {str(e)}")
                raise
            except RolloutNotFoundError as e:
                await ctx.error(f"Rollout not found: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(f"Failed to abort rollout: {str(e)}")
                raise ArgoRolloutError(f'Abort failed: {str(e)}')
        
        @mcp_instance.tool()
        async def argo_pause_rollout(
            name: str = Field(..., min_length=1, description='Rollout name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Pause a running rollout.
            
            Temporarily stops the rollout progression. Use resume_rollout to continue.
            
            Args:
                name: Rollout name
                namespace: Kubernetes namespace
            
            Returns:
                Pause result
            
            Raises:
                RolloutNotFoundError: If rollout doesn't exist
            """
            await ctx.info(
                f"Pausing rollout '{name}'",
                extra={'app_name': name, 'namespace': namespace}
            )
            
            try:
                result = await self.argo_service.pause_rollout(
                    name=name,
                    namespace=namespace
                )
                
                await ctx.info(
                    f"Successfully paused rollout '{name}'",
                    extra={'app_name': name}
                )
                
                return result
            
            except RolloutNotFoundError as e:
                await ctx.error(f"Rollout not found: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(f"Failed to pause rollout: {str(e)}")
                raise ArgoRolloutError(f'Pause failed: {str(e)}')
        
        @mcp_instance.tool()
        async def argo_resume_rollout(
            name: str = Field(..., min_length=1, description='Rollout name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Resume a paused rollout.
            
            Continues a previously paused rollout.
            
            Args:
                name: Rollout name
                namespace: Kubernetes namespace
            
            Returns:
                Resume result
            
            Raises:
                RolloutNotFoundError: If rollout doesn't exist
            """
            await ctx.info(
                f"Resuming rollout '{name}'",
                extra={'app_name': name, 'namespace': namespace}
            )
            
            try:
                result = await self.argo_service.resume_rollout(
                    name=name,
                    namespace=namespace
                )
                
                await ctx.info(
                    f"Successfully resumed rollout '{name}'",
                    extra={'app_name': name}
                )
                
                return result
            
            except RolloutNotFoundError as e:
                await ctx.error(f"Rollout not found: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(f"Failed to resume rollout: {str(e)}")
                raise ArgoRolloutError(f'Resume failed: {str(e)}')
        
        @mcp_instance.tool()
        async def argo_set_analysis_template(
            rollout_name: str = Field(..., min_length=1, description='Rollout name'),
            template_name: str = Field(..., min_length=1, description='Analysis template name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            metrics: Optional[List[Dict[str, Any]]]= Field(
                default=None,
                description='Metrics configuration (Prometheus queries with success criteria)'
            ),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Configure automated analysis template for rollout validation.
            
            Sets up automated metrics-based validation for a canary rollout.
            Requires Prometheus for metrics collection.
            
            Args:
                rollout_name: Rollout to configure
                template_name: Name for the analysis template
                namespace: Kubernetes namespace
                metrics: Optional custom metrics configuration
            
            Returns:
                Configuration result
            
            Raises:
                RolloutNotFoundError: If rollout doesn't exist
                AnalysisTemplateError: If configuration fails
            
            Example metrics:
                [
                    {
                        "name": "success-rate",
                        "successCriteria": ">= 99",
                        "provider": {
                            "prometheus": {
                                "address": "http://prometheus:9090",
                                "query": "sum(rate(http_requests_total{status=~\"2.*\"}[5m])) / sum(rate(http_requests_total[5m])) * 100"
                            }
                        }
                    }
                ]
            """
            await ctx.info(
                f"Configuring analysis template '{template_name}' for rollout '{rollout_name}'",
                extra={
                    'rollout_name': rollout_name,
                    'template_name': template_name,
                    'namespace': namespace
                }
            )
            
            if metrics:
                await ctx.debug(f"Using custom metrics configuration: {len(metrics)} metric(s)")
            else:
                await ctx.debug("Using default metrics configuration (success rate >= 99%)")
            
            try:
                result = await self.argo_service.set_analysis_template(
                    rollout_name=rollout_name,
                    template_name=template_name,
                    namespace=namespace,
                    metrics=metrics
                )
                
                await ctx.info(
                    f"Successfully configured analysis template '{template_name}' for rollout '{rollout_name}'",
                    extra={
                        'rollout_name': rollout_name,
                        'template_name': template_name
                    }
                )
                
                return result
            
            except AnalysisTemplateError as e:
                await ctx.error(f"Analysis template configuration failed: {str(e)}")
                raise
            except RolloutNotFoundError as e:
                await ctx.error(f"Rollout not found: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(f"Failed to configure analysis template: {str(e)}")
                raise ArgoRolloutError(f'Analysis configuration failed: {str(e)}')
        
        @mcp_instance.tool()
        async def argo_skip_analysis_promote(
            name: str = Field(..., min_length=1, description='Rollout name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Emergency override: Skip analysis and promote to next step.
            
            ⚠️  WARNING: Use only in emergencies when:
            - Analysis metrics are unavailable but the version is verified as healthy
            - Urgent production fix is needed
            - Manual validation has been completed
            
            This bypasses automated analysis and promotes the rollout.
            
            Args:
                name: Rollout name
                namespace: Kubernetes namespace
            
            Returns:
                Override result with warning
            
            Raises:
                RolloutNotFoundError: If rollout doesn't exist
            """
            await ctx.warning(
                f"⚠️  EMERGENCY OVERRIDE: Skipping analysis for rollout '{name}'",
                extra={'app_name': name, 'namespace': namespace}
            )
            
            try:
                result = await self.argo_service.skip_analysis_promote(
                    name=name,
                    namespace=namespace
                )
                
                await ctx.warning(
                    f"Analysis skipped for rollout '{name}' - ensure manual validation was performed",
                    extra={'app_name': name}
                )
                
                return result
            
            except RolloutNotFoundError as e:
                await ctx.error(f"Rollout not found: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(f"Failed to skip analysis: {str(e)}")
                raise ArgoRolloutError(f'Skip analysis failed: {str(e)}')
