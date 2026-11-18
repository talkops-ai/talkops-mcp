"""Migration tools for validating and converting live Deployments and Rollouts."""

from typing import Any, Dict, List, Literal, Optional
import yaml
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from argo_rollout_mcp_server.exceptions.custom import ArgoRolloutError
from argo_rollout_mcp_server.models.schemas import (
    CanaryServicesConfig,
    ExecutionResult,
    ReadinessReport,
    StrategyOptions,
)
from argo_rollout_mcp_server.tools.base import BaseTool, confirm_destructive_action


class MigrationTools(BaseTool):
    """Tools for live cluster Deployment-to-Rollout and Rollout-to-Deployment migration."""

    def register(self, mcp_instance) -> None:
        """Register migration tools based on configured toolsets and write gates."""
        if self.should_register("migration", is_write=False):
            self._register_read_tools(mcp_instance)

        if self.should_register("migration", is_write=True):
            self._register_write_tools(mcp_instance)

    def _register_read_tools(self, mcp_instance) -> None:
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Validate Deployment Readiness for Argo Rollouts",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def argo_validate_deployment_readiness(
            deployment_name: str = Field(..., min_length=1, description="Kubernetes Deployment name"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            ctx: Context = None,
        ) -> ReadinessReport:
            """Validate whether a live Kubernetes Deployment is ready for Argo Rollouts migration."""
            try:
                dep_yaml = await self.generator_service.fetch_deployment_yaml(
                    deployment_name=deployment_name,
                    namespace=namespace,
                )
                result = await self.generator_service.validate_deployment_ready(
                    deployment_yaml=dep_yaml,
                    namespace=namespace,
                )
                if result.get("status") == "error" or "error" in result:
                    raise ArgoRolloutError(result.get("error", "Deployment readiness validation failed"))

                return ReadinessReport(
                    ready=bool(result.get("ready", False)),
                    score=int(result.get("score", 0)),
                    app_name=result.get("app_name", deployment_name),
                    namespace=result.get("namespace", namespace),
                    replicas=int(result.get("replicas", 1)),
                    containers_count=int(result.get("containers_count", 0)),
                    detected_container_port=result.get("detected_container_port"),
                    issues=result.get("issues", []),
                    warnings=result.get("warnings", []),
                    recommendations=result.get("recommendations", []),
                    service_checks=result.get("service_checks", {}),
                )
            except Exception as e:
                self.handle_error(
                    e,
                    "argo_validate_deployment_readiness",
                    namespace=namespace,
                    resource_name=deployment_name,
                )

    def _register_write_tools(self, mcp_instance) -> None:
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Convert Deployment to Argo Rollout",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def argo_convert_deployment_to_rollout(
            deployment_name: str = Field(..., min_length=1, description="Live Kubernetes Deployment name"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            strategy: Literal["canary", "bluegreen"] = Field(
                default="canary",
                description="Target Rollout strategy: 'canary' or 'bluegreen'",
            ),
            migration_mode: Literal["direct", "workload_ref"] = Field(
                default="direct",
                description="'direct' (full pod template copy) or 'workload_ref' (zero-downtime reference)",
            ),
            strategy_options: Optional[StrategyOptions] = Field(
                default=None,
                description="Canary steps, traffic routing, or blue-green options",
            ),
            service_options: Optional[CanaryServicesConfig] = Field(
                default=None,
                description="Service port/selector overrides and auto-creation control",
            ),
            dry_run: bool = Field(
                default=True,
                description="If True (default), return converted Rollout YAML preview without mutating cluster",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Convert a live Kubernetes Deployment to an Argo Rollout (<= 8 parameters)."""
            self.check_write_access("argo_convert_deployment_to_rollout")

            s_opts = strategy_options or StrategyOptions()
            svc_opts = service_options or CanaryServicesConfig()

            traefik_svc = None
            gw_config = None
            if s_opts.traffic_routing:
                traefik_svc = s_opts.traffic_routing.traefik_service_name
                gw_config = s_opts.traffic_routing.gateway_api_config

            bg_opts: Dict[str, Any] = {
                "autoPromotionEnabled": s_opts.auto_promotion_enabled,
            }
            if s_opts.auto_promotion_seconds is not None:
                bg_opts["autoPromotionSeconds"] = s_opts.auto_promotion_seconds
            if s_opts.scale_down_delay_seconds is not None:
                bg_opts["scaleDownDelaySeconds"] = s_opts.scale_down_delay_seconds
            if s_opts.preview_replica_count is not None:
                bg_opts["previewReplicaCount"] = s_opts.preview_replica_count
            if s_opts.pre_promotion_analysis is not None:
                bg_opts["prePromotionAnalysis"] = s_opts.pre_promotion_analysis
            if s_opts.post_promotion_analysis is not None:
                bg_opts["postPromotionAnalysis"] = s_opts.post_promotion_analysis
            if s_opts.abort_scale_down_delay_seconds is not None:
                bg_opts["abortScaleDownDelaySeconds"] = s_opts.abort_scale_down_delay_seconds

            try:
                dep_yaml = await self.generator_service.fetch_deployment_yaml(
                    deployment_name=deployment_name,
                    namespace=namespace,
                )
                conv = await self.generator_service.convert_deployment_to_rollout(
                    deployment_yaml=dep_yaml,
                    strategy=strategy,
                    traefik_service_name=traefik_svc,
                    gateway_api_config=gw_config,
                    migration_mode=migration_mode,
                    scale_down="onsuccess",
                    canary_steps=s_opts.steps,
                    bluegreen_options=bg_opts if strategy == "bluegreen" else None,
                )
                if conv.get("status") == "error" or "error" in conv:
                    raise ArgoRolloutError(conv.get("error", "Conversion failed"))

                rollout_yaml = conv["rollout_yaml"]
                warnings: List[str] = []
                if migration_mode == "direct":
                    warnings.append(
                        f"Direct migration creates Rollout '{deployment_name}' alongside the existing Deployment. "
                        f"Once the Rollout is Healthy, scale down or delete Deployment '{deployment_name}' using "
                        "argo_manage_legacy_deployment to avoid running duplicate pods."
                    )

                if dry_run:
                    return ExecutionResult(
                        status="preview",
                        summary=(
                            f"Previewed conversion of Deployment '{deployment_name}' to '{strategy}' Rollout "
                            f"(migration_mode={migration_mode}, dry_run=True). Re-run with dry_run=False to apply."
                        ),
                        dry_run=True,
                        manifest=rollout_yaml,
                        warnings=warnings,
                        resource_uri=f"argorollout://rollouts/{namespace}/{deployment_name}/detail",
                        details={
                            "deployment_name": deployment_name,
                            "namespace": namespace,
                            "strategy": strategy,
                            "migration_mode": migration_mode,
                        },
                    )

                # Apply Services + Rollout CRD when dry_run=False
                dep_obj = yaml.safe_load(dep_yaml) or {}
                pod_template_spec = (dep_obj.get("spec") or {}).get("template", {}).get("spec")
                match_labels = (
                    svc_opts.selector_labels
                    or (dep_obj.get("spec") or {}).get("selector", {}).get("matchLabels")
                    or {"app": deployment_name}
                )

                services_info: Dict[str, Any] = {}
                if svc_opts.auto_create:
                    orig_svc = None
                    try:
                        orig_svc = await self.generator_service.discover_service_for_deployment(
                            match_labels=match_labels,
                            namespace=namespace,
                        )
                    except Exception:
                        orig_svc = None

                    if orig_svc is not None:
                        services_info = await self.generator_service.create_rollout_services_cloned(
                            original_service=orig_svc,
                            app_name=deployment_name,
                            namespace=namespace,
                            strategy=strategy,
                            pod_template=pod_template_spec,
                        )
                    else:
                        services_info = await self.generator_service.create_stable_canary_services(
                            app_name=deployment_name,
                            namespace=namespace,
                            port=svc_opts.port,
                            target_port=svc_opts.target_port,
                            selector_labels=match_labels,
                            apply=True,
                            strategy=strategy,
                            pod_template_spec=pod_template_spec,
                        )

                apply_res = await self.generator_service.apply_rollout_crd(
                    rollout_yaml=rollout_yaml,
                    namespace=namespace,
                )

                return ExecutionResult(
                    status="success",
                    summary=(
                        f"Converted Deployment '{deployment_name}' to '{strategy}' Rollout in namespace '{namespace}' "
                        f"(migration_mode={migration_mode})."
                    ),
                    dry_run=False,
                    manifest=rollout_yaml,
                    warnings=warnings,
                    resource_uri=f"argorollout://rollouts/{namespace}/{deployment_name}/detail",
                    details={
                        **apply_res,
                        "strategy": strategy,
                        "migration_mode": migration_mode,
                        "services": services_info,
                    },
                )
            except Exception as e:
                self.handle_error(
                    e,
                    "argo_convert_deployment_to_rollout",
                    namespace=namespace,
                    resource_name=deployment_name,
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Convert Rollout to Kubernetes Deployment",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def argo_convert_rollout_to_deployment(
            name: str = Field(..., min_length=1, description="Live Argo Rollout name"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            deployment_strategy: Literal["RollingUpdate", "Recreate"] = Field(
                default="RollingUpdate",
                description="Target Kubernetes Deployment strategy",
            ),
            dry_run: bool = Field(
                default=True,
                description="If True (default), return converted Deployment YAML without mutating cluster",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Reverse-migrate a live Argo Rollout back to a standard Kubernetes Deployment."""
            self.check_write_access("argo_convert_rollout_to_deployment")

            try:
                res = await self.argo_service.convert_rollout_to_deployment_live(
                    name=name,
                    namespace=namespace,
                    deployment_strategy=deployment_strategy,
                    dry_run=dry_run,
                    generator_service=self.generator_service,
                )
                return ExecutionResult(
                    status=res.get("status", "preview" if dry_run else "success"),
                    summary=res.get("message", f"Converted Rollout '{name}' to Deployment."),
                    dry_run=dry_run,
                    manifest=res.get("manifest"),
                    details=res,
                )
            except Exception as e:
                self.handle_error(
                    e,
                    "argo_convert_rollout_to_deployment",
                    namespace=namespace,
                    resource_name=name,
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Manage Legacy Deployment After Migration",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def argo_manage_legacy_deployment(
            name: str = Field(..., min_length=1, description="Legacy Deployment name (or Rollout name for set_scale_down_policy)"),
            action: Literal["scale", "delete", "set_scale_down_policy"] = Field(
                ...,
                description="'scale' (set replicas), 'delete' (remove Deployment), or 'set_scale_down_policy' (patch workloadRef.scaleDown)",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            replicas: Optional[int] = Field(
                default=None,
                ge=0,
                le=100,
                description="Target replica count when action='scale' (defaults to 0)",
            ),
            rollout_name: Optional[str] = Field(
                default=None,
                description="Replacement Rollout name to verify Healthy before scaling to 0 or deleting (defaults to name)",
            ),
            scale_down_policy: Optional[Literal["never", "onsuccess", "progressively"]] = Field(
                default=None,
                description="workloadRef.scaleDown policy when action='set_scale_down_policy'",
            ),
            confirm: bool = Field(
                default=False,
                description="Confirm destructive action (delete or scale to 0)",
            ),
            dry_run: bool = Field(
                default=True,
                description="If True (default), preview operation without mutating cluster",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Scale, delete, or configure workloadRef scale-down on a legacy Deployment after Rollout migration."""
            self.check_write_access("argo_manage_legacy_deployment")

            target_rollout = rollout_name or name
            target_replicas = 0 if replicas is None else replicas

            try:
                # Verify replacement Rollout is Healthy before scaling to 0 or deleting
                if action == "delete" or (action == "scale" and target_replicas == 0):
                    await self.argo_service.verify_rollout_healthy(
                        name=target_rollout,
                        namespace=namespace,
                    )

                if dry_run:
                    if action == "scale":
                        preview_doc = {
                            "apiVersion": "apps/v1",
                            "kind": "Deployment",
                            "metadata": {"name": name, "namespace": namespace},
                            "spec": {"replicas": target_replicas},
                        }
                    elif action == "set_scale_down_policy":
                        if not scale_down_policy:
                            raise ValueError("action='set_scale_down_policy' requires scale_down_policy")
                        preview_doc = {
                            "apiVersion": "argoproj.io/v1alpha1",
                            "kind": "Rollout",
                            "metadata": {"name": target_rollout, "namespace": namespace},
                            "spec": {"workloadRef": {"scaleDown": scale_down_policy}},
                        }
                    else:
                        preview_doc = {
                            "operation": "DELETE",
                            "kind": "Deployment",
                            "name": name,
                            "namespace": namespace,
                        }
                    return ExecutionResult(
                        status="preview",
                        summary=f"Previewed legacy Deployment action '{action}' on '{name}' in namespace '{namespace}' (dry_run=True). Re-run with dry_run=False to apply.",
                        dry_run=True,
                        manifest=yaml.dump(preview_doc, default_flow_style=False),
                        details={
                            "name": name,
                            "namespace": namespace,
                            "action": action,
                            "replicas": target_replicas if action == "scale" else None,
                            "scale_down_policy": scale_down_policy,
                        },
                    )

                if action == "delete" or (action == "scale" and target_replicas == 0):
                    confirmed = await confirm_destructive_action(
                        ctx,
                        action_summary=f"Execute '{action}' on legacy Deployment '{name}' in namespace '{namespace}'",
                        confirm=confirm,
                        details={"name": name, "namespace": namespace, "action": action, "replicas": target_replicas},
                    )
                    if not confirmed:
                        return ExecutionResult(
                            status="cancelled",
                            summary=(
                                f"Confirmation required to {action} legacy Deployment '{name}'. "
                                "Re-run with confirm=True after user approval."
                            ),
                            dry_run=False,
                            details={"name": name, "namespace": namespace, "action": action, "requires_confirmation": True},
                        )

                if action == "scale":
                    res = await self.argo_service.scale_deployment(
                        name=name,
                        namespace=namespace,
                        replicas=target_replicas,
                        dry_run=False,
                    )
                elif action == "delete":
                    res = await self.argo_service.delete_deployment(
                        name=name,
                        namespace=namespace,
                    )
                elif action == "set_scale_down_policy":
                    if not scale_down_policy:
                        raise ValueError("action='set_scale_down_policy' requires scale_down_policy")
                    res = await self.argo_service.patch_workload_ref_scale_down(
                        name=target_rollout,
                        namespace=namespace,
                        scale_down=scale_down_policy,
                        dry_run=False,
                    )
                else:
                    raise ValueError(f"Unsupported action: {action}")

                return ExecutionResult(
                    status="success",
                    summary=res.get("message", f"Executed '{action}' on '{name}'."),
                    dry_run=False,
                    details=res,
                )
            except Exception as e:
                self.handle_error(e, "argo_manage_legacy_deployment", namespace=namespace, resource_name=name)
