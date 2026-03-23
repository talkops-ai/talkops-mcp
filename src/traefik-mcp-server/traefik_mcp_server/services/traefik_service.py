"""Traefik Traffic Manager service - business logic layer.

This service encapsulates all Traefik CRD operations for traffic management,
routing, middleware, and canary deployments.
"""

import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from kubernetes import client, config
from kubernetes.dynamic import DynamicClient
from kubernetes.client.rest import ApiException

from traefik_mcp_server.config import ServerConfig
from traefik_mcp_server.traefik_middleware_builders import (
    build_middleware_crd,
    spec_add_prefix,
    spec_buffering,
    spec_circuit_breaker,
    spec_forward_auth,
    spec_headers_block,
    spec_inflight_req,
    spec_ip_allowlist,
    spec_ip_denylist,
    spec_rate_limit,
    spec_redirect_scheme,
    spec_replace_path,
    spec_replace_path_regex,
    spec_strip_prefix,
    spec_strip_prefix_regex,
)
from traefik_mcp_server.exceptions.custom import (
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
        self._k8s_client: Any = None
        self._dyn_client: Any = None
        self._ingressroute_api: Any = None
        self._traefikservice_api: Any = None
        self._middleware_api: Any = None
        self._ingressroutetcp_api: Any = None
        self._middlewaretcp_api: Any = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize Kubernetes clients and Traefik CRD APIs.
        
        Raises:
            KubernetesOperationError: If initialization fails
            KubernetesResourceError: If Traefik CRDs not found
        """
        if self._initialized:
            return
        
        assert self.config.kubernetes is not None

        try:
            # Load kubeconfig (try explicit config first, then fallbacks)
            try:
                if self.config.kubernetes.in_cluster:
                    config.load_incluster_config()
                else:
                    config.load_kube_config(
                        config_file=self.config.kubernetes.kubeconfig,
                        context=self.config.kubernetes.context_name
                    )
            except Exception as e:
                try:
                    config.load_incluster_config()
                except:
                    config.load_kube_config()
            
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
            try:
                self._ingressroutetcp_api = self._dyn_client.resources.get(
                    api_version="traefik.io/v1alpha1",
                    kind="IngressRouteTCP"
                )
            except Exception:
                self._ingressroutetcp_api = None
            try:
                self._middlewaretcp_api = self._dyn_client.resources.get(
                    api_version="traefik.io/v1alpha1",
                    kind="MiddlewareTCP"
                )
            except Exception:
                self._middlewaretcp_api = None

            self._initialized = True
        
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

    _ALLOWED_ENTRYPOINTS = {"web", "websecure"}

    def _normalize_entry_points(
        self, entry_points: Optional[List[str]], tls_enabled: bool
    ) -> List[str]:
        if entry_points is None:
            return ["websecure"] if tls_enabled else ["web"]
        out = ["websecure" if ep == "https" else ep for ep in entry_points]
        invalid = [ep for ep in out if ep not in self._ALLOWED_ENTRYPOINTS]
        if invalid:
            raise TraefikRouteConfigError(
                f"Entry point(s) {invalid} do not exist. Use 'web' or 'websecure'."
            )
        return out

    def _build_weighted_services(
        self,
        stable_service: Optional[str],
        canary_service: Optional[str],
        stable_weight: int,
        canary_weight: int,
    ) -> tuple:
        """Validate and return (stable_svc, canary_svc, weighted_services). Raises on invalid."""
        if not stable_service or not str(stable_service).strip():
            raise TraefikRouteConfigError("stable_service is required.")
        stable_svc = str(stable_service).strip()
        
        canary_svc = None
        if canary_service and str(canary_service).strip():
            canary_svc = str(canary_service).strip()
            
        if canary_weight > 0 and not canary_svc:
            raise TraefikRouteConfigError("canary_service required when canary_weight > 0.")
            
        total = stable_weight + canary_weight
        if total == 0:
            raise TraefikWeightError("Total weight must be > 0")
        if stable_weight < 0 or canary_weight < 0:
            raise TraefikWeightError("Weights cannot be negative")
            
        services = [{"name": stable_svc, "port": 80, "weight": stable_weight}]
        if canary_svc:
            services.append({"name": canary_svc, "port": 80, "weight": canary_weight})
            
        return stable_svc, canary_svc, services

    async def create_weighted_route(
        self,
        route_name: str,
        namespace: str = "default",
        hostname: str = "api.example.com",
        stable_service: Optional[str] = None,
        canary_service: Optional[str] = None,
        stable_weight: int = 100,
        canary_weight: int = 0,
        entry_points: Optional[List[str]] = None,
        path_prefix: Optional[str] = None,
        path_match_type: str = "PathPrefix",
        tls_enabled: bool = False,
        tls_secret_name: Optional[str] = None,
        middlewares: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create TraefikService (WRR) + IngressRoute for weighted canary. Single backend when canary_weight=0."""
        self._ensure_initialized()
        stable_svc, canary_svc, weighted_services = self._build_weighted_services(
            stable_service, canary_service, stable_weight, canary_weight
        )
        entry_points = self._normalize_entry_points(entry_points, tls_enabled)
        total_weight = stable_weight + canary_weight

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
                        "managed-by": "traefik-mcp-server"
                    }
                },
                "spec": {
                    "weighted": {
                        "services": weighted_services
                    }
                }
            }
            
            self._traefikservice_api.create(
                body=wrr_service,
                namespace=namespace
            )
            
            
            # Step 2: Build match rule (Host + optional path)
            match_rule = f"Host(`{hostname}`)"
            if path_prefix:
                prefix = path_prefix if path_prefix.startswith('/') else f'/{path_prefix}'
                if path_match_type == "Path":
                    match_rule += f" && Path(`{prefix}`)"
                elif path_match_type == "PathRegexp":
                    match_rule += f" && PathRegexp(`{prefix}`)"
                else:
                    match_rule += f" && PathPrefix(`{prefix}`)"
            
            # Step 3: Create IngressRoute
            route_spec: Dict[str, Any] = {
                "match": match_rule,
                "kind": "Rule",
                "services": [
                    {
                        "name": f"{route_name}-wrr",
                        "kind": "TraefikService"
                    }
                ]
            }
            if middlewares:
                route_spec["middlewares"] = [{"name": mw, "namespace": namespace} for mw in middlewares]
            
            ingress_route: Dict[str, Any] = {
                "apiVersion": "traefik.io/v1alpha1",
                "kind": "IngressRoute",
                "metadata": {
                    "name": route_name,
                    "namespace": namespace,
                    "labels": {
                        "app": route_name,
                        "managed-by": "traefik-mcp-server"
                    }
                },
                "spec": {
                    "entryPoints": entry_points,
                    "routes": [route_spec]
                }
            }
            if tls_enabled:
                tls_config: Dict[str, Any] = {}
                if tls_secret_name:
                    tls_config["secretName"] = tls_secret_name
                ingress_route["spec"]["tls"] = tls_config
            
            self._ingressroute_api.create(
                body=ingress_route,
                namespace=namespace
            )
            
            
            stable_percent = (stable_weight / total_weight) * 100 if total_weight > 0 else 0
            canary_percent = (canary_weight / total_weight) * 100 if total_weight > 0 else 0
            result = {
                "status": "success",
                "route_name": route_name,
                "wrr_service": f"{route_name}-wrr",
                "hostname": hostname,
                "stable_service": stable_svc,
                "canary_service": canary_svc,
                "stable_weight": stable_weight,
                "canary_weight": canary_weight,
                "stable_percent": stable_percent,
                "canary_percent": canary_percent,
                "message": f"Weighted route created: {stable_percent:.1f}% stable, {canary_percent:.1f}% canary"
            }
            if path_prefix:
                result["path_prefix"] = path_prefix
                result["path_match_type"] = path_match_type
            if tls_enabled:
                result["tls_enabled"] = True
                if tls_secret_name:
                    result["tls_secret_name"] = tls_secret_name
            if middlewares:
                result["middlewares"] = middlewares
            return result
        
        except ApiException as e:
            if e.status == 409:
                raise TraefikServiceError(f"Route '{route_name}' already exists")
            raise TraefikServiceError(f"Failed to create route: {e}")
        except (TraefikWeightError, TraefikServiceError):
            raise
        except Exception as e:
            raise TraefikServiceError(f"Failed to create route: {e}")

    async def create_traefik_service_only(
        self,
        route_name: str,
        namespace: str = "default",
        stable_service: Optional[str] = None,
        canary_service: Optional[str] = None,
        stable_weight: int = 100,
        canary_weight: int = 0,
    ) -> Dict[str, Any]:
        """Create only TraefikService (WRR) for an existing route. Name: {route_name}-wrr."""
        self._ensure_initialized()
        _, _, weighted_services = self._build_weighted_services(
            stable_service, canary_service, stable_weight, canary_weight
        )
        wrr_service = {
            "apiVersion": "traefik.io/v1alpha1",
            "kind": "TraefikService",
            "metadata": {
                "name": f"{route_name}-wrr",
                "namespace": namespace,
                "labels": {"app": route_name, "managed-by": "traefik-mcp-server"},
            },
            "spec": {"weighted": {"services": weighted_services}},
        }
        try:
            self._traefikservice_api.create(body=wrr_service, namespace=namespace)
            return {
                "status": "success",
                "route_name": route_name,
                "wrr_service": f"{route_name}-wrr",
                "message": "TraefikService created successfully",
            }
        except ApiException as e:
            if e.status == 409:
                raise TraefikServiceError(f"TraefikService '{route_name}-wrr' already exists")
            raise TraefikServiceError(f"Failed to create TraefikService: {e}")

    async def create_simple_ingress_route(
        self,
        route_name: str,
        namespace: str = "default",
        entry_points: Optional[List[str]] = None,
        routes: Optional[List[Dict[str, Any]]] = None,
        tls_enabled: bool = False,
        tls_secret_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """IngressRoute with one or more rules; each rule points at a K8s Service (no TraefikService). routes[*]: match, service_name, service_port?, middlewares?."""
        self._ensure_initialized()
        if not routes or not isinstance(routes, list):
            raise TraefikRouteConfigError("routes is required and must be a non-empty list of rule objects")
        entry_points = self._normalize_entry_points(entry_points, tls_enabled)
        route_specs: List[Dict[str, Any]] = []
        for i, r in enumerate(routes):
            if not isinstance(r, dict):
                raise TraefikRouteConfigError(f"routes[{i}] must be an object with match, service_name, and optional service_port, middlewares")
            match_expr = r.get("match")
            svc_name = r.get("service_name")
            if not match_expr or not str(match_expr).strip():
                raise TraefikRouteConfigError(f"routes[{i}].match is required")
            if not svc_name or not str(svc_name).strip():
                raise TraefikRouteConfigError(f"routes[{i}].service_name is required")
            port = r.get("service_port", 80)
            try:
                port = int(port)
            except (TypeError, ValueError):
                raise TraefikRouteConfigError(f"routes[{i}].service_port must be an integer")
            spec: Dict[str, Any] = {
                "kind": "Rule",
                "match": str(match_expr).strip(),
                "services": [
                    {"kind": "Service", "name": str(svc_name).strip(), "port": port}
                ],
            }
            mw_list = r.get("middlewares")
            if mw_list:
                spec["middlewares"] = [{"name": mw, "namespace": namespace} for mw in mw_list]
            route_specs.append(spec)
        body: Dict[str, Any] = {
            "apiVersion": "traefik.io/v1alpha1",
            "kind": "IngressRoute",
            "metadata": {
                "name": route_name,
                "namespace": namespace,
                "labels": {"app": route_name, "managed-by": "traefik-mcp-server"},
            },
            "spec": {"entryPoints": entry_points, "routes": route_specs},
        }
        if tls_enabled:
            body["spec"]["tls"] = {"secretName": tls_secret_name} if tls_secret_name else {}
        try:
            self._ingressroute_api.create(body=body, namespace=namespace)
            result: Dict[str, Any] = {
                "status": "success",
                "route_name": route_name,
                "message": f"IngressRoute created with {len(route_specs)} route rule(s) (direct K8s Service references, no TraefikService)",
                "routes": [{"match": s["match"], "service_name": s["services"][0]["name"], "service_port": s["services"][0]["port"]} for s in route_specs],
            }
            if tls_enabled and tls_secret_name:
                result["tls_secret_name"] = tls_secret_name
            return result
        except ApiException as e:
            if e.status == 409:
                try:
                    self._ingressroute_api.patch(
                        name=route_name,
                        namespace=namespace,
                        body={"spec": body["spec"]},
                        content_type="application/merge-patch+json"
                    )
                    result: Dict[str, Any] = {
                        "status": "success",
                        "route_name": route_name,
                        "message": f"IngressRoute updated with {len(route_specs)} route rule(s) (direct K8s Service references, no TraefikService)",
                        "routes": [{"match": s["match"], "service_name": s["services"][0]["name"], "service_port": s["services"][0]["port"]} for s in route_specs],
                    }
                    if tls_enabled and tls_secret_name:
                        result["tls_secret_name"] = tls_secret_name
                    return result
                except Exception as patch_e:
                    raise TraefikServiceError(f"IngressRoute '{route_name}' exists but failed to update: {patch_e}")
            raise TraefikServiceError(f"Failed to create/update IngressRoute: {e}")

    async def delete_simple_ingress_route(
        self,
        route_name: str,
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """Delete a simple IngressRoute by name (no TraefikService cleanup)."""
        self._ensure_initialized()
        try:
            self._ingressroute_api.delete(name=route_name, namespace=namespace)
            return {
                "status": "success",
                "route_name": route_name,
                "message": "Simple IngressRoute deleted successfully",
                "deleted": [f"IngressRoute/{route_name}"]
            }
        except ApiException as e:
            if e.status == 404:
                raise TraefikRouteNotFoundError(f"IngressRoute '{route_name}' not found")
            raise TraefikServiceError(f"Failed to delete simple IngressRoute: {e}")

    async def update_route_weights(
        self,
        route_name: str,
        namespace: str = "default",
        stable_weight: int = 100,
        canary_weight: int = 0
    ) -> Dict[str, Any]:
        """Update WRR weights. Reads existing TraefikService and patches weights."""
        self._ensure_initialized()
        # Validate weights
        total_weight = stable_weight + canary_weight
        if total_weight == 0:
            raise TraefikWeightError("Total weight must be greater than 0")
        
        if stable_weight < 0 or canary_weight < 0:
            raise TraefikWeightError("Weights cannot be negative")
        
        try:
            traefikservice_name = f"{route_name}-wrr"
            
            # Fetch current TraefikService to preserve backend service names
            # (create may have used custom stable_service/canary_service)
            ts = self._traefikservice_api.get(
                name=traefikservice_name,
                namespace=namespace
            )
            ts_dict = ts.to_dict()
            services_spec = ts_dict.get("spec", {}).get("weighted", {}).get("services", [])
            if not services_spec:
                raise TraefikServiceError(
                    f"TraefikService '{traefikservice_name}' has no weighted services"
                )
            # Read backend names from spec as-is (we do not assume -stable/-canary)
            def get_svc(s: dict, idx: int) -> tuple:
                name = s.get("name")
                if not name:
                    raise TraefikServiceError(
                        f"TraefikService '{traefikservice_name}' weighted.services[{idx}] missing 'name'"
                    )
                return name, s.get("port", 80)

            # Single-backend route: only stable; canary_weight must be 0
            if len(services_spec) == 1:
                if canary_weight != 0:
                    raise TraefikWeightError(
                        "Route has only one backend; set canary_weight=0 when updating."
                    )
                stable_svc_name, stable_port = get_svc(services_spec[0], 0)
                patch_services = [{"name": stable_svc_name, "port": stable_port, "weight": stable_weight}]
            else:
                stable_svc_name, stable_port = get_svc(services_spec[0], 0)
                canary_svc_name, canary_port = get_svc(services_spec[1], 1)
                patch_services = [
                    {"name": stable_svc_name, "port": stable_port, "weight": stable_weight},
                    {"name": canary_svc_name, "port": canary_port, "weight": canary_weight},
                ]

            # Build patch - preserve existing service names, update only weights
            patch = {
                "spec": {
                    "weighted": {
                        "services": patch_services
                    }
                }
            }
            
            self._traefikservice_api.patch(
                name=traefikservice_name,
                namespace=namespace,
                body=patch,
                content_type="application/merge-patch+json"
            )
            
            stable_percent = (stable_weight / total_weight) * 100 if total_weight else 0
            canary_percent = (canary_weight / total_weight) * 100 if total_weight else 0
            
            
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
        namespace: str = "default",
        clean_all: bool = False
    ) -> Dict[str, Any]:
        """Delete weighted route (cleanup after rollout complete).
        
        Args:
            route_name: Name of the route to delete
            namespace: Kubernetes namespace
            clean_all: Whether to attempt deleting associated services and middlewares
        
        Returns:
            Deletion result
        
        Raises:
            TraefikRouteNotFoundError: If route doesn't exist
        """
        self._ensure_initialized()

        deleted_resources = []
        traefikservice_name = f"{route_name}-wrr"

        # If clean_all, read backend service names from TraefikService (we don't assume -stable/-canary)
        backend_service_names: List[str] = []
        middleware_names_to_delete: List[str] = []
        if clean_all:
            try:
                ts = self._traefikservice_api.get(name=traefikservice_name, namespace=namespace)
                ts_dict = ts.to_dict()
                for s in ts_dict.get("spec", {}).get("weighted", {}).get("services", []):
                    name = s.get("name")
                    if name:
                        backend_service_names.append(name)
            except ApiException:
                pass
            try:
                ir = self._ingressroute_api.get(name=route_name, namespace=namespace)
                ir_dict = ir.to_dict()
                for route in ir_dict.get("spec", {}).get("routes", []) or []:
                    for mw in route.get("middlewares", []) or []:
                        name = mw.get("name") if isinstance(mw, dict) else mw
                        if name and name not in middleware_names_to_delete:
                            middleware_names_to_delete.append(name)
            except ApiException:
                pass

        try:
            # Delete IngressRoute
            try:
                self._ingressroute_api.delete(name=route_name, namespace=namespace)
                deleted_resources.append(f"IngressRoute/{route_name}")
            except ApiException as e:
                if e.status != 404:
                    raise

            # Delete TraefikService (naming convention: always {route_name}-wrr)
            try:
                self._traefikservice_api.delete(name=traefikservice_name, namespace=namespace)
                deleted_resources.append(f"TraefikService/{traefikservice_name}")
            except ApiException:
                pass

            if clean_all:
                core_v1 = client.CoreV1Api(self._k8s_client)
                for svc_name in backend_service_names:
                    try:
                        core_v1.delete_namespaced_service(name=svc_name, namespace=namespace)
                        deleted_resources.append(f"Service/{svc_name}")
                    except ApiException:
                        pass
                for mw_name in middleware_names_to_delete:
                    try:
                        self._middleware_api.delete(name=mw_name, namespace=namespace)
                        deleted_resources.append(f"Middleware/{mw_name}")
                    except ApiException:
                        pass

            if not deleted_resources:
                raise TraefikRouteNotFoundError(f"Route '{route_name}' and associated resources not found")
            
            return {
                "status": "success",
                "route_name": route_name,
                "deleted_resources": deleted_resources,
                "message": f"Route {route_name} and associated resources deleted successfully"
            }
        
        except ApiException as e:
            if e.status == 404:
                raise TraefikRouteNotFoundError(f"Route '{route_name}' not found")
            raise TraefikOperationError(f"Failed to delete route: {e}")
        except Exception as e:
            raise TraefikOperationError(f"Failed to delete route: {e}")
    
    async def delete_middleware(
        self,
        middleware_name: str,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        """Delete a Traefik Middleware CRD.

        Args:
            middleware_name: Name of the Middleware to delete.
            namespace: Kubernetes namespace.

        Returns:
            Deletion result.
        """
        self._ensure_initialized()
        try:
            self._middleware_api.delete(name=middleware_name, namespace=namespace)
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "namespace": namespace,
                "message": f"Middleware '{middleware_name}' deleted successfully",
            }
        except ApiException as e:
            if e.status == 404:
                raise TraefikMiddlewareError(f"Middleware '{middleware_name}' not found in namespace '{namespace}'")
            raise TraefikMiddlewareError(f"Failed to delete middleware: {e}")

    def _upsert_middleware_body(self, body: Dict[str, Any], namespace: str) -> None:
        """Create Middleware CRD, or merge-patch `spec` when it already exists (409)."""
        self._ensure_initialized()
        name = body["metadata"]["name"]
        try:
            self._middleware_api.create(body=body, namespace=namespace)
        except ApiException as e:
            if e.status != 409:
                raise TraefikMiddlewareError(f"Failed to create middleware: {e}") from e
            try:
                self._middleware_api.patch(
                    name=name,
                    namespace=namespace,
                    body={"spec": body["spec"]},
                    content_type="application/merge-patch+json",
                )
            except Exception as patch_e:
                raise TraefikMiddlewareError(
                    f"Middleware '{name}' exists but failed to update: {patch_e}"
                ) from patch_e

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
            body = build_middleware_crd(
                middleware_name,
                namespace,
                spec_rate_limit(average, burst, period),
            )
            self._upsert_middleware_body(body, namespace)
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "average": average,
                "burst": burst,
                "period": period,
                "message": f"Rate limit: {average} req/{period}, burst {burst}",
            }
        except TraefikMiddlewareError:
            raise
        except Exception as e:
            raise TraefikMiddlewareError(f"Failed to upsert rate limit: {e}") from e
    
    async def add_circuit_breaker(
        self,
        middleware_name: str,
        namespace: str = "default",
        trigger_type: str = "error-rate",
        threshold: float = 0.30,
        response_code: int = 503
    ) -> Dict[str, Any]:
        """Create circuit breaker middleware for auto-rollback.
        
        Args:
            middleware_name: Name of the middleware
            namespace: Kubernetes namespace
            trigger_type: 'error-rate' | 'latency' | 'network-error'
            threshold: Threshold value (0.30 = 30%, 100 = 100ms)
            response_code: HTTP status when circuit is open (e.g. 429, 503, 504). Use a different code than backend 503 to verify CB effect.
        
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
            body = build_middleware_crd(
                middleware_name,
                namespace,
                spec_circuit_breaker(expression, response_code),
            )
            self._middleware_api.create(body=body, namespace=namespace)
            
            
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "trigger_type": trigger_type,
                "threshold": threshold,
                "response_code": response_code,
                "expression": expression,
                "description": description,
                "message": f"Circuit breaker: {description} (when open returns {response_code})"
            }
        
        except ApiException as e:
            if e.status == 409:
                # Middleware exists — fetch current spec and merge user's changes (upsert)
                try:
                    existing = self._middleware_api.get(name=middleware_name, namespace=namespace)
                    existing_dict = existing.to_dict() if hasattr(existing, "to_dict") else dict(existing)
                    current_cb = (existing_dict.get("spec") or {}).get("circuitBreaker") or {}
                    # Merge: use new expression/responseCode; keep checkPeriod, fallbackDuration etc. from existing
                    circuit_spec = {**current_cb, "expression": expression, "responseCode": response_code}
                    patch_body = {"spec": {"circuitBreaker": circuit_spec}}
                    self._middleware_api.patch(
                        name=middleware_name,
                        namespace=namespace,
                        body=patch_body,
                        content_type="application/merge-patch+json",
                    )
                    return {
                        "status": "success",
                        "middleware_name": middleware_name,
                        "trigger_type": trigger_type,
                        "threshold": threshold,
                        "response_code": response_code,
                        "expression": expression,
                        "description": description,
                        "message": f"Circuit breaker updated: {description} (when open returns {response_code})",
                    }
                except Exception as patch_e:
                    raise TraefikCircuitBreakerError(f"Middleware exists but failed to update: {patch_e}")
            raise TraefikCircuitBreakerError(f"Failed to create circuit breaker: {e}")
        except TraefikCircuitBreakerError:
            raise
        except Exception as e:
            raise TraefikCircuitBreakerError(f"Failed to create circuit breaker: {e}")

    async def add_strip_prefix(
        self,
        middleware_name: str,
        namespace: str = "default",
        prefixes: Optional[List[str]] = None,
        regex_patterns: Optional[List[str]] = None,
        force_slash: bool = True,
    ) -> Dict[str, Any]:
        """Create stripPrefix or stripPrefixRegex middleware in the cluster.

        Args:
            middleware_name: Name of the middleware
            namespace: Kubernetes namespace
            prefixes: Prefixes to strip (e.g. ["/api"]). Use prefixes OR regex_patterns.
            regex_patterns: Regex for stripPrefixRegex. Use prefixes OR regex_patterns.
            force_slash: Force trailing slash after stripping (for stripPrefix only).

        Returns:
            Creation result
        """
        self._ensure_initialized()
        if not prefixes and not regex_patterns:
            raise TraefikMiddlewareError("Provide at least one of prefixes or regex_patterns")
        if prefixes and regex_patterns:
            raise TraefikMiddlewareError("Provide either prefixes OR regex_patterns, not both")

        if regex_patterns:
            spec = spec_strip_prefix_regex(regex_patterns)
            spec_key = "stripPrefixRegex"
            msg = f"stripPrefixRegex: {regex_patterns}"
        else:
            assert prefixes is not None
            spec = spec_strip_prefix(prefixes, force_slash=force_slash)
            spec_key = "stripPrefix"
            msg = f"stripPrefix: {prefixes}, forceSlash={force_slash}"

        try:
            body = build_middleware_crd(
                middleware_name,
                namespace,
                spec,
                labels={"managed-by": "traefik-mcp-server"},
            )
            self._upsert_middleware_body(body, namespace)
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "middleware_type": spec_key,
                "namespace": namespace,
                "message": msg,
            }
        except TraefikMiddlewareError:
            raise
        except Exception as e:
            raise TraefikMiddlewareError(f"Failed to upsert strip prefix middleware: {e}") from e

    @staticmethod
    def _merge_source_ranges(
        source_ranges: Optional[List[str]] = None,
        source_ranges_csv: Optional[str] = None,
    ) -> List[str]:
        out: List[str] = []
        if source_ranges:
            for s in source_ranges:
                out.extend([x.strip() for x in str(s).split(",") if x.strip()])
        if source_ranges_csv and str(source_ranges_csv).strip():
            out.extend(
                [x.strip() for x in str(source_ranges_csv).split(",") if x.strip()]
            )
        return out

    async def add_redirect_scheme(
        self,
        middleware_name: str,
        namespace: str = "default",
        permanent: bool = True,
    ) -> Dict[str, Any]:
        self._ensure_initialized()
        try:
            body = build_middleware_crd(
                middleware_name, namespace, spec_redirect_scheme(permanent=permanent)
            )
            self._upsert_middleware_body(body, namespace)
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "namespace": namespace,
                "message": f"redirectScheme: https, permanent={permanent}",
            }
        except TraefikMiddlewareError:
            raise
        except Exception as e:
            raise TraefikMiddlewareError(f"Failed to upsert redirectScheme: {e}") from e

    async def add_inflight_req(
        self,
        middleware_name: str,
        namespace: str = "default",
        amount: int = 10,
    ) -> Dict[str, Any]:
        self._ensure_initialized()
        if amount < 1:
            raise TraefikMiddlewareError("inFlightReq amount must be >= 1")
        try:
            body = build_middleware_crd(
                middleware_name, namespace, spec_inflight_req(amount)
            )
            self._upsert_middleware_body(body, namespace)
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "namespace": namespace,
                "message": f"inFlightReq: amount={amount}",
            }
        except TraefikMiddlewareError:
            raise
        except Exception as e:
            raise TraefikMiddlewareError(f"Failed to upsert inFlightReq: {e}") from e

    async def add_headers_middleware(
        self,
        middleware_name: str,
        namespace: str = "default",
        *,
        access_control_allow_origin_list: Optional[List[str]] = None,
        access_control_allow_methods: Optional[List[str]] = None,
        access_control_allow_headers: Optional[List[str]] = None,
        access_control_allow_credentials: Optional[bool] = None,
        access_control_max_age: Optional[int] = None,
        access_control_expose_headers: Optional[List[str]] = None,
        custom_request_headers: Optional[Dict[str, str]] = None,
        custom_response_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        self._ensure_initialized()
        spec = spec_headers_block(
            access_control_allow_origin_list=access_control_allow_origin_list,
            access_control_allow_methods=access_control_allow_methods,
            access_control_allow_headers=access_control_allow_headers,
            access_control_allow_credentials=access_control_allow_credentials,
            access_control_max_age=access_control_max_age,
            access_control_expose_headers=access_control_expose_headers,
            custom_request_headers=custom_request_headers,
            custom_response_headers=custom_response_headers,
        )
        inner = spec.get("headers") or {}
        if not inner:
            raise TraefikMiddlewareError(
                "headers middleware requires at least one CORS or custom header field"
            )
        try:
            body = build_middleware_crd(middleware_name, namespace, spec)
            self._upsert_middleware_body(body, namespace)
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "namespace": namespace,
                "message": "headers middleware upserted",
            }
        except TraefikMiddlewareError:
            raise
        except Exception as e:
            raise TraefikMiddlewareError(f"Failed to upsert headers middleware: {e}") from e

    async def add_ip_allowlist(
        self,
        middleware_name: str,
        namespace: str = "default",
        source_ranges: Optional[List[str]] = None,
        source_ranges_csv: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_initialized()
        ranges = self._merge_source_ranges(source_ranges, source_ranges_csv)
        if not ranges:
            raise TraefikMiddlewareError("ip_allowlist requires source_ranges or source_ranges_csv")
        try:
            body = build_middleware_crd(
                middleware_name, namespace, spec_ip_allowlist(ranges)
            )
            self._upsert_middleware_body(body, namespace)
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "namespace": namespace,
                "message": f"ipAllowList: {len(ranges)} source range(s)",
            }
        except TraefikMiddlewareError:
            raise
        except Exception as e:
            raise TraefikMiddlewareError(f"Failed to upsert ipAllowList: {e}") from e

    async def add_ip_denylist(
        self,
        middleware_name: str,
        namespace: str = "default",
        source_ranges: Optional[List[str]] = None,
        source_ranges_csv: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_initialized()
        ranges = self._merge_source_ranges(source_ranges, source_ranges_csv)
        if not ranges:
            raise TraefikMiddlewareError("ip_denylist requires source_ranges or source_ranges_csv")
        try:
            body = build_middleware_crd(
                middleware_name, namespace, spec_ip_denylist(ranges)
            )
            self._upsert_middleware_body(body, namespace)
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "namespace": namespace,
                "message": f"ipDenyList: {len(ranges)} source range(s)",
            }
        except TraefikMiddlewareError:
            raise
        except Exception as e:
            raise TraefikMiddlewareError(f"Failed to upsert ipDenyList: {e}") from e

    async def add_forward_auth(
        self,
        middleware_name: str,
        namespace: str = "default",
        address: str = "",
        auth_response_headers: Optional[List[str]] = None,
        trust_forward_header: bool = True,
        auth_request_headers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        self._ensure_initialized()
        addr = (address or "").strip()
        if not addr:
            raise TraefikMiddlewareError("forward_auth requires address")
        try:
            body = build_middleware_crd(
                middleware_name,
                namespace,
                spec_forward_auth(
                    addr,
                    auth_response_headers=auth_response_headers,
                    trust_forward_header=trust_forward_header,
                    auth_request_headers=auth_request_headers,
                ),
            )
            self._upsert_middleware_body(body, namespace)
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "namespace": namespace,
                "message": f"forwardAuth: {addr}",
            }
        except TraefikMiddlewareError:
            raise
        except Exception as e:
            raise TraefikMiddlewareError(f"Failed to upsert forwardAuth: {e}") from e

    async def add_buffering(
        self,
        middleware_name: str,
        namespace: str = "default",
        max_request_body_bytes: int = 0,
        mem_request_body_bytes: Optional[int] = None,
        max_response_body_bytes: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._ensure_initialized()
        if max_request_body_bytes < 1:
            raise TraefikMiddlewareError("buffering requires max_request_body_bytes >= 1")
        try:
            body = build_middleware_crd(
                middleware_name,
                namespace,
                spec_buffering(
                    max_request_body_bytes,
                    mem_request_body_bytes=mem_request_body_bytes,
                    max_response_body_bytes=max_response_body_bytes,
                ),
            )
            self._upsert_middleware_body(body, namespace)
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "namespace": namespace,
                "message": f"buffering: maxRequestBodyBytes={max_request_body_bytes}",
            }
        except TraefikMiddlewareError:
            raise
        except Exception as e:
            raise TraefikMiddlewareError(f"Failed to upsert buffering: {e}") from e

    async def add_replace_path(
        self,
        middleware_name: str,
        namespace: str = "default",
        path: str = "",
    ) -> Dict[str, Any]:
        self._ensure_initialized()
        p = (path or "").strip()
        if not p:
            raise TraefikMiddlewareError("replace_path requires path")
        try:
            body = build_middleware_crd(
                middleware_name, namespace, spec_replace_path(p)
            )
            self._upsert_middleware_body(body, namespace)
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "namespace": namespace,
                "message": f"replacePath: {p}",
            }
        except TraefikMiddlewareError:
            raise
        except Exception as e:
            raise TraefikMiddlewareError(f"Failed to upsert replacePath: {e}") from e

    async def add_replace_path_regex(
        self,
        middleware_name: str,
        namespace: str = "default",
        regex: str = "",
        replacement: str = "",
    ) -> Dict[str, Any]:
        self._ensure_initialized()
        rx = (regex or "").strip()
        repl = replacement  # allow empty replacement
        if not rx:
            raise TraefikMiddlewareError("replace_path_regex requires regex")
        try:
            body = build_middleware_crd(
                middleware_name,
                namespace,
                spec_replace_path_regex(rx, repl),
            )
            self._upsert_middleware_body(body, namespace)
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "namespace": namespace,
                "message": "replacePathRegex upserted",
            }
        except TraefikMiddlewareError:
            raise
        except Exception as e:
            raise TraefikMiddlewareError(f"Failed to upsert replacePathRegex: {e}") from e

    async def add_prefix_middleware(
        self,
        middleware_name: str,
        namespace: str = "default",
        prefix: str = "",
    ) -> Dict[str, Any]:
        self._ensure_initialized()
        p = (prefix or "").strip()
        if not p:
            raise TraefikMiddlewareError("add_prefix requires prefix")
        if not p.startswith("/"):
            p = f"/{p}"
        try:
            body = build_middleware_crd(
                middleware_name, namespace, spec_add_prefix(p)
            )
            self._upsert_middleware_body(body, namespace)
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "namespace": namespace,
                "message": f"addPrefix: {p}",
            }
        except TraefikMiddlewareError:
            raise
        except Exception as e:
            raise TraefikMiddlewareError(f"Failed to upsert addPrefix: {e}") from e

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
        
        # Validate percent; 0 means disable
        if mirror_percent < 0 or mirror_percent > 100:
            raise TraefikMirroringError("Mirror percentage must be between 0 and 100")
        if mirror_percent == 0:
            return await self.disable_traffic_mirroring(route_name=route_name, namespace=namespace)

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

    async def disable_traffic_mirroring(
        self,
        route_name: str,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        """Disable traffic mirroring by deleting the mirror TraefikService.

        Args:
            route_name: Name of the route (mirror TraefikService is {route_name}-mirror)
            namespace: Kubernetes namespace

        Returns:
            Deletion result
        """
        self._ensure_initialized()
        mirror_name = f"{route_name}-mirror"
        try:
            self._traefikservice_api.delete(
                name=mirror_name,
                namespace=namespace,
            )
            return {
                "status": "success",
                "route_name": route_name,
                "deleted_service": mirror_name,
                "message": f"Traffic mirroring disabled (deleted {mirror_name})",
            }
        except ApiException as e:
            if e.status == 404:
                raise TraefikMirroringError(f"Mirror service '{mirror_name}' not found")
            raise TraefikMirroringError(f"Failed to disable mirroring: {e}")
        except TraefikMirroringError:
            raise
        except Exception as e:
            raise TraefikMirroringError(f"Failed to disable mirroring: {e}")

    async def update_mirroring_percent(
        self,
        route_name: str,
        namespace: str = "default",
        mirror_percent: int = 20,
    ) -> Dict[str, Any]:
        """Update the mirror percentage on an existing mirror TraefikService.

        Args:
            route_name: Name of the route
            namespace: Kubernetes namespace
            mirror_percent: New percentage (0-100). Use 0 to disable (deletes the service).

        Returns:
            Update result
        """
        self._ensure_initialized()
        if mirror_percent == 0:
            return await self.disable_traffic_mirroring(route_name=route_name, namespace=namespace)
        if mirror_percent < 1 or mirror_percent > 100:
            raise TraefikMirroringError("Mirror percentage must be between 1 and 100")
        mirror_name = f"{route_name}-mirror"
        try:
            ts = self._traefikservice_api.get(name=mirror_name, namespace=namespace)
            ts_dict = ts.to_dict()
            mirroring_spec = ts_dict.get("spec", {}).get("mirroring", {})
            mirrors = list(mirroring_spec.get("mirrors", []))
            if not mirrors:
                raise TraefikMirroringError(f"No mirrors found in {mirror_name}")
            mirrors[0] = dict(mirrors[0])
            mirrors[0]["percent"] = mirror_percent
            patch_body = {"spec": {"mirroring": {**mirroring_spec, "mirrors": mirrors}}}
            self._traefikservice_api.patch(
                body=patch_body,
                content_type="application/merge-patch+json",
                name=mirror_name,
                namespace=namespace,
            )
            return {
                "status": "success",
                "route_name": route_name,
                "mirror_percent": mirror_percent,
                "message": f"Mirroring updated to {mirror_percent}%",
            }
        except ApiException as e:
            if e.status == 404:
                raise TraefikMirroringError(f"Mirror service '{mirror_name}' not found")
            raise TraefikMirroringError(f"Failed to update mirroring: {e}")
        except TraefikMirroringError:
            raise
        except Exception as e:
            raise TraefikMirroringError(f"Failed to update mirroring: {e}")

    def _ensure_tcp_available(self) -> None:
        """Ensure TCP CRDs are available."""
        if not self._ingressroutetcp_api or not self._middlewaretcp_api:
            raise KubernetesResourceError(
                "Traefik IngressRouteTCP or MiddlewareTCP CRD not found. "
                "Ensure Traefik is installed with TCP support."
            )

    async def create_ingress_route_tcp(
        self,
        route_name: str,
        service_name: str,
        service_port: int,
        namespace: str = "default",
        entry_points: Optional[List[str]] = None,
        sni_match: Optional[str] = None,
        tls_passthrough: bool = False,
        tls_secret_name: Optional[str] = None,
        middlewares: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create an IngressRouteTCP for TCP routing (e.g. PostgreSQL, Redis).

        Args:
            route_name: IngressRouteTCP name
            service_name: Backend K8s Service name
            service_port: Backend service port
            namespace: Kubernetes namespace
            entry_points: TCP entry points (default: ["postgresql"])
            sni_match: HostSNI match ("*" for catch-all)
            tls_passthrough: Forward TLS to backend
            tls_secret_name: TLS secret for termination
            middlewares: MiddlewareTCP names

        Returns:
            Creation result
        """
        self._ensure_initialized()
        self._ensure_tcp_available()
        if entry_points is None:
            entry_points = ["postgresql"]
        match_rule = f"HostSNI(`{sni_match or '*'}`)"
        route_spec: Dict[str, Any] = {
            "match": match_rule,
            "kind": "Rule",
            "services": [{"name": service_name, "port": service_port}],
        }
        if middlewares:
            route_spec["middlewares"] = [{"name": mw, "namespace": namespace} for mw in middlewares]
        spec: Dict[str, Any] = {"entryPoints": entry_points, "routes": [route_spec]}
        if tls_passthrough:
            spec["tls"] = {"passthrough": True}
        elif tls_secret_name:
            spec["tls"] = {"secretName": tls_secret_name}
        body = {
            "apiVersion": "traefik.io/v1alpha1",
            "kind": "IngressRouteTCP",
            "metadata": {
                "name": route_name,
                "namespace": namespace,
                "labels": {"managed-by": "traefik-mcp-server"},
            },
            "spec": spec,
        }
        try:
            self._ingressroutetcp_api.create(body=body, namespace=namespace)
            return {
                "status": "success",
                "route_name": route_name,
                "namespace": namespace,
                "service_name": service_name,
                "service_port": service_port,
                "sni_match": sni_match or "*",
                "message": f"TCP route {route_name} created",
            }
        except ApiException as e:
            if e.status == 409:
                try:
                    self._ingressroutetcp_api.patch(
                        name=route_name,
                        namespace=namespace,
                        body={"spec": spec},
                        content_type="application/merge-patch+json"
                    )
                    return {
                        "status": "success",
                        "route_name": route_name,
                        "namespace": namespace,
                        "service_name": service_name,
                        "service_port": service_port,
                        "sni_match": sni_match or "*",
                        "message": f"TCP route {route_name} updated",
                    }
                except Exception as patch_e:
                    raise TraefikServiceError(f"IngressRouteTCP '{route_name}' exists but failed to update: {patch_e}")
            raise TraefikServiceError(f"Failed to create/update IngressRouteTCP: {e}")

    async def delete_ingress_route_tcp(
        self,
        route_name: str,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        """Delete an IngressRouteTCP."""
        self._ensure_initialized()
        self._ensure_tcp_available()
        try:
            self._ingressroutetcp_api.delete(name=route_name, namespace=namespace)
            return {
                "status": "success",
                "route_name": route_name,
                "message": f"IngressRouteTCP {route_name} deleted",
            }
        except ApiException as e:
            if e.status == 404:
                raise TraefikRouteNotFoundError(f"IngressRouteTCP '{route_name}' not found")
            raise TraefikServiceError(f"Failed to delete IngressRouteTCP: {e}")

    async def create_middleware_tcp_ip_allowlist(
        self,
        middleware_name: str,
        source_ranges: List[str],
        namespace: str = "default",
    ) -> Dict[str, Any]:
        """Create a MiddlewareTCP with ipAllowList for TCP IP restriction.

        Args:
            middleware_name: MiddlewareTCP name
            source_ranges: Allowed IPs/CIDRs
            namespace: Kubernetes namespace

        Returns:
            Creation result
        """
        self._ensure_initialized()
        self._ensure_tcp_available()
        if not source_ranges:
            raise TraefikMiddlewareError("source_ranges is required")
        body = {
            "apiVersion": "traefik.io/v1alpha1",
            "kind": "MiddlewareTCP",
            "metadata": {
                "name": middleware_name,
                "namespace": namespace,
                "labels": {"managed-by": "traefik-mcp-server"},
            },
            "spec": {"ipAllowList": {"sourceRange": source_ranges}},
        }
        try:
            self._middlewaretcp_api.create(body=body, namespace=namespace)
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "namespace": namespace,
                "source_ranges": source_ranges,
                "message": f"MiddlewareTCP {middleware_name} created",
            }
        except ApiException as e:
            if e.status == 409:
                try:
                    self._middlewaretcp_api.patch(
                        name=middleware_name,
                        namespace=namespace,
                        body={"spec": body["spec"]},
                        content_type="application/merge-patch+json"
                    )
                    return {
                        "status": "success",
                        "middleware_name": middleware_name,
                        "namespace": namespace,
                        "source_ranges": source_ranges,
                        "message": f"MiddlewareTCP {middleware_name} updated",
                    }
                except Exception as patch_e:
                    raise TraefikMiddlewareError(f"MiddlewareTCP '{middleware_name}' exists but failed to update: {patch_e}")
            raise TraefikMiddlewareError(f"Failed to create/update MiddlewareTCP: {e}")

    async def delete_middleware_tcp(
        self,
        middleware_name: str,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        """Delete a MiddlewareTCP."""
        self._ensure_initialized()
        self._ensure_tcp_available()
        try:
            self._middlewaretcp_api.delete(name=middleware_name, namespace=namespace)
            return {
                "status": "success",
                "middleware_name": middleware_name,
                "message": f"MiddlewareTCP {middleware_name} deleted",
            }
        except ApiException as e:
            if e.status == 404:
                raise TraefikMiddlewareError(f"MiddlewareTCP '{middleware_name}' not found")
            raise TraefikMiddlewareError(f"Failed to delete MiddlewareTCP: {e}")

    async def inspect_route(
        self,
        route_name: str,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        """Comprehensive inspection of a Traefik route in one call.

        Fetches and combines:
        - IngressRoute: hostname, entrypoints, match rule, attached middlewares
        - TraefikService weights: stable/canary split with percentages
        - Middleware CRD specs for every attached middleware (rate limit, circuit breaker, etc.)
        - Best-effort: which Argo Rollout (if any) is linked to this TraefikService

        Args:
            route_name: IngressRoute name (TraefikService is inferred as {route_name}-wrr)
            namespace: Kubernetes namespace

        Returns:
            Combined inspection result

        Raises:
            TraefikRouteNotFoundError: If neither IngressRoute nor TraefikService found
        """
        self._ensure_initialized()

        result: Dict[str, Any] = {
            "status": "success",
            "route_name": route_name,
            "namespace": namespace,
            "timestamp": datetime.now().isoformat(),
            "ingress_route": None,
            "traffic_split": None,
            "middlewares": [],
            "linked_rollout": None,
        }

        # ── 1. IngressRoute ──────────────────────────────────────────────────
        middleware_names: list = []
        traefikservice_name = f"{route_name}-wrr"
        try:
            ir = self._ingressroute_api.get(name=route_name, namespace=namespace)
            ir_dict = ir.to_dict()
            routes = ir_dict.get("spec", {}).get("routes", [])
            # Collect middleware refs from all route rules
            for r in routes:
                for mw in r.get("middlewares") or []:
                    mw_name = mw.get("name")
                    if mw_name and mw_name not in middleware_names:
                        middleware_names.append(mw_name)

            active_backends = []
            for r in routes:
                if "services" in r:
                    active_backends = r["services"]
                    break

            for s in active_backends:
                if s.get("kind") == "TraefikService":
                    traefikservice_name = s.get("name")
                    break

            first_route = routes[0] if routes else {}
            result["ingress_route"] = {
                "hostname": ir_dict.get("spec", {}).get("routes", [{}])[0].get("match", ""),
                "match": first_route.get("match", ""),
                "entrypoints": ir_dict.get("spec", {}).get("entryPoints", []),
                "middlewares_attached": middleware_names,
                "active_backends": active_backends,
            }
        except Exception:
            # IngressRoute might not exist — still try TraefikService
            result["ingress_route"] = {"error": f"IngressRoute '{route_name}' not found"}

        # ── 2. TraefikService weights ─────────────────────────────────────────
        try:
            svc = self._traefikservice_api.get(name=traefikservice_name, namespace=namespace)
            svc_dict = svc.to_dict()
            spec = svc_dict.get("spec", {})
            
            if "weighted" in spec:
                backends_raw = spec.get("weighted", {}).get("services", [])
                total_weight = sum(b.get("weight", 0) for b in backends_raw)
                weights_present = any("weight" in b for b in backends_raw)
                argo_managed = not weights_present

                backends = []
                for b in backends_raw:
                    w = b.get("weight", None)
                    pct = (w / total_weight * 100) if (total_weight and w is not None) else None
                    backends.append({
                        "service": b.get("name"),
                        "port": b.get("port"),
                        "weight": w,
                        "percent": round(pct, 1) if pct is not None else "(argo-managed)",
                    })

                result["traffic_split"] = {
                    "traefik_service": traefikservice_name,
                    "type": "weighted",
                    "argo_managed": argo_managed,
                    "total_weight": total_weight if weights_present else "(argo-managed)",
                    "backends": backends,
                }
            elif "mirroring" in spec:
                mirroring = spec.get("mirroring", {})
                main_name = mirroring.get("name")
                mirrors = mirroring.get("mirrors", [])
                
                backends = [
                    {
                        "service": main_name,
                        "port": mirroring.get("port"),
                        "is_main": True,
                        "mirror_percent": "(main-traffic-sink)"
                    }
                ]
                for m in mirrors:
                    backends.append({
                        "service": m.get("name"),
                        "port": m.get("port"),
                        "is_main": False,
                        "mirror_percent": m.get("percent")
                    })
                    
                result["traffic_split"] = {
                    "traefik_service": traefikservice_name,
                    "type": "mirror",
                    "main_service": main_name,
                    "backends": backends
                }
            else:
                result["traffic_split"] = {"error": f"Unknown TraefikService type for '{traefikservice_name}'"}
        except ApiException as e:
            if e.status == 404:
                result["traffic_split"] = {"error": f"TraefikService '{traefikservice_name}' not found"}
            else:
                result["traffic_split"] = {"error": str(e)}
        except Exception as e:
            result["traffic_split"] = {"error": str(e)}

        # ── 3. Resolve middleware specs ───────────────────────────────────────
        for mw_name in middleware_names:
            try:
                mw_obj = self._middleware_api.get(name=mw_name, namespace=namespace)
                mw_dict = mw_obj.to_dict()
                spec = mw_dict.get("spec", {})
                # Detect type from top-level spec key
                mw_type = next(iter(spec), "unknown")
                result["middlewares"].append({
                    "name": mw_name,
                    "type": mw_type,
                    "spec": spec.get(mw_type, spec),
                })
            except Exception as e:
                result["middlewares"].append({
                    "name": mw_name,
                    "type": "unknown",
                    "error": f"Could not fetch spec: {e}",
                })

        # ── 4. Best-effort: find linked Rollout ───────────────────────────────
        try:
            rollout_api = self._dyn_client.resources.get(
                api_version="argoproj.io/v1alpha1",
                kind="Rollout"
            )
            rollouts = rollout_api.get(namespace=namespace)
            for ro in rollouts.get("items", []):
                strategy = (ro.get("spec") or {}).get("strategy") or {}
                canary = strategy.get("canary") or {}
                tr = canary.get("trafficRouting") or {}
                traefik_cfg = tr.get("traefik") or {}
                if traefik_cfg.get("weightedTraefikServiceName") == traefikservice_name:
                    result["linked_rollout"] = (ro.get("metadata") or {}).get("name")
                    break
        except Exception:
            result["linked_rollout"] = "(could not check)"

        return result

    # Keep old name as alias for backward compatibility
    async def get_service_traffic_distribution(self, route_name: str, namespace: str = "default") -> Dict[str, Any]:
        """Deprecated alias — use inspect_route instead."""
        return await self.inspect_route(route_name=route_name, namespace=namespace)


    async def list_traefik_services(
        self,
        namespace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List TraefikService CRDs — one namespace or cluster-wide.

        Args:
            namespace: Kubernetes namespace, or None to list across ALL namespaces.

        Returns:
            Dict with 'services' list, each entry has name, namespace, type,
            backends, argo_managed flag, and labels.
        """
        self._ensure_initialized()

        try:
            if namespace:
                result = self._traefikservice_api.get(namespace=namespace)
            else:
                # Omitting namespace triggers a cluster-wide list
                result = self._traefikservice_api.get()
            # Convert ResourceInstance objects → plain dicts so they are JSON-serializable
            raw_items = result.get("items", [])
            items = [i.to_dict() if hasattr(i, "to_dict") else dict(i) for i in raw_items]
        except Exception as exc:
            raise TraefikOperationError(f"Failed to list TraefikServices: {exc}")

        services_summary = []
        for item in items:
            meta = item.get("metadata", {}) or {}
            spec = item.get("spec", {}) or {}
            name = meta.get("name", "unknown")
            item_ns = meta.get("namespace", namespace or "unknown")

            # Detect type
            if "weighted" in spec:
                svc_type = "weighted"
                weighted = spec.get("weighted") or {}
                backends_raw = weighted.get("services") or []
                total_weight = sum(b.get("weight", 0) or 0 for b in backends_raw)
                # If no weights specified at all, Argo is managing them
                weights_present = any("weight" in b for b in backends_raw)
                argo_managed = not weights_present

                backends = []
                for b in backends_raw:
                    w = b.get("weight", None)
                    pct = (w / total_weight * 100) if (total_weight and w is not None) else None
                    backends.append({
                        "service": b.get("name"),
                        "port": b.get("port"),
                        "weight": w,
                        "percent": round(pct, 1) if pct is not None else None,
                    })
            elif "mirroring" in spec:
                svc_type = "mirror"
                argo_managed = False
                mirroring = spec.get("mirroring") or {}
                mirrors = mirroring.get("mirrors") or []
                
                main_service = mirroring.get("name")
                main_port = mirroring.get("port")
                
                backends = [
                    {
                        "service": m.get("name"),
                        "port": m.get("port"),
                        "mirror_percent": m.get("percent"),
                    }
                    for m in mirrors
                ]
            else:
                svc_type = "unknown"
                argo_managed = False
                backends = []

            # Ensure labels is always a plain dict (never None or ResourceField)
            raw_labels = meta.get("labels") or {}
            labels = dict(raw_labels) if raw_labels else {}

            entry = {
                "name": name,
                "namespace": item_ns,
                "type": svc_type,
                "argo_managed": argo_managed,
            }
            if svc_type == "mirror":
                entry["main_service"] = main_service
                entry["main_port"] = main_port
                entry["mirrors"] = backends
            else:
                entry["backends"] = backends
            entry["labels"] = labels

            services_summary.append(entry)

        return {
            "status": "success",
            "scope": "all-namespaces" if not namespace else namespace,
            "count": len(services_summary),
            "services": services_summary,
        }

    async def list_ingress_routes(
        self,
        namespace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List IngressRoute CRDs — one namespace or cluster-wide.

        Args:
            namespace: Kubernetes namespace, or None to list across ALL namespaces.

        Returns:
            Dict with 'ingress_routes' list, each entry has name, namespace, entryPoints, TLS, and route rules.
        """
        self._ensure_initialized()

        try:
            if namespace:
                result = self._ingressroute_api.get(namespace=namespace)
            else:
                result = self._ingressroute_api.get()
            
            raw_items = result.get("items", [])
            items = [i.to_dict() if hasattr(i, "to_dict") else dict(i) for i in raw_items]
        except Exception as exc:
            raise TraefikOperationError(f"Failed to list IngressRoutes: {exc}")

        routes_summary = []
        for item in items:
            meta = item.get("metadata", {}) or {}
            spec = item.get("spec", {}) or {}
            name = meta.get("name", "unknown")
            item_ns = meta.get("namespace", namespace or "unknown")

            entry_points = spec.get("entryPoints", [])
            tlsEnabled = "tls" in spec

            routes = []
            for r in spec.get("routes", []):
                match = r.get("match", "")
                r_services = r.get("services", [])
                r_middlewares = r.get("middlewares", [])
                targets = []
                for s in r_services:
                    targets.append({
                        "name": s.get("name"),
                        "kind": s.get("kind", "Service"),
                        "port": s.get("port")
                    })
                routes.append({
                    "match": match,
                    "targets": targets,
                    "middlewares": [{"name": m.get("name"), "namespace": m.get("namespace", item_ns)} for m in r_middlewares] if r_middlewares else []
                })

            raw_labels = meta.get("labels") or {}
            labels = dict(raw_labels) if raw_labels else {}

            routes_summary.append({
                "name": name,
                "namespace": item_ns,
                "entryPoints": entry_points,
                "tlsEnabled": tlsEnabled,
                "routes": routes,
                "labels": labels,
            })

        return {
            "status": "success",
            "scope": "all-namespaces" if not namespace else namespace,
            "count": len(routes_summary),
            "ingress_routes": routes_summary,
        }

    async def list_tcp_routes(
        self,
        namespace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List IngressRouteTCP CRDs — one namespace or cluster-wide."""
        self._ensure_initialized()
        if not self._ingressroutetcp_api:
            raise TraefikOperationError("IngressRouteTCP CRD missing")

        try:
            if namespace:
                result = self._ingressroutetcp_api.get(namespace=namespace)
            else:
                result = self._ingressroutetcp_api.get()
            
            raw_items = result.get("items", [])
            items = [i.to_dict() if hasattr(i, "to_dict") else dict(i) for i in raw_items]
        except Exception as exc:
            raise TraefikOperationError(f"Failed to list IngressRouteTCPs: {exc}")

        routes_summary = []
        mw_cache = {}
        for item in items:
            meta = item.get("metadata", {}) or {}
            spec = item.get("spec", {}) or {}
            name = meta.get("name", "unknown")
            item_ns = meta.get("namespace", namespace or "unknown")

            entry_points = spec.get("entryPoints", [])
            tlsEnabled = "tls" in spec

            routes = []
            for r in spec.get("routes", []):
                match = r.get("match", "")
                r_services = r.get("services", [])
                targets = []
                for s in r_services:
                    targets.append({
                        "name": s.get("name"),
                        "port": s.get("port"),
                        "weight": s.get("weight")
                    })
                r_middlewares = r.get("middlewares", [])
                middlewares = []
                if r_middlewares:
                    for m in r_middlewares:
                        mw_name = m.get("name")
                        mw_ns = m.get("namespace", item_ns)
                        mw_key = f"{mw_ns}/{mw_name}"
                        mw_info = {"name": mw_name, "namespace": mw_ns}
                        
                        if mw_key not in mw_cache:
                            try:
                                if self._middlewaretcp_api:
                                    mw_obj = self._middlewaretcp_api.get(name=mw_name, namespace=mw_ns)
                                    mw_spec = mw_obj.get("spec", {}) if isinstance(mw_obj, dict) else mw_obj.to_dict().get("spec", {})
                                    mw_cache[mw_key] = mw_spec
                                else:
                                    mw_cache[mw_key] = None
                            except Exception:
                                mw_cache[mw_key] = None
                        
                        if mw_cache.get(mw_key):
                            ip_allow_list = mw_cache[mw_key].get("ipAllowList", {})
                            if "sourceRange" in ip_allow_list:
                                mw_info["sourceRange"] = ip_allow_list["sourceRange"]
                        middlewares.append(mw_info)
                        
                routes.append({
                    "match": match,
                    "targets": targets,
                    "middlewares": middlewares
                })

            raw_labels = meta.get("labels") or {}
            labels = dict(raw_labels) if raw_labels else {}

            routes_summary.append({
                "name": name,
                "namespace": item_ns,
                "entryPoints": entry_points,
                "tlsEnabled": tlsEnabled,
                "routes": routes,
                "labels": labels,
            })

        return {
            "status": "success",
            "scope": "all-namespaces" if not namespace else namespace,
            "count": len(routes_summary),
            "tcp_routes": routes_summary,
        }

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

    async def attach_middleware_to_route(
        self,
        route_name: str,
        middleware_names: List[str],
        namespace: str = "default",
        traefik_version: str = "v3",
        route_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Attach one or more middlewares to an existing IngressRoute.

        Fetches the IngressRoute, merges the middleware references into every
        route rule (or only the specified rule index), and patches the resource
        back to the cluster. Idempotent — skips middlewares that are already
        attached.

        Args:
            route_name: IngressRoute name
            middleware_names: List of Middleware names to attach (same namespace)
            namespace: Kubernetes namespace
            traefik_version: 'v3' (traefik.io) or 'v2' (traefik.containo.us)
            route_index: If specified, attach only to that route rule (0-indexed).
                         If None, attaches to all route rules.

        Returns:
            Dict with keys: route_name, middleware_names, routes_updated (int),
            middlewares_already_present (list), status

        Raises:
            TraefikRouteNotFoundError: If IngressRoute doesn't exist
            TraefikOperationError: If patch fails
        """
        self._ensure_initialized()

        api_group = "traefik.io" if traefik_version == "v3" else "traefik.containo.us"

        try:
            ir_api = self._dyn_client.resources.get(
                api_version=f"{api_group}/v1alpha1",
                kind="IngressRoute"
            )
            ir_obj = ir_api.get(name=route_name, namespace=namespace)
        except Exception as exc:
            if "not found" in str(exc).lower() or "404" in str(exc):
                raise TraefikRouteNotFoundError(
                    f"IngressRoute '{route_name}' not found in namespace '{namespace}'"
                )
            raise TraefikOperationError(f"Failed to fetch IngressRoute: {exc}")

        routes = ir_obj.to_dict()["spec"].get("routes", [])
        routes_updated = 0
        already_present: list = []

        target_indices = (
            [route_index] if route_index is not None else range(len(routes))
        )

        for idx in target_indices:
            if idx >= len(routes):
                continue
            existing_mw = routes[idx].get("middlewares") or []
            existing_names = {m["name"] for m in existing_mw}

            new_refs = []
            for mw_name in middleware_names:
                if mw_name in existing_names:
                    already_present.append(mw_name)
                else:
                    new_refs.append({"name": mw_name, "namespace": namespace})

            if new_refs:
                routes[idx]["middlewares"] = existing_mw + new_refs
                routes_updated += 1

        if routes_updated == 0:
            return {
                "status": "no_change",
                "route_name": route_name,
                "middleware_names": middleware_names,
                "routes_updated": 0,
                "middlewares_already_present": already_present,
                "message": "All requested middlewares were already attached.",
            }

        # Patch back
        patch_body = {"spec": {"routes": routes}}
        try:
            ir_api.patch(
                name=route_name,
                namespace=namespace,
                body=patch_body,
                content_type="application/merge-patch+json",
            )
        except Exception as exc:
            raise TraefikOperationError(
                f"Failed to patch IngressRoute '{route_name}': {exc}"
            )

        return {
            "status": "success",
            "route_name": route_name,
            "namespace": namespace,
            "middleware_names": middleware_names,
            "routes_updated": routes_updated,
            "middlewares_already_present": already_present,
            "message": (
                f"✅ Attached {len(middleware_names)} middleware(s) to "
                f"{routes_updated} route rule(s) in IngressRoute '{route_name}'."
            ),
        }

    async def detach_middleware_from_route(
        self,
        route_name: str,
        middleware_names: List[str],
        namespace: str = "default",
        traefik_version: str = "v3",
        route_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Remove one or more middlewares from an IngressRoute.

        Fetches the IngressRoute, removes the given middleware references from
        every route rule (or only the specified rule index), and patches back.

        Args:
            route_name: IngressRoute name
            middleware_names: List of Middleware names to remove
            namespace: Kubernetes namespace
            traefik_version: 'v3' or 'v2'
            route_index: If specified, detach only from that route rule (0-indexed).

        Returns:
            Dict with route_name, middleware_names, routes_updated, status, message.
        """
        self._ensure_initialized()
        api_group = "traefik.io" if traefik_version == "v3" else "traefik.containo.us"
        to_remove = set(middleware_names)

        try:
            ir_api = self._dyn_client.resources.get(
                api_version=f"{api_group}/v1alpha1",
                kind="IngressRoute"
            )
            ir_obj = ir_api.get(name=route_name, namespace=namespace)
        except Exception as exc:
            if "not found" in str(exc).lower() or "404" in str(exc):
                raise TraefikRouteNotFoundError(
                    f"IngressRoute '{route_name}' not found in namespace '{namespace}'"
                )
            raise TraefikOperationError(f"Failed to fetch IngressRoute: {exc}")

        routes = ir_obj.to_dict()["spec"].get("routes", [])
        routes_updated = 0

        target_indices = (
            [route_index] if route_index is not None else range(len(routes))
        )

        for idx in target_indices:
            if idx >= len(routes):
                continue
            existing_mw = routes[idx].get("middlewares") or []
            new_mw = [m for m in existing_mw if m.get("name") not in to_remove]
            if len(new_mw) != len(existing_mw):
                routes[idx]["middlewares"] = new_mw
                routes_updated += 1

        if routes_updated == 0:
            return {
                "status": "no_change",
                "route_name": route_name,
                "middleware_names": list(middleware_names),
                "routes_updated": 0,
                "message": "None of the given middlewares were attached to the route.",
            }

        try:
            ir_api.patch(
                name=route_name,
                namespace=namespace,
                body={"spec": {"routes": routes}},
                content_type="application/merge-patch+json",
            )
        except Exception as exc:
            raise TraefikOperationError(
                f"Failed to patch IngressRoute '{route_name}': {exc}"
            )

        return {
            "status": "success",
            "route_name": route_name,
            "namespace": namespace,
            "middleware_names": list(middleware_names),
            "routes_updated": routes_updated,
            "message": (
                f"✅ Removed {len(middleware_names)} middleware(s) from "
                f"{routes_updated} route rule(s) in IngressRoute '{route_name}'."
            ),
        }
