"""Argo Rollouts management tools - CRUD operations for rollouts."""

import json
from typing import Dict, Any, Optional, List, Literal
from pydantic import Field
from fastmcp import Context

from argo_rollout_mcp_server.tools.base import BaseTool

UPDATE_ROLLOUT_TYPES = Literal["image", "strategy", "traffic_routing", "workload_ref"]
from argo_rollout_mcp_server.exceptions.custom import (
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
                description=(
                    'Canary steps. Supported step types: setWeight, pause, setCanaryScale (requires trafficRouting), '
                    'analysis (inline AnalysisTemplate), experiment. Examples: '
                    'setWeight: {"setWeight": 25}; pause: {"pause": {"duration": "5m"}} or {"pause": {}}; '
                    'setCanaryScale: {"setCanaryScale": {"replicas": 2}} or {"setCanaryScale": {"matchTrafficWeight": true}}; '
                    'analysis: {"analysis": {"templates": [{"templateName": "success-rate"}], "args": [{"name": "service-name", "value": "my-app"}]}}.'
                )
            ),
            traefik_service_name: Optional[str] = Field(
                default=None,
                description='TraefikService name for native traffic routing (enables Argo↔Traefik integration). Mutually exclusive with gateway_api_config.'
            ),
            gateway_api_config: Optional[Dict[str, Any]] = Field(
                default=None,
                description=(
                    'Gateway API plugin config for HTTPRoute-based canaries (Traefik 3.x, Envoy Gateway). '
                    'Mutually exclusive with traefik_service_name. Example: {"httpRoute": "my-app-route", "namespace": "default"}. '
                    'For multiple routes: {"httpRoutes": [{"name": "route1", "namespace": "default"}]}.'
                )
            ),
            stable_service: Optional[str] = Field(
                default=None,
                description='K8s Service name for stable pods (default: {name}-stable)'
            ),
            canary_service: Optional[str] = Field(
                default=None,
                description='K8s Service name for canary pods (default: {name}-canary)'
            ),
            # Blue-Green specific params
            active_service: Optional[str] = Field(
                default=None,
                description='K8s Service name for active pods (blue-green, default: {name}-active)'
            ),
            preview_service: Optional[str] = Field(
                default=None,
                description='K8s Service name for preview pods (blue-green, default: {name}-preview)'
            ),
            auto_create_services: bool = Field(
                default=True,
                description=(
                    'If True (default), automatically create the prerequisite stable+canary '
                    '(or active+preview for bluegreen) K8s Services before creating the Rollout. '
                    'Eliminates the need to call create_stable_canary_services separately. '
                    'Idempotent — safe to call if services already exist.'
                )
            ),
            service_port: int = Field(
                default=80,
                description='Port for the auto-created K8s Services (only used when auto_create_services=True)'
            ),
            service_target_port: Optional[int] = Field(
                default=None,
                description='Target port on pods for auto-created Services (defaults to service_port)'
            ),
            selector_labels: Optional[Dict[str, str]] = Field(
                default=None,
                description='Pod selector labels for auto-created Services (default: {app: name})'
            ),
            auto_promotion: bool = Field(
                default=False,
                description='Auto-promote blue-green after preview is ready'
            ),
            auto_promotion_seconds: Optional[int] = Field(
                default=None,
                description='Auto-promote after N seconds (blue-green)'
            ),
            scale_down_delay_seconds: Optional[int] = Field(
                default=None,
                description='Delay old RS scale-down after promotion (blue-green)'
            ),
            preview_replica_count: Optional[int] = Field(
                default=None,
                description='Number of preview pods (blue-green, default: same as replicas)'
            ),
            pre_promotion_analysis: Optional[Dict[str, Any]] = Field(
                default=None,
                description='AnalysisTemplate to run before promotion (blue-green)'
            ),
            post_promotion_analysis: Optional[Dict[str, Any]] = Field(
                default=None,
                description='AnalysisTemplate to run after promotion (blue-green)'
            ),
            anti_affinity: Optional[Dict[str, Any]] = Field(
                default=None,
                description='Anti-affinity between active and preview pods (blue-green)'
            ),
            active_metadata: Optional[Dict[str, Any]] = Field(
                default=None,
                description='Labels/annotations to add to active pods (blue-green)'
            ),
            preview_metadata: Optional[Dict[str, Any]] = Field(
                default=None,
                description='Labels/annotations to add to preview pods (blue-green)'
            ),
            abort_scale_down_delay_seconds: Optional[int] = Field(
                default=None,
                description='Delay preview RS scale-down on abort (blue-green)'
            ),
            resource_requests: Optional[Dict[str, str]] = Field(
                default=None,
                description='Container resource requests (e.g. {"memory": "32Mi", "cpu": "5m"}). Optional.'
            ),
            resource_limits: Optional[Dict[str, str]] = Field(
                default=None,
                description='Container resource limits (e.g. {"memory": "64Mi", "cpu": "100m"}). Optional.'
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
                Basic (setWeight + pause):
                    [{"setWeight": 10}, {"pause": {"duration": "5m"}}, {"setWeight": 25}, {"pause": {}}, {"setWeight": 100}]
                With setCanaryScale (requires traefik_service_name):
                    [{"setCanaryScale": {"replicas": 1}}, {"setWeight": 20}, {"pause": {}}, {"setWeight": 100}]
                With inline analysis step (templateName must reference existing AnalysisTemplate):
                    [{"setWeight": 20}, {"analysis": {"templates": [{"templateName": "success-rate"}], "args": [{"name": "service-name", "value": "my-app"}]}}, {"setWeight": 100}]
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

            if traefik_service_name and gateway_api_config:
                raise RolloutStrategyError(
                    "traefik_service_name and gateway_api_config are mutually exclusive. "
                    "Use one for TraefikService-based routing, or the other for Gateway API HTTPRoute."
                )
            
            if strategy == 'canary' and canary_steps:
                await ctx.debug(f"Using custom canary steps: {len(canary_steps)} steps defined")
            
            # --- Auto-create prerequisite K8s Services ---
            services_created = []
            services_already_existed = []
            if auto_create_services and strategy in ('canary', 'bluegreen'):
                if strategy == 'canary':
                    svc_stable = stable_service or f"{name}-stable"
                    svc_canary = canary_service or f"{name}-canary"
                    # Ensure the rollout will reference the right names
                    stable_service = svc_stable
                    canary_service = svc_canary
                    svc_pairs = [
                        (svc_stable, f"{name}-stable"),
                        (svc_canary, f"{name}-canary"),
                    ]
                else:  # bluegreen
                    svc_active = active_service or f"{name}-active"
                    svc_preview = preview_service or f"{name}-preview"
                    active_service = svc_active
                    preview_service = svc_preview
                    svc_pairs = [
                        (svc_active, f"{name}-active"),
                        (svc_preview, f"{name}-preview"),
                    ]
                
                await ctx.info(
                    f"Auto-creating prerequisite K8s Services for '{name}' ({strategy})",
                    extra={'services': [s[0] for s in svc_pairs], 'namespace': namespace}
                )

                for svc_name, _ in svc_pairs:
                    # Derive a clean app_name from the just-computed stable/canary name
                    svc_result = await self.generator_service.create_stable_canary_services(
                        app_name=svc_name.rsplit("-", 1)[0],  # strip "-stable"/"-canary" suffix
                        namespace=namespace,
                        port=service_port,
                        target_port=service_target_port,
                        selector_labels=selector_labels or {"app": name},
                        apply=True,
                    )
                    services_created.extend(svc_result.get("created", []))
                    services_already_existed.extend(svc_result.get("already_existed", []))
                    for s in svc_result.get("created", []):
                        await ctx.info(f"\u2705 Created Service: {s}")
                    for s in svc_result.get("already_existed", []):
                        await ctx.info(f"\u2139\ufe0f  Service '{s}' already exists \u2014 skipped")
            try:
                result = await self.argo_service.create_rollout(
                    name=name,
                    namespace=namespace,
                    image=image,
                    replicas=replicas,
                    strategy=strategy,
                    canary_steps=canary_steps,
                    traefik_service_name=traefik_service_name,
                    gateway_api_config=gateway_api_config,
                    stable_service=stable_service,
                    canary_service=canary_service,
                    active_service=active_service,
                    preview_service=preview_service,
                    auto_promotion=auto_promotion,
                    auto_promotion_seconds=auto_promotion_seconds,
                    scale_down_delay_seconds=scale_down_delay_seconds,
                    preview_replica_count=preview_replica_count,
                    pre_promotion_analysis=pre_promotion_analysis,
                    post_promotion_analysis=post_promotion_analysis,
                    anti_affinity=anti_affinity,
                    active_metadata=active_metadata,
                    preview_metadata=preview_metadata,
                    abort_scale_down_delay_seconds=abort_scale_down_delay_seconds,
                    resource_requests=resource_requests,
                    resource_limits=resource_limits,
                )
                
                await ctx.info(
                    f"Successfully created rollout '{name}'",
                    extra={
                        'rollout_name': name,
                        'namespace': namespace,
                        'strategy': strategy
                    }
                )
                
                # Enrich result with service creation summary
                if auto_create_services and strategy in ('canary', 'bluegreen'):
                    result['services_auto_created'] = services_created
                    result['services_already_existed'] = services_already_existed
                    result['services_note'] = (
                        f"{'✅' if services_created else 'ℹ️'} Services: "
                        f"created={services_created or 'none'}, "
                        f"already_existed={services_already_existed or 'none'}"
                    )

                # Add workflow-aware hints for what to do after creating a rollout.
                result.setdefault("next_action_hints", [])
                result["next_action_hints"].append({
                    "label": "Verify rollout status",
                    "description": (
                        "Read the rollout detail resource and wait for the phase to become "
                        "Healthy before driving traffic or promoting further."
                    ),
                    "resource": f"argorollout://rollouts/{namespace}/{name}/detail"
                })
                if strategy == "canary":
                    result["next_action_hints"].append({
                        "label": "Optional: Link traffic routing for canary",
                        "description": (
                            "If you use Traefik or another ingress with weighted routing, "
                            "link this rollout to your traffic service so canary weights "
                            "can be shifted gradually."
                        ),
                        "suggested_tool": "argo_update_rollout",
                        "suggested_args": {
                            "name": name,
                            "namespace": namespace,
                            "update_type": "traffic_routing",
                        }
                    })
                result["next_action_hints"].append({
                    "label": "Optional: Configure automated analysis",
                    "description": (
                        "Attach a Prometheus-backed AnalysisTemplate so the rollout can "
                        "auto-abort on failures instead of relying only on manual checks."
                    ),
                    "suggested_tool": "argo_configure_analysis_template",
                    "suggested_args": {
                        "rollout_name": name,
                        "namespace": namespace,
                        "mode": "execute",
                    }
                })
                
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
        async def argo_delete_rollout(
            name: str = Field(..., min_length=1, description='Rollout name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            clean_all: bool = Field(default=False, description='Delete associated services, analysis templates, and experiments'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Delete an Argo Rollout.
            
            Permanently deletes a rollout and all associated resources.
            
            Args:
                name: Rollout name
                namespace: Kubernetes namespace
                clean_all: Whether to attempt deleting associated services, analysis templates, and experiments
            
            Returns:
                Deletion result
            
            Raises:
                RolloutNotFoundError: If rollout doesn't exist
            """
            await ctx.warning(
                f"Deleting rollout '{name}' from namespace '{namespace}' (clean_all={clean_all})",
                extra={'rollout_name': name, 'namespace': namespace, 'clean_all': clean_all}
            )
            
            try:
                result = await self.argo_service.delete_rollout(
                    name=name,
                    namespace=namespace,
                    clean_all=clean_all
                )
                
                await ctx.info(
                    f"Successfully deleted rollout '{name}'",
                    extra={'rollout_name': name, 'namespace': namespace}
                )

                # Help agents close the loop after destructive operations.
                result.setdefault("next_action_hints", [])
                result["next_action_hints"].append({
                    "label": "Verify cleanup",
                    "description": (
                        "Confirm that traffic now points to the intended backend (for example, "
                        "a standard Deployment) and that no orphaned Services or AnalysisRuns "
                        "remain."
                    )
                })
                
                return result
            
            except RolloutNotFoundError as e:
                await ctx.error(f"Rollout not found: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(f"Failed to delete rollout: {str(e)}")
                raise ArgoRolloutError(f'Deletion failed: {str(e)}')
        
        @mcp_instance.tool()
        async def argo_update_rollout(
            name: str = Field(..., min_length=1, description="Rollout name"),
            update_type: UPDATE_ROLLOUT_TYPES = Field(
                ...,
                description="Update type: image, strategy, traffic_routing, or workload_ref",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            new_image: Optional[str] = Field(default=None, description="New container image (required for update_type=image)"),
            container_name: Optional[str] = Field(default=None, description="Container name (for image)"),
            traefik_service_name: Optional[str] = Field(
                default=None,
                description="TraefikService name (for traffic_routing). Mutually exclusive with gateway_api_config.",
            ),
            gateway_api_config: Optional[Dict[str, Any]] = Field(
                default=None,
                description="Gateway API plugin config (for traffic_routing). Example: {\"httpRoute\": \"my-route\", \"namespace\": \"default\"}. Mutually exclusive with traefik_service_name.",
            ),
            clear_routing: bool = Field(default=False, description="Remove trafficRouting (for traffic_routing)"),
            canary_service: Optional[str] = Field(default=None, description="Canary service name (for strategy)"),
            stable_service: Optional[str] = Field(default=None, description="Stable service name (for strategy)"),
            canary_steps: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description=(
                    "Canary steps (for strategy). Supports: setWeight, pause, setCanaryScale, analysis, experiment. "
                    "See argo_create_rollout canary_steps for examples."
                )
            ),
            scale_down_delay_seconds: Optional[int] = Field(default=None, description="Scale-down delay (for strategy)"),
            service_port: int = Field(default=80, description="Port for auto-created service (for strategy)"),
            scale_down: Optional[str] = Field(
                default=None,
                description="workloadRef scale-down: never, onsuccess, progressively (for workload_ref)",
            ),
            ctx: Context = None,
        ) -> Dict[str, Any]:
            """Update a rollout: image, strategy, traffic routing, or workloadRef scale-down.

            Unified tool for patching rollout configuration. Use update_type to select the operation.

            Args:
                name: Rollout name
                update_type: image | strategy | traffic_routing | workload_ref
                namespace: Kubernetes namespace
                new_image: For image — new container image
                container_name: For image — container name
                traefik_service_name: For traffic_routing — TraefikService to link
                clear_routing: For traffic_routing — remove trafficRouting
                canary_service, stable_service, canary_steps, scale_down_delay_seconds: For strategy
                service_port: For strategy — port for auto-created service
                scale_down: For workload_ref — never | onsuccess | progressively

            Returns:
                Update result
            """
            valid_types = ("image", "strategy", "traffic_routing", "workload_ref")
            if update_type not in valid_types:
                raise ValueError(f"Invalid update_type '{update_type}'. Must be one of: {', '.join(valid_types)}")

            if update_type == "image":
                if not new_image:
                    raise ValueError("update_type=image requires 'new_image' parameter")
                await ctx.info(
                    f"Updating rollout '{name}' image to '{new_image}'",
                    extra={"rollout_name": name, "namespace": namespace, "new_image": new_image},
                )
                result = await self.argo_service.update_rollout_image(
                    name=name,
                    new_image=new_image,
                    namespace=namespace,
                    container_name=container_name,
                )
                await ctx.info(f"Successfully updated rollout '{name}' image", extra={"rollout_name": name})
                result.setdefault("next_action_hints", [])
                result["next_action_hints"].append({
                    "label": "Monitor rollout progression",
                    "description": (
                        "Poll the rollout detail resource until all replicas are updated and "
                        "the phase is Healthy."
                    ),
                    "resource": f"argorollout://rollouts/{namespace}/{name}/detail",
                })
                result["next_action_hints"].append({
                    "label": "Optional: Drive canary steps explicitly",
                    "description": (
                        "If not relying on automatic analysis, advance the canary by "
                        "calling argo_manage_rollout_lifecycle(action='promote'), or abort with action='abort'."
                    ),
                    "suggested_tool": "argo_manage_rollout_lifecycle",
                    "suggested_args": {"name": name, "namespace": namespace},
                })
                return result

            if update_type == "traffic_routing":
                if not traefik_service_name and not gateway_api_config and not clear_routing:
                    raise ValueError(
                        "update_type=traffic_routing requires 'traefik_service_name', 'gateway_api_config', or 'clear_routing=True'"
                    )
                if traefik_service_name and gateway_api_config:
                    raise ValueError("traefik_service_name and gateway_api_config are mutually exclusive")
                await ctx.info(
                    f"Setting trafficRouting on Rollout '{name}'",
                    extra={
                        "rollout": name,
                        "namespace": namespace,
                        "traefik_service": traefik_service_name,
                        "gateway_api_config": gateway_api_config,
                        "clear": clear_routing,
                    },
                )
                result = await self.argo_service.set_traffic_routing(
                    name=name,
                    namespace=namespace,
                    traefik_service_name=traefik_service_name,
                    gateway_api_config=gateway_api_config,
                    clear_routing=clear_routing,
                )
                await ctx.info(result["message"])
                if result.get("persistence_warning"):
                    await ctx.info(result["persistence_warning"])
                result.setdefault("next_action_hints", [])
                if result.get("persistence_warning"):
                    result["next_action_hints"].append({
                        "label": "Persist trafficRouting (ArgoCD/Helm)",
                        "description": result["persistence_warning"],
                        "suggested_tool": "generate_argocd_ignore_differences",
                        "suggested_args": {
                            "include_traefik_service": True,
                            "include_rollout_status": True,
                            "include_rollout_traffic_routing": True,
                        },
                    })
                if clear_routing:
                    result["next_action_hints"].append({
                        "label": "After unlinking traffic routing",
                        "description": (
                            "Verify that future canary promotions rely on replica counts only, "
                            "and update any external ingress configuration if needed."
                        ),
                    })
                else:
                    result["next_action_hints"].append({
                        "label": "Verify canary weight propagation",
                        "description": (
                            "During a canary rollout, monitor the rollout detail resource and "
                            "your TraefikService to confirm weights are updated at each step."
                        ),
                        "resource": f"argorollout://rollouts/{namespace}/{name}/detail",
                    })
                return result

            if update_type == "strategy":
                if canary_service:
                    try:
                        await self.generator_service.create_rollout_service(
                            service_name=canary_service,
                            namespace=namespace,
                            port=service_port,
                            target_port=service_port,
                            selector_labels={"app": name},
                            app_name=name,
                        )
                    except Exception:
                        pass
                await ctx.info(f"Updating canary strategy on Rollout '{name}'", extra={"rollout": name})
                result = await self.argo_service.update_canary_strategy(
                    name=name,
                    namespace=namespace,
                    canary_service=canary_service,
                    stable_service=stable_service,
                    canary_steps=canary_steps,
                    scale_down_delay_seconds=scale_down_delay_seconds,
                )
                await ctx.info(result["message"])
                result.setdefault("next_action_hints", [])
                result["next_action_hints"].append({
                    "label": "Validate updated strategy",
                    "description": (
                        "Before pushing a new image, consider a small canary rollout."
                    ),
                    "suggested_tool": "argo_update_rollout",
                    "suggested_args": {"name": name, "namespace": namespace, "update_type": "image"},
                })
                return result

            if update_type == "workload_ref":
                if not scale_down:
                    raise ValueError("update_type=workload_ref requires 'scale_down' parameter (never|onsuccess|progressively)")
                if scale_down not in ("never", "onsuccess", "progressively"):
                    raise ValueError(f"scale_down must be never, onsuccess, or progressively; got '{scale_down}'")
                result = await self.argo_service.patch_workload_ref_scale_down(
                    name=name,
                    namespace=namespace,
                    scale_down=scale_down,
                )
                await ctx.info(result["message"])
                return result

            raise ValueError(f"Unhandled update_type: {update_type}")

        @mcp_instance.tool()
        async def argo_create_experiment(
            name: str = Field(..., min_length=1, description='Experiment name'),
            templates: List[Dict[str, Any]] = Field(
                ...,
                description='List of template specs. Each: {name, replicas, specRef: "stable"|"canary"} or {name, replicas, template: {podTemplateSpec}}'
            ),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            duration: Optional[str] = Field(default=None, description='Experiment duration (e.g. "20m", "1h")'),
            analyses: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description='List of analysis references. Each: {name, templateName, requiredForCompletion (optional), args (optional)}'
            ),
            progress_deadline_seconds: int = Field(default=300, description='Deadline for ReplicaSets to become available'),
            rollout_name: Optional[str] = Field(
                default=None,
                description='Rollout to resolve stable/canary from (required if templates use specRef)'
            ),
            rollout_namespace: Optional[str] = Field(
                default=None,
                description='Namespace of the Rollout (default: same as namespace)'
            ),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Create a standalone Argo Experiment.
            
            Experiments create ephemeral ReplicaSets for comparison/analysis.
            Can run AnalysisRuns alongside templates to validate metrics.
            
            ⚠️  IMPORTANT: Weighted experiment traffic routing is NOT supported
            with Traefik. Only SMI, ALB, and Istio support experiment traffic
            routing. With Traefik, use experiments for metrics comparison only
            (experiment-as-analysis-step pattern).
            
            Use cases:
            - Run two versions side-by-side to compare metrics
            - Validate canary metrics before shifting real traffic
            - A/B testing for non-traffic metrics (CPU, memory, error rates)
            
            Args:
                name: Experiment name
                namespace: Kubernetes namespace
                templates: Template specs (inline or reference)
                duration: How long to run the experiment
                analyses: AnalysisTemplate references
                progress_deadline_seconds: Pod availability deadline
            
            Returns:
                Creation result with experiment details
            """
            await ctx.info(
                f"Creating Argo Experiment '{name}'",
                extra={
                    'experiment_name': name,
                    'namespace': namespace,
                    'template_count': len(templates),
                    'duration': duration
                }
            )
            
            try:
                result = await self.argo_service.create_experiment(
                    name=name,
                    namespace=namespace,
                    templates=templates,
                    duration=duration,
                    analyses=analyses,
                    progress_deadline_seconds=progress_deadline_seconds,
                    rollout_name=rollout_name,
                    rollout_namespace=rollout_namespace
                )
                
                await ctx.info(
                    f"Experiment '{name}' created successfully",
                    extra={
                        'experiment': name,
                        'templates': result.get('templates', [])
                    }
                )

                # A/B workflow hints: monitor, then act on the results.
                result.setdefault("next_action_hints", [])
                result["next_action_hints"].append({
                    "label": "Monitor experiment progress",
                    "description": (
                        "Poll the experiment status resource until the phase becomes "
                        "Successful or Failed."
                    ),
                    "resource": f"argorollout://experiments/{namespace}/{name}/status"
                })
                result["next_action_hints"].append({
                    "label": "After results are in",
                    "description": (
                        "If the candidate wins, roll the image out with "
                        "argo_update_rollout(update_type='image'). If the baseline wins, clean up "
                        "the experiment with argo_delete_experiment."
                    ),
                    "suggested_tools": [
                        "argo_update_rollout",
                        "argo_delete_experiment"
                    ]
                })
                
                return result
            
            except ArgoRolloutError as e:
                await ctx.error(f"Failed to create experiment: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(f"Failed to create experiment: {str(e)}")
                raise ArgoRolloutError(f'Experiment creation failed: {str(e)}')
        
        @mcp_instance.tool()
        async def argo_delete_experiment(
            name: str = Field(..., min_length=1, description='Experiment name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Delete an Argo Experiment.
            
            Permanently deletes an experiment and its associated ReplicaSets.
            
            Args:
                name: Experiment name
                namespace: Kubernetes namespace
            
            Returns:
                Deletion result
            """
            await ctx.info(
                f"Deleting experiment '{name}'",
                extra={'experiment_name': name, 'namespace': namespace}
            )
            
            try:
                result = await self.argo_service.delete_experiment(
                    name=name,
                    namespace=namespace
                )
                
                await ctx.info(
                    f"Experiment '{name}' deleted successfully",
                    extra={'experiment': name}
                )

                result.setdefault("next_action_hints", [])
                result["next_action_hints"].append({
                    "label": "Confirm winner is in production",
                    "description": (
                        "If the candidate variant won, ensure the main rollout image has been "
                        "updated and the rollout is Healthy before removing any temporary resources."
                    ),
                    "resource_hint": "argorollout://rollouts/{namespace}/{rollout-name}/detail"
                })
                
                return result
            
            except RolloutNotFoundError as e:
                await ctx.error(f"Experiment not found: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(f"Failed to delete experiment: {str(e)}")
                raise ArgoRolloutError(f'Experiment deletion failed: {str(e)}')

        @mcp_instance.tool()
        async def argo_manage_legacy_deployment(
            action: Literal["scale_cluster", "delete_cluster", "generate_scale_down_manifest"] = Field(
                ...,
                description="Action: scale_cluster, delete_cluster, or generate_scale_down_manifest (GitOps)",
            ),
            name: Optional[str] = Field(
                default=None,
                description="Deployment name (required for scale_cluster/delete_cluster; optional for generate when deployment_yaml provided)",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            replicas: Optional[int] = Field(
                default=None,
                description="Target replica count for scale_cluster (e.g. 0 for scale-down)",
            ),
            deployment_yaml: Optional[str] = Field(
                default=None,
                description="Deployment YAML string for generate_scale_down_manifest (GitOps review-only, when Deployment not live in cluster)",
            ),
            ctx: Context = None,
        ):
            """Manage legacy Deployment during workloadRef migration: scale, delete, or generate scale-down manifest.

            Unified tool for Deployment lifecycle operations when migrating to Argo Rollouts.

            Args:
                action: scale_cluster (direct scale), delete_cluster (direct delete),
                    or generate_scale_down_manifest (GitOps — returns YAML with replicas: 0)
                name: Deployment name (required for scale/delete; for generate, use with deployment_yaml or alone)
                namespace: Kubernetes namespace
                replicas: For scale_cluster — target count (e.g. 0)
                deployment_yaml: For generate_scale_down_manifest — raw YAML for review-only workflow

            Returns:
                Action-specific result (scale/delete: dict; generate: JSON with deployment_yaml)
            """
            valid_actions = ("scale_cluster", "delete_cluster", "generate_scale_down_manifest")
            if action not in valid_actions:
                raise ValueError(f"Invalid action '{action}'. Must be one of: {', '.join(valid_actions)}")

            if action == "scale_cluster":
                if not name:
                    raise ValueError("action=scale_cluster requires 'name' parameter")
                if replicas is None:
                    raise ValueError("action=scale_cluster requires 'replicas' parameter")
                await ctx.info(
                    f"Scaling Deployment '{name}' to {replicas} replicas",
                    extra={"deployment": name, "namespace": namespace, "replicas": replicas},
                )
                result = await self.argo_service.scale_deployment(
                    name=name, namespace=namespace, replicas=replicas
                )
                await ctx.info(result["message"])
                return result

            if action == "delete_cluster":
                if not name:
                    raise ValueError("action=delete_cluster requires 'name' parameter")
                await ctx.warning(
                    f"Deleting Deployment '{name}' from namespace '{namespace}'",
                    extra={"deployment": name, "namespace": namespace},
                )
                result = await self.argo_service.delete_deployment(
                    name=name, namespace=namespace
                )
                await ctx.info(result["message"])
                return result

            if action == "generate_scale_down_manifest":
                if not name and not deployment_yaml:
                    raise ValueError(
                        "action=generate_scale_down_manifest requires 'name' or 'deployment_yaml'"
                    )
                await ctx.info("Generating Deployment scale-down manifest for GitOps")
                result = await self.generator_service.generate_deployment_scale_down_manifest(
                    deployment_name=name,
                    deployment_yaml=deployment_yaml,
                    namespace=namespace,
                )
                if result.get("status") == "success":
                    await ctx.info(
                        f"Generated scale-down manifest for '{result['app_name']}' (replicas: 0)",
                        extra={"app_name": result["app_name"]},
                    )
                return json.dumps(result, indent=2)

            raise ValueError(f"Unhandled action: {action}")

