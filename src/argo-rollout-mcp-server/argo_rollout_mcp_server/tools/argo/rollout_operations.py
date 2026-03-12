"""Argo Rollouts operation tools - Control rollout progression and lifecycle."""

from typing import Dict, Any, Optional, List, Literal
from pydantic import Field
from fastmcp import Context

from argo_rollout_mcp_server.tools.base import BaseTool
from argo_rollout_mcp_server.exceptions.custom import (
    ArgoRolloutError,
    RolloutNotFoundError,
    RolloutPromotionError,
    RolloutAbortError,
    AnalysisTemplateError,
)

LIFECYCLE_ACTIONS = Literal["promote", "promote_full", "pause", "resume", "abort", "retry", "skip_analysis"]


class RolloutOperationTools(BaseTool):
    """Tools for controlling rollout progression: promote, abort, pause, resume."""

    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""

        @mcp_instance.tool()
        async def argo_manage_rollout_lifecycle(
            name: str = Field(..., min_length=1, description="Rollout name"),
            action: LIFECYCLE_ACTIONS = Field(
                ...,
                description="Lifecycle action: promote (next step), promote_full (skip to 100%), pause, resume, abort, retry (clear abort to resume), skip_analysis (emergency override)",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            ctx: Context = None,
        ) -> Dict[str, Any]:
            """Manage rollout lifecycle: promote, pause, resume, abort, or skip analysis.

            Unified tool for changing the execution state of an active rollout.
            Use the action parameter to select the operation.

            Args:
                name: Rollout name
                namespace: Kubernetes namespace
                action: One of: promote (next step), promote_full (skip to 100%), pause,
                    resume, abort, retry (clear abort to resume deployment), skip_analysis (emergency override)

            Returns:
                Result dict with action-specific next_action_hints

            Raises:
                RolloutNotFoundError: If rollout doesn't exist
                RolloutPromotionError: If promotion fails (action=promote/promote_full)
                RolloutAbortError: If abort fails (action=abort)
            """
            valid_actions = ("promote", "promote_full", "pause", "resume", "abort", "retry", "skip_analysis")
            if action not in valid_actions:
                raise ValueError(
                    f"Invalid action '{action}'. Must be one of: {', '.join(valid_actions)}"
                )

            await ctx.info(
                f"Executing lifecycle action '{action}' on rollout '{name}'",
                extra={"app_name": name, "namespace": namespace, "action": action},
            )

            try:
                if action == "promote":
                    result = await self.argo_service.promote_rollout(
                        name=name, namespace=namespace, full=False
                    )
                    result.setdefault("next_action_hints", [])
                    result["next_action_hints"].append({
                        "label": "Monitor health after promotion",
                        "description": (
                            "After each promotion step, poll rollout and health resources to "
                            "ensure error rate and latency remain within acceptable bounds."
                        ),
                        "resources": [
                            f"argorollout://rollouts/{namespace}/{name}/detail",
                            f"argorollout://health/{namespace}/{name}/details",
                        ],
                    })
                    result["next_action_hints"].append({
                        "label": "Decide next step",
                        "description": (
                            "If metrics look good after the wait period, call "
                            "argo_manage_rollout_lifecycle(action='promote') again. "
                            "If they degrade, use action='abort'."
                        ),
                        "suggested_tool": "argo_manage_rollout_lifecycle",
                        "suggested_args": {"name": name, "namespace": namespace},
                    })
                elif action == "promote_full":
                    result = await self.argo_service.promote_rollout(
                        name=name, namespace=namespace, full=True
                    )
                    result.setdefault("next_action_hints", [])
                    result["next_action_hints"].append({
                        "label": "Monitor health after promotion",
                        "description": (
                            "After each promotion step, poll rollout and health resources to "
                            "ensure error rate and latency remain within acceptable bounds."
                        ),
                        "resources": [
                            f"argorollout://rollouts/{namespace}/{name}/detail",
                            f"argorollout://health/{namespace}/{name}/details",
                        ],
                    })
                    result["next_action_hints"].append({
                        "label": "Final verification",
                        "description": (
                            "Once fully promoted, verify the rollout is Healthy via the "
                            "rollout detail and health resources."
                        ),
                        "resources": [
                            f"argorollout://rollouts/{namespace}/{name}/detail",
                            f"argorollout://health/{namespace}/{name}/details",
                        ],
                    })
                elif action == "abort":
                    await ctx.warning(
                        f"Aborting rollout '{name}' - will rollback to stable",
                        extra={"app_name": name, "namespace": namespace},
                    )
                    result = await self.argo_service.abort_rollout(
                        name=name, namespace=namespace
                    )
                    result.setdefault("next_action_hints", [])
                    result["next_action_hints"].append({
                        "label": "Confirm rollback to stable",
                        "description": (
                            "Check the rollout detail resource and cluster health to verify that "
                            "traffic and pods are fully reverted to the previous stable version."
                        ),
                        "resources": [
                            f"argorollout://rollouts/{namespace}/{name}/detail",
                            "argorollout://health/summary",
                        ],
                    })
                elif action == "retry":
                    result = await self.argo_service.retry_rollout(
                        name=name, namespace=namespace
                    )
                    result.setdefault("next_action_hints", [])
                    result["next_action_hints"].append({
                        "label": "Monitor deployment progression",
                        "description": (
                            "After retry, the rollout will resume. Poll the rollout detail "
                            "until canary is at the first step (5%), then promote through steps."
                        ),
                        "resources": [
                            f"argorollout://rollouts/{namespace}/{name}/detail",
                            f"argorollout://health/{namespace}/{name}/details",
                        ],
                        "suggested_tool": "argo_manage_rollout_lifecycle",
                        "suggested_args": {"name": name, "namespace": namespace, "action": "promote"},
                    })
                elif action == "pause":
                    result = await self.argo_service.pause_rollout(
                        name=name, namespace=namespace
                    )
                    result.setdefault("next_action_hints", [])
                    result["next_action_hints"].append({
                        "label": "While paused",
                        "description": (
                            "Inspect rollout and health resources to decide whether to "
                            "resume promotion, keep the rollout paused, or abort."
                        ),
                        "resources": [
                            f"argorollout://rollouts/{namespace}/{name}/detail",
                            f"argorollout://health/{namespace}/{name}/details",
                        ],
                    })
                elif action == "resume":
                    result = await self.argo_service.resume_rollout(
                        name=name, namespace=namespace
                    )
                    result.setdefault("next_action_hints", [])
                    result["next_action_hints"].append({
                        "label": "After resuming",
                        "description": (
                            "Monitor the rollout and health resources to ensure the resumed "
                            "promotion behaves as expected; be ready to abort if metrics regress."
                        ),
                        "resources": [
                            f"argorollout://rollouts/{namespace}/{name}/detail",
                            f"argorollout://health/{namespace}/{name}/details",
                        ],
                        "suggested_tool": "argo_manage_rollout_lifecycle",
                        "suggested_args": {
                            "name": name,
                            "namespace": namespace,
                            "action": "abort",
                        },
                    })
                elif action == "skip_analysis":
                    await ctx.warning(
                        f"EMERGENCY OVERRIDE: Skipping analysis for rollout '{name}'",
                        extra={"app_name": name, "namespace": namespace},
                    )
                    result = await self.argo_service.skip_analysis_promote(
                        name=name, namespace=namespace
                    )
                    await ctx.warning(
                        f"Analysis skipped for rollout '{name}' - ensure manual validation was performed",
                        extra={"app_name": name},
                    )
                    result.setdefault("next_action_hints", [])
                    result["next_action_hints"].append({
                        "label": "Post-override safety checks",
                        "description": (
                            "Immediately check rollout and application health, and consider "
                            "configuring proper analysis templates to avoid needing this "
                            "emergency override in the future."
                        ),
                        "resources": [
                            f"argorollout://rollouts/{namespace}/{name}/detail",
                            f"argorollout://health/{namespace}/{name}/details",
                        ],
                        "suggested_tool": "argo_configure_analysis_template",
                        "suggested_args": {
                            "rollout_name": name,
                            "namespace": namespace,
                            "mode": "execute",
                        },
                    })
                else:
                    raise ValueError(f"Unhandled action: {action}")

                await ctx.info(
                    f"Successfully executed '{action}' on rollout '{name}'",
                    extra={"app_name": name, "action": action},
                )
                return result

            except RolloutPromotionError as e:
                await ctx.error(f"Promotion failed: {str(e)}")
                raise
            except RolloutAbortError as e:
                await ctx.error(f"Abort failed: {str(e)}")
                raise
            except RolloutNotFoundError as e:
                await ctx.error(f"Rollout not found: {str(e)}")
                raise
            except Exception as e:
                if isinstance(e, (RolloutPromotionError, RolloutAbortError, RolloutNotFoundError)):
                    raise
                await ctx.error(f"Lifecycle action '{action}' failed: {str(e)}")
                raise ArgoRolloutError(f"Lifecycle action failed: {str(e)}")

        @mcp_instance.tool()
        async def argo_configure_analysis_template(
            rollout_name: str = Field(..., min_length=1, description="Rollout name"),
            mode: Literal["execute", "generate_yaml"] = Field(
                ...,
                description="execute: create AnalysisTemplate CRD and link to rollout. generate_yaml: return YAML only (GitOps review).",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            template_name: Optional[str] = Field(
                default=None,
                description="Analysis template name. Defaults to {rollout_name}-analysis or {service_name}-analysis.",
            ),
            metrics: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description="Custom metrics (execute only). If omitted with execute, uses threshold-based or default.",
            ),
            service_name: Optional[str] = Field(
                default=None,
                description="Service name for Prometheus job selector (threshold-based). Defaults to rollout_name.",
            ),
            prometheus_url: Optional[str] = Field(
                default=None,
                description="Prometheus URL for threshold-based metrics. If omitted, uses PROMETHEUS_URL env var or http://prometheus:9090.",
            ),
            error_rate_threshold: float = Field(default=5.0, description="Max error rate percent (threshold-based)."),
            latency_p99_threshold: float = Field(default=2000.0, description="Max P99 latency ms (threshold-based)."),
            latency_p95_threshold: float = Field(default=1000.0, description="Max P95 latency ms (threshold-based)."),
            scope: Literal["namespace", "cluster"] = Field(
                default="namespace",
                description="namespace: create AnalysisTemplate (namespace-scoped). cluster: create ClusterAnalysisTemplate (reusable across cluster).",
            ),
            ctx: Context = None,
        ):
            """Configure AnalysisTemplate for rollout validation: create+link (execute) or generate YAML (generate_yaml).
            
            Unified tool replacing create_analysis_template_for_rollout and argo_set_analysis_template.
            
            Args:
                rollout_name: Rollout to configure
                mode: execute (create CRD + link) or generate_yaml (return YAML only)
                namespace: Kubernetes namespace
                template_name: Template name (default: {rollout_name}-analysis)
                metrics: Custom metrics for execute. If None, uses threshold-based or default.
                service_name: For threshold-based (default: rollout_name)
                prometheus_url: Prometheus URL for threshold-based
                error_rate_threshold, latency_p99_threshold, latency_p95_threshold: Threshold params
            
            Returns:
                execute: dict with status, template_name, rollout, message
                generate_yaml: dict with template_yaml, template_name, metrics, thresholds
            """
            svc_name = service_name or rollout_name
            tpl_name = template_name or f"{svc_name}-analysis"
            effective_prometheus_url = (
                prometheus_url
                or (self.config.prometheus_url if self.config else None)
                or "http://prometheus:9090"
            )

            if mode == "generate_yaml":
                await ctx.info(
                    f"Generating AnalysisTemplate YAML for '{svc_name}'",
                    extra={"service_name": svc_name, "namespace": namespace},
                )
                try:
                    result = await self.generator_service.create_analysis_template_for_rollout(
                        service_name=svc_name,
                        prometheus_url=effective_prometheus_url,
                        namespace=namespace,
                        error_rate_threshold=error_rate_threshold,
                        latency_p99_threshold=latency_p99_threshold,
                        latency_p95_threshold=latency_p95_threshold,
                        scope=scope,
                    )
                    result.setdefault("next_action_hints", [])
                    result["next_action_hints"].append({
                        "label": "Apply and link to rollout",
                        "description": (
                            "Use argo_configure_analysis_template(mode='execute') with the same "
                            "params to create the CRD and link it to the rollout."
                        ),
                        "suggested_tool": "argo_configure_analysis_template",
                        "suggested_args": {
                            "rollout_name": rollout_name,
                            "mode": "execute",
                            "namespace": namespace,
                            "service_name": svc_name,
                            "prometheus_url": effective_prometheus_url,
                            "error_rate_threshold": error_rate_threshold,
                            "latency_p99_threshold": latency_p99_threshold,
                            "latency_p95_threshold": latency_p95_threshold,
                            "scope": scope,
                        },
                    })
                    return result
                except Exception as e:
                    await ctx.error(f"AnalysisTemplate generation failed: {str(e)}")
                    raise ArgoRolloutError(f"AnalysisTemplate generation failed: {str(e)}")

            # mode == "execute"
            await ctx.info(
                f"Configuring analysis template '{tpl_name}' for rollout '{rollout_name}'",
                extra={"rollout_name": rollout_name, "template_name": tpl_name, "namespace": namespace},
            )
            if metrics:
                await ctx.debug(f"Using custom metrics: {len(metrics)} metric(s)")
                metrics_to_use = metrics
            else:
                metrics_to_use = self.generator_service.get_analysis_metrics_from_thresholds(
                    service_name=svc_name,
                    prometheus_url=effective_prometheus_url,
                    error_rate_threshold=error_rate_threshold,
                    latency_p99_threshold=latency_p99_threshold,
                    latency_p95_threshold=latency_p95_threshold,
                )
                await ctx.debug(f"Using threshold-based metrics (error<{error_rate_threshold}%%, p99<{latency_p99_threshold}ms)")

            try:
                result = await self.argo_service.set_analysis_template(
                    rollout_name=rollout_name,
                    template_name=tpl_name,
                    namespace=namespace,
                    metrics=metrics_to_use,
                    scope=scope,
                )
                await ctx.info(
                    f"Successfully configured analysis template '{tpl_name}' for rollout '{rollout_name}'",
                    extra={"rollout_name": rollout_name, "template_name": tpl_name},
                )
                result.setdefault("next_action_hints", [])
                result["next_action_hints"].append({
                    "label": "Use analysis in future deployments",
                    "description": (
                        "When you next update the rollout image, the analysis template "
                        "will auto-validate canary health. Use argo_update_rollout(update_type='image')."
                    ),
                    "suggested_tool": "argo_update_rollout",
                    "suggested_args": {
                        "name": rollout_name,
                        "namespace": namespace,
                        "update_type": "image",
                    },
                })
                return result
            except AnalysisTemplateError as e:
                await ctx.error(f"Analysis template configuration failed: {str(e)}")
                raise
            except RolloutNotFoundError as e:
                await ctx.error(f"Rollout not found: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(f"Failed to configure analysis template: {str(e)}")
                raise ArgoRolloutError("Analysis configuration failed")
        
