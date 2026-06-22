"""Generator tools for converting Deployments to Rollouts and creating supporting resources."""

import json
from typing import Dict, Any, List, Optional
from pydantic import Field
from mcp.types import ToolAnnotations
from fastmcp import Context

from argo_rollout_mcp_server.tools.base import BaseTool


class GeneratorTools(BaseTool):
    """Tools for generating Rollout resources from Deployments."""
    
    async def _resolve_deployment_yaml(
        self,
        deployment_yaml: Optional[str],
        deployment_name: Optional[str],
        namespace: str,
        ctx: Context
    ) -> str:
        """Resolve deployment YAML from either direct input or cluster fetch.
        
        Args:
            deployment_yaml: Direct YAML string (takes priority if provided)
            deployment_name: Name to fetch from cluster (used if yaml not provided)
            namespace: Kubernetes namespace for fetch
            ctx: MCP context for logging
            
        Returns:
            Deployment YAML string
            
        Raises:
            ValueError: If neither deployment_yaml nor deployment_name is provided
        """
        if deployment_yaml:
            return deployment_yaml
        
        if deployment_name:
            await ctx.info(
                f"Auto-fetching Deployment '{deployment_name}' from namespace '{namespace}'"
            )
            return await self.generator_service.fetch_deployment_yaml(
                deployment_name=deployment_name,
                namespace=namespace
            )
        
        raise ValueError(
            "Either 'deployment_yaml' or 'deployment_name' must be provided. "
            "Provide the YAML string directly, or pass deployment_name to auto-fetch from the cluster."
        )
    
    def register(self, mcp_instance) -> None:
        """Register generator tools with FastMCP."""
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Convert Deployment to Rollout",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def convert_deployment_to_rollout(
            deployment_yaml: Optional[str] = Field(default=None, description="Kubernetes Deployment YAML as string. If not provided, use deployment_name to auto-fetch. Not needed when mode='generate_services_only'."),
            deployment_name: Optional[str] = Field(default=None, description="Name of existing Deployment to fetch from cluster. Alternative to deployment_yaml. Not needed when mode='generate_services_only'."),
            namespace: str = Field(default="default", description="Kubernetes namespace (used when fetching by deployment_name)"),
            strategy: str = Field(default="canary", description="Rollout strategy: canary or bluegreen"),
            mode: str = Field(
                default="full",
                description="'full' (default): convert Deployment to Rollout. 'generate_services_only': create only the prerequisite K8s Services (stable+canary or active+preview) without conversion. Requires app_name when generate_services_only.",
            ),
            app_name: Optional[str] = Field(
                default=None,
                description="Application name. Required when mode='generate_services_only'. Otherwise derived from Deployment.",
            ),
            traefik_service_name: Optional[str] = Field(
                default=None,
                description="TraefikService name for native traffic routing (adds trafficRouting.traefik). Mutually exclusive with gateway_api_config.",
            ),
            gateway_api_config: Optional[Dict[str, Any]] = Field(
                default=None,
                description="Gateway API plugin config for HTTPRoute-based canaries. Example: {\"httpRoute\": \"my-route\", \"namespace\": \"default\"}. Mutually exclusive with traefik_service_name.",
            ),
            migration_mode: str = Field(default="direct", description="Migration mode: 'direct' (replace Deployment) or 'workload_ref' (reference existing Deployment)"),
            scale_down: str = Field(default="onsuccess", description="For workload_ref mode: 'never', 'onsuccess', or 'progressively'"),
            canary_steps: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description=(
                    "Custom canary steps. If None, uses default progressive steps. Supports: setWeight, pause, "
                    "setCanaryScale (requires trafficRouting), analysis (inline AnalysisTemplate; templateName must exist), "
                    "experiment, plugin. See argo_create_rollout canary_steps for examples."
                )
            ),
            bluegreen_options: Optional[Dict[str, Any]] = Field(default=None, description="Blue-Green overrides: autoPromotionSeconds, scaleDownDelaySeconds, previewReplicaCount, prePromotionAnalysis, postPromotionAnalysis, antiAffinity, etc."),
            apply: bool = Field(
                default=False,
                description=(
                    "If True, apply the converted Rollout directly to the cluster AND auto-create the "
                    "prerequisite K8s Services (stable+canary for canary strategy, active+preview for bluegreen). "
                    "No kubectl needed. Idempotent \u2014 safe to re-run if resources already exist. "
                    "If False (default), returns YAML only for review."
                )
            ),
            service_port: Optional[int] = Field(
                default=None,
                description=(
                    "Override port for auto-created K8s Services (only used when apply=True). "
                    "If omitted, the tool auto-discovers the port from the existing Service "
                    "that matches the Deployment's selector."
                )
            ),
            selector_labels: Optional[Dict[str, str]] = Field(
                default=None,
                description="Override pod selector labels for auto-created Services. If omitted, labels are auto-discovered from the existing Service."
            ),
            ctx: Context = None
        ) -> str:
            """Convert a Kubernetes Deployment to an Argo Rollout.

            Bridges standard K8s Deployments and Argo Rollouts for
            progressive delivery. Pass deployment_yaml directly or
            deployment_name to auto-fetch from cluster.

            Modes:
            - full (default): Convert Deployment → Rollout.
            - generate_services_only: Create prerequisite K8s Services only.

            Returns:
            - JSON string with {"status": str, "rollout_yaml": str,
              "next_action_hints": [...]}

            When NOT to use:
            - To create a new rollout from scratch → use argo_create_rollout.
            - To validate before converting → use validate_deployment_ready.
            """
            # --- mode=generate_services_only: create Services only (parity with create_stable_canary_services) ---
            if mode == "generate_services_only":
                if not app_name:
                    raise ValueError(
                        "mode='generate_services_only' requires 'app_name'. "
                        "Example: convert_deployment_to_rollout(mode='generate_services_only', app_name='api-service', namespace='default', apply=True)"
                    )
                await ctx.info(
                    f"{'Applying' if apply else 'Generating'} prerequisite Services for '{app_name}' ({strategy})",
                    extra={'app_name': app_name, 'strategy': strategy, 'apply': apply}
                )
                try:
                    svc_result = await self.generator_service.create_stable_canary_services(
                        app_name=app_name,
                        namespace=namespace,
                        port=service_port or 80,
                        target_port=None,
                        selector_labels=selector_labels or {"app": app_name},
                        apply=apply,
                        strategy=strategy,
                    )
                    svc_result.setdefault("next_action_hints", [])
                    svc_result["next_action_hints"].append({
                        "label": "Attach services to a rollout",
                        "description": (
                            "Create a rollout with `argo_create_rollout` or convert a Deployment with "
                            "`convert_deployment_to_rollout(mode='full')` so the Services are used."
                        ),
                        "suggested_tools": ["argo_create_rollout", "convert_deployment_to_rollout"],
                        "suggested_args": {"name": app_name, "namespace": namespace},
                    })
                    return json.dumps(svc_result, indent=2)
                except Exception as e:
                    await ctx.error(f"Service generation failed: {str(e)}")
                    return json.dumps({"status": "error", "error": str(e)}, indent=2)

            await ctx.info(
                f"{'Applying' if apply else 'Converting'} Deployment to Rollout with {strategy} strategy",
                extra={'strategy': strategy, 'apply': apply, 'migration_mode': migration_mode}
            )
            
            try:
                yaml_str = await self._resolve_deployment_yaml(
                    deployment_yaml, deployment_name, namespace, ctx
                )
                
                if traefik_service_name and gateway_api_config:
                    raise ValueError("traefik_service_name and gateway_api_config are mutually exclusive")
                if strategy == "bluegreen" and (traefik_service_name or gateway_api_config):
                    raise ValueError(
                        "trafficRouting (traefik_service_name/gateway_api_config) is not supported for blue-green. "
                        "Argo Rollouts uses Service selector changes only. Use canary strategy if you need Traefik weighted routing."
                    )
                result = await self.generator_service.convert_deployment_to_rollout(
                    deployment_yaml=yaml_str,
                    strategy=strategy,
                    traefik_service_name=traefik_service_name,
                    gateway_api_config=gateway_api_config,
                    migration_mode=migration_mode,
                    scale_down=scale_down,
                    canary_steps=canary_steps,
                    bluegreen_options=bluegreen_options,
                )
                
                if result.get("status") != "success":
                    await ctx.error(f"Conversion failed: {result.get('error')}")
                    # Even on failure, provide a simple next-step hint so agents know what to do.
                    result.setdefault("next_action_hints", [])
                    result["next_action_hints"].append({
                        "label": "If conversion failed",
                        "description": (
                            "Inspect the error, fix any structural deployment issues, then re-run "
                            "`validate_deployment_ready` followed by `convert_deployment_to_rollout`."
                        ),
                        "suggested_tools": [
                            "validate_deployment_ready",
                            "convert_deployment_to_rollout"
                        ]
                    })
                    return json.dumps(result, indent=2)
                
                app_name = result.get("app_name")
                await ctx.info(
                    f"Successfully converted Deployment '{app_name}' to Rollout",
                    extra={'app_name': app_name, 'strategy': strategy}
                )
                
                if apply:
                    # --- Apply Rollout CRD (service layer) ---
                    apply_result = await self.generator_service.apply_rollout_crd(
                        rollout_yaml=result["rollout_yaml"],
                        namespace=namespace,
                    )
                    rollout_name = apply_result["rollout_name"]
                    rollout_applied = apply_result["rollout_applied"]
                    rollout_already_existed = apply_result["rollout_already_existed"]

                    if rollout_applied:
                        await ctx.info(f"✅ Applied Rollout: {rollout_name}")
                    else:
                        await ctx.info(f"ℹ️  Rollout '{rollout_name}' already exists \u2014 skipped")

                    # --- Create Rollout Services: auto-discover existing Service first ---
                    import yaml as _yaml
                    dep_obj = _yaml.safe_load(yaml_str)
                    match_labels = (
                        dep_obj.get("spec", {}).get("selector", {}).get("matchLabels") or {}
                    )

                    services_created = []
                    services_already_existed = []
                    discovered_ports = None
                    source_service = None

                    existing_svc = await self.generator_service.discover_service_for_deployment(
                        match_labels=match_labels,
                        namespace=namespace,
                    )

                    if existing_svc:
                        await ctx.info(
                            f"🔍 Found existing Service '{existing_svc.metadata.name}' — "
                            f"cloning spec (ports: {[p.port for p in existing_svc.spec.ports or []]})"
                        )
                        # Extract pod template spec from the Deployment for
                        # named targetPort resolution (e.g. "http" → 80).
                        dep_pod_template = (
                            dep_obj.get("spec", {})
                            .get("template", {})
                            .get("spec")
                        )
                        svc_result = await self.generator_service.create_rollout_services_cloned(
                            original_service=existing_svc,
                            app_name=app_name,
                            namespace=namespace,
                            strategy=strategy,
                            pod_template=dep_pod_template,
                        )
                        services_created = svc_result["services_created"]
                        services_already_existed = svc_result["services_already_existed"]
                        discovered_ports = svc_result["discovered_ports"]
                        source_service = svc_result["source_service"]
                    else:
                        # Fallback: no existing service found — auto-discover
                        # the container port from the Deployment's pod template
                        # so the Service targetPort matches the actual listener
                        # (prevents 502 Bad Gateway when container is not on 80).
                        dep_pod_template = (
                            dep_obj.get("spec", {})
                            .get("template", {})
                            .get("spec")
                        )
                        auto_port = self.generator_service._extract_container_port_from_pod_template(
                            dep_pod_template
                        )
                        fallback_port = service_port or auto_port
                        await ctx.info(
                            f"⚠️  No existing Service found matching deployment selector — "
                            f"creating Services with port={fallback_port} "
                            f"(auto-discovered containerPort={auto_port} from pod template)"
                        )
                        svc_result = await self.generator_service.create_stable_canary_services(
                            app_name=app_name,
                            namespace=namespace,
                            port=fallback_port,
                            selector_labels=selector_labels or {"app": app_name},
                            apply=True,
                            strategy=strategy,
                            pod_template_spec=dep_pod_template,
                        )
                        services_created = svc_result.get("created", [])
                        services_already_existed = svc_result.get("already_existed", [])

                    for s in services_created:
                        await ctx.info(f"✅ Service created: {s}")
                    for s in services_already_existed:
                        await ctx.info(f"ℹ️  Service '{s}' already exists \u2014 skipped")

                    result["applied"] = True
                    result["rollout_applied"] = rollout_applied
                    result["rollout_already_existed"] = rollout_already_existed
                    result["services_created"] = services_created
                    result["services_already_existed"] = services_already_existed
                    if discovered_ports:
                        result["discovered_from_service"] = source_service
                        result["discovered_ports"] = discovered_ports
                    result["apply_summary"] = (
                        f"✅ Rollout: {'created' if rollout_applied else 'already existed'} | "
                        f"Services created: {services_created or 'none'} | "
                        f"Services skipped: {services_already_existed or 'none'}"
                        + (f" | Cloned from: {source_service}" if source_service else "")
                    )
                    await ctx.info(result["apply_summary"])

                    # Add workflow-aware next-step hints for the onboarding journey (apply=True).
                    result["next_action_hints"] = [
                        {
                            "label": "Verify rollout health",
                            "description": (
                                "Read the live rollout status and ensure the phase is Healthy "
                                "before changing traffic."
                            ),
                            "resource": f"argorollout://rollouts/{namespace}/{app_name}/detail"
                        },
                        {
                            "label": "Optional: Link traffic routing (canary only)",
                            "description": (
                                "If you use Traefik or another ingress with weighted routing, "
                                "link this rollout to the traffic service so canary weights "
                                "can be shifted automatically."
                            ),
                            "suggested_tool": "argo_update_rollout",
                            "suggested_args": {
                                "name": app_name,
                                "namespace": namespace,
                                "update_type": "traffic_routing",
                            }
                        },
                        {
                            "label": "Optional: Configure automated analysis",
                            "description": (
                                "Configure a Prometheus-backed AnalysisTemplate so canaries can "
                                "auto-abort on failures."
                            ),
                            "suggested_tool": "argo_configure_analysis_template",
                            "suggested_args": {
                                "rollout_name": app_name,
                                "namespace": namespace,
                                "mode": "execute",
                            }
                        },
                        {
                            "label": "Optional: Pre-flight readiness",
                            "description": (
                                "Before deploying a new image, verify rollout status via "
                                "the rollout detail resource."
                            ),
                            "resource": f"argorollout://rollouts/{namespace}/{app_name}/detail"
                        }
                    ]
                else:
                    # apply=False → YAML review mode; guide towards GitOps/apply + verification.
                    result["next_action_hints"] = [
                        {
                            "label": "Review and apply Rollout YAML",
                            "description": (
                                "Review the generated Rollout YAML. Apply it via GitOps or "
                                "`kubectl apply -f` and ensure the resource is created in the "
                                f"'{namespace}' namespace."
                            )
                        },
                        {
                            "label": "After applying, verify rollout",
                            "description": (
                                "Once applied, read the rollout detail resource to confirm it is "
                                "Healthy before sending any production traffic."
                            ),
                            "resource": f"argorollout://rollouts/{namespace}/{app_name}/detail"
                        }
                    ]
                
                return json.dumps(result, indent=2)
                
            except Exception as e:
                error_msg = f"Conversion failed: {str(e)}"
                await ctx.error(error_msg)
                return json.dumps({"error": error_msg}, indent=2)
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Validate Deployment Readiness",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def validate_deployment_ready(
            deployment_yaml: Optional[str] = Field(default=None, description="Kubernetes Deployment YAML as string. If not provided, use deployment_name to auto-fetch."),
            deployment_name: Optional[str] = Field(default=None, description="Name of existing Deployment to fetch from cluster. Alternative to deployment_yaml."),
            namespace: str = Field(default="default", description="Kubernetes namespace (used when fetching by deployment_name and for Service selector validation)"),
            ctx: Context = None
        ) -> str:
            """Validate if a Deployment is ready for Rollout conversion.

            Pre-flight check combining structural and routing validation:
            Deployment structure, selectors, containers, probes, and
            Service selector compatibility. Read-only.

            Returns:
            - JSON string with {"ready": bool, "score": int,
              "issues": [...], "warnings": [...], "next_action_hints": [...]}

            When NOT to use:
            - To actually convert → use convert_deployment_to_rollout.
            """
            await ctx.info("Validating Deployment readiness for Rollout conversion (structural + Service selector)")
            
            try:
                yaml_str = await self._resolve_deployment_yaml(
                    deployment_yaml, deployment_name, namespace, ctx
                )
                
                result = await self.generator_service.validate_deployment_ready(
                    deployment_yaml=yaml_str,
                    namespace=namespace,
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

                # Add workflow-aware next-step hints so agents know how to proceed.
                ready = result.get("ready")
                app_name = result.get("app_name") or deployment_name or "unknown-app"
                result.setdefault("next_action_hints", [])

                if ready:
                    result["next_action_hints"].append({
                        "label": "Ready for Rollout onboarding",
                        "description": (
                            "Convert this Deployment to an Argo Rollout and (optionally) apply "
                            "it directly to the cluster."
                        ),
                        "suggested_tool": "convert_deployment_to_rollout",
                        "suggested_args": {
                            "deployment_name": app_name,
                            "namespace": namespace,
                            "strategy": "canary"
                        }
                    })
                else:
                    result["next_action_hints"].append({
                        "label": "Not ready yet",
                        "description": (
                            "Review the blocking issues, update the Deployment manifest, then "
                            "re-run `validate_deployment_ready` until `ready` is true before "
                            "attempting conversion."
                        )
                    })

                # Always suggest optional preflight checks once structural issues are resolved.
                result["next_action_hints"].append({
                    "label": "Optional: Pre-flight readiness",
                    "description": (
                        "Once the Deployment is structurally ready, verify cluster health "
                        "before rolling out a new image."
                    ),
                    "resource": "argorollout://cluster/health"
                })
                
                return json.dumps(result, indent=2)
                
            except Exception as e:
                error_msg = f"Validation failed: {str(e)}"
                await ctx.error(error_msg)
                return json.dumps({"error": error_msg}, indent=2)

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Create Stable/Canary Services",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def create_stable_canary_services(
            app_name: str = Field(..., description="Application name"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            port: int = Field(default=80, description="Service port"),
            target_port: Optional[int] = Field(default=None, description="Target port on pods (default: same as port)"),
            selector_labels: Optional[Dict[str, str]] = Field(default=None, description="Pod selector labels (default: {app: app_name})"),
            apply: bool = Field(default=False, description="If True, create Services directly in the cluster (no kubectl needed). If False, return YAML only."),
            ctx: Context = None
        ) -> str:
            """[Advanced/Legacy] Create stable and canary K8s Services.

            Creates {app_name}-stable and {app_name}-canary Services
            required by Argo Rollouts for traffic routing. Idempotent.

            Prefer convert_deployment_to_rollout(mode='generate_services_only').

            Returns:
            - JSON string with {"status": str, "stable_service_name": str,
              "canary_service_name": str, "next_action_hints": [...]}

            When NOT to use:
            - For full conversion → use convert_deployment_to_rollout(apply=True).
            """
            await ctx.info(
                f"{'Applying' if apply else 'Generating'} stable/canary Services for '{app_name}'",
                extra={'app_name': app_name, 'namespace': namespace, 'port': port, 'apply': apply}
            )
            
            try:
                result = await self.generator_service.create_stable_canary_services(
                    app_name=app_name,
                    namespace=namespace,
                    port=port,
                    target_port=target_port,
                    selector_labels=selector_labels,
                    apply=apply,
                    strategy="canary",
                )
                
                if result.get("status") == "success":
                    if apply:
                        created = result.get("created", [])
                        existed = result.get("already_existed", [])
                        await ctx.info(
                            f"Services applied: created={created}, already_existed={existed}",
                            extra={
                                'stable_service': result['stable_service_name'],
                                'canary_service': result['canary_service_name'],
                                'created': created,
                                'already_existed': existed
                            }
                        )
                    else:
                        await ctx.info(
                            f"Generated Services: {result['stable_service_name']}, {result['canary_service_name']}",
                            extra={
                                'stable_service': result['stable_service_name'],
                                'canary_service': result['canary_service_name']
                            }
                        )

                    # Nudge agents toward using these services in a rollout.
                    result.setdefault("next_action_hints", [])
                    result["next_action_hints"].append({
                        "label": "Attach services to a rollout",
                        "description": (
                            "Either create a brand-new rollout with `argo_create_rollout` or "
                            "convert an existing Deployment with `convert_deployment_to_rollout` "
                            "so that this stable/canary pair is used for progressive delivery."
                        ),
                        "suggested_tools": [
                            "argo_create_rollout",
                            "convert_deployment_to_rollout"
                        ],
                        "suggested_args": {
                            "name_or_app_name": app_name,
                            "namespace": namespace
                        }
                    })
                else:
                    await ctx.error(f"Service operation failed: {result.get('error')}")
                
                return json.dumps(result, indent=2)
                
            except Exception as e:
                error_msg = f"Failed to create stable/canary Services: {str(e)}"
                await ctx.error(error_msg)
                return json.dumps({"error": error_msg}, indent=2)

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Generate ArgoCD ignoreDifferences",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def generate_argocd_ignore_differences(
            include_traefik_service: bool = Field(default=True, description="Include TraefikService weight paths"),
            include_rollout_status: bool = Field(default=True, description="Include Rollout status paths"),
            include_rollout_traffic_routing: bool = Field(
                default=False,
                description="Include Rollout spec.strategy.*.trafficRouting so MCP-patched trafficRouting persists when ArgoCD/Helm manages the Rollout"
            ),
            include_analysis_run: bool = Field(default=False, description="Include AnalysisRun status paths"),
            include_deployment_replicas: bool = Field(
                default=False,
                description="Include Deployment /spec/replicas (for workloadRef; prevents Argo CD from reverting Rollout scale-down)"
            ),
            deployment_name: Optional[str] = Field(
                default=None,
                description="Deployment name to scope ignore (for include_deployment_replicas)"
            ),
            traefik_api_group: str = Field(default="traefik.io", description="Traefik API group (traefik.io or traefik.containo.us)"),
            ctx: Context = None
        ) -> str:
            """Generate ArgoCD ignoreDifferences YAML for Argo Rollouts + Traefik.

            Generates the ignoreDifferences configuration to prevent
            ArgoCD from showing Rollouts-managed resources as OutOfSync.
            Read-only — does not apply anything.

            Returns:
            - JSON string with {"ignore_differences_yaml": str,
              "resources_covered": [...], "next_action_hints": [...]}

            When NOT to use:
            - To apply the config → manually add to ArgoCD Application spec.
            """
            await ctx.info(
                "Generating Argo CD ignoreDifferences snippet",
                extra={
                    'traefik_service': include_traefik_service,
                    'rollout_status': include_rollout_status,
                    'analysis_run': include_analysis_run
                }
            )
            
            try:
                result = await self.generator_service.generate_argocd_ignore_differences(
                    include_traefik_service=include_traefik_service,
                    include_rollout_status=include_rollout_status,
                    include_rollout_traffic_routing=include_rollout_traffic_routing,
                    include_analysis_run=include_analysis_run,
                    include_deployment_replicas=include_deployment_replicas,
                    deployment_name=deployment_name,
                    traefik_api_group=traefik_api_group,
                )
                
                if result.get("status") == "success":
                    await ctx.info(
                        f"Generated ignoreDifferences for {result['resource_count']} resources: {', '.join(result['resources_covered'])}",
                        extra={'resources': result['resources_covered']}
                    )

                    # Help agents understand how to finish the GitOps wiring.
                    result.setdefault("next_action_hints", [])
                    result["next_action_hints"].append({
                        "label": "Apply ignoreDifferences in Argo CD",
                        "description": (
                            "Copy the generated YAML into the `spec.ignoreDifferences` section of "
                            "your Argo CD Application, commit it, and sync the app so Argo Rollouts "
                            "status/weight changes no longer show as OutOfSync."
                        )
                    })
                else:
                    await ctx.error(f"Generation failed: {result.get('error')}")
                
                return json.dumps(result, indent=2)
                
            except Exception as e:
                error_msg = f"Failed to generate ignoreDifferences: {str(e)}"
                await ctx.error(error_msg)
                return json.dumps({"error": error_msg}, indent=2)
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Convert Rollout to Deployment",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def convert_rollout_to_deployment(
            rollout_yaml: Optional[str] = Field(default=None, description="Rollout YAML string to convert"),
            deployment_strategy: str = Field(default="RollingUpdate", description="Deployment strategy: 'RollingUpdate' or 'Recreate'"),
            max_surge: str = Field(default="25%", description="Max surge for RollingUpdate"),
            max_unavailable: str = Field(default="25%", description="Max unavailable for RollingUpdate"),
            ctx: Context = None
        ) -> str:
            """Convert an Argo Rollout YAML back to a standard K8s Deployment.

            Reverse migration tool. Preserves template, replicas, and
            metadata while stripping Argo-specific fields. Read-only —
            generates YAML only.

            Returns:
            - JSON string with {"status": str, "deployment_yaml": str,
              "next_action_hints": [...]}

            When NOT to use:
            - To convert Deployment → Rollout → use convert_deployment_to_rollout.
            """
            if not rollout_yaml:
                return json.dumps({"error": "rollout_yaml is required"}, indent=2)
            
            await ctx.info("Converting Rollout to Deployment")
            
            try:
                result = await self.generator_service.convert_rollout_to_deployment(
                    rollout_yaml=rollout_yaml,
                    deployment_strategy=deployment_strategy,
                    max_surge=max_surge,
                    max_unavailable=max_unavailable,
                )
                
                if result.get("status") == "success":
                    await ctx.info(
                        f"Converted Rollout '{result['app_name']}' ({result['original_strategy']}) → Deployment ({result['deployment_strategy']})",
                    )

                    # Provide reverse-migration follow-up guidance.
                    app_name = result.get("app_name")
                    result.setdefault("next_action_hints", [])
                    result["next_action_hints"].append({
                        "label": "Apply the generated Deployment",
                        "description": (
                            "Apply the generated Deployment manifest (via GitOps or `kubectl apply -f`) "
                            "so the application is managed by a standard Deployment again."
                        )
                    })
                    result["next_action_hints"].append({
                        "label": "Clean up the old Rollout",
                        "description": (
                            "Once the Deployment is live and stable, delete the old Rollout and "
                            "associated routing/analysis resources."
                        ),
                        "suggested_tool": "argo_delete_rollout",
                        "suggested_args": {
                            "name": app_name
                        }
                    })
                else:
                    await ctx.error(f"Conversion failed: {result.get('error')}")
                
                return json.dumps(result, indent=2)
                
            except Exception as e:
                error_msg = f"Failed to convert Rollout to Deployment: {str(e)}"
                await ctx.error(error_msg)
                return json.dumps({"error": error_msg}, indent=2)
