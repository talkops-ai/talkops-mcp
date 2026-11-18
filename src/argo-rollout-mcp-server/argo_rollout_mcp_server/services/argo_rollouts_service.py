"""Argo Rollouts service - business logic layer.

This service encapsulates all Argo Rollouts operations using the Kubernetes
Python client to interact with Rollout CRDs.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, TYPE_CHECKING
import yaml

if TYPE_CHECKING:
    from argo_rollout_mcp_server.services.generator_service import GeneratorService
from kubernetes import client, config
from kubernetes.dynamic import DynamicClient
from kubernetes.client.rest import ApiException

from argo_rollout_mcp_server.config import ServerConfig
from argo_rollout_mcp_server.exceptions.custom import (
    ArgoRolloutError,
    RolloutNotFoundError,
    RolloutStateError,
    RolloutPromotionError,
    RolloutStrategyError,
    RolloutAbortError,
    AnalysisTemplateError,
    KubernetesOperationError,
    KubernetesResourceError,
    KubernetesPatchError,
)

logger = logging.getLogger(__name__)


def _to_plain_dict(obj: Any) -> Any:
    """Convert ResourceInstance/None to plain Python types for API serialization."""
    if obj is None:
        return {}
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return {k: _to_plain_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_plain_dict(v) for v in obj]
    return obj


def _compute_health_score(phase: str, desired: int, ready: int, available: int) -> int:
    """Compute a 0-100 health score for a Rollout from its phase and replica counts."""
    if desired <= 0:
        return 100 if phase in ("Healthy", "Running") else 0
    score = int((ready / desired) * 100)
    if phase == "Progressing":
        score = max(score - 10, 0)
    elif phase == "Degraded":
        score = max(score - 30, 0)
    elif phase == "Paused":
        score = max(score - 5, 0)
    elif phase not in ("Healthy", "Running"):
        score = 0
    if available == desired and phase in ("Healthy", "Running", "Progressing", "Paused"):
        score = min(score + 5, 100)
    return max(0, min(100, score))


class ArgoRolloutsService:
    """Service for Argo Rollouts operations.
    
    Encapsulates all Argo Rollouts CRD interactions and business logic.
    Can be used by multiple tools without duplication.
    """
    
    def __init__(
        self,
        config_obj: ServerConfig,
        generator_service: Optional["GeneratorService"] = None,
    ):
        """Initialize with configuration.
        
        Args:
            config_obj: Server configuration instance
            generator_service: Optional GeneratorService for canonical metric defaults
                when set_analysis_template receives metrics=None
        """
        self.config = config_obj
        self._generator_service = generator_service
        self._k8s_client = None
        self._dyn_client = None
        self._rollout_api = None
        self._analysis_template_api = None
        self._cluster_analysis_template_api = None
        self._analysis_run_api = None
        self._experiment_api = None
        self._replicaset_api = None
        self._apps_v1 = None
        self._core_v1 = None
        self._initialized = False
        self._lazy_init_enabled = False
        self._last_init_error: Optional[str] = None

    def enable_lazy_init(self) -> None:
        """Allow _ensure_initialized() to lazily connect to the cluster on first call."""
        self._lazy_init_enabled = True

    def _init_sync(self) -> None:
        """Synchronously initialize Kubernetes clients and CRD handles."""
        if self._initialized:
            return

        try:
            try:
                if self.config and self.config.kubernetes and self.config.kubernetes.in_cluster:
                    config.load_incluster_config()
                    logger.info("Loaded in-cluster Kubernetes config from explicit preference")
                else:
                    kubeconfig = self.config.kubernetes.kubeconfig if (self.config and self.config.kubernetes) else None
                    ctx_name = self.config.kubernetes.context_name if (self.config and self.config.kubernetes) else None
                    config.load_kube_config(
                        config_file=kubeconfig,
                        context=ctx_name,
                    )
                    logger.info("Loaded local kubeconfig using explicit preferences")
            except Exception as e:
                logger.warning(f"Failed to load configured kubeconfig: {e}. Trying fallbacks.")
                try:
                    config.load_incluster_config()
                except Exception:
                    config.load_kube_config()

            self._k8s_client = client.ApiClient()
            self._dyn_client = DynamicClient(self._k8s_client)
            self._apps_v1 = client.AppsV1Api(self._k8s_client)
            self._core_v1 = client.CoreV1Api(self._k8s_client)

            try:
                self._rollout_api = self._dyn_client.resources.get(
                    api_version="argoproj.io/v1alpha1",
                    kind="Rollout",
                )
            except Exception:
                raise KubernetesResourceError(
                    "Argo Rollouts CRD not found. Is Argo Rollouts installed? "
                    "Install: kubectl create namespace argo-rollouts && "
                    "kubectl apply -n argo-rollouts -f https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml"
                )

            for attr, api_ver, kind in [
                ("_analysis_template_api", "argoproj.io/v1alpha1", "AnalysisTemplate"),
                ("_cluster_analysis_template_api", "argoproj.io/v1alpha1", "ClusterAnalysisTemplate"),
                ("_analysis_run_api", "argoproj.io/v1alpha1", "AnalysisRun"),
                ("_experiment_api", "argoproj.io/v1alpha1", "Experiment"),
                ("_replicaset_api", "apps/v1", "ReplicaSet"),
            ]:
                try:
                    setattr(
                        self,
                        attr,
                        self._dyn_client.resources.get(api_version=api_ver, kind=kind),
                    )
                except Exception:
                    logger.warning(f"{kind} resource not available")
                    setattr(self, attr, None)

            self._initialized = True
            self._last_init_error = None
            logger.info("✅ Argo Rollouts Service initialized")

        except KubernetesResourceError as e:
            self._last_init_error = str(e)
            raise
        except Exception as e:
            self._last_init_error = str(e)
            raise KubernetesOperationError(f"Failed to initialize Argo Rollouts service: {e}")

    async def initialize(self, strict: bool = True) -> None:
        """Initialize Kubernetes clients.

        Args:
            strict: When False, logs initialization errors instead of raising so the
                server can start and expose tools/resources before a cluster is reachable.
        """
        if self._initialized:
            return
        self._lazy_init_enabled = True
        try:
            self._init_sync()
        except Exception as e:
            if strict:
                raise
            logger.warning(f"Lazy cluster initialization deferred until first cluster call: {e}")

    def _ensure_initialized(self) -> None:
        """Ensure service is initialized, attempting lazy initialization if enabled."""
        if self._initialized:
            return
        if getattr(self, "_lazy_init_enabled", False):
            self._init_sync()
            return
        raise KubernetesOperationError(
            "Argo Rollouts service not initialized. Call initialize() first."
        )
    
    async def create_rollout(
        self,
        name: str,
        namespace: str = "default",
        image: str = "nginx:1.15.4",
        replicas: int = 3,
        strategy: str = "canary",
        canary_steps: Optional[List[Dict]] = None,
        dry_run: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a Rollout resource.
        
        Args:
            name: Rollout name
            namespace: Kubernetes namespace
            image: Container image
            replicas: Number of replicas
            strategy: 'canary' | 'bluegreen' | 'rolling'
            canary_steps: List of canary steps. Supported step types:
                - setWeight: {"setWeight": 25}
                - pause: {"pause": {"duration": "5m"}} or {"pause": {}}
                - setCanaryScale: {"setCanaryScale": {"replicas": 2}} (requires trafficRouting)
                - analysis: {"analysis": {"templates": [...], "args": [...]}}
                - experiment: {"experiment": {"templates": [...], "duration": "20m"}}
                - setHeaderRoute: NOT supported with Traefik (Istio-only)
                - setMirrorRoute: NOT supported with Traefik (Istio-only)
                - plugin: {"plugin": {"pluginName": {...}}}
            **kwargs: Additional options:
                Canary: stable_service, canary_service, traefik_service_name
                Blue-Green: active_service, preview_service, auto_promotion,
                    pre_promotion_analysis, post_promotion_analysis,
                    scale_down_delay_seconds, preview_replica_count,
                    auto_promotion_seconds, anti_affinity,
                    active_metadata, preview_metadata,
                    abort_scale_down_delay_seconds
                Container: resource_requests, resource_limits (e.g. {"memory": "32Mi", "cpu": "5m"})
        
        Returns:
            Created Rollout details
        
        Raises:
            RolloutStrategyError: If strategy configuration is invalid
            ArgoRolloutError: If creation fails
        """
        self._ensure_initialized()
        
        # Default canary steps if not provided
        if canary_steps is None and strategy == "canary":
            canary_steps = [
                {"setWeight": 10},
                {"pause": {"duration": "5m"}},
                {"setWeight": 25},
                {"pause": {"duration": "5m"}},
                {"setWeight": 50},
                {"pause": {"duration": "5m"}},
                {"setWeight": 75},
                {"pause": {"duration": "5m"}},
            ]
        
        # Build strategy specification
        if strategy == "canary":
            if not canary_steps:
                raise RolloutStrategyError("Canary strategy requires canary_steps")
            
            canary_spec = {
                "canaryService": kwargs.get('canary_service', f"{name}-canary"),
                "stableService": kwargs.get('stable_service', f"{name}-stable"),
                "maxSurge": kwargs.get('max_surge', "25%"),
                "maxUnavailable": kwargs.get('max_unavailable', 0),
                "steps": canary_steps,
                "scaleDownDelaySeconds": kwargs.get('scale_down_delay_seconds', 30),
            }
            
            # Validate canary step types and document constraints
            step_warnings = []
            known_step_types = {
                'setWeight', 'pause', 'setCanaryScale', 'analysis',
                'experiment', 'setHeaderRoute', 'setMirrorRoute', 'plugin',
                'replicaProgressThreshold'
            }
            has_traffic_routing = bool(kwargs.get('traefik_service_name') or kwargs.get('gateway_api_config'))
            
            for step in canary_steps:
                step_type = next(iter(step.keys()), None)
                if step_type and step_type not in known_step_types:
                    step_warnings.append(f"Unknown step type: '{step_type}'")
                if step_type == 'setCanaryScale' and not has_traffic_routing:
                    step_warnings.append(
                        "setCanaryScale requires trafficRouting to be configured"
                    )
                if step_type == 'setCanaryScale':
                    scs = step.get('setCanaryScale')
                    if not isinstance(scs, dict):
                        step_warnings.append(
                            "setCanaryScale value must be a dict with replicas, weight, or matchTrafficWeight"
                        )
                    else:
                        valid_keys = {'replicas', 'weight', 'matchTrafficWeight'}
                        if not any(k in scs for k in valid_keys):
                            step_warnings.append(
                                "setCanaryScale requires at least one of: replicas, weight, matchTrafficWeight"
                            )
                        if 'replicas' in scs and not isinstance(scs.get('replicas'), (int, type(None))):
                            step_warnings.append("setCanaryScale.replicas must be an integer")
                        elif 'replicas' in scs and scs.get('replicas', 0) < 0:
                            step_warnings.append("setCanaryScale.replicas must be non-negative")
                        if 'weight' in scs:
                            w = scs.get('weight')
                            if w is not None and (not isinstance(w, int) or w < 0 or w > 100):
                                step_warnings.append("setCanaryScale.weight must be 0-100")
                if step_type == 'setHeaderRoute':
                    step_warnings.append(
                        "setHeaderRoute is Istio-only — not supported with Traefik"
                    )
                if step_type == 'setMirrorRoute':
                    step_warnings.append(
                        "setMirrorRoute is Istio-only — not supported with Traefik"
                    )
            
            # Add traffic routing: TraefikService or Gateway API plugin
            traefik_service_name = kwargs.get('traefik_service_name')
            gateway_api_config = kwargs.get('gateway_api_config')
            if traefik_service_name:
                canary_spec["trafficRouting"] = {
                    "traefik": {
                        "weightedTraefikServiceName": traefik_service_name
                    }
                }
            elif gateway_api_config:
                # Build trafficRouting.plugins for argoproj-labs/gatewayAPI
                plugin_config: Dict[str, Any] = {}
                if "httpRoute" in gateway_api_config:
                    plugin_config["httpRoute"] = gateway_api_config["httpRoute"]
                if "httpRoutes" in gateway_api_config:
                    plugin_config["httpRoutes"] = gateway_api_config["httpRoutes"]
                if "namespace" in gateway_api_config:
                    plugin_config["namespace"] = gateway_api_config["namespace"]
                if "inProgressLabelKey" in gateway_api_config:
                    plugin_config["inProgressLabelKey"] = gateway_api_config["inProgressLabelKey"]
                if "inProgressLabelValue" in gateway_api_config:
                    plugin_config["inProgressLabelValue"] = gateway_api_config["inProgressLabelValue"]
                if "disableInProgressLabel" in gateway_api_config:
                    plugin_config["disableInProgressLabel"] = gateway_api_config["disableInProgressLabel"]
                canary_spec["trafficRouting"] = {
                    "plugins": {
                        "argoproj-labs/gatewayAPI": plugin_config
                    }
                }
            
            strategy_spec = {"canary": canary_spec}
        
        elif strategy == "bluegreen":
            bluegreen_spec: Dict[str, Any] = {
                "activeService": kwargs.get('active_service', f"{name}-active"),
                "previewService": kwargs.get('preview_service', f"{name}-preview"),
                "autoPromotionEnabled": kwargs.get('auto_promotion', False)
            }
            
            # P2 #10: Enhanced Blue-Green options
            if kwargs.get('auto_promotion_seconds'):
                bluegreen_spec["autoPromotionSeconds"] = kwargs['auto_promotion_seconds']
            if kwargs.get('scale_down_delay_seconds'):
                bluegreen_spec["scaleDownDelaySeconds"] = kwargs['scale_down_delay_seconds']
            if kwargs.get('abort_scale_down_delay_seconds'):
                bluegreen_spec["abortScaleDownDelaySeconds"] = kwargs['abort_scale_down_delay_seconds']
            if kwargs.get('preview_replica_count') is not None:
                bluegreen_spec["previewReplicaCount"] = kwargs['preview_replica_count']
            if kwargs.get('pre_promotion_analysis'):
                bluegreen_spec["prePromotionAnalysis"] = kwargs['pre_promotion_analysis']
            if kwargs.get('post_promotion_analysis'):
                bluegreen_spec["postPromotionAnalysis"] = kwargs['post_promotion_analysis']
            if kwargs.get('anti_affinity'):
                bluegreen_spec["antiAffinity"] = kwargs['anti_affinity']
            if kwargs.get('active_metadata'):
                bluegreen_spec["activeMetadata"] = kwargs['active_metadata']
            if kwargs.get('preview_metadata'):
                bluegreen_spec["previewMetadata"] = kwargs['preview_metadata']
            
            strategy_spec = {"blueGreen": bluegreen_spec}
        
        else:  # rolling -> zero-step canary in Argo Rollouts CRD
            strategy_spec = {
                "canary": {
                    "steps": [],
                    "maxSurge": kwargs.get('max_surge', "25%"),
                    "maxUnavailable": kwargs.get('max_unavailable', 0)
                }
            }
        
        # Build container spec
        container_spec: Dict[str, Any] = {
            "name": name,
            "image": image,
            "imagePullPolicy": "Always",
            "ports": [
                {"containerPort": kwargs.get('port', 80)}
            ]
        }
        # Add optional resource requests/limits if provided
        resource_requests = kwargs.get('resource_requests')
        resource_limits = kwargs.get('resource_limits')
        if resource_requests or resource_limits:
            container_spec["resources"] = {}
            if resource_requests:
                container_spec["resources"]["requests"] = resource_requests
            if resource_limits:
                container_spec["resources"]["limits"] = resource_limits

        # Construct Rollout manifest
        rollout_manifest = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Rollout",
            "metadata": {
                "name": name,
                "namespace": namespace,
                "labels": {
                    "app": name,
                    "managed-by": "argoflow-mcp-server"
                }
            },
            "spec": {
                "replicas": replicas,
                "selector": {
                    "matchLabels": {
                        "app": name
                    }
                },
                "template": {
                    "metadata": {
                        "labels": {
                            "app": name
                        }
                    },
                    "spec": {
                        "containers": [container_spec]
                    }
                },
                "strategy": strategy_spec
            }
        }
        
        try:
            create_kwargs: Dict[str, Any] = {
                "body": rollout_manifest,
                "namespace": namespace,
            }
            if dry_run:
                create_kwargs["dry_run"] = "All"

            created_rollout = self._rollout_api.create(**create_kwargs)

            manifest_yaml = yaml.dump(rollout_manifest, default_flow_style=False)
            logger.info(f"✅ Rollout {'previewed' if dry_run else 'created'}: {name} in {namespace}")
            result = {
                "status": "preview" if dry_run else "success",
                "dry_run": dry_run,
                "rollout": name,
                "namespace": namespace,
                "strategy": strategy,
                "replicas": replicas,
                "image": image,
                "manifest": manifest_yaml,
                "manifest_yaml": manifest_yaml,
                "message": (
                    f"[DRY-RUN PREVIEW] Rollout {name} validated successfully"
                    if dry_run
                    else f"Rollout {name} created successfully"
                ),
            }

            if strategy == "canary" and step_warnings:
                result["step_warnings"] = step_warnings

            return result

        except ApiException as e:
            if e.status == 409:
                raise ArgoRolloutError(f"Rollout '{name}' already exists in namespace '{namespace}'")
            elif e.status == 403:
                raise KubernetesOperationError(f"Permission denied to create rollout in '{namespace}'")
            else:
                raise ArgoRolloutError(f"Failed to create rollout: {e}")
        except Exception as e:
            raise ArgoRolloutError(f"Failed to create rollout: {e}")

    async def get_rollout_status(
        self,
        name: str,
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """Get current status of a Rollout.
        
        Args:
            name: Rollout name
            namespace: Kubernetes namespace
        
        Returns:
            Detailed rollout status with metrics
        
        Raises:
            RolloutNotFoundError: If rollout doesn't exist
        """
        self._ensure_initialized()
        
        try:
            rollout = self._rollout_api.get(name=name, namespace=namespace)
            
            # Convert to plain dict to avoid ResourceField serialization issues
            rollout_dict = rollout.to_dict() if hasattr(rollout, 'to_dict') else dict(rollout)
            
            # Extract status
            status = rollout_dict.get("status", {}) or {}
            spec = rollout_dict.get("spec", {}) or {}
            
            # Determine phase
            phase = status.get("phase", "Unknown")
            message = status.get("message", "")
            
            # Convert conditions to plain dicts
            conditions_raw = status.get("conditions", [])
            conditions = []
            if conditions_raw:
                for cond in conditions_raw:
                    if hasattr(cond, 'to_dict'):
                        conditions.append(cond.to_dict())
                    elif isinstance(cond, dict):
                        conditions.append(dict(cond))
                    else:
                        conditions.append(cond)
            
            # Extract metrics
            replicas = status.get("replicas", 0) or 0
            updated_replicas = status.get("updatedReplicas", 0) or 0
            ready_replicas = status.get("readyReplicas", 0) or 0
            available_replicas = status.get("availableReplicas", 0) or 0
            desired_replicas = spec.get("replicas", 0) or 0
            
            # Determine current step and total steps (for canary)
            current_step = status.get("currentStepIndex", None)
            strategy_block = spec.get("strategy", {}) or {}
            canary_block = strategy_block.get("canary", {}) or {}
            total_steps = len(canary_block.get("steps", []) or [])
            
            # Canary weight & ReplicaSet hashes
            canary_status = status.get("canary", {}) or {}
            weights = canary_status.get("weights", {}) or {}
            canary_weight = (weights.get("canary") or {}).get("weight")
            stable_rs = status.get("stableRS", "")
            current_pod_hash = status.get("currentPodHash", "")
            pause_conditions = _to_plain_dict(status.get("pauseConditions", []) or [])
            paused = bool(spec.get("paused") or pause_conditions or phase == "Paused")
            aborted = bool(status.get("abort"))
            
            # Primary container image
            containers = (
                (spec.get("template") or {})
                .get("spec", {})
                .get("containers", [])
            ) or []
            image = containers[0].get("image", "") if containers else ""
            
            # Get strategy type
            strategy_type = "canary" if "canary" in strategy_block else \
                           "bluegreen" if "blueGreen" in strategy_block else \
                           "rolling"
            
            health_score = _compute_health_score(
                phase=phase,
                desired=desired_replicas,
                ready=ready_replicas,
                available=available_replicas,
            )
            
            return {
                "status": "success",
                "name": name,
                "namespace": namespace,
                "phase": phase,
                "message": message,
                "strategy": strategy_type,
                "current_step": current_step,
                "total_steps": total_steps,
                "canary_weight": canary_weight,
                "stable_rs": stable_rs,
                "current_pod_hash": current_pod_hash,
                "image": image,
                "paused": paused,
                "pause_conditions": pause_conditions,
                "aborted": aborted,
                "health_score": health_score,
                "workload_ref": _to_plain_dict(spec.get("workloadRef")) if spec.get("workloadRef") else None,
                "desired_replicas": desired_replicas,
                "replicas": {
                    "total": replicas,
                    "updated": updated_replicas,
                    "ready": ready_replicas,
                    "available": available_replicas
                },
                "conditions": conditions,
                "timestamp": datetime.now().isoformat()
            }
        
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to get rollout status: {e}")
        except Exception as e:
            raise ArgoRolloutError(f"Failed to get rollout status: {e}")
    
    async def get_rollout_manifest(
        self,
        name: str,
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """Get full Rollout manifest from cluster.
        
        Args:
            name: Rollout name
            namespace: Kubernetes namespace
        
        Returns:
            Full rollout resource as dict (spec + status + metadata)
        
        Raises:
            RolloutNotFoundError: If rollout doesn't exist
        """
        self._ensure_initialized()
        
        try:
            rollout = self._rollout_api.get(name=name, namespace=namespace)
            rollout_dict = rollout.to_dict() if hasattr(rollout, 'to_dict') else dict(rollout)
            return rollout_dict
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to get rollout manifest: {e}")
        except Exception as e:
            raise ArgoRolloutError(f"Failed to get rollout manifest: {e}")
    
    async def promote_rollout(
        self,
        name: str,
        namespace: str = "default",
        full: bool = False
    ) -> Dict[str, Any]:
        """Promote a paused Rollout to next step.
        
        Args:
            name: Rollout name
            namespace: Kubernetes namespace
            full: If True, promote fully (skip all steps)
        
        Returns:
            Promotion result
        
        Raises:
            RolloutNotFoundError: If rollout doesn't exist
            RolloutPromotionError: If promotion fails
        """
        self._ensure_initialized()
        
        try:
            # Get current rollout
            rollout = self._rollout_api.get(name=name, namespace=namespace)
            
            # Get current status
            status = rollout.get("status", {})
            spec = rollout.get("spec", {})
            
            custom_api = client.CustomObjectsApi(self._k8s_client)
            
            if full:
                # Full promotion
                if spec.get("paused"):
                    # Unpause spec
                    self._rollout_api.patch(
                        name=name,
                        namespace=namespace,
                        body={"spec": {"paused": False}},
                        content_type="application/merge-patch+json"
                    )
                
                # Patch status: promote full and clear abort if set (so Degraded clears)
                status_patch = {"status": {"promoteFull": True}}
                if status.get("abort"):
                    status_patch["status"]["abort"] = False
                custom_api.patch_namespaced_custom_object_status(
                    group="argoproj.io",
                    version="v1alpha1",
                    namespace=namespace,
                    plural="rollouts",
                    name=name,
                    body=status_patch
                )
            else:
                # Incremental promotion
                # Per Argo Rollouts docs: patch spec.paused=false AND status.pauseConditions=null.
                # Must use two patches: main resource for spec, status subresource for status.
                self._rollout_api.patch(
                    name=name,
                    namespace=namespace,
                    body={"spec": {"paused": False}},
                    content_type="application/merge-patch+json"
                )
                
                status_patch = {}
                if status.get("pauseConditions"):
                    status_patch = {"status": {"pauseConditions": None}}
                    if status.get("abort"):
                        status_patch["status"]["abort"] = False
                elif not spec.get("paused"):
                    raise RolloutPromotionError("Rollout is not paused or has no pause conditions to clear")
                
                if status_patch:
                    custom_api.patch_namespaced_custom_object_status(
                        group="argoproj.io",
                        version="v1alpha1",
                        namespace=namespace,
                        plural="rollouts",
                        name=name,
                        body=status_patch
                    )
            
            logger.info(f"✅ Promoted rollout: {name}")
            return {
                "status": "success",
                "rollout": name,
                "namespace": namespace,
                "promoted_fully": full,
                "message": f"Rollout {name} promoted successfully"
            }
        
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise RolloutPromotionError(f"Failed to promote rollout: {e}")
        except (RolloutNotFoundError, RolloutPromotionError):
            raise
        except Exception as e:
            raise RolloutPromotionError(f"Failed to promote rollout: {e}")
    
    async def abort_rollout(
        self,
        name: str,
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """Abort an ongoing Rollout and rollback to stable.
        
        Args:
            name: Rollout name
            namespace: Kubernetes namespace
        
        Returns:
            Abort result
        
        Raises:
            RolloutNotFoundError: If rollout doesn't exist
            RolloutAbortError: If abort fails
        """
        self._ensure_initialized()
        
        try:
            custom_api = client.CustomObjectsApi(self._k8s_client)
            # Per Argo Rollouts: abort is a status field, must patch status subresource
            custom_api.patch_namespaced_custom_object_status(
                group="argoproj.io",
                version="v1alpha1",
                namespace=namespace,
                plural="rollouts",
                name=name,
                body={"status": {"abort": True}}
            )
            
            logger.info(f"✅ Aborted rollout: {name}")
            return {
                "status": "success",
                "rollout": name,
                "namespace": namespace,
                "message": f"Rollout {name} aborted and rolled back to stable"
            }
        
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise RolloutAbortError(f"Failed to abort rollout: {e}")
        except (RolloutNotFoundError, RolloutAbortError):
            raise
        except Exception as e:
            raise RolloutAbortError(f"Failed to abort rollout: {e}")
    
    async def retry_rollout(
        self,
        name: str,
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """Retry an aborted rollout (clear abort status so deployment can proceed).
        
        Equivalent to `kubectl argo rollouts retry rollout <name>`.
        Patches status.abort to False so the controller resumes the deployment.
        
        Args:
            name: Rollout name
            namespace: Kubernetes namespace
        
        Returns:
            Retry result
        """
        self._ensure_initialized()
        
        try:
            custom_api = client.CustomObjectsApi(self._k8s_client)
            custom_api.patch_namespaced_custom_object_status(
                group="argoproj.io",
                version="v1alpha1",
                namespace=namespace,
                plural="rollouts",
                name=name,
                body={"status": {"abort": False}}
            )
            
            logger.info(f"✅ Retried rollout: {name} (abort cleared)")
            return {
                "status": "success",
                "rollout": name,
                "namespace": namespace,
                "message": f"Rollout {name} retry initiated; deployment will resume"
            }
        
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise RolloutAbortError(f"Failed to retry rollout: {e}")
        except (RolloutNotFoundError, RolloutAbortError):
            raise
        except Exception as e:
            raise RolloutAbortError(f"Failed to retry rollout: {e}")
    
    async def pause_rollout(
        self,
        name: str,
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """Pause a running Rollout.
        
        Args:
            name: Rollout name
            namespace: Kubernetes namespace
        
        Returns:
            Pause result
        """
        self._ensure_initialized()
        
        try:
            patch = {
                "spec": {
                    "paused": True
                }
            }
            
            self._rollout_api.patch(
                name=name,
                namespace=namespace,
                body=patch,
                content_type="application/merge-patch+json"
            )
            
            logger.info(f"✅ Paused rollout: {name}")
            return {
                "status": "success",
                "rollout": name,
                "message": f"Rollout {name} paused"
            }
        
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to pause rollout: {e}")
        except Exception as e:
            raise ArgoRolloutError(f"Failed to pause rollout: {e}")
    
    async def resume_rollout(
        self,
        name: str,
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """Resume a paused Rollout.
        
        Args:
            name: Rollout name
            namespace: Kubernetes namespace
        
        Returns:
            Resume result
        """
        self._ensure_initialized()
        
        try:
            patch = {
                "spec": {
                    "paused": False,
                    "restartAt": None,
                }
            }
            
            self._rollout_api.patch(
                name=name,
                namespace=namespace,
                body=patch,
                content_type="application/merge-patch+json"
            )
            
            logger.info(f"✅ Resumed rollout: {name}")
            return {
                "status": "success",
                "rollout": name,
                "message": f"Rollout {name} resumed"
            }
        
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to resume rollout: {e}")
        except Exception as e:
            raise ArgoRolloutError(f"Failed to resume rollout: {e}")
    
    async def get_rollout_history(
        self,
        name: str,
        namespace: str = "default",
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get historical data of rollout updates.
        
        Args:
            name: Rollout name
            namespace: Kubernetes namespace
            limit: Maximum number of history entries
        
        Returns:
            List of past rollout states
        
        Raises:
            RolloutNotFoundError: If rollout doesn't exist
        """
        self._ensure_initialized()
        
        try:
            rollout = self._rollout_api.get(name=name, namespace=namespace)
            status = rollout.get("status", {})
            
            # Get history from status conditions
            conditions = status.get("conditions", [])
            
            history = []
            for condition in conditions:
                history.append({
                    "type": condition.get("type"),
                    "status": condition.get("status"),
                    "reason": condition.get("reason"),
                    "message": condition.get("message"),
                    "lastUpdateTime": condition.get("lastUpdateTime"),
                    "lastTransitionTime": condition.get("lastTransitionTime")
                })
            
            return {
                "status": "success",
                "rollout": name,
                "namespace": namespace,
                "history_count": len(history),
                "history": history[:limit],
                "timestamp": datetime.now().isoformat()
            }
        
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to get history: {e}")
        except Exception as e:
            raise ArgoRolloutError(f"Failed to get history: {e}")
            
    async def get_rollout_revision_history(
        self,
        name: str,
        namespace: str = "default",
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get deployment revision history (images, ReplicaSets) for a rollout.
        
        Args:
            name: Rollout name
            namespace: Kubernetes namespace
            limit: Maximum number of history entries
            
        Returns:
            Dict containing revisions data
            
        Raises:
            RolloutNotFoundError: If rollout doesn't exist
        """
        self._ensure_initialized()
        
        if self._replicaset_api is None:
            raise ArgoRolloutError("ReplicaSet core API not available")
            
        try:
            # 1. Get Rollout to read its spec.selector and status limits
            rollout = self._rollout_api.get(name=name, namespace=namespace)
            rollout_dict = rollout.to_dict() if hasattr(rollout, 'to_dict') else dict(rollout)
            
            spec = rollout_dict.get("spec", {})
            status = rollout_dict.get("status", {})
            match_labels = spec.get("selector", {}).get("matchLabels", {})
            
            current_pod_hash = status.get("currentPodHash", "")
            history_limit = spec.get("revisionHistoryLimit", 10)
            
            # 2. List ReplicaSets in the namespace with the rollout's matchLabels
            label_selector = ",".join([f"{k}={v}" for k, v in match_labels.items()])
            rs_list = self._replicaset_api.get(namespace=namespace, label_selector=label_selector)
            
            items = rs_list.get('items', [])
            
            revisions = []
            current_revision_num = 0
            
            for item in items:
                rs_dict = item.to_dict() if hasattr(item, 'to_dict') else dict(item)
                metadata = rs_dict.get("metadata", {})
                
                # Filter by owner references to be sure it's owned by this rollout
                owners = metadata.get("ownerReferences", [])
                is_owned = any(o.get("kind") == "Rollout" and o.get("name") == name for o in owners)
                
                if not is_owned:
                    continue
                    
                annotations = metadata.get("annotations", {})
                revision_str = annotations.get("rollout.argoproj.io/revision", "0")
                revision_num = int(revision_str) if revision_str.isdigit() else 0
                
                # Derive hash from name if not directly available
                rs_name = metadata.get("name", "")
                rs_hash = annotations.get("rollout.argoproj.io/pod-template-hash", "")
                if not rs_hash and "-" in rs_name:
                    rs_hash = rs_name.split("-")[-1]
                    
                rs_spec = rs_dict.get("spec", {})
                rs_status = rs_dict.get("status", {})
                
                # Fetch image info
                containers = rs_spec.get("template", {}).get("spec", {}).get("containers", [])
                images_map = {c.get("name"): c.get("image") for c in containers}
                primary_image = next(iter(images_map.values())) if images_map else ""
                
                replicas = rs_spec.get("replicas", 0)
                available = rs_status.get("availableReplicas", 0)
                
                is_current = (rs_hash == current_pod_hash) if current_pod_hash else (replicas > 0 and available > 0)
                if is_current and revision_num > current_revision_num:
                    current_revision_num = revision_num
                    
                status_str = "active" if replicas > 0 else "scaled-down"
                if not is_current and replicas == 0:
                    status_str = "replaced"
                    
                revisions.append({
                    "revision": revision_num,
                    "replicaSetHash": rs_hash,
                    "image": primary_image,
                    "images": images_map,
                    "replicas": replicas,
                    "createdAt": metadata.get("creationTimestamp", ""),
                    "status": status_str,
                    "isCurrent": is_current
                })
                
            # Sort revisions by creation time or revision number (descending)
            revisions.sort(key=lambda x: x["revision"], reverse=True)
            
            # Limit returned revisions
            revisions = revisions[:min(limit, history_limit)]
            
            return {
                "deployment": name,
                "namespace": namespace,
                "currentRevision": current_revision_num,
                "revisions": revisions
            }
            
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to get revision history: {e}")
        except Exception as e:
            raise ArgoRolloutError(f"Failed to get revision history: {e}")
    
    async def update_rollout_image(
        self,
        name: str,
        new_image: str,
        namespace: str = "default",
        container_name: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Update rollout container image.
        
        For direct rollouts: patches Rollout spec.template.
        For workloadRef rollouts: patches the referenced Deployment's template.
        The Argo Rollouts controller observes the Deployment change and starts
        a new canary/bluegreen revision.
        """
        self._ensure_initialized()
        
        if container_name is None:
            container_name = name
        
        try:
            # Fetch current rollout
            current = self._rollout_api.get(name=name, namespace=namespace)
            current_dict = current.to_dict() if hasattr(current, "to_dict") else dict(current)
            workload_ref = current_dict.get("spec", {}).get("workloadRef")
            
            if workload_ref:
                dep_name = workload_ref.get("name")
                if not dep_name:
                    raise ArgoRolloutError(
                        f"Rollout '{name}' workloadRef has no 'name'. "
                        "Cannot update image for workloadRef rollouts without a referenced Deployment."
                    )
                return await self._update_deployment_image(
                    deployment_name=dep_name,
                    new_image=new_image,
                    namespace=namespace,
                    container_name=container_name,
                    rollout_name=name,
                    dry_run=dry_run,
                )
            
            # Direct rollout: patch Rollout spec.template
            containers = (
                current_dict.get("spec", {})
                .get("template", {})
                .get("spec", {})
                .get("containers", [])
            )
            if not containers:
                raise ArgoRolloutError(
                    f"Rollout '{name}' has no containers in spec.template.spec"
                )
            updated = False
            for c in containers:
                if c.get("name") == container_name:
                    c["image"] = new_image
                    updated = True
                    break
            if not updated:
                raise ArgoRolloutError(
                    f"Container '{container_name}' not found in rollout '{name}'. "
                    f"Containers: {[c.get('name') for c in containers]}"
                )
            patch = {
                "spec": {
                    "template": {
                        "spec": {
                            "containers": containers,
                        }
                    },
                    "restartAt": None,
                }
            }
            patch_kwargs: Dict[str, Any] = {
                "name": name,
                "namespace": namespace,
                "body": patch,
                "content_type": "application/merge-patch+json",
            }
            if dry_run:
                patch_kwargs["dry_run"] = "All"

            self._rollout_api.patch(**patch_kwargs)
            
            logger.info(f"✅ {'Previewed' if dry_run else 'Updated'} rollout image: {name} -> {new_image}")
            return {
                "status": "preview" if dry_run else "success",
                "dry_run": dry_run,
                "rollout": name,
                "namespace": namespace,
                "new_image": new_image,
                "message": (
                    f"[DRY-RUN PREVIEW] Rollout {name} image patch to {new_image} validated"
                    if dry_run
                    else f"Rollout {name} image updated to {new_image}"
                ),
            }
        
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to update image: {e}")
        except (RolloutNotFoundError, ArgoRolloutError):
            raise
        except Exception as e:
            raise ArgoRolloutError(f"Failed to update image: {e}")
    
    async def _update_deployment_image(
        self,
        deployment_name: str,
        new_image: str,
        namespace: str = "default",
        container_name: Optional[str] = None,
        rollout_name: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Update a Deployment's container image. Used for workloadRef rollouts."""
        apps_v1 = self._get_apps_v1()
        try:
            dep = apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
            containers = dep.spec.template.spec.containers or []
            if not containers:
                raise ArgoRolloutError(
                    f"Deployment '{deployment_name}' has no containers"
                )
            container_index = None
            for i, c in enumerate(containers):
                if c.name == container_name:
                    container_index = i
                    break
            if container_index is None:
                raise ArgoRolloutError(
                    f"Container '{container_name}' not found in Deployment '{deployment_name}'. "
                    f"Containers: {[c.name for c in containers]}"
                )
            json_patch = [
                {"op": "replace", "path": f"/spec/template/spec/containers/{container_index}/image", "value": new_image}
            ]
            deployment_resource = self._dyn_client.resources.get(api_version="apps/v1", kind="Deployment")
            patch_kwargs: Dict[str, Any] = {
                "name": deployment_name,
                "namespace": namespace,
                "body": json_patch,
                "content_type": "application/json-patch+json",
            }
            if dry_run:
                patch_kwargs["dry_run"] = "All"
            deployment_resource.patch(**patch_kwargs)
            msg = f"Deployment '{deployment_name}' image {'previewed' if dry_run else 'updated'} to {new_image}"
            if rollout_name:
                msg += f". Rollout '{rollout_name}' will observe the change and start a new revision."
            logger.info(f"✅ {msg}")
            return {
                "status": "preview" if dry_run else "success",
                "dry_run": dry_run,
                "rollout": rollout_name or deployment_name,
                "namespace": namespace,
                "new_image": new_image,
                "message": msg,
            }
        except ApiException as e:
            if e.status == 404:
                raise ArgoRolloutError(f"Deployment '{deployment_name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to update Deployment image: {e}")

    async def check_workload_ref_delete_safety(
        self,
        name: str,
        namespace: str = "default",
    ) -> None:
        """Raise ArgoRolloutError if Rollout uses workloadRef and the referenced Deployment has 0 replicas."""
        self._ensure_initialized()
        try:
            ro = self._rollout_api.get(name=name, namespace=namespace)
            ro_dict = _to_plain_dict(ro)
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            return
        except Exception:
            return

        workload_ref = (ro_dict.get("spec") or {}).get("workloadRef")
        if not isinstance(workload_ref, dict) or not workload_ref.get("name"):
            return

        dep_name = workload_ref["name"]
        try:
            apps_v1 = self._get_apps_v1()
            dep = apps_v1.read_namespaced_deployment(name=dep_name, namespace=namespace)
            replicas = getattr(dep.spec, "replicas", None)
            if replicas is None and isinstance(dep, dict):
                replicas = (dep.get("spec") or {}).get("replicas")
            if replicas == 0:
                raise ArgoRolloutError(
                    f"Blocked deletion of Rollout '{name}': it references Deployment '{dep_name}' "
                    "via workloadRef, and that Deployment is scaled to 0 replicas. Deleting the Rollout "
                    "now would cause a total service outage. First scale up the Deployment using "
                    f"argo_manage_legacy_deployment(name='{dep_name}', namespace='{namespace}', "
                    "action='scale', replicas=3, dry_run=False) or convert the Rollout back with "
                    f"argo_convert_rollout_to_deployment(name='{name}', namespace='{namespace}')."
                )
        except ArgoRolloutError:
            raise
        except Exception:
            pass

    async def verify_rollout_healthy(
        self,
        rollout_name: Optional[str] = None,
        namespace: str = "default",
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify that a Rollout is Healthy with ready replicas before scaling down/deleting a legacy Deployment."""
        target_name = rollout_name or name
        if not target_name:
            raise ArgoRolloutError("rollout_name or name is required for verify_rollout_healthy")
        status = await self.get_rollout_status(name=target_name, namespace=namespace)
        phase = status.get("phase", "Unknown")
        ready = (status.get("replicas") or {}).get("ready", 0) or 0
        if phase != "Healthy" or ready <= 0:
            raise ArgoRolloutError(
                f"Refusing to scale down or delete legacy Deployment because Rollout '{target_name}' "
                f"in namespace '{namespace}' is in phase '{phase}' (ready_replicas={ready}), not Healthy. "
                f"Wait until Rollout '{target_name}' is Healthy or diagnose it with "
                f"argo_diagnose_rollout(name='{target_name}', namespace='{namespace}')."
            )
        return status
    
    async def delete_rollout(
        self,
        name: str,
        namespace: str = "default",
        clean_all: bool = False
    ) -> Dict[str, Any]:
        """Delete a Rollout resource.
        
        Args:
            name: Rollout name
            namespace: Kubernetes namespace
            clean_all: Whether to attempt deleting associated services and analysis templates
        
        Returns:
            Deletion result
        
        Raises:
            RolloutNotFoundError: If rollout doesn't exist
            ArgoRolloutError: If workloadRef safety guard blocks deletion
        """
        self._ensure_initialized()

        # Pre-check: prevent outage if Rollout uses workloadRef and Deployment is at 0 replicas
        await self.check_workload_ref_delete_safety(name=name, namespace=namespace)
        
        deleted_resources = []
        
        try:
            try:
                self._rollout_api.delete(name=name, namespace=namespace)
                logger.info(f"✅ Deleted rollout: {name}")
                deleted_resources.append(f"Rollout/{name}")
            except ApiException as e:
                if e.status != 404:
                    raise
            
            if clean_all:
                core_v1 = client.CoreV1Api(self._k8s_client)
                
                # Delete related services commonly used by Rollouts
                for svc_name in [f"{name}-stable", f"{name}-canary", f"{name}-active", f"{name}-preview"]:
                    try:
                        core_v1.delete_namespaced_service(name=svc_name, namespace=namespace)
                        logger.info(f"✅ Deleted Service: {svc_name}")
                        deleted_resources.append(f"Service/{svc_name}")
                    except ApiException:
                        pass
                
                # Delete related analysis templates
                if self._analysis_template_api:
                    for at_name in [f"{name}-analysis", f"{name}-pre-promotion", f"{name}-post-promotion", name]:
                        try:
                            self._analysis_template_api.delete(name=at_name, namespace=namespace)
                            logger.info(f"✅ Deleted AnalysisTemplate: {at_name}")
                            deleted_resources.append(f"AnalysisTemplate/{at_name}")
                        except ApiException:
                            pass
                
                # Delete related experiment
                if self._experiment_api:
                    try:
                        self._experiment_api.delete(name=name, namespace=namespace)
                        logger.info(f"✅ Deleted Experiment: {name}")
                        deleted_resources.append(f"Experiment/{name}")
                    except ApiException:
                        pass
            
            if not deleted_resources:
                raise RolloutNotFoundError(f"Rollout '{name}' and associated resources not found in namespace '{namespace}'")
            
            return {
                "status": "success",
                "rollout": name,
                "namespace": namespace,
                "deleted_resources": deleted_resources,
                "message": f"Rollout {name} and associated resources deleted successfully" if clean_all else f"Rollout {name} deleted successfully"
            }
        
        except (RolloutNotFoundError, ArgoRolloutError):
            raise
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to delete rollout: {e}")
        except Exception as e:
            raise ArgoRolloutError(f"Failed to delete rollout: {e}")

    async def patch_workload_ref_scale_down(
        self,
        name: str,
        namespace: str = "default",
        scale_down: str = "progressively",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Patch workloadRef.scaleDown on an existing Rollout."""
        self._ensure_initialized()
        if scale_down not in ("never", "onsuccess", "progressively"):
            raise ArgoRolloutError(
                f"Invalid scale_down '{scale_down}'. Must be 'never', 'onsuccess', or 'progressively'."
            )

        try:
            current = self._rollout_api.get(name=name, namespace=namespace)
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to fetch rollout: {e}")

        current_dict = current.to_dict() if hasattr(current, 'to_dict') else dict(current)
        if not current_dict.get("spec", {}).get("workloadRef"):
            raise ArgoRolloutError(
                f"Rollout '{name}' has no workloadRef. This tool only applies to workloadRef rollouts."
            )

        patch_body = {
            "spec": {
                "workloadRef": {
                    **current_dict["spec"]["workloadRef"],
                    "scaleDown": scale_down,
                }
            }
        }

        try:
            patch_kwargs: Dict[str, Any] = {
                "name": name,
                "namespace": namespace,
                "body": patch_body,
                "content_type": "application/merge-patch+json",
            }
            if dry_run:
                patch_kwargs["dry_run"] = "All"
            self._rollout_api.patch(**patch_kwargs)
        except ApiException as e:
            raise ArgoRolloutError(f"Failed to patch workloadRef.scaleDown on rollout '{name}': {e}")

        logger.info(f"✅ {'Previewed' if dry_run else 'Patched'} workloadRef.scaleDown on Rollout '{name}' to '{scale_down}'")
        return {
            "status": "preview" if dry_run else "success",
            "dry_run": dry_run,
            "rollout_name": name,
            "namespace": namespace,
            "scale_down": scale_down,
            "message": (
                f"[DRY-RUN PREVIEW] Rollout '{name}' workloadRef.scaleDown patch to '{scale_down}' validated"
                if dry_run
                else f"Rollout '{name}' workloadRef.scaleDown set to '{scale_down}'"
            ),
        }

    def _get_apps_v1(self):
        """Lazily get AppsV1Api for Deployment operations."""
        if getattr(self, "_apps_v1", None) is not None:
            return self._apps_v1
        return client.AppsV1Api(self._k8s_client)

    async def scale_deployment(
        self,
        name: str,
        namespace: str = "default",
        replicas: int = 0,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Scale a Deployment's replicas."""
        self._ensure_initialized()
        apps_v1 = self._get_apps_v1()

        try:
            dep = apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
            dep.spec.replicas = replicas
            replace_kwargs: Dict[str, Any] = {
                "name": name,
                "namespace": namespace,
                "body": dep,
            }
            if dry_run:
                replace_kwargs["dry_run"] = "All"
            apps_v1.replace_namespaced_deployment(**replace_kwargs)
        except ApiException as e:
            if e.status == 404:
                raise ArgoRolloutError(f"Deployment '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to scale Deployment '{name}': {e}")

        logger.info(f"✅ {'Previewed scaling' if dry_run else 'Scaled'} Deployment '{name}' to {replicas} replicas")
        return {
            "status": "preview" if dry_run else "success",
            "deployment_name": name,
            "namespace": namespace,
            "replicas": replicas,
            "message": (
                f"[DRY-RUN PREVIEW] Deployment '{name}' scale to {replicas} replicas validated."
                if dry_run
                else f"Deployment '{name}' scaled to {replicas} replicas. "
                "If Argo CD manages this Deployment, it may revert on next sync."
            ),
        }

    async def delete_deployment(
        self,
        name: str,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        """Delete a Deployment from the cluster."""
        self._ensure_initialized()
        apps_v1 = self._get_apps_v1()

        try:
            apps_v1.delete_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=client.V1DeleteOptions(propagation_policy="Background"),
            )
        except ApiException as e:
            if e.status == 404:
                return {
                    "status": "success",
                    "deployment_name": name,
                    "namespace": namespace,
                    "message": f"Deployment '{name}' not found (already deleted or never existed)",
                }
            raise ArgoRolloutError(f"Failed to delete Deployment '{name}': {e}")

        logger.info(f"✅ Deleted Deployment '{name}'")
        return {
            "status": "success",
            "deployment_name": name,
            "namespace": namespace,
            "message": f"Deployment '{name}' deleted. "
            "If Argo CD manages it, it may recreate on next sync.",
        }

    async def list_rollouts(
        self,
        namespace: Optional[str] = None
    ) -> Dict[str, Any]:
        """List all rollouts in a namespace or cluster-wide.
        
        Args:
            namespace: Kubernetes namespace, or None to list across ALL namespaces
        
        Returns:
            List of rollouts with basic info and computed health_score
        """
        self._ensure_initialized()
        
        try:
            if namespace:
                list_result = self._rollout_api.get(namespace=namespace)
            else:
                list_result = self._rollout_api.get()
            
            rollouts = []
            items = list_result.get('items', [])
            for item in items:
                item_dict = item.to_dict() if hasattr(item, 'to_dict') else dict(item)
                metadata = item_dict.get("metadata", {}) or {}
                spec = item_dict.get("spec", {}) or {}
                status = item_dict.get("status", {}) or {}
                item_namespace = metadata.get("namespace") or namespace or "default"
                
                strategy = "canary" if "canary" in spec.get("strategy", {}) else \
                          "bluegreen" if "blueGreen" in spec.get("strategy", {}) else \
                          "rolling"
                
                containers = spec.get("template", {}).get("spec", {}).get("containers", [])
                image = containers[0].get("image", "") if containers else ""

                desired = spec.get("replicas", 0) or 0
                current = status.get("replicas", 0) or 0
                ready = status.get("readyReplicas", 0) or 0
                available = status.get("availableReplicas", ready) or 0
                phase = status.get("phase", "Unknown")
                health_score = _compute_health_score(phase, desired, ready, available)
                
                rollouts.append({
                    "name": metadata.get("name"),
                    "namespace": item_namespace,
                    "strategy": strategy,
                    "desired_replicas": desired,
                    "current_replicas": current,
                    "ready_replicas": ready,
                    "available_replicas": available,
                    "phase": phase,
                    "health_score": health_score,
                    "created": metadata.get("creationTimestamp"),
                    "image": image
                })
            
            return {
                "status": "success",
                "namespace": namespace if namespace else "_all",
                "count": len(rollouts),
                "rollouts": rollouts
            }
        
        except Exception as e:
            raise ArgoRolloutError(f"Failed to list rollouts: {e}")
    
    async def set_analysis_template(
        self,
        rollout_name: str,
        template_name: str,
        namespace: str = "default",
        metrics: Optional[List[Dict]] = None,
        scope: str = "namespace",
        prometheus_url: str = "http://prometheus:9090",
        error_rate_threshold: float = 5.0,
        latency_p99_threshold: float = 2000.0,
        latency_p95_threshold: float = 1000.0,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Configure analysis template for automated metrics validation."""
        self._ensure_initialized()
        
        if scope == "cluster":
            if not self._cluster_analysis_template_api:
                raise AnalysisTemplateError("ClusterAnalysisTemplate CRD not available")
        else:
            if not self._analysis_template_api:
                raise AnalysisTemplateError("AnalysisTemplate CRD not available")
        
        if metrics is None:
            if self._generator_service is not None:
                metrics = self._generator_service.get_analysis_metrics_from_thresholds(
                    service_name=rollout_name,
                    prometheus_url=prometheus_url,
                    error_rate_threshold=error_rate_threshold,
                    latency_p99_threshold=latency_p99_threshold,
                    latency_p95_threshold=latency_p95_threshold,
                )
            else:
                metrics = [
                    {
                        "name": "success-rate",
                        "interval": "60s",
                        "initialDelay": "60s",
                        "failureLimit": 2,
                        "count": 3,
                        "successCondition": "result[0] >= 0.99",
                        "provider": {
                            "prometheus": {
                                "address": prometheus_url,
                                "query": 'sum(rate(http_requests_total{status=~"2.*"}[5m])) / sum(rate(http_requests_total[5m]))'
                            }
                        }
                    }
                ]
        
        metrics = [
            {**m, "count": m.get("count", 3)} if m.get("successCondition") and "count" not in m else m
            for m in metrics
        ]
        
        try:
            rollout = self._rollout_api.get(name=rollout_name, namespace=namespace)
            rollout_dict = _to_plain_dict(rollout)
            strategy = rollout_dict.get("spec", {}).get("strategy", {})
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{rollout_name}' not found")
            raise AnalysisTemplateError(f"Failed to get rollout: {e}")
        
        if scope == "cluster":
            analysis_template = {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "ClusterAnalysisTemplate",
                "metadata": {"name": template_name},
                "spec": {"metrics": metrics},
            }
        else:
            analysis_template = {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "AnalysisTemplate",
                "metadata": {
                    "name": template_name,
                    "namespace": namespace
                },
                "spec": {"metrics": metrics},
            }
        
        template_yaml = yaml.dump(analysis_template, default_flow_style=False)

        try:
            create_extra: Dict[str, Any] = {"dry_run": "All"} if dry_run else {}
            patch_extra: Dict[str, Any] = {"dry_run": "All"} if dry_run else {}

            if scope == "cluster":
                try:
                    self._cluster_analysis_template_api.create(body=analysis_template, **create_extra)
                except ApiException as e:
                    if e.status == 409:
                        self._cluster_analysis_template_api.patch(
                            name=template_name,
                            body=analysis_template,
                            content_type="application/merge-patch+json",
                            **patch_extra,
                        )
                    else:
                        raise
            else:
                try:
                    self._analysis_template_api.create(
                        body=analysis_template,
                        namespace=namespace,
                        **create_extra,
                    )
                except ApiException as e:
                    if e.status == 409:
                        self._analysis_template_api.patch(
                            name=template_name,
                            namespace=namespace,
                            body=analysis_template,
                            content_type="application/merge-patch+json",
                            **patch_extra,
                        )
                    else:
                        raise
            
            template_ref = {"templateName": template_name}
            if scope == "cluster":
                template_ref["clusterScope"] = True

            if "blueGreen" in strategy:
                patch = {
                    "spec": {
                        "strategy": {
                            "blueGreen": {
                                "prePromotionAnalysis": {
                                    "templates": [template_ref]
                                }
                            }
                        }
                    }
                }
            else:
                patch = {
                    "spec": {
                        "strategy": {
                            "canary": {
                                "analysis": {
                                    "templates": [template_ref]
                                }
                            }
                        }
                    }
                }

            self._rollout_api.patch(
                name=rollout_name,
                namespace=namespace,
                body=patch,
                content_type="application/merge-patch+json",
                **patch_extra,
            )
            
            logger.info(f"✅ Analysis template {template_name} {'previewed' if dry_run else 'configured'}")
            return {
                "status": "preview" if dry_run else "success",
                "dry_run": dry_run,
                "template_name": template_name,
                "rollout": rollout_name,
                "namespace": namespace,
                "scope": scope,
                "manifest": template_yaml,
                "template_yaml": template_yaml,
                "message": (
                    f"[DRY-RUN PREVIEW] AnalysisTemplate '{template_name}' and Rollout '{rollout_name}' link validated"
                    if dry_run
                    else f"Analysis template configured for rollout {rollout_name}"
                ),
            }
        
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{rollout_name}' not found")
            raise AnalysisTemplateError(f"Failed to configure analysis: {e}")
        except Exception as e:
            raise AnalysisTemplateError(f"Failed to configure analysis: {e}")

    def delete_analysis_template(
        self,
        name: str,
        namespace: str = "default",
        scope: str = "namespace",
    ) -> Dict[str, Any]:
        """Delete an AnalysisTemplate or ClusterAnalysisTemplate from the cluster."""
        self._ensure_initialized()

        try:
            if scope == "cluster":
                if not self._cluster_analysis_template_api:
                    raise AnalysisTemplateError("ClusterAnalysisTemplate CRD not available")
                self._cluster_analysis_template_api.delete(name=name)
            else:
                if not self._analysis_template_api:
                    raise AnalysisTemplateError("AnalysisTemplate CRD not available")
                self._analysis_template_api.delete(name=name, namespace=namespace)
            logger.info(f"✅ Deleted {'Cluster' if scope == 'cluster' else ''}AnalysisTemplate: {name}")
            return {
                "status": "success",
                "template_name": name,
                "namespace": namespace if scope != "cluster" else None,
                "scope": scope,
                "message": f"{'Cluster' if scope == 'cluster' else ''}AnalysisTemplate '{name}' deleted successfully",
            }
        except ApiException as e:
            if e.status == 404:
                return {
                    "status": "success",
                    "template_name": name,
                    "namespace": namespace if scope != "cluster" else None,
                    "scope": scope,
                    "message": f"{'Cluster' if scope == 'cluster' else ''}AnalysisTemplate '{name}' not found (already deleted or never existed)",
                }
            raise AnalysisTemplateError(f"Failed to delete AnalysisTemplate '{name}': {e}")
    
    async def skip_analysis_promote(
        self,
        name: str,
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """Emergency override: Skip analysis and promote to next step.
        
        Use only when:
        - Analysis tool is failing but version is healthy
        - Urgent prod fix needed
        - Manual validation completed
        
        Args:
            name: Rollout name
            namespace: Kubernetes namespace
        
        Returns:
            Override result
        """
        self._ensure_initialized()
        
        try:
            # Get current rollout
            rollout = self._rollout_api.get(name=name, namespace=namespace)
            status = rollout.get("status", {})
            
            # Skip analysis by incrementing step
            current_step = status.get("currentStepIndex", 0)
            
            patch = {
                "status": {
                    "currentStepIndex": current_step + 1,
                    "skippedAnalysis": True,
                    "lastTransitionTime": datetime.now().isoformat()
                },
                "metadata": {
                    "annotations": {
                        "analysis-skipped-at": datetime.now().isoformat(),
                        "skip-reason": "Emergency override"
                    }
                }
            }
            
            self._rollout_api.patch(
                name=name,
                namespace=namespace,
                body=patch,
                content_type="application/merge-patch+json"
            )
            
            logger.warning(f"⚠️  EMERGENCY OVERRIDE: Skipped analysis for {name}")
            return {
                "status": "success",
                "rollout": name,
                "namespace": namespace,
                "message": f"Analysis skipped for {name} - promoted to next step",
                "warning": "Analysis was skipped - ensure version was validated manually"
            }
        
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to skip analysis: {e}")
        except Exception as e:
            raise ArgoRolloutError(f"Failed to skip analysis: {e}")
    
    async def _resolve_spec_ref_templates(
        self,
        rollout_name: str,
        rollout_namespace: str,
        templates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Resolve specRef to full pod templates from Rollout ReplicaSets.
        
        Supports canary (stable/canary) and blue-green (active/preview) aliases.
        """
        # Fetch rollout
        try:
            rollout = await self.get_rollout_manifest(rollout_name, rollout_namespace)
        except Exception as e:
            raise ArgoRolloutError(
                f"Failed to fetch Rollout '{rollout_name}' in namespace "
                f"'{rollout_namespace}' to resolve specRef: {e}"
            )
            
        status = rollout.get("status", {})
        spec = rollout.get("spec", {})
        match_labels = (spec.get("selector") or {}).get("matchLabels") or {}

        # Extract ReplicaSet hashes for 'stable'/'active' and 'canary'/'preview'
        stable_hash = status.get("stableRS", "")
        current_hash = status.get("currentPodHash", "")
        
        # In generic terms, the "new" variant (canary/preview) is the currentPodHash.
        # But if the Rollout is fully promoted, currentPodHash == stableRS.
        canary_hash = current_hash if current_hash and current_hash != stable_hash else ""

        resolved = []
        for t in templates:
            spec_ref = t.get("specRef")
            if spec_ref not in ("stable", "canary", "active", "preview"):
                # Missing or unrecognized specRef -> pass through full template
                resolved.append(t)
                continue

            # Map specRef to hash
            if spec_ref in ("stable", "active"):
                pod_hash = stable_hash
                if not pod_hash:
                    raise ArgoRolloutError(
                        f"Rollout '{rollout_name}' has no stable/active ReplicaSet "
                        f"(status.stableRS is empty)."
                    )
            else:  # "canary" or "preview"
                if not canary_hash:
                    raise ArgoRolloutError(
                        f"specRef '{spec_ref}' requires a new deployment in progress. "
                        f"Rollout '{rollout_name}' is fully promoted (no distinct "
                        f"canary/preview ReplicaSet). Trigger an image update first."
                    )
                pod_hash = canary_hash

            # Fetch ReplicaSet
            rs_name = f"{rollout_name}-{pod_hash}"
            try:
                if not self._replicaset_api:
                    # Fallback to init if missing
                    self._ensure_initialized()
                    
                rs = await asyncio.to_thread(
                    self._replicaset_api.get,
                    name=rs_name,
                    namespace=rollout_namespace
                )
                # Convert ResourceInstance to plain dict for API compatibility
                rs_dict = _to_plain_dict(rs)
                rs_spec = rs_dict.get("spec") or {}
                pod_template = _to_plain_dict(rs_spec.get("template") or {})
            except ApiException as e:
                # E.g. 404
                raise ArgoRolloutError(
                    f"Failed to fetch ReplicaSet '{rs_name}' for specRef '{spec_ref}': {e}. "
                    "Ensure the required deployment state exists."
                )

            # Build full experiment template
            template_name = t.get("name", spec_ref)
            selector_labels = dict(match_labels)
            
            # The experiment CRD requires the template pods to match its selector.
            # But the newly created experiment pods need to NOT match the Rollout's Service
            # directly (otherwise they'd receive live traffic inadvertently).
            # So we add a unique experiment variant label.
            selector_labels["experiment-variant"] = template_name

            template_metadata = pod_template.get("metadata") or {}
            template_labels = dict(template_metadata.get("labels") or {})
            template_labels.update(selector_labels)

            resolved_template = {
                "name": template_name,
                "replicas": t.get("replicas", 1),
                "selector": {"matchLabels": selector_labels},
                "template": {
                    "metadata": {**template_metadata, "labels": template_labels},
                    "spec": pod_template.get("spec", {})
                }
            }
            resolved.append(resolved_template)

        return resolved

    async def create_experiment(
        self,
        name: str,
        namespace: str = "default",
        templates: Optional[List[Dict[str, Any]]] = None,
        duration: Optional[str] = None,
        analyses: Optional[List[Dict[str, Any]]] = None,
        progress_deadline_seconds: int = 300,
        rollout_name: Optional[str] = None,
        rollout_namespace: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Create a standalone Argo Experiment.
        
        Experiments create ephemeral ReplicaSets for comparison/analysis.
        Optionally launch AnalysisRuns alongside templates.
        
        NOTE: Weighted experiment traffic routing is only supported for
        SMI, ALB, and Istio traffic routers — NOT Traefik. Experiments
        with Traefik should be used for metrics comparison only
        (experiment-as-analysis-step pattern), not for live traffic routing.
        
        Args:
            name: Experiment name
            namespace: Kubernetes namespace
            templates: List of template specs, each with:
                - name: Template name
                - replicas: Number of replicas (default: 1)
                - specRef: "stable" or "canary" (for inline rollout experiments)
                - template: Pod template spec (for standalone experiments)
            duration: How long to run (e.g. "20m", "1h")
            analyses: List of analysis references, each with:
                - name: Analysis name
                - templateName: AnalysisTemplate name
                - requiredForCompletion: bool (optional)
                - args: List of {name, value} pairs (optional)
            progress_deadline_seconds: Deadline for ReplicaSets to become available
            dry_run: If True, run server-side dry-run ("All") without mutating cluster
        
        Returns:
            Creation result with experiment details
        """
        self._ensure_initialized()
        
        if self._experiment_api is None:
            raise ArgoRolloutError(
                "Experiment CRD not available. Ensure Argo Rollouts is installed "
                "with Experiment CRD support."
            )
        
        if not templates:
            raise ArgoRolloutError("At least one template is required for an Experiment.")
            
        # Resolve 'specRef' shortcuts to full pod templates if present
        has_spec_ref = any("specRef" in t for t in templates)
        if has_spec_ref:
            if not rollout_name:
                raise ArgoRolloutError("rollout_name is required when creating an Experiment with templates using 'specRef'.")
            
            # Default lookup namespace to experiment namespace if not provided
            lookup_ns = rollout_namespace or namespace
            templates = await self._resolve_spec_ref_templates(
                rollout_name=rollout_name,
                rollout_namespace=lookup_ns,
                templates=templates
            )
        
        try:
            # Build Experiment spec
            experiment_spec: Dict[str, Any] = {
                "templates": templates,
                "progressDeadlineSeconds": progress_deadline_seconds
            }
            
            if duration:
                experiment_spec["duration"] = duration
            
            if analyses:
                experiment_spec["analyses"] = analyses
            
            experiment_body = {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "Experiment",
                "metadata": {
                    "name": name,
                    "namespace": namespace,
                    "labels": {
                        "managed-by": "argoflow-mcp-server"
                    }
                },
                "spec": experiment_spec
            }
            # JSON round-trip ensures plain Python types only — avoids Kubernetes
            # client sanitize_for_serialization hitting ResourceInstance/openapi_types
            experiment_body = json.loads(json.dumps(experiment_body, default=str))

            create_kwargs: Dict[str, Any] = {
                "body": experiment_body,
                "namespace": namespace,
            }
            if dry_run:
                create_kwargs["dry_run"] = "All"

            result = await asyncio.to_thread(
                self._experiment_api.create,
                **create_kwargs
            )
            
            return {
                "status": "preview" if dry_run else "success",
                "dry_run": dry_run,
                "experiment": name,
                "namespace": namespace,
                "templates": [t.get("name", "unknown") for t in templates],
                "duration": duration or "indefinite",
                "analyses": [a.get("name", "unknown") for a in (analyses or [])],
                "manifest": yaml.dump(experiment_body, default_flow_style=False),
                "message": f"Experiment '{name}' {'validated (dry-run)' if dry_run else 'created successfully'}",
                "traefik_note": "Weighted experiment traffic routing is NOT supported with Traefik. Use experiments for metrics comparison only."
            }
        
        except ApiException as e:
            raise ArgoRolloutError(f"Failed to create experiment '{name}': {e}")
        except Exception as e:
            raise ArgoRolloutError(f"Failed to create experiment '{name}': {e}")
    
    async def get_experiment_status(
        self,
        name: str,
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """Get status of an Argo Experiment.
        
        Args:
            name: Experiment name
            namespace: Kubernetes namespace
        
        Returns:
            Experiment status including phase, template statuses, analysis results
        """
        self._ensure_initialized()
        
        if self._experiment_api is None:
            raise ArgoRolloutError("Experiment CRD not available.")
        
        try:
            experiment = await asyncio.to_thread(
                self._experiment_api.get,
                name=name,
                namespace=namespace
            )
            
            status = experiment.get("status", {})
            spec = experiment.get("spec", {})
            
            # Extract template statuses
            template_statuses = []
            for ts in status.get("templateStatuses", []):
                template_statuses.append({
                    "name": ts.get("name"),
                    "replicas": ts.get("replicas", 0),
                    "readyReplicas": ts.get("readyReplicas", 0),
                    "availableReplicas": ts.get("availableReplicas", 0),
                    "status": ts.get("status", "Unknown")
                })
            
            # Extract analysis statuses
            analysis_statuses = []
            for ar in status.get("analysisRuns", []):
                analysis_statuses.append({
                    "name": ar.get("name"),
                    "analysisRun": ar.get("analysisRun"),
                    "phase": ar.get("phase", "Unknown")
                })
            
            return {
                "status": "success",
                "experiment": name,
                "namespace": namespace,
                "phase": status.get("phase", "Unknown"),
                "message": status.get("message", ""),
                "duration": spec.get("duration", "indefinite"),
                "templateStatuses": template_statuses,
                "analysisRuns": analysis_statuses,
                "availableAt": status.get("availableAt", ""),
                "conditions": [
                    {
                        "type": c.get("type"),
                        "status": c.get("status"),
                        "reason": c.get("reason", ""),
                        "message": c.get("message", "")
                    }
                    for c in status.get("conditions", [])
                ]
            }
        
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Experiment '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to get experiment status: {e}")
        except Exception as e:
            raise ArgoRolloutError(f"Failed to get experiment status: {e}")
    
    async def delete_experiment(
        self,
        name: str,
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """Delete an Argo Experiment.
        
        Args:
            name: Experiment name
            namespace: Kubernetes namespace
        
        Returns:
            Deletion result
        """
        self._ensure_initialized()
        
        if self._experiment_api is None:
            raise ArgoRolloutError("Experiment CRD not available.")
        
        try:
            await asyncio.to_thread(
                self._experiment_api.delete,
                name=name,
                namespace=namespace
            )
            
            return {
                "status": "success",
                "experiment": name,
                "namespace": namespace,
                "message": f"Experiment '{name}' deleted successfully"
            }
        
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Experiment '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to delete experiment: {e}")
        except Exception as e:
            raise ArgoRolloutError(f"Failed to delete experiment: {e}")

    async def set_traffic_routing(
        self,
        name: str,
        namespace: str = "default",
        traefik_service_name: Optional[str] = None,
        gateway_api_config: Optional[Dict[str, Any]] = None,
        clear_routing: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Patch the trafficRouting stanza on an existing Rollout.

        This is the critical link between an Argo Rollout and Traefik:
        the Argo Rollouts controller reads `spec.strategy.canary.trafficRouting`
        to know which TraefikService to update weights on during canary steps.

        Without this, the controller shifts traffic purely via replica counts
        and never touches the Traefik weights — canary traffic shifting via
        Traefik does NOT work.

        Args:
            name: Rollout name
            namespace: Kubernetes namespace
            traefik_service_name: TraefikService name (e.g. 'hello-service-route-wrr').
                                  Must already exist in the same namespace. Mutually exclusive with gateway_api_config.
            gateway_api_config: Gateway API plugin config for HTTPRoute-based canaries.
                               Example: {"httpRoute": "my-app-route", "namespace": "default"}.
                               Mutually exclusive with traefik_service_name.
            clear_routing: If True, remove any existing trafficRouting stanza.
            dry_run: If True, run server-side dry-run ("All") without mutating cluster.

        Returns:
            Dict with status, rollout_name, traffic_routing config applied.

        Raises:
            RolloutNotFoundError: If rollout doesn't exist
            RolloutStrategyError: If the rollout is not canary strategy
            ArgoRolloutError: If patch fails
        """
        self._ensure_initialized()

        # Fetch current rollout to determine strategy
        try:
            current = self._rollout_api.get(name=name, namespace=namespace)
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to fetch rollout: {e}")

        current_dict = _to_plain_dict(current)
        strategy = current_dict.get("spec", {}).get("strategy", {})

        if "canary" not in strategy and "blueGreen" not in strategy:
            raise RolloutStrategyError(
                f"Rollout '{name}' has no canary or blueGreen strategy configured. "
                "trafficRouting can only be set on canary or blueGreen rollouts."
            )

        strategy_key = "canary" if "canary" in strategy else "blueGreen"

        # Argo Rollouts CRD only supports trafficRouting for canary, not blueGreen
        if strategy_key == "blueGreen" and not clear_routing and (traefik_service_name or gateway_api_config):
            raise RolloutStrategyError(
                f"Rollout '{name}' uses blue-green strategy. Argo Rollouts does not support "
                "trafficRouting (Traefik/Gateway API) for blue-green — only for canary. "
                "Convert the rollout to canary strategy if you need Traefik weighted routing."
            )

        if clear_routing:
            patch_body = {
                "spec": {
                    "strategy": {
                        strategy_key: {
                            "trafficRouting": None
                        }
                    }
                }
            }
            traffic_routing_applied = None
        elif traefik_service_name:
            traffic_routing = {
                "traefik": {
                    "weightedTraefikServiceName": traefik_service_name
                }
            }
            patch_body = {
                "spec": {
                    "strategy": {
                        strategy_key: {
                            "trafficRouting": traffic_routing
                        }
                    }
                }
            }
            traffic_routing_applied = traffic_routing
        elif gateway_api_config:
            plugin_config: Dict[str, Any] = {}
            if "httpRoute" in gateway_api_config:
                plugin_config["httpRoute"] = gateway_api_config["httpRoute"]
            if "httpRoutes" in gateway_api_config:
                plugin_config["httpRoutes"] = gateway_api_config["httpRoutes"]
            if "namespace" in gateway_api_config:
                plugin_config["namespace"] = gateway_api_config["namespace"]
            if "inProgressLabelKey" in gateway_api_config:
                plugin_config["inProgressLabelKey"] = gateway_api_config["inProgressLabelKey"]
            if "inProgressLabelValue" in gateway_api_config:
                plugin_config["inProgressLabelValue"] = gateway_api_config["inProgressLabelValue"]
            if "disableInProgressLabel" in gateway_api_config:
                plugin_config["disableInProgressLabel"] = gateway_api_config["disableInProgressLabel"]
            traffic_routing = {
                "plugins": {
                    "argoproj-labs/gatewayAPI": plugin_config
                }
            }
            patch_body = {
                "spec": {
                    "strategy": {
                        strategy_key: {
                            "trafficRouting": traffic_routing
                        }
                    }
                }
            }
            traffic_routing_applied = traffic_routing
        else:
            raise ArgoRolloutError(
                "Provide 'traefik_service_name' or 'gateway_api_config' to set routing, "
                "or set 'clear_routing=True' to remove it."
            )

        patch_kwargs: Dict[str, Any] = {
            "name": name,
            "namespace": namespace,
            "body": patch_body,
            "content_type": "application/merge-patch+json",
        }
        if dry_run:
            patch_kwargs["dry_run"] = "All"

        try:
            self._rollout_api.patch(**patch_kwargs)
        except ApiException as e:
            raise ArgoRolloutError(f"Failed to patch trafficRouting on rollout '{name}': {e}")

        routing_type = "traefik" if traefik_service_name else "gatewayAPI" if gateway_api_config else "cleared"
        logger.info(
            f"✅ Set trafficRouting on Rollout '{name}' "
            f"(strategy={strategy_key}, type={routing_type})"
        )

        if traffic_routing_applied:
            if traefik_service_name:
                msg = f"✅ trafficRouting patched on Rollout '{name}'. Argo Rollouts controller will now manage weights on TraefikService '{traefik_service_name}' during canary steps."
            else:
                msg = f"✅ trafficRouting patched on Rollout '{name}'. Argo Rollouts controller will now manage weights on Gateway API HTTPRoute during canary steps."
        else:
            msg = f"✅ trafficRouting cleared from Rollout '{name}'."

        # Detect ArgoCD/Helm management — patch may be reverted on next sync
        metadata = current_dict.get("metadata", {})
        annotations = metadata.get("annotations", {}) or {}
        labels = metadata.get("labels", {}) or {}
        is_argocd_managed = "argocd.argoproj.io/tracking-id" in annotations
        is_helm_managed = "helm.sh/chart" in labels or ("app.kubernetes.io/managed-by" in labels and labels.get("app.kubernetes.io/managed-by") == "Helm")
        persistence_warning = None
        if (is_argocd_managed or is_helm_managed) and traffic_routing_applied:
            persistence_warning = (
                "This rollout is managed by ArgoCD or Helm. The trafficRouting patch may be "
                "reverted on the next sync. Add trafficRouting to your Helm chart or ArgoCD "
                "Application source manifest to persist this change."
            )

        result = {
            "status": "preview" if dry_run else "success",
            "dry_run": dry_run,
            "rollout_name": name,
            "namespace": namespace,
            "strategy": strategy_key,
            "traffic_routing": traffic_routing_applied,
            "manifest": yaml.dump(patch_body, default_flow_style=False),
            "message": msg,
        }
        if persistence_warning:
            result["persistence_warning"] = persistence_warning
        return result

    async def update_canary_strategy(
        self,
        name: str,
        namespace: str = "default",
        canary_service: Optional[str] = None,
        stable_service: Optional[str] = None,
        canary_steps: Optional[List[Dict[str, Any]]] = None,
        scale_down_delay_seconds: Optional[int] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Update the canary strategy on an existing Rollout.

        Patches spec.strategy.canary with new canaryService, stableService,
        canary steps, and/or scaleDownDelaySeconds. Preserves existing trafficRouting if present.

        Args:
            name: Rollout name
            namespace: Kubernetes namespace
            canary_service: New canary service name (optional)
            stable_service: New stable service name (optional)
            canary_steps: New canary steps (optional)
            scale_down_delay_seconds: Delay before scaling down old ReplicaSet (optional).
                Use 30 for default; 0 prevents scale down (keeps old RS for fast rollback).
            dry_run: If True, run server-side dry-run ("All") without mutating cluster.

        Returns:
            Dict with status and updated strategy details

        Raises:
            RolloutNotFoundError: If rollout doesn't exist
            RolloutStrategyError: If rollout is not canary strategy
            ArgoRolloutError: If patch fails
        """
        self._ensure_initialized()

        try:
            current = self._rollout_api.get(name=name, namespace=namespace)
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to fetch rollout: {e}")

        current_dict = _to_plain_dict(current)
        strategy = current_dict.get("spec", {}).get("strategy", {})

        if "canary" not in strategy:
            raise RolloutStrategyError(
                f"Rollout '{name}' is not a canary strategy. "
                "Use update_canary_strategy only for canary rollouts."
            )

        canary_spec = dict(strategy.get("canary", {}))
        updated = False

        if canary_service is not None:
            canary_spec["canaryService"] = canary_service
            updated = True
        if stable_service is not None:
            canary_spec["stableService"] = stable_service
            updated = True
        if canary_steps is not None:
            canary_spec["steps"] = canary_steps
            updated = True
        if scale_down_delay_seconds is not None:
            canary_spec["scaleDownDelaySeconds"] = scale_down_delay_seconds
            updated = True

        if not updated:
            return {
                "status": "preview" if dry_run else "success",
                "dry_run": dry_run,
                "rollout_name": name,
                "namespace": namespace,
                "message": "No changes specified; strategy unchanged.",
            }

        patch_body = {
            "spec": {
                "strategy": {
                    "canary": canary_spec
                }
            }
        }

        patch_kwargs: Dict[str, Any] = {
            "name": name,
            "namespace": namespace,
            "body": patch_body,
            "content_type": "application/merge-patch+json",
        }
        if dry_run:
            patch_kwargs["dry_run"] = "All"

        try:
            self._rollout_api.patch(**patch_kwargs)
        except ApiException as e:
            raise ArgoRolloutError(f"Failed to patch canary strategy on rollout '{name}': {e}")

        logger.info(f"✅ Updated canary strategy on Rollout '{name}'")

        return {
            "status": "preview" if dry_run else "success",
            "dry_run": dry_run,
            "rollout_name": name,
            "namespace": namespace,
            "canary_service": canary_spec.get("canaryService"),
            "stable_service": canary_spec.get("stableService"),
            "canary_steps": canary_spec.get("steps"),
            "scale_down_delay_seconds": canary_spec.get("scaleDownDelaySeconds"),
            "manifest": yaml.dump(patch_body, default_flow_style=False),
            "message": f"✅ Canary strategy {'validated (dry-run)' if dry_run else 'updated'} on Rollout '{name}'",
        }

    def remove_conflicting_strategy_block(
        self,
        name: str,
        namespace: str = "default",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Remove conflicting strategy block (e.g. canary from blue-green rollout).

        When argo_configure_analysis_template incorrectly adds canary.analysis to a
        blue-green rollout, the spec ends up with both blueGreen and canary, causing
        InvalidSpec. This patches to remove the canary block, leaving blueGreen intact.

        Args:
            name: Rollout name
            namespace: Kubernetes namespace
            dry_run: If True, run server-side dry-run ("All") without mutating cluster.

        Returns:
            Dict with status and message
        """
        self._ensure_initialized()

        try:
            current = self._rollout_api.get(name=name, namespace=namespace)
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to fetch rollout: {e}")

        current_dict = _to_plain_dict(current)
        strategy = current_dict.get("spec", {}).get("strategy", {})

        if "canary" not in strategy:
            return {
                "status": "preview" if dry_run else "success",
                "dry_run": dry_run,
                "rollout_name": name,
                "namespace": namespace,
                "message": "No conflicting canary block found; rollout spec is valid.",
            }

        if "blueGreen" not in strategy:
            raise RolloutStrategyError(
                f"Rollout '{name}' has canary strategy only. "
                "Use this fix only when both blueGreen and canary are present."
            )

        # JSON merge patch: null removes the key
        patch_body = {
            "spec": {
                "strategy": {
                    "canary": None,
                }
            }
        }

        patch_kwargs: Dict[str, Any] = {
            "name": name,
            "namespace": namespace,
            "body": patch_body,
            "content_type": "application/merge-patch+json",
        }
        if dry_run:
            patch_kwargs["dry_run"] = "All"

        try:
            self._rollout_api.patch(**patch_kwargs)
        except ApiException as e:
            raise ArgoRolloutError(f"Failed to remove conflicting strategy block on rollout '{name}': {e}")

        logger.info(f"✅ Removed conflicting canary block from blue-green Rollout '{name}'")

        return {
            "status": "preview" if dry_run else "success",
            "dry_run": dry_run,
            "rollout_name": name,
            "namespace": namespace,
            "manifest": yaml.dump(patch_body, default_flow_style=False),
            "message": f"✅ Removed conflicting canary block from Rollout '{name}'. Blue-green strategy is now valid.",
        }

    async def diagnose_rollout(
        self,
        name: str,
        namespace: str = "default",
        include_events: bool = True,
        include_analysis: bool = True,
        include_pods: bool = False,
    ) -> Dict[str, Any]:
        """Collect single-call diagnosis snapshot for a Rollout.

        Produces deterministic diagnosis codes for the troubleshooting-argo-rollouts skill.
        """
        self._ensure_initialized()

        try:
            rollout_obj = self._rollout_api.get(name=name, namespace=namespace)
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to fetch rollout '{name}': {e}")

        rollout_dict = _to_plain_dict(rollout_obj)
        spec = rollout_dict.get("spec") or {}
        status = rollout_dict.get("status") or {}
        metadata = rollout_dict.get("metadata") or {}
        strategy_dict = spec.get("strategy") or {}

        strategy_type = "canary" if "canary" in strategy_dict else ("bluegreen" if "blueGreen" in strategy_dict else "unknown")
        phase = status.get("phase", "Unknown")
        message = status.get("message", "") or ""
        current_step = status.get("currentStepIndex")
        canary_weight = (status.get("canary") or {}).get("weights", {}).get("canary", {}).get("weight")
        paused = bool(status.get("pauseConditions")) or bool(spec.get("paused", False))
        aborted = bool(status.get("abort", False)) or phase == "Degraded" and "abort" in message.lower()

        replicas_info = {
            "desired": spec.get("replicas", 0),
            "ready": status.get("readyReplicas", 0),
            "available": status.get("availableReplicas", 0),
            "updated": status.get("updatedReplicas", 0),
        }

        diagnosis_codes: List[str] = []

        # 1. Conflicting strategy blocks / InvalidSpec
        conditions = status.get("conditions") or []
        has_both_strategies = "canary" in strategy_dict and "blueGreen" in strategy_dict
        has_invalid_spec_cond = any(
            c.get("type") == "InvalidSpec" and c.get("status") == "True"
            for c in conditions
        )
        if has_both_strategies or has_invalid_spec_cond or "InvalidSpec" in message:
            diagnosis_codes.append("INVALID_SPEC_STRATEGY_CONFLICT")

        # 2. ProgressDeadlineExceeded
        if any(
            c.get("reason") == "ProgressDeadlineExceeded" or "ProgressDeadlineExceeded" in (c.get("message") or "")
            for c in conditions
        ) or "ProgressDeadlineExceeded" in message:
            diagnosis_codes.append("PROGRESS_DEADLINE_EXCEEDED")

        # 3. Rollout Aborted
        if aborted or any(c.get("reason") == "RolloutAborted" for c in conditions):
            diagnosis_codes.append("ROLLOUT_ABORTED")

        # 4. Paused awaiting promotion
        if paused or phase == "Paused":
            diagnosis_codes.append("PAUSED_AWAITING_PROMOTION")

        # 5. Collect latest AnalysisRuns if requested
        failing_metrics: List[Dict[str, Any]] = []
        if include_analysis:
            runs_resp = await self.list_analysis_runs(rollout_name=name, namespace=namespace, limit=5)
            for run in runs_resp.get("analysis_runs", []):
                if run.get("phase") in ("Failed", "Error", "Inconclusive"):
                    if "ANALYSIS_RUN_FAILED" not in diagnosis_codes:
                        diagnosis_codes.append("ANALYSIS_RUN_FAILED")
                    for fm in run.get("failing_metrics", []):
                        failing_metrics.append(fm)

        # 6. Collect pod statuses & warning events
        warning_events: List[Dict[str, Any]] = []
        pods_snapshot: List[Dict[str, Any]] = []
        match_labels = (spec.get("selector") or {}).get("matchLabels") or {"app": name}
        label_selector = ",".join(f"{k}={v}" for k, v in match_labels.items())

        if self._core_v1 and (include_pods or include_events):
            try:
                pod_list = self._core_v1.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=label_selector,
                )
                for pod in getattr(pod_list, "items", []) or []:
                    pod_dict = _to_plain_dict(pod)
                    pod_meta = pod_dict.get("metadata") or {}
                    pod_status = pod_dict.get("status") or {}
                    c_statuses = pod_status.get("containerStatuses") or pod_status.get("container_statuses") or []
                    waiting_reasons = []
                    restarts = 0
                    for cs in c_statuses:
                        restarts += int(cs.get("restartCount") or cs.get("restart_count") or 0)
                        state = cs.get("state") or {}
                        waiting = state.get("waiting") or {}
                        reason = waiting.get("reason")
                        if reason:
                            waiting_reasons.append(reason)
                            if reason in ("ImagePullBackOff", "ErrImagePull") and "IMAGE_PULL_BACKOFF" not in diagnosis_codes:
                                diagnosis_codes.append("IMAGE_PULL_BACKOFF")
                            if reason == "CrashLoopBackOff" and "CRASH_LOOP_BACKOFF" not in diagnosis_codes:
                                diagnosis_codes.append("CRASH_LOOP_BACKOFF")
                    if include_pods:
                        pods_snapshot.append({
                            "name": pod_meta.get("name"),
                            "phase": pod_status.get("phase"),
                            "restarts": restarts,
                            "waiting_reasons": waiting_reasons,
                        })
            except Exception as exc:
                logger.debug(f"Could not list pods for rollout diagnosis: {exc}")

        if self._core_v1 and include_events:
            try:
                ev_list = self._core_v1.list_namespaced_event(namespace=namespace)
                for ev in getattr(ev_list, "items", []) or []:
                    ev_dict = _to_plain_dict(ev)
                    ev_type = ev_dict.get("type", "Normal")
                    involved = ev_dict.get("involvedObject") or ev_dict.get("involved_object") or {}
                    involved_name = involved.get("name") or ""
                    if ev_type == "Warning" and involved_name.startswith(name):
                        reason = ev_dict.get("reason", "")
                        msg_ev = ev_dict.get("message", "")
                        warning_events.append({
                            "reason": reason,
                            "object": involved_name,
                            "message": msg_ev,
                        })
                        if reason in ("Failed", "BackOff") and ("ImagePullBackOff" in msg_ev or "ErrImagePull" in msg_ev):
                            if "IMAGE_PULL_BACKOFF" not in diagnosis_codes:
                                diagnosis_codes.append("IMAGE_PULL_BACKOFF")
                        if "CrashLoopBackOff" in msg_ev and "CRASH_LOOP_BACKOFF" not in diagnosis_codes:
                            diagnosis_codes.append("CRASH_LOOP_BACKOFF")
            except Exception as exc:
                logger.debug(f"Could not list warning events for rollout diagnosis: {exc}")

        # 7. Check ArgoCD traffic routing drift risk
        annotations = metadata.get("annotations") or {}
        canary_cfg = strategy_dict.get("canary") or {}
        if "argocd.argoproj.io/tracking-id" in annotations and canary_cfg.get("trafficRouting"):
            diagnosis_codes.append("ARGOCD_TRAFFIC_ROUTING_DRIFT")

        # 8. Replica degraded check
        if phase == "Degraded" and not diagnosis_codes:
            diagnosis_codes.append("REPLICA_DEGRADED")

        if not diagnosis_codes and phase == "Healthy":
            diagnosis_codes.append("HEALTHY")

        summary_msg = (
            f"Rollout '{name}' in namespace '{namespace}' is in phase '{phase}'"
            f" (codes: {', '.join(diagnosis_codes) if diagnosis_codes else 'NONE'})."
        )
        if message:
            summary_msg += f" Controller message: {message}"

        return {
            "name": name,
            "namespace": namespace,
            "phase": phase,
            "strategy": strategy_type,
            "summary": summary_msg,
            "diagnosis_codes": diagnosis_codes,
            "current_step": current_step,
            "canary_weight": canary_weight,
            "replicas": replicas_info,
            "conditions": [
                {
                    "type": c.get("type"),
                    "status": c.get("status"),
                    "reason": c.get("reason", ""),
                    "message": c.get("message", ""),
                }
                for c in conditions
            ],
            "failing_metrics": failing_metrics,
            "warning_events": warning_events[:15],
            "pods": pods_snapshot,
        }

    async def list_analysis_runs(
        self,
        rollout_name: str,
        namespace: str = "default",
        limit: int = 5,
    ) -> Dict[str, Any]:
        """List recent AnalysisRuns associated with a Rollout."""
        self._ensure_initialized()
        if self._analysis_run_api is None:
            return {"rollout_name": rollout_name, "namespace": namespace, "analysis_runs": []}

        try:
            resp = self._analysis_run_api.get(namespace=namespace)
            items = getattr(resp, "items", None) or (_to_plain_dict(resp).get("items") or [])
            runs = []
            for item in items:
                d = _to_plain_dict(item)
                meta = d.get("metadata") or {}
                run_name = meta.get("name", "")
                owner_refs = meta.get("ownerReferences") or meta.get("owner_references") or []
                belongs = run_name.startswith(rollout_name) or any(
                    o.get("name") == rollout_name for o in owner_refs
                )
                if not belongs:
                    continue
                st = d.get("status") or {}
                metric_results = st.get("metricResults") or []
                failing = []
                for mr in metric_results:
                    if mr.get("phase") in ("Failed", "Error", "Inconclusive"):
                        measurements = mr.get("measurements") or []
                        last_val = measurements[-1].get("value") if measurements else None
                        failing.append({
                            "metric": mr.get("name"),
                            "phase": mr.get("phase"),
                            "value": last_val,
                            "message": mr.get("message", ""),
                        })
                runs.append({
                    "name": run_name,
                    "phase": st.get("phase", "Unknown"),
                    "message": st.get("message", ""),
                    "created_at": str(meta.get("creationTimestamp") or meta.get("creation_timestamp") or ""),
                    "metric_results": [
                        {
                            "name": mr.get("name"),
                            "phase": mr.get("phase"),
                            "count": mr.get("count", 0),
                            "successful": mr.get("successful", 0),
                            "failed": mr.get("failed", 0),
                        }
                        for mr in metric_results
                    ],
                    "failing_metrics": failing,
                })
            runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
            return {
                "rollout_name": rollout_name,
                "namespace": namespace,
                "count": len(runs[:limit]),
                "analysis_runs": runs[:limit],
            }
        except Exception as e:
            logger.debug(f"Could not list AnalysisRuns for '{rollout_name}': {e}")
            return {"rollout_name": rollout_name, "namespace": namespace, "analysis_runs": [], "error": str(e)}

    async def list_analysis_templates(
        self,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        """List namespace AnalysisTemplates and ClusterAnalysisTemplates."""
        self._ensure_initialized()
        templates: List[Dict[str, Any]] = []

        if self._analysis_template_api is not None:
            try:
                ns_resp = self._analysis_template_api.get(namespace=namespace)
                ns_items = getattr(ns_resp, "items", None) or (_to_plain_dict(ns_resp).get("items") or [])
                for item in ns_items:
                    d = _to_plain_dict(item)
                    meta = d.get("metadata") or {}
                    spec = d.get("spec") or {}
                    templates.append({
                        "name": meta.get("name"),
                        "namespace": meta.get("namespace", namespace),
                        "scope": "namespace",
                        "args": [a.get("name") for a in (spec.get("args") or [])],
                        "metrics": [m.get("name") for m in (spec.get("metrics") or [])],
                    })
            except Exception as e:
                logger.debug(f"Could not list AnalysisTemplates in '{namespace}': {e}")

        if self._cluster_analysis_template_api is not None:
            try:
                cl_resp = self._cluster_analysis_template_api.get()
                cl_items = getattr(cl_resp, "items", None) or (_to_plain_dict(cl_resp).get("items") or [])
                for item in cl_items:
                    d = _to_plain_dict(item)
                    meta = d.get("metadata") or {}
                    spec = d.get("spec") or {}
                    templates.append({
                        "name": meta.get("name"),
                        "namespace": None,
                        "scope": "cluster",
                        "args": [a.get("name") for a in (spec.get("args") or [])],
                        "metrics": [m.get("name") for m in (spec.get("metrics") or [])],
                    })
            except Exception as e:
                logger.debug(f"Could not list ClusterAnalysisTemplates: {e}")

        return {
            "namespace": namespace,
            "count": len(templates),
            "templates": templates,
        }

    def get_kube_contexts(self) -> Dict[str, Any]:
        """Return available kubeconfig contexts and active context without credentials."""
        try:
            contexts, active_context = config.list_kube_config_contexts(
                config_file=self.config.kubernetes.kubeconfig
            )
            ctx_list = []
            for c in contexts or []:
                ctx_info = c.get("context") or {}
                ctx_list.append({
                    "name": c.get("name"),
                    "cluster": ctx_info.get("cluster"),
                    "namespace": ctx_info.get("namespace", "default"),
                })
            active_name = (
                self.config.kubernetes.context_name
                or (active_context.get("name") if active_context else None)
            )
            return {
                "active_context": active_name,
                "configured_context": self.config.kubernetes.context_name,
                "in_cluster": self.config.kubernetes.in_cluster,
                "contexts": ctx_list,
            }
        except Exception as e:
            return {
                "active_context": self.config.kubernetes.context_name,
                "configured_context": self.config.kubernetes.context_name,
                "in_cluster": self.config.kubernetes.in_cluster,
                "contexts": [],
                "note": f"Could not load local kubeconfig contexts: {e}",
            }

    def get_server_capabilities(self) -> Dict[str, Any]:
        """Return server capabilities, write mode, enabled toolsets, and CRD availability."""
        cluster_connected = False
        try:
            self._ensure_initialized()
            cluster_connected = self._initialized
        except Exception:
            cluster_connected = False

        return {
            "server_name": getattr(self.config, "server_name", "argo-rollout-mcp-server"),
            "server_version": getattr(self.config, "server_version", "0.2.0"),
            "allow_write": getattr(self.config, "allow_write", False),
            "toolsets": getattr(self.config, "toolsets", ["all"]),
            "cluster_connected": cluster_connected,
            "crds_installed": {
                "rollout": self._rollout_api is not None,
                "analysis_template": self._analysis_template_api is not None,
                "cluster_analysis_template": self._cluster_analysis_template_api is not None,
                "analysis_run": self._analysis_run_api is not None,
                "experiment": self._experiment_api is not None,
            },
            "prometheus_url": getattr(self.config, "prometheus_url", None),
        }

    async def convert_rollout_to_deployment_live(
        self,
        name: str,
        namespace: str = "default",
        deployment_strategy: str = "RollingUpdate",
        dry_run: bool = True,
        generator_service: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Fetch a live Rollout from the cluster and convert it back to a Deployment.

        When dry_run=True, returns the converted Deployment YAML without applying it.
        When dry_run=False, creates/patches the Deployment in the cluster via AppsV1Api.
        """
        rollout_dict = await self.get_rollout_manifest(name=name, namespace=namespace)
        if generator_service is None:
            from argo_rollout_mcp_server.services.generator_service import GeneratorService
            generator_service = GeneratorService(self.config)

        spec = (rollout_dict or {}).get("spec") or {} if isinstance(rollout_dict, dict) else {}
        workload_ref = spec.get("workloadRef") if isinstance(spec, dict) else None
        if workload_ref and "template" not in spec:
            ref_name = workload_ref.get("name") or name
            desired_replicas = int(spec.get("replicas", 1))
            base_dep_yaml = await generator_service.fetch_deployment_yaml(
                deployment_name=ref_name,
                namespace=namespace,
            )
            dep_obj = yaml.safe_load(base_dep_yaml) or {}
            dep_obj.setdefault("spec", {})["replicas"] = desired_replicas
            if deployment_strategy == "RollingUpdate":
                dep_obj["spec"]["strategy"] = {
                    "type": "RollingUpdate",
                    "rollingUpdate": {"maxSurge": "25%", "maxUnavailable": "25%"},
                }
            else:
                dep_obj["spec"]["strategy"] = {"type": "Recreate"}
            dep_yaml = yaml.dump(dep_obj, default_flow_style=False)
            removed_fields = ["spec.strategy (Argo canary/bluegreen)", "spec.workloadRef"]
            if dry_run:
                return {
                    "status": "preview",
                    "dry_run": True,
                    "name": ref_name,
                    "namespace": namespace,
                    "deployment_strategy": deployment_strategy,
                    "manifest": dep_yaml,
                    "removed_fields": removed_fields,
                    "message": (
                        f"Generated Deployment preview restoring referenced Deployment '{ref_name}' "
                        f"to {desired_replicas} replica(s) from workloadRef Rollout '{name}' (dry_run=True). "
                        "Re-run with dry_run=False to apply."
                    ),
                }
            await self.patch_workload_ref_scale_down(
                name=name,
                namespace=namespace,
                scale_down="never",
                dry_run=False,
            )
            self._ensure_initialized()
            self._apps_v1.patch_namespaced_deployment(
                name=ref_name,
                namespace=namespace,
                body=dep_obj,
            )
            return {
                "status": "success",
                "dry_run": False,
                "name": ref_name,
                "namespace": namespace,
                "deployment_strategy": deployment_strategy,
                "manifest": dep_yaml,
                "removed_fields": removed_fields,
                "message": (
                    f"Restored referenced Deployment '{ref_name}' to {desired_replicas} replica(s) "
                    f"and set Rollout '{name}' workloadRef.scaleDown='never' in namespace '{namespace}'."
                ),
            }

        rollout_yaml_str = (
            yaml.safe_dump(rollout_dict, default_flow_style=False)
            if isinstance(rollout_dict, dict)
            else rollout_dict
        )
        conv = await generator_service.convert_rollout_to_deployment(
            rollout_yaml=rollout_yaml_str,
            deployment_strategy=deployment_strategy,
        )
        if conv.get("status") == "error":
            raise ArgoRolloutError(conv.get("error", "Rollout to Deployment conversion failed"))

        dep_yaml = conv["deployment_yaml"]
        if dry_run:
            return {
                "status": "preview",
                "dry_run": True,
                "name": name,
                "namespace": namespace,
                "deployment_strategy": deployment_strategy,
                "manifest": dep_yaml,
                "removed_fields": conv.get("removed_fields", []),
                "message": f"Generated Deployment preview from Rollout '{name}' (dry_run=True). Re-run with dry_run=False to apply.",
            }

        self._ensure_initialized()
        dep_obj = yaml.safe_load(dep_yaml)
        try:
            self._apps_v1.create_namespaced_deployment(
                namespace=namespace,
                body=dep_obj,
            )
            action_taken = "created"
        except ApiException as e:
            if e.status == 409:
                self._apps_v1.patch_namespaced_deployment(
                    name=name,
                    namespace=namespace,
                    body=dep_obj,
                )
                action_taken = "patched"
            else:
                raise ArgoRolloutError(f"Failed to apply Deployment '{name}': {e}")

        return {
            "status": "success",
            "dry_run": False,
            "name": name,
            "namespace": namespace,
            "deployment_strategy": deployment_strategy,
            "manifest": dep_yaml,
            "removed_fields": conv.get("removed_fields", []),
            "message": f"Converted Rollout '{name}' to Deployment ({action_taken} in namespace '{namespace}').",
        }
