"""Argo Rollouts management tools — CRUD and strategy configuration for Rollouts."""

from typing import Any, Dict, List, Literal, Optional
import yaml
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from argo_rollout_mcp_server.exceptions.custom import (
    ArgoRolloutError,
    RolloutStrategyError,
)
from argo_rollout_mcp_server.models.schemas import (
    CanaryServicesConfig,
    ExecutionResult,
    StrategyOptions,
    TrafficRoutingConfig,
    WorkloadOptions,
)
from argo_rollout_mcp_server.tools.base import BaseTool, confirm_destructive_action


class RolloutManagementTools(BaseTool):
    """Tools for creating, updating image/strategy, and deleting Argo Rollouts."""

    def register(self, mcp_instance) -> None:
        """Register rollout management tools with FastMCP based on toolset/write config."""
        if not self.should_register("rollouts", is_write=True):
            return

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Create Argo Rollout",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def argo_create_rollout(
            name: str = Field(..., min_length=1, description="Rollout name"),
            image: str = Field(..., min_length=1, description="Container image (e.g., nginx:1.25)"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            strategy: Literal["canary", "bluegreen", "rolling"] = Field(
                default="canary",
                description="Progressive delivery strategy: canary, bluegreen, or rolling",
            ),
            strategy_options: Optional[StrategyOptions] = Field(
                default=None,
                description="Canary steps, traffic routing, or blue-green options",
            ),
            workload_options: Optional[WorkloadOptions] = Field(
                default=None,
                description="Replicas, container port, and resource requests/limits",
            ),
            service_options: Optional[CanaryServicesConfig] = Field(
                default=None,
                description="Stable/canary or active/preview Service names, ports, and auto-creation",
            ),
            dry_run: bool = Field(
                default=True,
                description="If True (default), validate and return YAML preview without mutating cluster",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Create a new Argo Rollout for progressive delivery (<= 8 parameters).

            Defaults to dry_run=True to preview the generated Rollout and Service
            manifests before applying them to the cluster.
            """
            self.check_write_access("argo_create_rollout")

            s_opts = strategy_options or StrategyOptions()
            w_opts = workload_options or WorkloadOptions()
            svc_opts = service_options or CanaryServicesConfig()

            valid_strategies = ("canary", "bluegreen", "rolling")
            if strategy not in valid_strategies:
                self.handle_error(
                    RolloutStrategyError(
                        f"Invalid strategy '{strategy}'. Must be one of: {', '.join(valid_strategies)}"
                    ),
                    "argo_create_rollout",
                    namespace=namespace,
                    resource_name=name,
                )

            traefik_svc = None
            gw_config = None
            if s_opts.traffic_routing:
                traefik_svc = s_opts.traffic_routing.traefik_service_name
                gw_config = s_opts.traffic_routing.gateway_api_config
                if traefik_svc and gw_config:
                    self.handle_error(
                        RolloutStrategyError(
                            "traefik_service_name and gateway_api_config are mutually exclusive."
                        ),
                        "argo_create_rollout",
                        namespace=namespace,
                        resource_name=name,
                    )

            stable_service = svc_opts.stable_service or (f"{name}-stable" if strategy == "canary" else None)
            canary_service = svc_opts.canary_service or (f"{name}-canary" if strategy == "canary" else None)
            active_service = svc_opts.active_service or (f"{name}-active" if strategy == "bluegreen" else None)
            preview_service = svc_opts.preview_service or (f"{name}-preview" if strategy == "bluegreen" else None)

            if dry_run:
                # Build preview manifest without mutating cluster
                container_spec: Dict[str, Any] = {
                    "name": name,
                    "image": image,
                    "ports": [{"containerPort": w_opts.container_port}],
                }
                if w_opts.resource_requests or w_opts.resource_limits:
                    res: Dict[str, Any] = {}
                    if w_opts.resource_requests:
                        res["requests"] = w_opts.resource_requests
                    if w_opts.resource_limits:
                        res["limits"] = w_opts.resource_limits
                    container_spec["resources"] = res

                preview_spec: Dict[str, Any] = {
                    "replicas": w_opts.replicas,
                    "selector": {"matchLabels": svc_opts.selector_labels or {"app": name}},
                    "template": {
                        "metadata": {"labels": svc_opts.selector_labels or {"app": name}},
                        "spec": {"containers": [container_spec]},
                    },
                    "strategy": {},
                }
                if strategy == "canary":
                    steps = s_opts.steps or [
                        {"setWeight": 5},
                        {"pause": {}},
                        {"setWeight": 10},
                        {"pause": {}},
                        {"setWeight": 25},
                        {"pause": {}},
                        {"setWeight": 50},
                        {"pause": {}},
                    ]
                    canary_cfg: Dict[str, Any] = {
                        "stableService": stable_service,
                        "canaryService": canary_service,
                        "steps": steps,
                    }
                    if traefik_svc:
                        canary_cfg["trafficRouting"] = {
                            "traefik": {"weightedTraefikServiceName": traefik_svc}
                        }
                    elif gw_config:
                        canary_cfg["trafficRouting"] = {
                            "plugins": {"argoproj-labs/gatewayAPI": gw_config}
                        }
                    if s_opts.scale_down_delay_seconds is not None:
                        canary_cfg["scaleDownDelaySeconds"] = s_opts.scale_down_delay_seconds
                    preview_spec["strategy"]["canary"] = canary_cfg
                elif strategy == "bluegreen":
                    bg_cfg: Dict[str, Any] = {
                        "activeService": active_service,
                        "previewService": preview_service,
                        "autoPromotionEnabled": s_opts.auto_promotion_enabled,
                    }
                    if s_opts.auto_promotion_seconds is not None:
                        bg_cfg["autoPromotionSeconds"] = s_opts.auto_promotion_seconds
                    if s_opts.scale_down_delay_seconds is not None:
                        bg_cfg["scaleDownDelaySeconds"] = s_opts.scale_down_delay_seconds
                    if s_opts.preview_replica_count is not None:
                        bg_cfg["previewReplicaCount"] = s_opts.preview_replica_count
                    preview_spec["strategy"]["blueGreen"] = bg_cfg
                else:
                    preview_spec["strategy"]["canary"] = {"steps": []}

                rollout_manifest = {
                    "apiVersion": "argoproj.io/v1alpha1",
                    "kind": "Rollout",
                    "metadata": {"name": name, "namespace": namespace},
                    "spec": preview_spec,
                }
                manifest_str = yaml.dump(rollout_manifest, default_flow_style=False)
                return ExecutionResult(
                    status="preview",
                    summary=f"Previewed Rollout '{name}' in namespace '{namespace}' (strategy={strategy}, dry_run=True). Re-run with dry_run=False to apply.",
                    dry_run=True,
                    manifest=manifest_str,
                    resource_uri=f"argorollout://rollouts/{namespace}/{name}/detail",
                    details={
                        "rollout_name": name,
                        "namespace": namespace,
                        "strategy": strategy,
                        "replicas": w_opts.replicas,
                    },
                )

            try:
                services_created: List[str] = []
                services_already_existed: List[str] = []
                if svc_opts.auto_create and strategy in ("canary", "bluegreen"):
                    # Fix B5: call create_stable_canary_services ONCE with strategy=strategy
                    svc_result = await self.generator_service.create_stable_canary_services(
                        app_name=name,
                        namespace=namespace,
                        port=svc_opts.port,
                        target_port=svc_opts.target_port or w_opts.container_port,
                        selector_labels=svc_opts.selector_labels or {"app": name},
                        apply=True,
                        strategy=strategy,
                    )
                    if svc_result.get("status") == "error":
                        raise ArgoRolloutError(svc_result.get("error", "Service creation failed"))
                    services_created.extend(svc_result.get("created", []))
                    services_already_existed.extend(svc_result.get("already_existed", []))

                result = await self.argo_service.create_rollout(
                    name=name,
                    namespace=namespace,
                    image=image,
                    replicas=w_opts.replicas,
                    strategy=strategy,
                    canary_steps=s_opts.steps,
                    traefik_service_name=traefik_svc,
                    gateway_api_config=gw_config,
                    stable_service=stable_service,
                    canary_service=canary_service,
                    active_service=active_service,
                    preview_service=preview_service,
                    auto_promotion=s_opts.auto_promotion_enabled,
                    auto_promotion_seconds=s_opts.auto_promotion_seconds,
                    scale_down_delay_seconds=s_opts.scale_down_delay_seconds,
                    preview_replica_count=s_opts.preview_replica_count,
                    pre_promotion_analysis=s_opts.pre_promotion_analysis,
                    post_promotion_analysis=s_opts.post_promotion_analysis,
                    abort_scale_down_delay_seconds=s_opts.abort_scale_down_delay_seconds,
                    resource_requests=w_opts.resource_requests,
                    resource_limits=w_opts.resource_limits,
                    dry_run=False,
                )

                return ExecutionResult(
                    status="success",
                    summary=f"Created Rollout '{name}' in namespace '{namespace}' with '{strategy}' strategy.",
                    dry_run=False,
                    manifest=result.get("manifest"),
                    resource_uri=f"argorollout://rollouts/{namespace}/{name}/detail",
                    details={
                        **result,
                        "services_created": services_created,
                        "services_already_existed": services_already_existed,
                    },
                )
            except Exception as e:
                self.handle_error(e, "argo_create_rollout", namespace=namespace, resource_name=name)

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Set Rollout Image",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def argo_set_rollout_image(
            name: str = Field(..., min_length=1, description="Rollout name"),
            image: str = Field(..., min_length=1, description="New container image (e.g., nginx:1.26)"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            container_name: Optional[str] = Field(
                default=None,
                description="Target container name (defaults to first container)",
            ),
            dry_run: bool = Field(
                default=False,
                description="If True, preview image patch without mutating the cluster",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Update the container image on an existing Argo Rollout to trigger a rollout cycle."""
            self.check_write_access("argo_set_rollout_image")

            if dry_run:
                patch_preview = {
                    "spec": {
                        "template": {
                            "spec": {
                                "containers": [
                                    {"name": container_name or name, "image": image}
                                ]
                            }
                        }
                    }
                }
                return ExecutionResult(
                    status="preview",
                    summary=f"Previewed image update on Rollout '{name}' to '{image}' (dry_run=True).",
                    dry_run=True,
                    manifest=yaml.dump(patch_preview, default_flow_style=False),
                    resource_uri=f"argorollout://rollouts/{namespace}/{name}/detail",
                    details={
                        "rollout_name": name,
                        "namespace": namespace,
                        "new_image": image,
                        "container_name": container_name,
                    },
                )

            try:
                result = await self.argo_service.update_rollout_image(
                    name=name,
                    new_image=image,
                    namespace=namespace,
                    container_name=container_name,
                    dry_run=False,
                )
                return ExecutionResult(
                    status="success",
                    summary=result.get("message", f"Updated Rollout '{name}' image to '{image}'."),
                    dry_run=False,
                    resource_uri=f"argorollout://rollouts/{namespace}/{name}/detail",
                    details=result,
                )
            except Exception as e:
                self.handle_error(e, "argo_set_rollout_image", namespace=namespace, resource_name=name)

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Configure Rollout Strategy",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def argo_configure_rollout_strategy(
            name: str = Field(..., min_length=1, description="Rollout name"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            steps: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description="Updated canary steps list (setWeight, pause, analysis, setCanaryScale, experiment)",
            ),
            traffic_routing: Optional[TrafficRoutingConfig] = Field(
                default=None,
                description="TraefikService or Gateway API HTTPRoute traffic routing configuration",
            ),
            services: Optional[CanaryServicesConfig] = Field(
                default=None,
                description="Stable/canary Service names and optional Service creation parameters",
            ),
            repair_conflicts: bool = Field(
                default=False,
                description="If True, remove conflicting canary strategy block from a blue-green Rollout",
            ),
            dry_run: bool = Field(
                default=True,
                description="If True (default), return patch preview without mutating the cluster",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Configure or repair Rollout strategy steps, Services, and traffic routing."""
            self.check_write_access("argo_configure_rollout_strategy")

            if traffic_routing and traffic_routing.traefik_service_name and traffic_routing.gateway_api_config:
                self.handle_error(
                    RolloutStrategyError(
                        "traefik_service_name and gateway_api_config are mutually exclusive."
                    ),
                    "argo_configure_rollout_strategy",
                    namespace=namespace,
                    resource_name=name,
                )

            if dry_run:
                patch_preview: Dict[str, Any] = {"spec": {"strategy": {}}}
                if repair_conflicts:
                    patch_preview["spec"]["strategy"]["canary"] = None
                else:
                    canary_patch: Dict[str, Any] = {}
                    if steps is not None:
                        canary_patch["steps"] = steps
                    if services:
                        if services.canary_service:
                            canary_patch["canaryService"] = services.canary_service
                        if services.stable_service:
                            canary_patch["stableService"] = services.stable_service
                    if traffic_routing:
                        if traffic_routing.clear_routing:
                            canary_patch["trafficRouting"] = None
                        elif traffic_routing.traefik_service_name:
                            canary_patch["trafficRouting"] = {
                                "traefik": {
                                    "weightedTraefikServiceName": traffic_routing.traefik_service_name
                                }
                            }
                        elif traffic_routing.gateway_api_config:
                            canary_patch["trafficRouting"] = {
                                "plugins": {
                                    "argoproj-labs/gatewayAPI": traffic_routing.gateway_api_config
                                }
                            }
                    patch_preview["spec"]["strategy"]["canary"] = canary_patch

                return ExecutionResult(
                    status="preview",
                    summary=f"Previewed strategy configuration for Rollout '{name}' (dry_run=True). Re-run with dry_run=False to apply.",
                    dry_run=True,
                    manifest=yaml.dump(patch_preview, default_flow_style=False),
                    resource_uri=f"argorollout://rollouts/{namespace}/{name}/detail",
                    details={"rollout_name": name, "namespace": namespace, "patch": patch_preview},
                )

            try:
                details: Dict[str, Any] = {"rollout_name": name, "namespace": namespace}
                warnings: List[str] = []

                if repair_conflicts:
                    fix_res = self.argo_service.remove_conflicting_strategy_block(
                        name=name,
                        namespace=namespace,
                        dry_run=False,
                    )
                    details["repair_conflicts"] = fix_res

                # Fix B6: do not swallow service creation errors when configuring strategy
                if services and services.auto_create:
                    for svc_name in filter(None, [services.canary_service, services.stable_service]):
                        svc_res = await self.generator_service.create_rollout_service(
                            service_name=svc_name,
                            namespace=namespace,
                            port=services.port,
                            target_port=services.target_port or services.port,
                            selector_labels=services.selector_labels or {"app": name},
                            app_name=name,
                        )
                        details.setdefault("services_created", []).extend(svc_res.get("created", []))

                if steps is not None or (services and (services.canary_service or services.stable_service)):
                    strat_res = await self.argo_service.update_canary_strategy(
                        name=name,
                        namespace=namespace,
                        canary_service=services.canary_service if services else None,
                        stable_service=services.stable_service if services else None,
                        canary_steps=steps,
                        dry_run=False,
                    )
                    details["strategy_update"] = strat_res

                if traffic_routing:
                    tr_res = await self.argo_service.set_traffic_routing(
                        name=name,
                        namespace=namespace,
                        traefik_service_name=traffic_routing.traefik_service_name,
                        gateway_api_config=traffic_routing.gateway_api_config,
                        clear_routing=traffic_routing.clear_routing,
                        dry_run=False,
                    )
                    details["traffic_routing"] = tr_res
                    if tr_res.get("persistence_warning"):
                        warnings.append(tr_res["persistence_warning"])

                return ExecutionResult(
                    status="success",
                    summary=f"Configured strategy on Rollout '{name}' in namespace '{namespace}'.",
                    dry_run=False,
                    warnings=warnings,
                    resource_uri=f"argorollout://rollouts/{namespace}/{name}/detail",
                    details=details,
                )
            except Exception as e:
                self.handle_error(e, "argo_configure_rollout_strategy", namespace=namespace, resource_name=name)

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Delete Argo Rollout",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def argo_delete_rollout(
            name: str = Field(..., min_length=1, description="Rollout name"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            clean_all: bool = Field(
                default=False,
                description="Also delete associated Services, AnalysisTemplates, and Experiments",
            ),
            confirm: bool = Field(
                default=False,
                description="Confirm permanent deletion when interactive elicitation is unavailable",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Permanently delete an Argo Rollout (blocks if workloadRef Deployment has 0 replicas)."""
            self.check_write_access("argo_delete_rollout")

            try:
                await self.argo_service.check_workload_ref_delete_safety(
                    name=name,
                    namespace=namespace,
                )
            except Exception as e:
                self.handle_error(e, "argo_delete_rollout", namespace=namespace, resource_name=name)

            confirmed = await confirm_destructive_action(
                ctx,
                action_summary=f"Delete Rollout '{name}' in namespace '{namespace}' (clean_all={clean_all})",
                confirm=confirm,
                resource_uri=f"argorollout://rollouts/{namespace}/{name}/detail",
                details={"rollout_name": name, "namespace": namespace, "clean_all": clean_all},
            )
            if not confirmed:
                return compressed_cancel_result(
                    name=name,
                    namespace=namespace,
                    action=f"delete Rollout '{name}'",
                )

            try:
                result = await self.argo_service.delete_rollout(
                    name=name,
                    namespace=namespace,
                    clean_all=clean_all,
                )
                return ExecutionResult(
                    status="success",
                    summary=f"Deleted Rollout '{name}' from namespace '{namespace}' (clean_all={clean_all}).",
                    dry_run=False,
                    details=result,
                )
            except Exception as e:
                self.handle_error(e, "argo_delete_rollout", namespace=namespace, resource_name=name)


def compressed_cancel_result(name: str, namespace: str, action: str) -> ExecutionResult:
    """Return a standard cancelled ExecutionResult when destructive confirmation is not granted."""
    return ExecutionResult(
        status="cancelled",
        summary=(
            f"Confirmation required to {action} in namespace '{namespace}'. "
            "Re-run with confirm=True after user approval."
        ),
        dry_run=False,
        resource_uri=f"argorollout://rollouts/{namespace}/{name}/detail",
        details={"name": name, "namespace": namespace, "requires_confirmation": True},
    )
