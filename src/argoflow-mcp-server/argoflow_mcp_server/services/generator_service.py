"""Generator service for converting Deployments to Rollouts.

This service provides the bridge between standard Kubernetes Deployments
(created by ArgoCD or other CI/CD tools) and Argo Rollouts for progressive delivery.
"""

import yaml
from typing import Dict, Any, List, Optional


class GeneratorService:
    """Service for generating Rollout resources from Deployments."""
    
    def __init__(self, config=None):
        """Initialize generator service.
        
        Args:
            config: Optional server configuration
        """
        self.config = config
    
    async def convert_deployment_to_rollout(
        self,
        deployment_yaml: str,
        strategy: str = "canary"
    ) -> Dict[str, Any]:
        """Convert a Kubernetes Deployment to an Argo Rollout.
        
        Args:
            deployment_yaml: Deployment YAML as string
            strategy: Rollout strategy ("canary" or "bluegreen")
        
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
            
            # Create Rollout from Deployment
            rollout = {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "Rollout",
                "metadata": deployment["metadata"],
                "spec": {
                    "replicas": deployment["spec"]["replicas"],
                    "selector": deployment["spec"]["selector"],
                    "template": deployment["spec"]["template"]
                }
            }
            
            # Add strategy
            if strategy == "canary":
                rollout["spec"]["strategy"] = {
                    "canary": {
                        "canaryService": f"{app_name}-canary",
                        "stableService": f"{app_name}-stable",
                        "steps": [
                            {"setWeight": 5},
                            {"pause": {}},
                            {"setWeight": 10},
                            {"pause": {}},
                            {"setWeight": 25},
                            {"pause": {}},
                            {"setWeight": 50},
                            {"pause": {}},
                        ]
                    }
                }
            elif strategy == "bluegreen":
                rollout["spec"]["strategy"] = {
                    "blueGreen": {
                        "activeService": f"{app_name}-active",
                        "previewService": f"{app_name}-preview",
                        "autoPromotionEnabled": False
                    }
                }
            else:
                raise ValueError(f"Invalid strategy: {strategy}. Must be 'canary' or 'bluegreen'")
            
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
    
    async def create_traefik_service_for_rollout(
        self,
        app_name: str,
        stable_service: str,
        canary_service: str,
        namespace: str = "default",
        initial_canary_weight: int = 5,
        port: int = 80
    ) -> Dict[str, Any]:
        """Create a Traefik WeightedService for canary traffic splitting.
        
        Args:
            app_name: Application name
            stable_service: K8s Service name for stable pods
            canary_service: K8s Service name for canary pods
            namespace: Kubernetes namespace
            initial_canary_weight: Initial canary traffic percentage (0-100)
            port: Service port number
        
        Returns:
            Dict containing:
                - status: "success" or "error"
                - service_name: Generated TraefikService name
                - namespace: Kubernetes namespace
                - stable_weight: Stable traffic percentage
                - canary_weight: Canary traffic percentage
                - traefik_yaml: Generated TraefikService YAML
                - error: Error message (if failed)
        """
        try:
            stable_weight = 100 - initial_canary_weight
            
            traefik_service = {
                "apiVersion": "traefik.containo.us/v1alpha1",
                "kind": "TraefikService",
                "metadata": {
                    "name": f"{app_name}-weighted",
                    "namespace": namespace
                },
                "spec": {
                    "weighted": {
                        "services": [
                            {
                                "name": stable_service,
                                "port": port,
                                "weight": stable_weight
                            },
                            {
                                "name": canary_service,
                                "port": port,
                                "weight": initial_canary_weight
                            }
                        ]
                    }
                }
            }
            
            traefik_yaml = yaml.dump(traefik_service, default_flow_style=False)
            
            return {
                "status": "success",
                "service_name": f"{app_name}-weighted",
                "namespace": namespace,
                "stable_weight": stable_weight,
                "canary_weight": initial_canary_weight,
                "traefik_yaml": traefik_yaml
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to create TraefikService: {str(e)}"
            }
    
    async def create_analysis_template_for_rollout(
        self,
        service_name: str,
        prometheus_url: str,
        namespace: str = "default",
        error_rate_threshold: float = 5.0,
        latency_p99_threshold: float = 2000.0,
        latency_p95_threshold: float = 1000.0
    ) -> Dict[str, Any]:
        """Create an Argo AnalysisTemplate for automated canary health validation.
        
        Args:
            service_name: Service name to monitor
            prometheus_url: Prometheus server URL
            namespace: Kubernetes namespace
            error_rate_threshold: Maximum acceptable error rate percentage
            latency_p99_threshold: Maximum acceptable P99 latency in milliseconds
            latency_p95_threshold: Maximum acceptable P95 latency in milliseconds
        
        Returns:
            Dict containing:
                - status: "success" or "error"
                - template_name: Generated template name
                - namespace: Kubernetes namespace
                - metrics: List of metric names
                - thresholds: Dict of threshold values
                - template_yaml: Generated AnalysisTemplate YAML
                - error: Error message (if failed)
        """
        try:
            # Convert thresholds to appropriate formats
            error_rate_decimal = error_rate_threshold / 100.0
            latency_p99_sec = latency_p99_threshold / 1000.0
            latency_p95_sec = latency_p95_threshold / 1000.0
            
            template = {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "AnalysisTemplate",
                "metadata": {
                    "name": f"{service_name}-analysis",
                    "namespace": namespace
                },
                "spec": {
                    "metrics": [
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
                            "successCriteria": f"result[0] < {error_rate_decimal}"
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
                            "successCriteria": f"result[0] < {latency_p99_sec}"
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
                            "successCriteria": f"result[0] < {latency_p95_sec}"
                        }
                    ]
                }
            }
            
            template_yaml = yaml.dump(template, default_flow_style=False)
            
            return {
                "status": "success",
                "template_name": f"{service_name}-analysis",
                "namespace": namespace,
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
    
    async def validate_deployment_ready_for_rollout(
        self,
        deployment_yaml: str
    ) -> Dict[str, Any]:
        """Validate if a Deployment is ready to be converted to a Rollout.
        
        Args:
            deployment_yaml: Deployment YAML as string
        
        Returns:
            Dict containing:
                - ready: Boolean indicating if ready for conversion
                - score: Readiness score (0-100)
                - app_name: Application name
                - replicas: Replica count
                - containers_count: Number of containers
                - issues: List of blocking problems
                - warnings: List of recommendations
                - recommendations: List of improvements
                - error: Error message (if validation failed)
        """
        try:
            deployment = yaml.safe_load(deployment_yaml)
            
            if deployment.get("kind") != "Deployment":
                raise ValueError(f"Input must be a Deployment, got: {deployment.get('kind')}")
            
            app_name = deployment.get("metadata", {}).get("name", "unknown")
            issues = []
            warnings = []
            recommendations = []
            score = 100
            
            # Check replica count
            replicas = deployment.get("spec", {}).get("replicas", 1)
            if replicas < 2:
                issues.append(f"Only {replicas} replica(s) configured (minimum: 2 for HA)")
                score -= 20
            elif replicas < 3:
                warnings.append("Only 2 replicas (recommended: 3+ for safety)")
                score -= 5
            
            # Check containers
            containers = deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
            if not containers:
                issues.append("No containers defined in deployment")
                score -= 25
                
                return {
                    "ready": False,
                    "score": max(0, score),
                    "app_name": app_name,
                    "replicas": replicas,
                    "containers_count": 0,
                    "issues": issues,
                    "warnings": warnings,
                    "recommendations": ["Define at least one container"]
                }
            
            # Validate each container
            for container in containers:
                container_name = container.get("name", "unnamed")
                
                # Check resource limits
                resources = container.get("resources", {})
                limits = resources.get("limits", {})
                requests = resources.get("requests", {})
                
                if not limits.get("memory") or not limits.get("cpu"):
                    issues.append(f"Container '{container_name}' missing resource limits")
                    score -= 15
                if not requests.get("memory") or not requests.get("cpu"):
                    issues.append(f"Container '{container_name}' missing resource requests")
                    score -= 10
                
                # Check probes
                if not container.get("readinessProbe"):
                    warnings.append(f"Container '{container_name}' missing readiness probe")
                    score -= 5
                if not container.get("livenessProbe"):
                    warnings.append(f"Container '{container_name}' missing liveness probe")
                    score -= 5
            
            # Generate recommendations
            if issues:
                recommendations.append("Fix all blocking issues before converting to Rollout")
            if not any(c.get("resources", {}).get("limits") for c in containers):
                recommendations.append("Set resource limits for all containers")
            if not any(c.get("resources", {}).get("requests") for c in containers):
                recommendations.append("Set resource requests for all containers")
            if not any(c.get("readinessProbe") for c in containers):
                recommendations.append("Add readiness probe (minimum: HTTP GET /health)")
            if not any(c.get("livenessProbe") for c in containers):
                recommendations.append("Add liveness probe for automatic recovery")
            if replicas < 3:
                recommendations.append("Increase replicas to 3 or more for high availability")
            
            ready = len(issues) == 0
            final_score = max(0, score)
            
            return {
                "ready": ready,
                "score": final_score,
                "app_name": app_name,
                "replicas": replicas,
                "containers_count": len(containers),
                "issues": issues,
                "warnings": warnings,
                "recommendations": recommendations
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
