"""Generator service for converting Deployments to Rollouts.

This service provides the bridge between standard Kubernetes Deployments
(created by ArgoCD or other CI/CD tools) and Argo Rollouts for progressive delivery.
"""

import yaml
import logging
from typing import Dict, Any, List, Optional
from kubernetes import client
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


class GeneratorService:
    """Service for generating Rollout resources from Deployments."""
    
    def __init__(self, config=None):
        """Initialize generator service.
        
        Args:
            config: Optional server configuration
        """
        self.config = config
        self._apps_v1 = None
    
    def _ensure_k8s_client(self):
        """Lazily initialize Kubernetes AppsV1 client."""
        if self._apps_v1 is None:
            self._apps_v1 = client.AppsV1Api()
    
    async def fetch_deployment_yaml(
        self,
        deployment_name: str,
        namespace: str = "default"
    ) -> str:
        """Fetch a Kubernetes Deployment and return it as YAML string.
        
        This is a shared utility used by validate_deployment_ready
        and convert_deployment_to_rollout to auto-fetch deployments from the cluster
        instead of requiring the user to provide raw YAML.
        
        Args:
            deployment_name: Name of the Deployment
            namespace: Kubernetes namespace
            
        Returns:
            Deployment YAML as a string
            
        Raises:
            ApiException: If the Deployment is not found or API fails
        """
        self._ensure_k8s_client()
        
        try:
            deployment = self._apps_v1.read_namespaced_deployment(
                name=deployment_name,
                namespace=namespace
            )
            
            # Convert to dict, stripping managed fields and status for cleanliness
            dep_dict = deployment.to_dict()
            
            # Strip the entire status subresource — it is read-only and must not
            # appear in a declarative manifest sent back to the user or applied.
            dep_dict.pop("status", None)

            # Clean up K8s client artifacts that aren't useful for conversion.
            # Note: the Python client returns snake_case keys from to_dict().
            metadata = dep_dict.get("metadata", {})

            _STRIP_META_KEYS = {
                "managed_fields", "resource_version", "uid",
                "generation", "creation_timestamp",
            }
            for key in _STRIP_META_KEYS:
                metadata.pop(key, None)

            # Strip controller-managed annotations that must not appear in a manifest
            _CONTROLLER_ANNOTATIONS = {
                "deployment.kubernetes.io/revision",
                "rollout.argoproj.io/revision",
                "kubectl.kubernetes.io/last-applied-configuration",
            }
            annotations = metadata.get("annotations") or {}
            metadata["annotations"] = {
                k: v for k, v in annotations.items()
                if k not in _CONTROLLER_ANNOTATIONS
            }
            if not metadata["annotations"]:
                metadata.pop("annotations", None)
            
            # Remove None values recursively for cleaner YAML
            dep_dict = self._clean_none_values(dep_dict)
            
            # Convert snake_case keys back to camelCase for standard K8s YAML
            dep_dict = self._to_camel_case_keys(dep_dict)

            # After camelCase conversion, also ensure creationTimestamp is gone
            # (it may survive through the mapping as-is if not in CAMEL_MAP)
            dep_dict.get("metadata", {}).pop("creationTimestamp", None)

            logger.info(f"✅ Fetched Deployment '{deployment_name}' from namespace '{namespace}'")
            return yaml.dump(dep_dict, default_flow_style=False)
            
        except ApiException as e:
            if e.status == 404:
                raise ApiException(
                    status=404,
                    reason=f"Deployment '{deployment_name}' not found in namespace '{namespace}'"
                )
            raise
    
    def _clean_none_values(self, d):
        """Recursively remove None values from a dict."""
        if isinstance(d, dict):
            return {k: self._clean_none_values(v) for k, v in d.items() 
                    if v is not None}
        elif isinstance(d, list):
            return [self._clean_none_values(item) for item in d if item is not None]
        return d
    
    def _to_camel_case_keys(self, obj):
        """Convert snake_case dict keys to camelCase for K8s YAML compatibility."""
        # Mapping of common snake_case -> camelCase for K8s API
        CAMEL_MAP = {
            "api_version": "apiVersion",
            "match_labels": "matchLabels",
            "container_port": "containerPort",
            "readiness_probe": "readinessProbe",
            "liveness_probe": "livenessProbe",
            "startup_probe": "startupProbe",
            "initial_delay_seconds": "initialDelaySeconds",
            "period_seconds": "periodSeconds",
            "timeout_seconds": "timeoutSeconds",
            "success_threshold": "successThreshold",
            "failure_threshold": "failureThreshold",
            "http_get": "httpGet",
            "tcp_socket": "tcpSocket",
            "grpc": "grpc",
            "exec": "exec",
            "host_port": "hostPort",
            "host_ip": "hostIP",
            "image_pull_policy": "imagePullPolicy",
            "termination_message_path": "terminationMessagePath",
            "termination_message_policy": "terminationMessagePolicy",
            "dns_policy": "dnsPolicy",
            "restart_policy": "restartPolicy",
            "scheduler_name": "schedulerName",
            "termination_grace_period_seconds": "terminationGracePeriodSeconds",
            "service_account": "serviceAccount",
            "service_account_name": "serviceAccountName",
            "node_selector": "nodeSelector",
            "security_context": "securityContext",
            "run_as_user": "runAsUser",
            "run_as_group": "runAsGroup",
            "run_as_non_root": "runAsNonRoot",
            "fs_group": "fsGroup",
            "revision_history_limit": "revisionHistoryLimit",
            "progress_deadline_seconds": "progressDeadlineSeconds",
            "max_surge": "maxSurge",
            "max_unavailable": "maxUnavailable",
            "rolling_update": "rollingUpdate",
            "match_expressions": "matchExpressions",
            "claim_name": "claimName",
            "config_map": "configMap",
            "mount_path": "mountPath",
            "sub_path": "subPath",
            "read_only": "readOnly",
            "volume_mounts": "volumeMounts",
            "env_from": "envFrom",
            "value_from": "valueFrom",
            "config_map_ref": "configMapRef",
            "secret_ref": "secretRef",
            "config_map_key_ref": "configMapKeyRef",
            "secret_key_ref": "secretKeyRef",
            "field_ref": "fieldRef",
            "field_path": "fieldPath",
            "resource_field_ref": "resourceFieldRef",
        }
        
        if isinstance(obj, dict):
            return {
                CAMEL_MAP.get(k, k): self._to_camel_case_keys(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [self._to_camel_case_keys(item) for item in obj]
        return obj
    
    async def convert_deployment_to_rollout(
        self,
        deployment_yaml: str,
        strategy: str = "canary",
        traefik_service_name: Optional[str] = None,
        gateway_api_config: Optional[Dict[str, Any]] = None,
        migration_mode: str = "direct",
        scale_down: str = "onsuccess",
        canary_steps: Optional[List[Dict[str, Any]]] = None,
        bluegreen_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Convert a Kubernetes Deployment to an Argo Rollout.
        
        Args:
            deployment_yaml: Deployment YAML as string
            strategy: Rollout strategy ("canary" or "bluegreen")
            traefik_service_name: TraefikService name for native routing
            migration_mode: "direct" or "workload_ref"
            scale_down: workloadRef scale-down policy
            canary_steps: Custom canary steps (if None, uses default progressive steps).
                Supports all step types: setWeight, pause, setCanaryScale, analysis,
                experiment, plugin. Note: setHeaderRoute/setMirrorRoute are Istio-only.
            bluegreen_options: Optional Blue-Green overrides, e.g.:
                {
                    "autoPromotionEnabled": True,
                    "autoPromotionSeconds": 120,
                    "scaleDownDelaySeconds": 30,
                    "previewReplicaCount": 1,
                    "prePromotionAnalysis": {...},
                    "postPromotionAnalysis": {...},
                    "antiAffinity": {...},
                    "activeMetadata": {...},
                    "previewMetadata": {...}
                }
        
        Returns:
            Dict containing:
                - status: "success" or "error"
                - app_name: Application name
                - strategy: Selected strategy
                - rollout_yaml: Generated Rollout YAML
                - error: Error message (if failed)
        
        Raises:
            ValueError: If input is invalid
        """
        try:
            # Parse input YAML
            deployment = yaml.safe_load(deployment_yaml)
            
            # Validate it's a Deployment
            if deployment.get("kind") != "Deployment":
                raise ValueError(f"Input must be a Deployment, got: {deployment.get('kind')}")
            
            app_name = deployment.get("metadata", {}).get("name", "unknown")
            
            # --- Sanitise metadata: keep only declarative fields ---
            # Server-assigned fields (resourceVersion, uid, creationTimestamp, generation)
            # and controller-managed annotations must not appear in a stored manifest.
            _CONTROLLER_ANNOTATIONS = {
                "deployment.kubernetes.io/revision",
                "rollout.argoproj.io/revision",
                "kubectl.kubernetes.io/last-applied-configuration",
            }
            raw_meta = deployment.get("metadata", {})
            clean_annotations = {
                k: v
                for k, v in (raw_meta.get("annotations") or {}).items()
                if k not in _CONTROLLER_ANNOTATIONS
            }
            clean_meta: Dict[str, Any] = {
                "name": raw_meta["name"],
            }
            if raw_meta.get("namespace"):
                clean_meta["namespace"] = raw_meta["namespace"]
            if raw_meta.get("labels"):
                clean_meta["labels"] = raw_meta["labels"]
            if clean_annotations:
                clean_meta["annotations"] = clean_annotations

            # Create Rollout from Deployment
            rollout = {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "Rollout",
                "metadata": clean_meta,
                "spec": {
                    "replicas": deployment["spec"]["replicas"],
                    "selector": deployment["spec"]["selector"],
                    "template": deployment["spec"]["template"]
                }
            }
            
            # Add strategy
            if strategy == "canary":
                # Use custom steps if provided, otherwise defaults
                steps = canary_steps if canary_steps else [
                    {"setWeight": 5},
                    {"pause": {}},
                    {"setWeight": 10},
                    {"pause": {}},
                    {"setWeight": 25},
                    {"pause": {}},
                    {"setWeight": 50},
                    {"pause": {}},
                ]
                
                canary_spec = {
                    "canaryService": f"{app_name}-canary",
                    "stableService": f"{app_name}-stable",
                    "steps": steps
                }
                
                # Add traffic routing: TraefikService or Gateway API plugin
                if traefik_service_name:
                    canary_spec["trafficRouting"] = {
                        "traefik": {
                            "weightedTraefikServiceName": traefik_service_name
                        }
                    }
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
                    canary_spec["trafficRouting"] = {
                        "plugins": {
                            "argoproj-labs/gatewayAPI": plugin_config
                        }
                    }
                
                rollout["spec"]["strategy"] = {"canary": canary_spec}
            elif strategy == "bluegreen":
                bluegreen_spec: Dict[str, Any] = {
                    "activeService": f"{app_name}-active",
                    "previewService": f"{app_name}-preview",
                    "autoPromotionEnabled": False
                }
                
                # Apply blue-green overrides if provided
                if bluegreen_options:
                    for key in [
                        "autoPromotionEnabled", "autoPromotionSeconds",
                        "scaleDownDelaySeconds", "abortScaleDownDelaySeconds",
                        "previewReplicaCount", "prePromotionAnalysis",
                        "postPromotionAnalysis", "antiAffinity",
                        "activeMetadata", "previewMetadata"
                    ]:
                        if key in bluegreen_options:
                            bluegreen_spec[key] = bluegreen_options[key]
                
                rollout["spec"]["strategy"] = {"blueGreen": bluegreen_spec}
            else:
                raise ValueError(f"Invalid strategy: {strategy}. Must be 'canary' or 'bluegreen'")
            
            # Handle workloadRef migration mode
            if migration_mode == "workload_ref":
                rollout["spec"]["workloadRef"] = {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": app_name,
                    "scaleDown": scale_down
                }
                # Remove template — workloadRef replaces it
                rollout["spec"].pop("template", None)
                rollout["spec"].pop("selector", None)
            
            # Convert to YAML
            rollout_yaml = yaml.dump(rollout, default_flow_style=False)
            
            return {
                "status": "success",
                "app_name": app_name,
                "strategy": strategy,
                "rollout_yaml": rollout_yaml
            }
            
        except yaml.YAMLError as e:
            return {
                "status": "error",
                "error": f"Invalid YAML: {str(e)}"
            }
        except ValueError as e:
            return {
                "status": "error",
                "error": str(e)
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Conversion failed: {str(e)}"
            }
    
    
    def get_analysis_metrics_from_thresholds(
        self,
        service_name: str,
        prometheus_url: str,
        error_rate_threshold: float = 5.0,
        latency_p99_threshold: float = 2000.0,
        latency_p95_threshold: float = 1000.0,
    ) -> List[Dict[str, Any]]:
        """Build Prometheus metrics list from threshold parameters.
        
        Used by both generate_yaml and execute modes of argo_configure_analysis_template.
        
        Args:
            service_name: Service name for Prometheus job selector
            prometheus_url: Prometheus server URL
            error_rate_threshold: Max error rate (%)
            latency_p99_threshold: Max P99 latency (ms)
            latency_p95_threshold: Max P95 latency (ms)
        
        Returns:
            List of metric spec dicts for AnalysisTemplate
        """
        error_rate_decimal = error_rate_threshold / 100.0
        latency_p99_sec = latency_p99_threshold / 1000.0
        latency_p95_sec = latency_p95_threshold / 1000.0
        return [
            {
                "name": "error-rate",
                "interval": "60s",
                "initialDelay": "60s",
                "failureLimit": 2,
                "provider": {
                    "prometheus": {
                        "address": prometheus_url,
                        "query": (
                            f'sum(rate(http_requests_total{{job="{service_name}",'
                            f'status=~"5.."}}[5m])) / '
                            f'sum(rate(http_requests_total{{job="{service_name}"}}[5m]))'
                        )
                    }
                },
                "successCondition": f"result[0] < {error_rate_decimal}"
            },
            {
                "name": "latency-p99",
                "interval": "60s",
                "initialDelay": "60s",
                "failureLimit": 2,
                "provider": {
                    "prometheus": {
                        "address": prometheus_url,
                        "query": (
                            f'histogram_quantile(0.99, '
                            f'sum(rate(http_request_duration_seconds_bucket{{'
                            f'job="{service_name}"}}[5m])) by (le))'
                        )
                    }
                },
                "successCondition": f"result[0] < {latency_p99_sec}"
            },
            {
                "name": "latency-p95",
                "interval": "60s",
                "initialDelay": "60s",
                "failureLimit": 2,
                "provider": {
                    "prometheus": {
                        "address": prometheus_url,
                        "query": (
                            f'histogram_quantile(0.95, '
                            f'sum(rate(http_request_duration_seconds_bucket{{'
                            f'job="{service_name}"}}[5m])) by (le))'
                        )
                    }
                },
                "successCondition": f"result[0] < {latency_p95_sec}"
            }
        ]

    async def create_analysis_template_for_rollout(
        self,
        service_name: str,
        prometheus_url: str,
        namespace: str = "default",
        error_rate_threshold: float = 5.0,
        latency_p99_threshold: float = 2000.0,
        latency_p95_threshold: float = 1000.0,
        scope: str = "namespace",
    ) -> Dict[str, Any]:
        """Create an Argo AnalysisTemplate or ClusterAnalysisTemplate for automated canary health validation.
        
        Args:
            service_name: Service name to monitor
            prometheus_url: Prometheus server URL
            namespace: Kubernetes namespace (ignored when scope='cluster')
            error_rate_threshold: Maximum acceptable error rate percentage
            latency_p99_threshold: Maximum acceptable P99 latency in milliseconds
            latency_p95_threshold: Maximum acceptable P95 latency in milliseconds
            scope: 'namespace' for AnalysisTemplate, 'cluster' for ClusterAnalysisTemplate
        
        Returns:
            Dict containing:
                - status: "success" or "error"
                - template_name: Generated template name
                - namespace: Kubernetes namespace (or None for cluster scope)
                - metrics: List of metric names
                - thresholds: Dict of threshold values
                - template_yaml: Generated YAML
                - error: Error message (if failed)
        """
        try:
            metrics = self.get_analysis_metrics_from_thresholds(
                service_name=service_name,
                prometheus_url=prometheus_url,
                error_rate_threshold=error_rate_threshold,
                latency_p99_threshold=latency_p99_threshold,
                latency_p95_threshold=latency_p95_threshold,
            )
            template_name = f"{service_name}-analysis"
            if scope == "cluster":
                template = {
                    "apiVersion": "argoproj.io/v1alpha1",
                    "kind": "ClusterAnalysisTemplate",
                    "metadata": {"name": template_name},
                    "spec": {"metrics": metrics},
                }
            else:
                template = {
                    "apiVersion": "argoproj.io/v1alpha1",
                    "kind": "AnalysisTemplate",
                    "metadata": {
                        "name": template_name,
                        "namespace": namespace,
                    },
                    "spec": {"metrics": metrics},
                }
            
            template_yaml = yaml.dump(template, default_flow_style=False)
            
            return {
                "status": "success",
                "template_name": f"{service_name}-analysis",
                "namespace": None if scope == "cluster" else namespace,
                "scope": scope,
                "metrics": ["error-rate", "latency-p99", "latency-p95"],
                "thresholds": {
                    "error_rate_pct": error_rate_threshold,
                    "latency_p99_ms": latency_p99_threshold,
                    "latency_p95_ms": latency_p95_threshold
                },
                "template_yaml": template_yaml
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to create AnalysisTemplate: {str(e)}"
            }
    
    async def validate_deployment_ready(
        self,
        deployment_yaml: str,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        """Validate if a Deployment is ready to be converted to a Rollout.
        
        Performs a unified pre-flight check combining:
        - DEPLOYMENT CHECKS: Structural validation (selector, template, containers,
          replicas, resource limits, probes, preStop, terminationGracePeriodSeconds)
        - SERVICE CHECKS: Fetches the matching Service, validates selector compatibility
          (no pod-template-hash or rollouts-pod-template-hash)
        
        Separates checks into:
        - ISSUES (blocking): Structural problems that prevent Rollout conversion
          (wrong kind, missing containers, missing selector/template, or Service
          selector uses pod-template-hash)
        - WARNINGS (non-blocking): Kubernetes best practices that improve reliability
          (replicas, resource limits, probes) but are NOT Argo Rollouts requirements
        
        Args:
            deployment_yaml: Deployment YAML as string
            namespace: Kubernetes namespace (used for Service discovery when validating
                selector compatibility)
        
        Returns:
            Dict containing:
                - ready: Boolean indicating if ready for conversion
                - score: Readiness score (0-100)
                - app_name: Application name
                - namespace: Kubernetes namespace
                - issues: List of blocking problems (structural + routing)
                - warnings: List of best-practice recommendations (non-blocking)
                - recommendations: List of improvements
                - deployment_checks: Summary of Deployment validation
                - service_checks: Summary of Service selector compatibility
                - error: Error message (if validation failed)
        """
        try:
            deployment = yaml.safe_load(deployment_yaml)
            
            if deployment.get("kind") != "Deployment":
                raise ValueError(f"Input must be a Deployment, got: {deployment.get('kind')}")
            
            app_name = deployment.get("metadata", {}).get("name", "unknown")
            issues = []       # Blocking: structural problems
            warnings = []     # Non-blocking: best practices
            recommendations = []
            score = 100
            
            # ─── BLOCKING CHECKS (Argo Rollouts prerequisites) ───
            
            # Check spec exists
            spec = deployment.get("spec", {})
            if not spec:
                issues.append("Deployment has no spec")
                score -= 50
            
            # Check selector exists
            if not spec.get("selector"):
                issues.append("Deployment has no selector (required for Rollout)")
                score -= 25
            
            # Check template exists
            template = spec.get("template", {})
            if not template or not template.get("spec"):
                issues.append("Deployment has no pod template spec")
                score -= 25
            
            # Check containers exist
            containers = template.get("spec", {}).get("containers", [])
            if not containers:
                issues.append("No containers defined in deployment")
                score -= 25
                match_labels = spec.get("selector", {}).get("matchLabels") or {}
                service_checks = await self._run_service_checks(
                    match_labels, namespace, issues, warnings
                )
                return {
                    "ready": False,
                    "score": max(0, score),
                    "app_name": app_name,
                    "namespace": namespace,
                    "replicas": spec.get("replicas", 1),
                    "containers_count": 0,
                    "issues": issues,
                    "warnings": warnings,
                    "recommendations": ["Define at least one container"],
                    "deployment_checks": {"replicas": spec.get("replicas", 1), "containers_count": 0},
                    "service_checks": service_checks,
                }
            
            # ─── NON-BLOCKING CHECKS (K8s best practices, NOT Argo requirements) ───
            
            replicas = spec.get("replicas", 1)
            
            # Replica count (WARNING, not blocking — Argo Rollouts works fine with 1)
            if replicas < 2:
                warnings.append(
                    f"Only {replicas} replica(s) — consider 2+ for HA. "
                    f"Argo Rollouts works with any replica count, but canary "
                    f"traffic splitting is more meaningful with multiple replicas."
                )
                score -= 10
            elif replicas < 3:
                warnings.append("2 replicas — consider 3+ for production safety")
                score -= 5
            
            # Validate each container
            for container in containers:
                container_name = container.get("name", "unnamed")
                
                # Resource limits (WARNING — Argo Rollouts doesn't check this)
                resources = container.get("resources", {})
                limits = resources.get("limits", {})
                requests = resources.get("requests", {})
                
                if not limits.get("memory") or not limits.get("cpu"):
                    warnings.append(
                        f"Container '{container_name}' missing resource limits — "
                        f"recommended for stable scheduling and HPA"
                    )
                    score -= 5
                
                if not requests.get("memory") or not requests.get("cpu"):
                    warnings.append(
                        f"Container '{container_name}' missing resource requests — "
                        f"required for HPA and proper pod scheduling"
                    )
                    score -= 5
                
                # Probes (WARNING — improves rollout health detection)
                if not container.get("readinessProbe"):
                    warnings.append(
                        f"Container '{container_name}' missing readiness probe — "
                        f"Argo Rollouts uses readiness to determine pod health during canary"
                    )
                    score -= 5
                if not container.get("livenessProbe"):
                    warnings.append(
                        f"Container '{container_name}' missing liveness probe"
                    )
                    score -= 3

                # lifecycle.preStop (WARNING — improves connection draining)
                lifecycle = container.get("lifecycle", {})
                pre_stop = lifecycle.get("preStop") if isinstance(lifecycle, dict) else None
                if not pre_stop:
                    warnings.append(
                        f"Container '{container_name}' missing preStop hook — "
                        "recommended for graceful connection draining during rollout"
                    )
                    score -= 2

            # terminationGracePeriodSeconds (WARNING — pod spec level)
            pod_spec = template.get("spec", {})
            term_grace = pod_spec.get("terminationGracePeriodSeconds")
            if term_grace is None or (isinstance(term_grace, (int, float)) and term_grace < 30):
                warnings.append(
                    "terminationGracePeriodSeconds not set or < 30 — "
                    "recommend 30+ for graceful shutdown during rollout"
                )
                score -= 2

            # maxUnavailable (WARNING — strategy)
            strategy = spec.get("strategy", {}) or {}
            ru = strategy.get("rollingUpdate", {}) or {}
            max_unavail = ru.get("maxUnavailable")
            if max_unavail is not None and max_unavail != 0 and str(max_unavail) != "0%":
                warnings.append(
                    f"maxUnavailable is {max_unavail} — for zero-downtime, consider maxUnavailable: 0"
                )
                score -= 3
            
            # ─── RECOMMENDATIONS ───
            
            if issues:
                recommendations.append("Fix all blocking issues before converting to Rollout")
            if not any(c.get("resources", {}).get("limits") for c in containers):
                recommendations.append("Set resource limits for predictable scheduling")
            if not any(c.get("resources", {}).get("requests") for c in containers):
                recommendations.append("Set resource requests for HPA and scheduling")
            if not any(c.get("readinessProbe") for c in containers):
                recommendations.append(
                    "Add readiness probe — Argo Rollouts checks readiness to "
                    "determine if canary pods are healthy before promoting"
                )
            if not any(c.get("livenessProbe") for c in containers):
                recommendations.append("Add liveness probe for automatic recovery")
            if replicas < 3:
                recommendations.append("Increase replicas to 3+ for high availability")
            if not any(
                c.get("lifecycle", {}).get("preStop")
                for c in containers
                if isinstance(c.get("lifecycle"), dict)
            ):
                recommendations.append(
                    "Add preStop hook for connection draining — e.g. sleep 5 before SIGTERM"
                )
            if pod_spec.get("terminationGracePeriodSeconds") is None:
                recommendations.append(
                    "Set terminationGracePeriodSeconds to 30+ for graceful shutdown"
                )
            if ru.get("maxUnavailable") not in (0, "0", "0%"):
                recommendations.append(
                    "Set maxUnavailable: 0 for zero-downtime rolling updates"
                )
            recommendations.append(
                "Consider adding a PodDisruptionBudget (PDB) for the Deployment — "
                "check manually; this tool does not validate PDB."
            )
            
            # ─── SERVICE CHECKS (selector compatibility for Rollout migration) ───
            match_labels = spec.get("selector", {}).get("matchLabels") or {}
            service_checks = await self._run_service_checks(
                match_labels, namespace, issues, warnings
            )
            
            # ready = no BLOCKING issues (warnings don't block)
            ready = len(issues) == 0
            final_score = max(0, score)
            
            return {
                "ready": ready,
                "score": final_score,
                "app_name": app_name,
                "namespace": namespace,
                "replicas": replicas,
                "containers_count": len(containers),
                "issues": issues,
                "warnings": warnings,
                "recommendations": recommendations,
                "deployment_checks": {
                    "replicas": replicas,
                    "containers_count": len(containers),
                },
                "service_checks": service_checks,
            }
            
        except yaml.YAMLError as e:
            return {
                "status": "error",
                "error": f"Invalid YAML: {str(e)}"
            }
        except ValueError as e:
            return {
                "status": "error",
                "error": str(e)
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Validation failed: {str(e)}"
            }

    async def _run_service_checks(
        self,
        match_labels: Dict[str, str],
        namespace: str,
        issues: List[str],
        warnings: List[str],
    ) -> Dict[str, Any]:
        """Run Service selector compatibility checks for migration readiness.
        
        Fetches the matching Service, validates no pod-template-hash in selectors,
        and returns service_checks dict. Mutates issues and warnings in place.
        """
        service_checks: Dict[str, Any] = {
            "service_found": False,
            "service_name": None,
            "selector_ok": None,
        }
        svc = await self.discover_service_for_deployment(
            match_labels=match_labels,
            namespace=namespace,
        )
        if svc:
            service_checks["service_found"] = True
            service_checks["service_name"] = svc.metadata.name
            svc_selector = svc.spec.selector or {}
            bad_keys = {"pod-template-hash", "rollouts-pod-template-hash"}
            has_bad_selector = any(k in bad_keys for k in svc_selector)
            if has_bad_selector:
                for k in svc_selector:
                    if k in bad_keys:
                        issues.append(
                            f"Service '{svc.metadata.name}' selector uses '{k}'. "
                            "Remove it for Rollout compatibility; use stable labels only."
                        )
                service_checks["selector_ok"] = False
            else:
                selector_matches = all(
                    match_labels.get(k) == v for k, v in svc_selector.items()
                )
                service_checks["selector_ok"] = selector_matches
                if not selector_matches:
                    warnings.append(
                        f"Service '{svc.metadata.name}' selector may not fully match "
                        "Deployment matchLabels."
                    )
        else:
            warnings.append(
                f"No Service found matching Deployment selector {match_labels}. "
                "create_stable_canary_services will create the required Services."
            )
        return service_checks

    async def discover_service_for_deployment(
        self,
        match_labels: Dict[str, str],
        namespace: str = "default",
    ) -> Optional[Any]:
        """Discover the existing K8s Service that routes traffic to a Deployment.

        Searches for Services in the namespace whose ``spec.selector`` is a
        subset of (or equal to) the Deployment's ``spec.selector.matchLabels``.
        Returns the first match, or None if nothing is found.

        Args:
            match_labels: Deployment's ``spec.selector.matchLabels`` dict
            namespace: Kubernetes namespace to search

        Returns:
            kubernetes.client.V1Service object or None
        """
        from kubernetes import client as k8s_client, config as k8s_config

        try:
            k8s_config.load_incluster_config()
        except Exception:
            k8s_config.load_kube_config()

        core_v1 = k8s_client.CoreV1Api()
        services = core_v1.list_namespaced_service(namespace=namespace).items

        for svc in services:
            svc_selector = svc.spec.selector or {}
            # The service selector must be a non-empty subset of the deployment matchLabels
            if svc_selector and all(
                match_labels.get(k) == v for k, v in svc_selector.items()
            ):
                return svc

        return None

    async def create_rollout_services_cloned(
        self,
        original_service: Any,
        app_name: str,
        namespace: str = "default",
        strategy: str = "canary",
        pod_template: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Clone an existing K8s Service into the stable + canary (or active + preview) pair.

        All port definitions, selectors, labels and annotations from the original
        service are preserved faithfully in each clone.  Only the ``name`` field
        is changed to ``{app_name}-stable`` / ``{app_name}-canary`` etc.

        When the original Service uses a **named** ``targetPort`` (e.g. ``"http"``),
        Kubernetes resolves the name by looking it up in the Pod's container port
        definitions.  If the Rollout's pod template later loses its ``ports`` array
        (e.g. because ArgoCD/Helm overwrites the manifest), the lookup fails and
        traffic routing breaks.  To prevent this, pass the Deployment's
        ``pod_template`` (``spec.template.spec``) so that named ports are resolved
        to their numeric ``containerPort`` values **at Service creation time**.

        Args:
            original_service: V1Service object returned by discover_service_for_deployment
            app_name: Application name (used to construct new service names)
            namespace: Target namespace
            strategy: "canary" (→ stable/canary) or "bluegreen" (→ active/preview)
            pod_template: Optional Deployment pod template spec
                (``deployment["spec"]["template"]["spec"]``).  Used to resolve
                named ``targetPort`` values to numeric ``containerPort`` values.

        Returns:
            Dict with keys: services_created (list), services_already_existed (list),
            discovered_ports (list of port numbers), source_service (str)
        """
        from kubernetes import client as k8s_client
        from kubernetes.client.rest import ApiException as K8sApiException

        if strategy == "canary":
            suffixes = ["stable", "canary"]
        else:
            suffixes = ["active", "preview"]

        # ── Resolve named targetPort → numeric containerPort ──
        # Build a name→containerPort map from the pod template so that named
        # targetPort strings (e.g. "http") are replaced with the real port
        # number (e.g. 80).  This makes the cloned Services resilient to
        # ArgoCD/Helm overwriting the Rollout template and dropping ports.
        named_port_map: Dict[str, int] = {}
        if pod_template:
            for container in pod_template.get("containers", []):
                for port_def in container.get("ports", []):
                    port_name = port_def.get("name")
                    container_port = port_def.get("containerPort")
                    if port_name and container_port is not None:
                        named_port_map[port_name] = int(container_port)
            if named_port_map:
                logger.info(
                    f"Named-port resolution map from pod template: {named_port_map}"
                )

        def _resolve_target_port(p):
            """Return a numeric target_port, resolving named ports when possible."""
            tp = p.target_port
            if isinstance(tp, str):
                # Named port — try to resolve via pod template
                if tp in named_port_map:
                    resolved = named_port_map[tp]
                    logger.info(
                        f"Resolved named targetPort '{tp}' → {resolved} "
                        f"(from pod template)"
                    )
                    return resolved
                # Fallback: use the service port number as a best-effort guess
                logger.warning(
                    f"Named targetPort '{tp}' not found in pod template; "
                    f"falling back to service port {p.port}"
                )
                return p.port
            return tp

        # Build cloned port specs from the original service (preserves all port defs)
        orig_ports = original_service.spec.ports or []
        cloned_ports = [
            k8s_client.V1ServicePort(
                name=p.name,
                port=p.port,
                target_port=_resolve_target_port(p),
                protocol=p.protocol or "TCP",
                node_port=None,  # NodePort must not be copied — K8s assigns fresh ones
            )
            for p in orig_ports
        ]

        # Strip runtime-injected selector labels:
        # - rollouts-pod-template-hash: added by Argo Rollouts at runtime to pin a
        #   service to a specific ReplicaSet. Must NEVER be baked into the manifest
        #   or the Argo controller cannot update the selector during future rollouts.
        # - Any other Argo/K8s controller labels that are not part of the original
        #   pod identity selector.
        _RUNTIME_SELECTOR_KEYS = {
            "rollouts-pod-template-hash",
            "pod-template-hash",         # standard Deployment controller label
        }
        selector = {
            k: v
            for k, v in (original_service.spec.selector or {}).items()
            if k not in _RUNTIME_SELECTOR_KEYS
        }

        # Carry original labels, stripping server-assigned ones
        _SKIP_LABELS = {
            "kubernetes.io/metadata.name",
        }
        orig_labels = {
            k: v
            for k, v in (original_service.metadata.labels or {}).items()
            if k not in _SKIP_LABELS
        }

        core_v1 = k8s_client.CoreV1Api()
        services_created = []
        services_already_existed = []

        for suffix in suffixes:
            svc_name = f"{app_name}-{suffix}"
            svc_body = k8s_client.V1Service(
                api_version="v1",
                kind="Service",
                metadata=k8s_client.V1ObjectMeta(
                    name=svc_name,
                    namespace=namespace,
                    labels={**orig_labels, "managed-by": "argoflow-mcp-server"},
                ),
                spec=k8s_client.V1ServiceSpec(
                    selector=selector,
                    ports=cloned_ports,
                    type="ClusterIP",  # Rollout services are always ClusterIP
                ),
            )
            try:
                core_v1.create_namespaced_service(namespace=namespace, body=svc_body)
                services_created.append(svc_name)
            except K8sApiException as exc:
                if exc.status == 409:
                    services_already_existed.append(svc_name)
                else:
                    raise

        return {
            "services_created": services_created,
            "services_already_existed": services_already_existed,
            "discovered_ports": [p.port for p in orig_ports],
            "source_service": original_service.metadata.name,
        }

    async def apply_rollout_crd(
        self,
        rollout_yaml: str,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        """Apply an Argo Rollout CRD to the cluster from YAML.

        Uses the Kubernetes CustomObjectsApi to create the Rollout resource.
        Idempotent — if the Rollout already exists (409 Conflict), it is skipped
        gracefully without raising an error.

        Args:
            rollout_yaml: Argo Rollout YAML string (argoproj.io/v1alpha1/Rollout)
            namespace: Kubernetes namespace to apply into

        Returns:
            Dict with keys:
                - rollout_name: str
                - rollout_applied: bool   (True = newly created)
                - rollout_already_existed: bool
        """
        from kubernetes import client as k8s_client, config as k8s_config
        from kubernetes.client.rest import ApiException as K8sApiException

        try:
            k8s_config.load_incluster_config()
        except Exception:
            k8s_config.load_kube_config()

        custom_api = k8s_client.CustomObjectsApi()
        rollout_obj = yaml.safe_load(rollout_yaml)
        rollout_name = rollout_obj.get("metadata", {}).get("name", "unknown")

        try:
            custom_api.create_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=namespace,
                plural="rollouts",
                body=rollout_obj,
            )
            return {
                "rollout_name": rollout_name,
                "rollout_applied": True,
                "rollout_already_existed": False,
            }
        except K8sApiException as exc:
            if exc.status == 409:
                return {
                    "rollout_name": rollout_name,
                    "rollout_applied": False,
                    "rollout_already_existed": True,
                }
            raise

    async def create_stable_canary_services(
        self,
        app_name: str,
        namespace: str = "default",
        port: int = 80,
        target_port: Optional[int] = None,
        selector_labels: Optional[Dict[str, str]] = None,
        apply: bool = False,
        strategy: str = "canary",
    ) -> Dict[str, Any]:
        """Generate (and optionally apply) two K8s Service specs (stable+canary or active+preview).
        
        These Services are required by Argo Rollouts to route traffic to
        stable and canary ReplicaSets respectively. The Argo Rollouts 
        controller manages the pod selectors at runtime.
        
        Args:
            app_name: Application name (used for service naming)
            namespace: Kubernetes namespace
            port: Service port number
            target_port: Target port on pods (defaults to same as port)
            selector_labels: Pod selector labels (default: {app: app_name})
            apply: If True, create the Services directly in the cluster via
                   CoreV1Api (no kubectl needed). If False (default), return
                   YAML strings only.
            strategy: "canary" (stable+canary) or "bluegreen" (active+preview)
        
        Returns:
            Dict containing:
                - status: "success" or "error"
                - stable_service_name: Generated stable service name
                - canary_service_name: Generated canary service name
                - stable_yaml: Generated stable Service YAML
                - canary_yaml: Generated canary Service YAML
                - combined_yaml: Both services in a single multi-document YAML
                - applied: True if Services were created in cluster (apply=True)
                - created: List of service names that were newly created
                - already_existed: List of service names that already existed
                - error: Error message (if failed)
        """
        try:
            if target_port is None:
                target_port = port
            if selector_labels is None:
                selector_labels = {"app": app_name}
            
            def _make_service(name: str) -> Dict[str, Any]:
                return {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {
                        "name": name,
                        "namespace": namespace,
                        "labels": {
                            "app": app_name,
                            "managed-by": "argoflow-mcp-server"
                        }
                    },
                    "spec": {
                        "selector": selector_labels,
                        "ports": [
                            {
                                "port": port,
                                "targetPort": target_port,
                                "protocol": "TCP"
                            }
                        ]
                    }
                }
            
            if strategy == "bluegreen":
                stable_name = f"{app_name}-active"
                canary_name = f"{app_name}-preview"
            else:
                stable_name = f"{app_name}-stable"
                canary_name = f"{app_name}-canary"
            
            stable_svc = _make_service(stable_name)
            canary_svc = _make_service(canary_name)
            
            stable_yaml = yaml.dump(stable_svc, default_flow_style=False)
            canary_yaml = yaml.dump(canary_svc, default_flow_style=False)
            combined_yaml = stable_yaml + "---\n" + canary_yaml
            
            result = {
                "status": "success",
                "stable_service_name": stable_name,
                "canary_service_name": canary_name,
                "namespace": namespace,
                "stable_yaml": stable_yaml,
                "canary_yaml": canary_yaml,
                "combined_yaml": combined_yaml,
                "applied": False,
                "created": [],
                "already_existed": []
            }
            
            if apply:
                from kubernetes import client as k8s_client, config as k8s_config
                from kubernetes.client.rest import ApiException as K8sApiException
                
                # Load kubeconfig (try explicit config first, then fallbacks)
                try:
                    if self.config.kubernetes.in_cluster:
                        k8s_config.load_incluster_config()
                    else:
                        k8s_config.load_kube_config(
                            config_file=self.config.kubernetes.kubeconfig,
                            context=self.config.kubernetes.context_name
                        )
                except Exception:
                    try:
                        k8s_config.load_incluster_config()
                    except Exception:
                        k8s_config.load_kube_config()
                
                core_v1 = k8s_client.CoreV1Api()
                
                for svc_name, svc_dict in [(stable_name, stable_svc), (canary_name, canary_svc)]:
                    svc_body = k8s_client.V1Service(
                        api_version="v1",
                        kind="Service",
                        metadata=k8s_client.V1ObjectMeta(
                            name=svc_name,
                            namespace=namespace,
                            labels=svc_dict["metadata"]["labels"]
                        ),
                        spec=k8s_client.V1ServiceSpec(
                            selector=selector_labels,
                            ports=[
                                k8s_client.V1ServicePort(
                                    port=port,
                                    target_port=target_port,
                                    protocol="TCP"
                                )
                            ]
                        )
                    )
                    try:
                        core_v1.create_namespaced_service(namespace=namespace, body=svc_body)
                        result["created"].append(svc_name)
                        logger.info(f"✅ Created Service: {svc_name}")
                    except K8sApiException as e:
                        if e.status == 409:
                            # Already exists — idempotent, not an error
                            result["already_existed"].append(svc_name)
                            logger.info(f"ℹ️  Service '{svc_name}' already exists — skipped")
                        else:
                            raise
                
                result["applied"] = True
                result["message"] = (
                    f"Services applied to cluster. "
                    f"Created: {result['created'] or 'none'}. "
                    f"Already existed: {result['already_existed'] or 'none'}."
                )
            
            return result
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to create stable/canary Services: {str(e)}"
            }

    async def create_rollout_service(
        self,
        service_name: str,
        namespace: str = "default",
        port: int = 80,
        target_port: Optional[int] = None,
        selector_labels: Optional[Dict[str, str]] = None,
        app_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a single K8s Service for Argo Rollouts (e.g. canary-preview).

        Used when updating a rollout to use a non-default service name
        (e.g. canary-demo-preview instead of canary-demo-canary).

        Args:
            service_name: Full service name (e.g. canary-demo-preview)
            namespace: Kubernetes namespace
            port: Service port
            target_port: Target port on pods (defaults to port)
            selector_labels: Pod selector (default: {app: app_name or derived from service_name})
            app_name: App name for labels (default: derived from service_name)

        Returns:
            Dict with status, created/already_existed
        """
        from kubernetes import client as k8s_client, config as k8s_config
        from kubernetes.client.rest import ApiException as K8sApiException

        if target_port is None:
            target_port = port
        if app_name is None:
            app_name = service_name.rsplit("-", 1)[0] if "-" in service_name else service_name
        if selector_labels is None:
            selector_labels = {"app": app_name}

        try:
            try:
                k8s_config.load_incluster_config()
            except Exception:
                k8s_config.load_kube_config()

            core_v1 = k8s_client.CoreV1Api()
            svc_body = k8s_client.V1Service(
                api_version="v1",
                kind="Service",
                metadata=k8s_client.V1ObjectMeta(
                    name=service_name,
                    namespace=namespace,
                    labels={"app": app_name, "managed-by": "argoflow-mcp-server"},
                ),
                spec=k8s_client.V1ServiceSpec(
                    selector=selector_labels,
                    ports=[
                        k8s_client.V1ServicePort(
                            port=port,
                            target_port=target_port,
                            protocol="TCP",
                        )
                    ],
                ),
            )
            core_v1.create_namespaced_service(namespace=namespace, body=svc_body)
            return {"status": "success", "created": [service_name], "already_existed": []}
        except K8sApiException as e:
            if e.status == 409:
                return {"status": "success", "created": [], "already_existed": [service_name]}
            raise
    async def generate_deployment_scale_down_manifest(
        self,
        deployment_name: Optional[str] = None,
        deployment_yaml: Optional[str] = None,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        """Generate Deployment YAML with replicas: 0 for GitOps scale-down.

        GitOps path: when the Deployment is managed by Argo CD, scaling via
        cluster APIs is reverted. This returns the updated manifest for the
        user to commit to Git. Argo CD syncs → Deployment stays at 0.

        Args:
            deployment_name: Deployment name to fetch from cluster
            deployment_yaml: Deployment YAML string (alternative to deployment_name)
            namespace: Kubernetes namespace (used when fetching by name)

        Returns:
            Dict with deployment_yaml (replicas: 0), app_name, and Git commit guidance
        """
        if deployment_yaml:
            dep_dict = yaml.safe_load(deployment_yaml)
        elif deployment_name:
            yaml_str = await self.fetch_deployment_yaml(
                deployment_name=deployment_name,
                namespace=namespace,
            )
            dep_dict = yaml.safe_load(yaml_str)
        else:
            return {
                "status": "error",
                "error": "Either deployment_name or deployment_yaml must be provided.",
            }

        if dep_dict.get("kind") != "Deployment":
            return {
                "status": "error",
                "error": f"Input must be a Deployment, got: {dep_dict.get('kind')}",
            }

        app_name = dep_dict.get("metadata", {}).get("name", "unknown")
        dep_dict.setdefault("spec", {})["replicas"] = 0
        manifest_yaml = yaml.dump(dep_dict, default_flow_style=False)

        return {
            "status": "success",
            "app_name": app_name,
            "namespace": dep_dict.get("metadata", {}).get("namespace", namespace),
            "deployment_yaml": manifest_yaml,
            "replicas": 0,
            "git_guidance": (
                "Commit this Deployment manifest to your Git repo (with replicas: 0). "
                "Argo CD will sync and scale the Deployment to 0. It will not revert "
                "because Git is the source of truth."
            ),
            "alternative": (
                "Alternatively, remove the Deployment manifest from Git entirely "
                "and let Argo CD prune it."
            ),
        }

    async def generate_argocd_ignore_differences(
        self,
        include_traefik_service: bool = True,
        include_rollout_status: bool = True,
        include_rollout_traffic_routing: bool = False,
        include_analysis_run: bool = False,
        include_deployment_replicas: bool = False,
        deployment_name: Optional[str] = None,
        traefik_api_group: str = "traefik.io",
        custom_resources: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Generate an Argo CD ignoreDifferences snippet.
        
        When Argo Rollouts manages TraefikService weights and Rollout status,
        Argo CD will show OutOfSync. This generates the ignoreDifferences
        configuration to prevent that.
        
        For workloadRef: when the Rollout controller scales the referenced
        Deployment, Argo CD may revert it. Set include_deployment_replicas=True
        to ignore Deployment /spec/replicas.
        
        Args:
            include_traefik_service: Include TraefikService weight paths
            include_rollout_status: Include Rollout status paths
            include_rollout_traffic_routing: Include Rollout spec.strategy.*.trafficRouting
                (allows MCP-patched trafficRouting to persist when ArgoCD/Helm manages the Rollout)
            include_analysis_run: Include AnalysisRun status paths
            include_deployment_replicas: Include Deployment /spec/replicas (for workloadRef)
            deployment_name: Optional Deployment name to scope ignore (namePrefix)
            traefik_api_group: Traefik API group (traefik.io or traefik.containo.us)
            custom_resources: Additional custom ignoreDifferences entries
        
        Returns:
            Dict with ignore_differences_yaml and metadata
        """
        try:
            ignore_diffs: List[Dict[str, Any]] = []
            
            if include_deployment_replicas:
                dep_entry: Dict[str, Any] = {
                    "group": "apps",
                    "kind": "Deployment",
                    "jsonPointers": ["/spec/replicas"],
                }
                if deployment_name:
                    dep_entry["name"] = deployment_name
                ignore_diffs.append(dep_entry)
            
            if include_traefik_service:
                ignore_diffs.append({
                    "group": traefik_api_group,
                    "kind": "TraefikService",
                    "jsonPointers": [
                        "/spec/weighted/services"
                    ]
                })
            
            if include_rollout_status:
                ignore_diffs.append({
                    "group": "argoproj.io",
                    "kind": "Rollout",
                    "jsonPointers": [
                        "/status"
                    ]
                })
            
            if include_rollout_traffic_routing:
                ignore_diffs.append({
                    "group": "argoproj.io",
                    "kind": "Rollout",
                    "jsonPointers": [
                        "/spec/strategy/canary/trafficRouting",
                        "/spec/strategy/blueGreen/trafficRouting"
                    ]
                })
            
            if include_analysis_run:
                ignore_diffs.append({
                    "group": "argoproj.io",
                    "kind": "AnalysisRun",
                    "jsonPointers": [
                        "/status"
                    ]
                })
            
            if custom_resources:
                ignore_diffs.extend(custom_resources)
            
            # Build the Application snippet
            snippet = {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "Application",
                "spec": {
                    "ignoreDifferences": ignore_diffs
                }
            }
            
            snippet_yaml = yaml.dump(snippet, default_flow_style=False)
            
            return {
                "status": "success",
                "resource_count": len(ignore_diffs),
                "resources_covered": [d["kind"] for d in ignore_diffs],
                "ignore_differences_yaml": snippet_yaml,
                "note": "Add the ignoreDifferences section to your Argo CD Application spec to prevent OutOfSync caused by Argo Rollouts mutations."
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to generate ignoreDifferences: {str(e)}"
            }
    
    
    async def convert_rollout_to_deployment(
        self,
        rollout_yaml: str,
        deployment_strategy: str = "RollingUpdate",
        max_surge: str = "25%",
        max_unavailable: str = "25%"
    ) -> Dict[str, Any]:
        """Convert an Argo Rollout YAML to a standard Kubernetes Deployment.
        
        Reverse migration: strips Argo-specific fields and converts back
        to a standard Deployment. Useful for rollback or abandoning Argo Rollouts.
        
        Preserves: metadata (name, namespace, labels, annotations), spec.template,
        spec.replicas, spec.selector.
        
        Removes: Argo strategy (canary/bluegreen), workloadRef, trafficRouting.
        
        Args:
            rollout_yaml: Argo Rollout YAML string
            deployment_strategy: Deployment strategy type ("RollingUpdate" or "Recreate")
            max_surge: Max surge for RollingUpdate (default: "25%")
            max_unavailable: Max unavailable for RollingUpdate (default: "25%")
        
        Returns:
            Dict with deployment_yaml and metadata
        """
        try:
            rollout = yaml.safe_load(rollout_yaml)
            
            if not rollout:
                raise ValueError("Empty YAML input")
            
            kind = rollout.get("kind", "")
            if kind != "Rollout":
                raise ValueError(f"Input must be a Rollout, got: {kind}")
            
            metadata = rollout.get("metadata", {})
            spec = rollout.get("spec", {})
            app_name = metadata.get("name", "unknown")
            
            # Build Deployment
            deployment: Dict[str, Any] = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {
                    "name": metadata.get("name", ""),
                    "namespace": metadata.get("namespace", "default"),
                }
            }
            
            # Preserve labels (remove argoflow-managed label)
            labels = dict(metadata.get("labels", {}))
            labels.pop("managed-by", None)
            if labels:
                deployment["metadata"]["labels"] = labels
            
            # Preserve annotations (remove argo-specific ones)
            annotations = dict(metadata.get("annotations", {}))
            argo_keys = [k for k in annotations if "argoproj" in k or "argo-rollouts" in k]
            for k in argo_keys:
                annotations.pop(k, None)
            if annotations:
                deployment["metadata"]["annotations"] = annotations
            
            # Build Deployment spec
            deployment_spec: Dict[str, Any] = {}
            
            # Preserve replicas
            if "replicas" in spec:
                deployment_spec["replicas"] = spec["replicas"]
            
            # Preserve selector
            if "selector" in spec:
                deployment_spec["selector"] = spec["selector"]
            
            # Preserve template
            if "template" in spec:
                deployment_spec["template"] = spec["template"]
            
            # Add standard Deployment strategy
            if deployment_strategy == "RollingUpdate":
                deployment_spec["strategy"] = {
                    "type": "RollingUpdate",
                    "rollingUpdate": {
                        "maxSurge": max_surge,
                        "maxUnavailable": max_unavailable
                    }
                }
            else:
                deployment_spec["strategy"] = {"type": "Recreate"}
            
            deployment["spec"] = deployment_spec
            
            deployment_yaml = yaml.dump(deployment, default_flow_style=False)
            
            # Document what was removed
            original_strategy = spec.get("strategy", {})
            strategy_type = "canary" if "canary" in original_strategy else (
                "bluegreen" if "blueGreen" in original_strategy else "unknown"
            )
            
            return {
                "status": "success",
                "app_name": app_name,
                "original_strategy": strategy_type,
                "deployment_strategy": deployment_strategy,
                "deployment_yaml": deployment_yaml,
                "removed_fields": [
                    "spec.strategy (Argo canary/bluegreen)",
                    "spec.workloadRef (if present)",
                    "Argo-specific annotations"
                ],
                "note": "Review the generated Deployment before applying. Ensure Services point to the correct selectors."
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to convert Rollout to Deployment: {str(e)}"
            }
