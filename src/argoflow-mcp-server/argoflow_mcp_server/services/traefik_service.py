"""Traefik Traffic Manager service - business logic layer.

This service encapsulates all Traefik CRD operations for traffic management,
routing, middleware, and canary deployments.
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
    TraefikOperationError,
    TraefikRouteNotFoundError,
    TraefikServiceError,
    TraefikWeightError,
    TraefikMiddlewareError,
    TraefikRouteConfigError,
    TraefikMirroringError,
    TraefikCircuitBreakerError,
    TraefikAnomalyError,
    KubernetesOperationError,
    KubernetesResourceError,
)

logger = logging.getLogger(__name__)


class TraefikService:
    """Service for Traefik traffic management operations.
    
    Encapsulates all Traefik CRD interactions for progressive delivery,
    traffic routing, middleware configuration, and monitoring.
    """
    
    def __init__(self, config_obj: ServerConfig):
        """Initialize with configuration.
        
        Args:
            config_obj: Server configuration instance
        """
        self.config = config_obj
        self._k8s_client = None
        self._dyn_client = None
        self._ingressroute_api = None
        self._traefikservice_api = None
        self._middleware_api = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize Kubernetes clients and Traefik CRD APIs.
        
        Raises:
            KubernetesOperationError: If initialization fails
            KubernetesResourceError: If Traefik CRDs not found
        """
        if self._initialized:
            return
        
        try:
            # Load kubeconfig
            try:
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes config")
            except:
                config.load_kube_config()
                logger.info("Loaded local kubeconfig")
            
            # Create dynamic client
            self._k8s_client = client.ApiClient()
            self._dyn_client = DynamicClient(self._k8s_client)
            
            # Get Traefik API resources
            try:
                self._ingressroute_api = self._dyn_client.resources.get(
                    api_version="traefik.io/v1alpha1",
                    kind="IngressRoute"
                )
            except Exception as e:
                raise KubernetesResourceError(
                    "Traefik IngressRoute CRD not found. Is Traefik installed? "
                    f"Install: helm install traefik traefik/traefik --namespace traefik --create-namespace"
                )
            
            try:
                self._traefikservice_api = self._dyn_client.resources.get(
                    api_version="traefik.io/v1alpha1",
                    kind="TraefikService"
                )
            except Exception as e:
                raise KubernetesResourceError("Traefik TraefikService CRD not found")
            
            try:
                self._middleware_api = self._dyn_client.resources.get(
                    api_version="traefik.io/v1alpha1",
                    kind="Middleware"
                )
            except Exception as e:
                raise KubernetesResourceError("Traefik Middleware CRD not found")
            
            self._initialized = True
            logger.info("✅ Traefik Service initialized")
        
        except (KubernetesResourceError, KubernetesOperationError):
            raise
        except Exception as e:
            raise KubernetesOperationError(f"Failed to initialize Traefik service: {e}")
    
    def _ensure_initialized(self) -> None:
        """Ensure service is initialized.
        
        Raises:
            KubernetesOperationError: If service is not initialized
        """
        if not self._initialized:
            raise KubernetesOperationError(
                "Traefik service not initialized. Call initialize() first."
            )
    
    async def create_weighted_route(
        self,
        route_name: str,
        namespace: str = "default",
        hostname: str = "api.example.com",
        stable_service: Optional[str] = None,
        canary_service: Optional[str] = None,
        stable_weight: int = 100,
        canary_weight: int = 0,
        entry_points: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create weighted route for canary deployment.
        
        Creates a TraefikService with weighted round robin distribution,
        then creates IngressRoute pointing to it.
        
        Args:
            route_name: Name of the route
            namespace: Kubernetes namespace
            hostname: Hostname for routing
            stable_service: Stable service name (default: {route_name}-stable)
            canary_service: Canary service name (default: {route_name}-canary)
            stable_weight: Weight for stable service (0-100)
            canary_weight: Weight for canary service (0-100)
            entry_points: Entry points list (default: ['web'])
        
        Returns:
            Creation result with route details
        
        Raises:
            TraefikWeightError: If weights are invalid
            TraefikServiceError: If creation fails
        """
        self._ensure_initialized()
        
        # Set defaults
        if stable_service is None:
            stable_service = f"{route_name}-stable"
        if canary_service is None:
            canary_service = f"{route_name}-canary"
        if entry_points is None:
            entry_points = ['web']
        
        # Validate weights
        total_weight = stable_weight + canary_weight
        if total_weight == 0:
            raise TraefikWeightError("Total weight must be greater than 0")
        
        if stable_weight < 0 or canary_weight < 0:
            raise TraefikWeightError("Weights cannot be negative")
        
        try:
            # Step 1: Create TraefikService with weighted routing
            wrr_service = {
                "apiVersion": "traefik.io/v1alpha1",
                "kind": "TraefikService",
                "metadata": {
                    "name": f"{route_name}-wrr",
                    "namespace": namespace,
                    "labels": {
                        "app": route_name,
                        "managed-by": "argoflow-mcp-server"
                    }
                },
                "spec": {
                    "weighted": {
                        "services": [
                            {
                                "name": stable_service,
                                "port": 80,
                                "weight": stable_weight
                            },
                            {
                                "name": canary_service,
                                "port": 80,
                                "weight": canary_weight
                            }
                        ]
                    }
                }
            }
            
            self._traefikservice_api.create(
                body=wrr_service,
                namespace=namespace
            )
            
            logger.info(f"✅ Created TraefikService: {route_name}-wrr")
            
            # Step 2: Create IngressRoute
            ingress_route = {
                "apiVersion": "traefik.io/v1alpha1",
                "kind": "IngressRoute",
                "metadata": {
                    "name": route_name,
                    "namespace": namespace,
                    "labels": {
                        "app": route_name,
                        "managed-by": "argoflow-mcp-server"
                    }
                },
                "spec": {
                    "entryPoints": entry_points,
                    "routes": [
                        {
                            "match": f"Host(`{hostname}`)",
                            "kind": "Rule",
                            "services": [
                                {
                                    "name": f"{route_name}-wrr",
                                    "kind": "TraefikService"
                                }
                            ]
                        }
                    ]
                }
            }
            
            self._ingressroute_api.create(
                body=ingress_route,
                namespace=namespace
            )
            
            logger.info(f"✅ Created IngressRoute: {route_name}")
            
            stable_percent = (stable_weight / total_weight) * 100 if total_weight > 0 else 0
            canary_percent = (canary_weight / total_weight) * 100 if total_weight > 0 else 0
            
            return {
                "status": "success",
                "route_name": route_name,
                "wrr_service": f"{route_name}-wrr",
                "hostname": hostname,
                "stable_service": stable_service,
                "canary_service": canary_service,
                "stable_weight": stable_weight,
                "canary_weight": canary_weight,
                "stable_percent": stable_percent,
                "canary_percent": canary_percent,
                "message": f"Weighted route created: {stable_percent:.1f}% stable, {canary_percent:.1f}% canary"
            }
        
        except ApiException as e:
            if e.status == 409:
                raise TraefikServiceError(f"Route '{route_name}' already exists")
            raise TraefikServiceError(f"Failed to create route: {e}")
        except (TraefikWeightError, TraefikServiceError):
            raise
        except Exception as e:
            raise TraefikServiceError(f"Failed to create route: {e}")
    
    async def update_route_weights(
        self,
        route_name: str,
        namespace: str = "default",
        stable_weight: int = 100,
        canary_weight: int = 0
    ) -> Dict[str, Any]:
        """Update traffic weights between stable and canary.
        
        Progressive traffic shift: 5% → 10% → 25% → 50% → 100%
        
        Args:
            route_name: Name of the route
            namespace: Kubernetes namespace
            stable_weight: New weight for stable service
            canary_weight: New weight for canary service
        
        Returns:
            Update result with percentages
        
        Raises:
            TraefikWeightError: If weights are invalid
            TraefikRouteNotFoundError: If route doesn't exist
        """
        self._ensure_initialized()
        
        # Validate weights
        total_weight = stable_weight + canary_weight
        if total_weight == 0:
            raise TraefikWeightError("Total weight must be greater than 0")
        
        if stable_weight < 0 or canary_weight < 0:
            raise TraefikWeightError("Weights cannot be negative")
        
        try:
            traefikservice_name = f"{route_name}-wrr"
            
            # Build patch
            patch = {
                "spec": {
                    "weighted": {
                        "services": [
                            {
                                "name": f"{route_name}-stable",
                                "port": 80,
                                "weight": stable_weight
                            },
                            {
                                "name": f"{route_name}-canary",
                                "port": 80,
                                "weight": canary_weight
                            }
                        ]
                    }
                }
            }
            
            self._traefikservice_api.patch(
                name=traefikservice_name,
                namespace=namespace,
                body=patch,
                content_type="application/merge-patch+json"
            )
            
            stable_percent = (stable_weight / total_weight) * 100
            canary_percent = (canary_weight / total_weight) * 100
            
            logger.info(f"✅ Updated weights: {stable_percent:.1f}% stable, {canary_percent:.1f}% canary")
            
            return {
                "status": "success",
                "route_name": route_name,
                "stable_weight": stable_weight,
                "canary_weight": canary_weight,
                "stable_percent": stable_percent,
                "canary_percent": canary_percent,
                "message": "Weights updated successfully"
            }
        
        except ApiException as e:
            if e.status == 404:
                raise TraefikRouteNotFoundError(f"TraefikService '{traefikservice_name}' not found")
            raise TraefikServiceError(f"Failed to update weights: {e}")
        except (TraefikWeightError, TraefikRouteNotFoundError):
            raise
        except Exception as e:
            raise TraefikServiceError(f"Failed to update weights: {e}")
    
    async def delete_route(
        self,
        route_name: str,
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """Delete weighted route (cleanup after rollout complete).
        
        Args:
            route_name: Name of the route to delete
            namespace: Kubernetes namespace
        
        Returns:
            Deletion result
        
        Raises:
            TraefikRouteNotFoundError: If route doesn't exist
        """
        self._ensure_initialized()
        
        try:
            # Delete IngressRoute
            self._ingressroute_api.delete(
                name=route_name,
                namespace=namespace
            )
            logger.info(f"✅ Deleted IngressRoute: {route_name}")
            
            # Delete TraefikService
            traefikservice_name = f"{route_name}-wrr"
            self._traefikservice_api.delete(
                name=traefikservice_name,
                namespace=namespace
            )
            logger.info(f"✅ Deleted TraefikService: {traefikservice_name}")
            
            return {
                "status": "success",
                "route_name": route_name,
                "deleted_resources": [
                    f"IngressRoute/{route_name}",
                    f"TraefikService/{traefikservice_name}"
                ],
                "message": f"Route {route_name} deleted successfully"
            }
        
        except ApiException as e:
            if e.status == 404:
                raise TraefikRouteNotFoundError(f"Route '{route_name}' not found")
            raise TraefikOperationError(f"Failed to delete route: {e}")
        except Exception as e:
            raise TraefikOperationError(f"Failed to delete route: {e}")
    
    async def add_rate_limiting(
        self,
        middleware_name: str,
        namespace: str = "default",
        average: int = 100,
        burst: int = 200,
        period: str = "1s"
    ) -> Dict[str, Any]:
        """Create rate limiting middleware for canary protection.
        
        Args:
            middleware_name: Name of the middleware
            namespace: Kubernetes namespace
            average: Average requests per period
            burst: Maximum burst size
            period: Time period ('1s', '1m', etc.)
        
        Returns:
            Creation result
        
        Raises:
            TraefikMiddlewareError: If creation fails
        """
        self._ensure_initialized()
        
        try:
            middleware = {
                "apiVersion": "traefik.io/v1alpha1",
                "kind": "Middleware",
                "metadata": {
                    "name": middleware_name,
                    "namespace": namespace
                },
                "spec": {
                    "rateLimit": {
                        "average": average,
                        "burst": burst,
                        "period": period
                    }
                }
            }
            
            self._middleware_api.create(
                body=middleware,
                namespace=namespace
            )
            
            logger.info(f"✅ Created rate limit middleware: {middleware_name}")
            
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "average": average,
                "burst": burst,
                "period": period,
                "message": f"Rate limit: {average} req/{period}, burst {burst}"
            }
        
        except ApiException as e:
            if e.status == 409:
                raise TraefikMiddlewareError(f"Middleware '{middleware_name}' already exists")
            raise TraefikMiddlewareError(f"Failed to create rate limit: {e}")
        except Exception as e:
            raise TraefikMiddlewareError(f"Failed to create rate limit: {e}")
    
    async def add_circuit_breaker(
        self,
        middleware_name: str,
        namespace: str = "default",
        trigger_type: str = "error-rate",
        threshold: float = 0.30
    ) -> Dict[str, Any]:
        """Create circuit breaker middleware for auto-rollback.
        
        Args:
            middleware_name: Name of the middleware
            namespace: Kubernetes namespace
            trigger_type: 'error-rate' | 'latency' | 'network-error'
            threshold: Threshold value (0.30 = 30%, 100 = 100ms)
        
        Returns:
            Creation result
        
        Raises:
            TraefikCircuitBreakerError: If creation fails or invalid trigger type
        """
        self._ensure_initialized()
        
        # Build expression based on trigger type
        if trigger_type == "error-rate":
            expression = f"ResponseCodeRatio(500, 600, 0, 600) > {threshold}"
            description = f"Error rate > {threshold*100}%"
        elif trigger_type == "latency":
            expression = f"LatencyAtQuantileMS(50.0) > {threshold}"
            description = f"Latency p50 > {threshold}ms"
        elif trigger_type == "network-error":
            expression = f"NetworkErrorRatio() > {threshold}"
            description = f"Network errors > {threshold*100}%"
        else:
            raise TraefikCircuitBreakerError(
                f"Unknown trigger type: {trigger_type}. Must be 'error-rate', 'latency', or 'network-error'"
            )
        
        try:
            middleware = {
                "apiVersion": "traefik.io/v1alpha1",
                "kind": "Middleware",
                "metadata": {
                    "name": middleware_name,
                    "namespace": namespace
                },
                "spec": {
                    "circuitBreaker": {
                        "expression": expression
                    }
                }
            }
            
            self._middleware_api.create(
                body=middleware,
                namespace=namespace
            )
            
            logger.info(f"✅ Created circuit breaker: {middleware_name}")
            
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "trigger_type": trigger_type,
                "threshold": threshold,
                "expression": expression,
                "description": description,
                "message": f"Circuit breaker: {description}"
            }
        
        except ApiException as e:
            if e.status == 409:
                raise TraefikMiddlewareError(f"Middleware '{middleware_name}' already exists")
            raise TraefikCircuitBreakerError(f"Failed to create circuit breaker: {e}")
        except TraefikCircuitBreakerError:
            raise
        except Exception as e:
            raise TraefikCircuitBreakerError(f"Failed to create circuit breaker: {e}")
    
    async def enable_traffic_mirroring(
        self,
        route_name: str,
        namespace: str = "default",
        main_service: Optional[str] = None,
        mirror_service: Optional[str] = None,
        mirror_percent: int = 20
    ) -> Dict[str, Any]:
        """Enable traffic mirroring for shadow testing.
        
        Copy traffic from main service to shadow/canary service.
        
        Args:
            route_name: Name of the route
            namespace: Kubernetes namespace
            main_service: Main service (default: {route_name}-stable)
            mirror_service: Mirror service (default: {route_name}-staging)
            mirror_percent: Percentage to mirror (1-100)
        
        Returns:
            Creation result
        
        Raises:
            TraefikMirroringError: If mirroring setup fails
        """
        self._ensure_initialized()
        
        if main_service is None:
            main_service = f"{route_name}-stable"
        if mirror_service is None:
            mirror_service = f"{route_name}-staging"
        
        # Validate percent
        if mirror_percent < 0 or mirror_percent > 100:
            raise TraefikMirroringError("Mirror percentage must be between 0 and 100")
        
        try:
            # Create Traefik Service with mirroring
            mirror_svc = {
                "apiVersion": "traefik.io/v1alpha1",
                "kind": "TraefikService",
                "metadata": {
                    "name": f"{route_name}-mirror",
                    "namespace": namespace
                },
                "spec": {
                    "mirroring": {
                        "name": main_service,
                        "port": 80,
                        "mirrors": [
                            {
                                "name": mirror_service,
                                "port": 80,
                                "percent": mirror_percent
                            }
                        ]
                    }
                }
            }
            
            self._traefikservice_api.create(
                body=mirror_svc,
                namespace=namespace
            )
            
            logger.info(f"✅ Enabled traffic mirroring: {mirror_percent}% to {mirror_service}")
            
            return {
                "status": "success",
                "route_name": route_name,
                "main_service": main_service,
                "mirror_service": mirror_service,
                "mirror_percent": mirror_percent,
                "message": f"Mirroring {mirror_percent}% of traffic to {mirror_service}"
            }
        
        except ApiException as e:
            if e.status == 409:
                raise TraefikMirroringError(f"Mirror service '{route_name}-mirror' already exists")
            raise TraefikMirroringError(f"Failed to enable mirroring: {e}")
        except TraefikMirroringError:
            raise
        except Exception as e:
            raise TraefikMirroringError(f"Failed to enable mirroring: {e}")
    
    async def get_service_traffic_distribution(
        self,
        route_name: str,
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """Get current traffic distribution for a route.
        
        Args:
            route_name: Name of the route
            namespace: Kubernetes namespace
        
        Returns:
            Traffic distribution details
        
        Raises:
            TraefikRouteNotFoundError: If route doesn't exist
        """
        self._ensure_initialized()
        
        try:
            traefikservice_name = f"{route_name}-wrr"
            svc = self._traefikservice_api.get(
                name=traefikservice_name,
                namespace=namespace
            )
            
            spec = svc.get("spec", {})
            weighted = spec.get("weighted", {})
            services = weighted.get("services", [])
            
            distribution = []
            total_weight = sum(s.get("weight", 0) for s in services)
            
            for service in services:
                weight = service.get("weight", 0)
                percent = (weight / total_weight * 100) if total_weight > 0 else 0
                distribution.append({
                    "service": service.get("name"),
                    "weight": weight,
                    "percent": percent
                })
            
            return {
                "status": "success",
                "route_name": route_name,
                "total_weight": total_weight,
                "distribution": distribution,
                "timestamp": datetime.now().isoformat()
            }
        
        except ApiException as e:
            if e.status == 404:
                raise TraefikRouteNotFoundError(f"TraefikService '{traefikservice_name}' not found")
            raise TraefikOperationError(f"Failed to get traffic distribution: {e}")
        except Exception as e:
            raise TraefikOperationError(f"Failed to get traffic distribution: {e}")
    
    async def detect_traffic_anomalies(
        self,
        route_name: str,
        namespace: str = "default",
        threshold: float = 2.0
    ) -> Dict[str, Any]:
        """Detect traffic anomalies (placeholder for metrics-based detection).
        
        Args:
            route_name: Name of the route
            namespace: Kubernetes namespace
            threshold: Standard deviations for anomaly
        
        Returns:
            Anomaly detection results
        
        Note:
            This is a placeholder. Full implementation requires Prometheus integration.
        """
        self._ensure_initialized()
        
        # Placeholder - would integrate with Prometheus in production
        return {
            "status": "success",
            "route_name": route_name,
            "anomalies_detected": False,
            "threshold": threshold,
            "message": "Anomaly detection requires Prometheus integration",
            "timestamp": datetime.now().isoformat()
        }
