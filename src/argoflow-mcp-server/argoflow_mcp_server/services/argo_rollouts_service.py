"""Argo Rollouts service - business logic layer.

This service encapsulates all Argo Rollouts operations using the Kubernetes
Python client to interact with Rollout CRDs.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from kubernetes import client, config
from kubernetes.dynamic import DynamicClient
from kubernetes.client.rest import ApiException

from argoflow_mcp_server.config import ServerConfig
from argoflow_mcp_server.exceptions.custom import (
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


class ArgoRolloutsService:
    """Service for Argo Rollouts operations.
    
    Encapsulates all Argo Rollouts CRD interactions and business logic.
    Can be used by multiple tools without duplication.
    """
    
    def __init__(self, config_obj: ServerConfig):
        """Initialize with configuration.
        
        Args:
            config_obj: Server configuration instance
        """
        self.config = config_obj
        self._k8s_client = None
        self._dyn_client = None
        self._rollout_api = None
        self._analysis_template_api = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize Kubernetes clients.
        
        Loads kubeconfig and initializes dynamic client for CRD access.
        
        Raises:
            KubernetesOperationError: If initialization fails
        """
        if self._initialized:
            return
        
        try:
            # Load kubeconfig (try in-cluster first, then local)
            try:
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes config")
            except:
                config.load_kube_config()
                logger.info("Loaded local kubeconfig")
            
            # Create dynamic client
            self._k8s_client = client.ApiClient()
            self._dyn_client = DynamicClient(self._k8s_client)
            
            # Get Rollout API resource
            try:
                self._rollout_api = self._dyn_client.resources.get(
                    api_version="argoproj.io/v1alpha1",
                    kind="Rollout"
                )
            except Exception as e:
                raise KubernetesResourceError(
                    "Argo Rollouts CRD not found. Is Argo Rollouts installed? "
                    f"Install: kubectl create namespace argo-rollouts && "
                    f"kubectl apply -n argo-rollouts -f https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml"
                )
            
            # Get AnalysisTemplate API resource
            try:
                self._analysis_template_api = self._dyn_client.resources.get(
                    api_version="argoproj.io/v1alpha1",
                    kind="AnalysisTemplate"
                )
            except Exception as e:
                logger.warning("AnalysisTemplate CRD not available")
                self._analysis_template_api = None
            
            self._initialized = True
            logger.info("✅ Argo Rollouts Service initialized")
        
        except KubernetesResourceError:
            raise
        except Exception as e:
            raise KubernetesOperationError(f"Failed to initialize Argo Rollouts service: {e}")
    
    def _ensure_initialized(self) -> None:
        """Ensure service is initialized.
        
        Raises:
            KubernetesOperationError: If service is not initialized
        """
        if not self._initialized:
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
        **kwargs
    ) -> Dict[str, Any]:
        """Create a Rollout resource.
        
        Args:
            name: Rollout name
            namespace:Kubernetes namespace
            image: Container image
            replicas: Number of replicas
            strategy: 'canary' | 'bluegreen' | 'rolling'
            canary_steps: List of canary steps (if strategy='canary')
            **kwargs: Additional options (stable_service, canary_service, etc.)
        
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
            
            strategy_spec = {
                "canary": {
                    "canaryService": kwargs.get('canary_service', f"{name}-canary"),
                    "stableService": kwargs.get('stable_service', f"{name}-stable"),
                    "maxSurge": kwargs.get('max_surge', "25%"),
                    "maxUnavailable": kwargs.get('max_unavailable', 0),
                    "steps": canary_steps
                }
            }
        
        elif strategy == "bluegreen":
            strategy_spec = {
                "blueGreen": {
                    "activeService": kwargs.get('active_service', f"{name}-active"),
                    "previewService": kwargs.get('preview_service', f"{name}-preview"),
                    "autoPromotionEnabled": kwargs.get('auto_promotion', False)
                }
            }
        
        else:  # rolling
            strategy_spec = {
                "rolling": {
                    "maxSurge": kwargs.get('max_surge', "25%"),
                    "maxUnavailable": kwargs.get('max_unavailable', 0)
                }
            }
        
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
                        "containers": [
                            {
                                "name": name,
                                "image": image,
                                "ports": [
                                    {"containerPort": kwargs.get('port', 80)}
                                ]
                            }
                        ]
                    }
                },
                "strategy": strategy_spec
            }
        }
        
        try:
            created_rollout = self._rollout_api.create(
                body=rollout_manifest,
                namespace=namespace
            )
            
            logger.info(f"✅ Rollout created: {name} in {namespace}")
            return {
                "status": "success",
                "rollout": name,
                "namespace": namespace,
                "strategy": strategy,
                "replicas": replicas,
                "image": image,
                "message": f"Rollout {name} created successfully"
            }
        
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
            status = rollout_dict.get("status", {})
            spec = rollout_dict.get("spec", {})
            
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
            replicas = status.get("replicas", 0)
            updated_replicas = status.get("updatedReplicas", 0)
            ready_replicas = status.get("readyReplicas", 0)
            available_replicas = status.get("availableReplicas", 0)
            
            # Determine current step (for canary)
            current_step = status.get("currentStepIndex", None)
            
            # Get strategy type
            strategy_type = "canary" if "canary" in spec.get("strategy", {}) else \
                           "bluegreen" if "blueGreen" in spec.get("strategy", {}) else \
                           "rolling"
            
            return {
                "status": "success",
                "name": name,
                "namespace": namespace,
                "phase": phase,
                "message": message,
                "strategy": strategy_type,
                "current_step": current_step,
                "desired_replicas": spec.get("replicas", 0),
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
            
            # Prepare patch
            if full:
                # Full promotion
                patch = {
                    "status": {
                        "promotionFullyPromoted": True,
                        "lastTransitionTime": datetime.now().isoformat()
                    }
                }
            else:
                # Incremental promotion
                current_step = status.get("currentStepIndex", 0)
                steps = spec.get("strategy", {}).get("canary", {}).get("steps", [])
                
                if current_step >= len(steps):
                   raise RolloutPromotionError("Rollout already at final step")
                
                patch = {
                    "status": {
                        "currentStepIndex": current_step + 1,
                        "lastTransitionTime": datetime.now().isoformat()
                    }
                }
            
            # Apply patch
            promoted = self._rollout_api.patch(
                name=name,
                namespace=namespace,
                body=patch,
                content_type="application/merge-patch+json"
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
            # Patch to mark as aborted
            patch = {
                "spec": {
                    "paused": True
                },
                "status": {
                    "phase": "Degraded",
                    "aborted": True,
                    "lastTransitionTime": datetime.now().isoformat()
                }
            }
            
            aborted = self._rollout_api.patch(
                name=name,
                namespace=namespace,
                body=patch,
                content_type="application/merge-patch+json"
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
                    "paused": False
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
    
    async def update_rollout_image(
        self,
        name: str,
        new_image: str,
        namespace: str = "default",
        container_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update rollout container image.
        
        Args:
            name: Rollout name
            new_image: New container image
            namespace: Kubernetes namespace
            container_name: Container name (defaults to rollout name)
        
        Returns:
            Update result
        
        Raises:
            RolloutNotFoundError: If rollout doesn't exist
        """
        self._ensure_initialized()
        
        if container_name is None:
            container_name = name
        
        try:
            patch = {
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": container_name,
                                    "image": new_image
                                }
                            ]
                        }
                    }
                }
            }
            
            self._rollout_api.patch(
                name=name,
                namespace=namespace,
                body=patch,
                content_type="application/merge-patch+json"
            )
            
            logger.info(f"✅ Updated rollout image: {name} -> {new_image}")
            return {
                "status": "success",
                "rollout": name,
                "namespace": namespace,
                "new_image": new_image,
                "message": f"Rollout {name} image updated to {new_image}"
            }
        
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to update image: {e}")
        except Exception as e:
            raise ArgoRolloutError(f"Failed to update image: {e}")
    
    async def delete_rollout(
        self,
        name: str,
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """Delete a Rollout resource.
        
        Args:
            name: Rollout name
            namespace: Kubernetes namespace
        
        Returns:
            Deletion result
        
        Raises:
            RolloutNotFoundError: If rollout doesn't exist
        """
        self._ensure_initialized()
        
        try:
            self._rollout_api.delete(
                name=name,
                namespace=namespace
            )
            
            logger.info(f"✅ Deleted rollout: {name}")
            return {
                "status": "success",
                "rollout": name,
                "namespace": namespace,
                "message": f"Rollout {name} deleted successfully"
            }
        
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{name}' not found in namespace '{namespace}'")
            raise ArgoRolloutError(f"Failed to delete rollout: {e}")
        except Exception as e:
            raise ArgoRolloutError(f"Failed to delete rollout: {e}")
    
    async def list_rollouts(
        self,
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """List all rollouts in a namespace.
        
        Args:
            namespace: Kubernetes namespace
        
        Returns:
            List of rollouts with basic info
        """
        self._ensure_initialized()
        
        try:
            # Use get() to list all rollouts in namespace (DynamicClient API)
            list_result = self._rollout_api.get(namespace=namespace)
            
            rollouts = []
            # list_result is a dict with 'items' list
            items = list_result.get('items', [])
            for item in items:
                metadata = item.get("metadata", {})
                spec = item.get("spec", {})
                status = item.get("status", {})
                
                # Determine strategy
                strategy = "canary" if "canary" in spec.get("strategy", {}) else \
                          "bluegreen" if "blueGreen" in spec.get("strategy", {}) else \
                          "rolling"
                
                # Extract image
                containers = spec.get("template", {}).get("spec", {}).get("containers", [])
                image = containers[0].get("image", "") if containers else ""
                
                rollouts.append({
                    "name": metadata.get("name"),
                    "namespace": namespace,
                    "strategy": strategy,
                    "desired_replicas": spec.get("replicas", 0),
                    "current_replicas": status.get("replicas", 0),
                    "ready_replicas": status.get("readyReplicas", 0),
                    "phase": status.get("phase", "Unknown"),
                    "created": metadata.get("creationTimestamp"),
                    "image": image
                })
            
            return {
                "status": "success",
                "namespace": namespace,
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
        metrics: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Configure analysis template for automated metrics validation.
        
        Args:
            rollout_name: Name of rollout to configure
            template_name: Name of analysis template
            namespace: Kubernetes namespace
            metrics: List of metric configurations
        
        Returns:
            Configuration result
        
        Raises:
            AnalysisTemplateError: If configuration fails
        """
        self._ensure_initialized()
        
        if not self._analysis_template_api:
            raise AnalysisTemplateError("AnalysisTemplate CRD not available")
        
        # Default metrics if not provided
        if metrics is None:
            metrics = [
                {
                    "name": "success-rate",
                    "successCriteria": ">= 99",
                    "provider": {
                        "prometheus": {
                            "address": "http://prometheus:9090",
                            "query": 'sum(rate(http_requests_total{status=~"2.*"}[5m])) / sum(rate(http_requests_total[5m])) * 100'
                        }
                    }
                }
            ]
        
        # Create AnalysisTemplate
        analysis_template = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "AnalysisTemplate",
            "metadata": {
                "name": template_name,
                "namespace": namespace
            },
            "spec": {
                "metrics": metrics
            }
        }
        
        try:
            # Create or update template
            try:
                self._analysis_template_api.create(
                    body=analysis_template,
                    namespace=namespace
                )
            except ApiException as e:
                if e.status == 409:  # Already exists, update it
                    self._analysis_template_api.patch(
                        name=template_name,
                        namespace=namespace,
                        body=analysis_template,
                        content_type="application/merge-patch+json"
                    )
            
            # Update rollout to reference this template
            rollout = self._rollout_api.get(name=rollout_name, namespace=namespace)
            
            patch = {
                "spec": {
                    "strategy": {
                        "canary": {
                            "analysis": {
                                "templates": [
                                    {
                                        "templateName": template_name
                                    }
                                ]
                            }
                        }
                    }
                }
            }
            
            self._rollout_api.patch(
                name=rollout_name,
                namespace=namespace,
                body=patch,
                content_type="application/merge-patch+json"
            )
            
            logger.info(f"✅ Analysis template {template_name} configured")
            return {
                "status": "success",
                "template_name": template_name,
                "rollout": rollout_name,
                "namespace": namespace,
                "message": f"Analysis template configured for rollout {rollout_name}"
            }
        
        except ApiException as e:
            if e.status == 404:
                raise RolloutNotFoundError(f"Rollout '{rollout_name}' not found")
            raise AnalysisTemplateError(f"Failed to configure analysis: {e}")
        except Exception as e:
            raise AnalysisTemplateError(f"Failed to configure analysis: {e}")
    
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
