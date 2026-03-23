"""Generator service for converting Deployments to Rollouts.

This service provides the bridge between standard Kubernetes Deployments
(created by ArgoCD or other CI/CD tools) and Argo Rollouts for progressive delivery.
"""
import yaml
from typing import Dict, Any, List, Optional
from kubernetes import client
from kubernetes.client.rest import ApiException

class TraefikGeneratorService:
    """Service for generating Rollout resources from Deployments."""

    def __init__(self, config=None):
        """Initialize generator service.
        
        Args:
            config: Optional server configuration
        """
        self.config = config
        self._apps_v1 = None

    def _clean_none_values(self, d):
        """Recursively remove None values from a dict."""
        if isinstance(d, dict):
            return {k: self._clean_none_values(v) for k, v in d.items() if v is not None}
        elif isinstance(d, list):
            return [self._clean_none_values(item) for item in d if item is not None]
        return d

    def _to_camel_case_keys(self, obj):
        """Convert snake_case dict keys to camelCase for K8s YAML compatibility."""
        CAMEL_MAP = {'api_version': 'apiVersion', 'match_labels': 'matchLabels', 'container_port': 'containerPort', 'readiness_probe': 'readinessProbe', 'liveness_probe': 'livenessProbe', 'startup_probe': 'startupProbe', 'initial_delay_seconds': 'initialDelaySeconds', 'period_seconds': 'periodSeconds', 'timeout_seconds': 'timeoutSeconds', 'success_threshold': 'successThreshold', 'failure_threshold': 'failureThreshold', 'http_get': 'httpGet', 'tcp_socket': 'tcpSocket', 'grpc': 'grpc', 'exec': 'exec', 'host_port': 'hostPort', 'host_ip': 'hostIP', 'image_pull_policy': 'imagePullPolicy', 'termination_message_path': 'terminationMessagePath', 'termination_message_policy': 'terminationMessagePolicy', 'dns_policy': 'dnsPolicy', 'restart_policy': 'restartPolicy', 'scheduler_name': 'schedulerName', 'termination_grace_period_seconds': 'terminationGracePeriodSeconds', 'service_account': 'serviceAccount', 'service_account_name': 'serviceAccountName', 'node_selector': 'nodeSelector', 'security_context': 'securityContext', 'run_as_user': 'runAsUser', 'run_as_group': 'runAsGroup', 'run_as_non_root': 'runAsNonRoot', 'fs_group': 'fsGroup', 'revision_history_limit': 'revisionHistoryLimit', 'progress_deadline_seconds': 'progressDeadlineSeconds', 'max_surge': 'maxSurge', 'max_unavailable': 'maxUnavailable', 'rolling_update': 'rollingUpdate', 'match_expressions': 'matchExpressions', 'claim_name': 'claimName', 'config_map': 'configMap', 'mount_path': 'mountPath', 'sub_path': 'subPath', 'read_only': 'readOnly', 'volume_mounts': 'volumeMounts', 'env_from': 'envFrom', 'value_from': 'valueFrom', 'config_map_ref': 'configMapRef', 'secret_ref': 'secretRef', 'config_map_key_ref': 'configMapKeyRef', 'secret_key_ref': 'secretKeyRef', 'field_ref': 'fieldRef', 'field_path': 'fieldPath', 'resource_field_ref': 'resourceFieldRef'}
        if isinstance(obj, dict):
            return {CAMEL_MAP.get(k, k): self._to_camel_case_keys(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._to_camel_case_keys(item) for item in obj]
        return obj

    async def create_traefik_service_for_rollout(self, app_name: str, stable_service: str, canary_service: str, namespace: str='default', initial_canary_weight: int=5, port: int=80, managed_by_argo: bool=True, traefik_version: str='v3') -> Dict[str, Any]:
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
            api_version = 'traefik.io/v1alpha1' if traefik_version == 'v3' else 'traefik.containo.us/v1alpha1'
            stable_svc = {'name': stable_service, 'port': port}
            canary_svc = {'name': canary_service, 'port': port}
            if not managed_by_argo:
                stable_svc['weight'] = stable_weight
                canary_svc['weight'] = initial_canary_weight
            traefik_service = {'apiVersion': api_version, 'kind': 'TraefikService', 'metadata': {'name': f'{app_name}-weighted', 'namespace': namespace}, 'spec': {'weighted': {'services': [stable_svc, canary_svc]}}}
            traefik_yaml = yaml.dump(traefik_service, default_flow_style=False)
            return {'status': 'success', 'service_name': f'{app_name}-weighted', 'namespace': namespace, 'stable_weight': stable_weight, 'canary_weight': initial_canary_weight, 'traefik_yaml': traefik_yaml}
        except Exception as e:
            return {'status': 'error', 'error': f'Failed to create TraefikService: {str(e)}'}

    async def create_ingress_route_for_traefik_service(self, traefik_service_name: str, hostname: str, namespace: str='default', route_name: Optional[str]=None, entry_points: Optional[List[str]]=None, path_prefix: Optional[str]=None, tls_enabled: bool=False, tls_secret_name: Optional[str]=None, traefik_version: str='v3', middlewares: Optional[List[str]]=None) -> Dict[str, Any]:
        """Generate an IngressRoute CRD pointing to a TraefikService.
        
        This completes the native Argo Rollouts + Traefik flow:
        1. TraefikService (weights omitted, managed by Argo) — create_traefik_service_for_rollout
        2. IngressRoute pointing to TraefikService — THIS METHOD
        3. Rollout with trafficRouting.traefik — argo_create_rollout
        
        Args:
            traefik_service_name: Name of the TraefikService to route to
            hostname: Hostname for routing (e.g. api.example.com)
            namespace: Kubernetes namespace
            route_name: Name of the IngressRoute (default: {traefik_service_name}-route)
            entry_points: Traefik entry points (default: ["web"])
            path_prefix: Optional path prefix match (e.g. "/api")
            tls_enabled: Whether to enable TLS
            tls_secret_name: TLS secret name (if tls_enabled)
            traefik_version: "v3" (traefik.io) or "v2" (traefik.containo.us)
            middlewares: Optional list of middleware names to attach
        
        Returns:
            Dict containing:
                - status: "success" or "error"
                - route_name: Generated IngressRoute name
                - ingress_route_yaml: IngressRoute YAML string
                - error: Error message (if failed)
        """
        try:
            if not traefik_service_name:
                raise ValueError('traefik_service_name is required')
            if not hostname:
                raise ValueError('hostname is required')
            if route_name is None:
                route_name = f'{traefik_service_name}-route'
            if entry_points is None:
                entry_points = ['web']
            api_version = 'traefik.io/v1alpha1' if traefik_version == 'v3' else 'traefik.containo.us/v1alpha1'
            match_rule = f'Host(`{hostname}`)'
            if path_prefix:
                prefix = path_prefix if path_prefix.startswith('/') else f'/{path_prefix}'
                match_rule += f' && PathPrefix(`{prefix}`)'
            route_spec: Dict[str, Any] = {'match': match_rule, 'kind': 'Rule', 'services': [{'name': traefik_service_name, 'kind': 'TraefikService'}]}
            if middlewares:
                route_spec['middlewares'] = [{'name': mw, 'namespace': namespace} for mw in middlewares]
            ingress_route: Dict[str, Any] = {'apiVersion': api_version, 'kind': 'IngressRoute', 'metadata': {'name': route_name, 'namespace': namespace, 'labels': {'managed-by': 'traefik-mcp-server'}}, 'spec': {'entryPoints': entry_points, 'routes': [route_spec]}}
            if tls_enabled:
                tls_config: Dict[str, Any] = {}
                if tls_secret_name:
                    tls_config['secretName'] = tls_secret_name
                ingress_route['spec']['tls'] = tls_config
            ingress_route_yaml = yaml.dump(ingress_route, default_flow_style=False)
            return {'status': 'success', 'route_name': route_name, 'namespace': namespace, 'hostname': hostname, 'traefik_service_name': traefik_service_name, 'entry_points': entry_points, 'tls_enabled': tls_enabled, 'ingress_route_yaml': ingress_route_yaml}
        except Exception as e:
            return {'status': 'error', 'error': f'Failed to create IngressRoute: {str(e)}'}

    async def create_ingress_route_for_services(self, route_name: str, hostname: str, routes: List[Dict[str, Any]], namespace: str='default', entry_points: Optional[List[str]]=None, tls_enabled: bool=False, tls_secret_name: Optional[str]=None, traefik_version: str='v3') -> Dict[str, Any]:
        """Generate an IngressRoute CRD pointing to direct Kubernetes Services.
        
        Args:
            route_name: Base name for the route
            hostname: Hostname for routing (e.g., api.example.com)
            routes: List of route definitions. Each must have:
                   - path_prefix (str): URL path prefix
                   - service_name (str): Backend K8s service name
                   - service_port (int): Backend service port
                   - middlewares (Optional[List[str]]): List of middleware names
            namespace: Kubernetes namespace
            entry_points: Traefik entry points (defaults to ['web'] or ['websecure'])
            tls_enabled: Whether to enable TLS
            tls_secret_name: Name of the TLS secret (if applicable)
            traefik_version: Traefik version ("v2" or "v3") to determine apiVersion
            
        Returns:
            Dict containing generation status and YAML
        """
        try:
            if entry_points is None:
                entry_points = ['websecure'] if tls_enabled else ['web']
            api_version = 'traefik.io/v1alpha1' if traefik_version == 'v3' else 'traefik.containo.us/v1alpha1'
            ingress_route = {'apiVersion': api_version, 'kind': 'IngressRoute', 'metadata': {'name': route_name, 'namespace': namespace, 'labels': {'managed-by': 'traefik-mcp-server', 'generator': 'ingress-converter'}}, 'spec': {'entryPoints': entry_points, 'routes': []}}
            for i, route in enumerate(routes):
                path_prefix = route.get('path_prefix', '/')
                svc_name = route.get('service_name')
                svc_port = route.get('service_port', 80)
                middlewares = route.get('middlewares', [])
                if not svc_name:
                    return {'status': 'error', 'error': f"Route index {i} is missing 'service_name'"}
                match = f'Host(`{hostname}`)'
                if path_prefix and path_prefix != '/':
                    if '(' in path_prefix or '$' in path_prefix or '^' in path_prefix:
                        match += f' && PathRegexp(`{path_prefix}`)'
                    else:
                        match += f' && PathPrefix(`{path_prefix}`)'
                route_spec = {'match': match, 'kind': 'Rule', 'services': [{'name': svc_name, 'port': svc_port, 'kind': 'Service'}]}
                if middlewares:
                    route_spec['middlewares'] = [{'name': mw} for mw in middlewares]
                ingress_route['spec']['routes'].append(route_spec)
            if tls_enabled:
                tls_config = {}
                if tls_secret_name:
                    tls_config['secretName'] = tls_secret_name
                ingress_route['spec']['tls'] = tls_config
            ingress_yaml = yaml.dump(ingress_route, default_flow_style=False)
            return {'status': 'success', 'route_name': route_name, 'namespace': namespace, 'ingress_yaml': ingress_yaml}
        except Exception as e:
            return {'status': 'error', 'error': f'Failed to create IngressRoute: {str(e)}'}

    async def create_canary_header_route(self, canary_service_name: str, hostname: str, header_name: str='X-Canary', header_value: str='true', namespace: str='default', route_name: Optional[str]=None, entry_points: Optional[List[str]]=None, path_prefix: Optional[str]=None, tls_enabled: bool=False, tls_secret_name: Optional[str]=None, traefik_version: str='v3', cookie_name: Optional[str]=None, cookie_regex: Optional[str]=None, priority: int=100, port: int=80) -> Dict[str, Any]:
        """Generate a secondary IngressRoute with header/cookie-match for canary routing.
        
        This creates an IngressRoute that directs traffic matching a specific
        header (or cookie) to the canary service, while default traffic goes
        to the main IngressRoute (stable). This is the Traefik-native way to
        do header-based canary routing (setHeaderRoute is Istio-only in Argo Rollouts).
        
        Args:
            canary_service_name: K8s Service name for canary pods
            hostname: Hostname for routing
            header_name: Header name to match (default: X-Canary)
            header_value: Header value to match (default: true)
            namespace: Kubernetes namespace
            route_name: IngressRoute name (default: {canary_service}-header-route)
            entry_points: Traefik entry points (default: ["web"])
            path_prefix: Optional path prefix match
            tls_enabled: Whether to enable TLS
            tls_secret_name: TLS secret name
            traefik_version: "v3" or "v2"
            cookie_name: Optional cookie name for cookie-based routing
            cookie_regex: Optional cookie regex pattern
            priority: Route priority (higher = matched first, default: 100)
        
        Returns:
            Dict with canary IngressRoute YAML
        """
        try:
            if not canary_service_name:
                raise ValueError('canary_service_name is required')
            if not hostname:
                raise ValueError('hostname is required')
            if route_name is None:
                route_name = f'{canary_service_name}-header-route'
            if entry_points is None:
                entry_points = ['web']
            api_version = 'traefik.io/v1alpha1' if traefik_version == 'v3' else 'traefik.containo.us/v1alpha1'
            match_parts = [f'Host(`{hostname}`)']
            if path_prefix:
                prefix = path_prefix if path_prefix.startswith('/') else f'/{path_prefix}'
                match_parts.append(f'PathPrefix(`{prefix}`)')
            if cookie_name:
                if cookie_regex:
                    match_parts.append(f'HeaderRegexp(`Cookie`, `{cookie_name}={cookie_regex}`)')
                else:
                    match_parts.append(f'HeaderRegexp(`Cookie`, `.*{cookie_name}=true.*`)')
            else:
                match_parts.append(f'Header(`{header_name}`, `{header_value}`)')
            match_rule = ' && '.join(match_parts)
            route_spec: Dict[str, Any] = {'match': match_rule, 'kind': 'Rule', 'priority': priority, 'services': [{'name': canary_service_name, 'port': port}]}
            ingress_route: Dict[str, Any] = {'apiVersion': api_version, 'kind': 'IngressRoute', 'metadata': {'name': route_name, 'namespace': namespace, 'labels': {'managed-by': 'traefik-mcp-server', 'argoflow/route-type': 'canary-header'}}, 'spec': {'entryPoints': entry_points, 'routes': [route_spec]}}
            if tls_enabled:
                tls_config: Dict[str, Any] = {}
                if tls_secret_name:
                    tls_config['secretName'] = tls_secret_name
                ingress_route['spec']['tls'] = tls_config
            ingress_route_yaml = yaml.dump(ingress_route, default_flow_style=False)
            routing_type = 'cookie' if cookie_name else 'header'
            return {'status': 'success', 'route_name': route_name, 'namespace': namespace, 'hostname': hostname, 'canary_service_name': canary_service_name, 'routing_type': routing_type, 'match_rule': match_rule, 'priority': priority, 'ingress_route_yaml': ingress_route_yaml, 'note': f'This IngressRoute routes {routing_type}-matched traffic to canary. Default traffic continues to the main IngressRoute (stable).'}
        except Exception as e:
            return {'status': 'error', 'error': f'Failed to create canary header route: {str(e)}'}

    async def create_mirroring_traefik_service(
        self,
        route_name: str,
        main_service: str,
        mirror_service: str,
        mirror_percent: int = 20,
        namespace: str = 'default',
        port: int = 80,
        traefik_version: str = 'v3',
    ) -> Dict[str, Any]:
        """Generate a TraefikService with mirroring spec for shadow testing.

        Args:
            route_name: Base name (TraefikService will be {route_name}-mirror)
            main_service: Primary service receiving real traffic
            mirror_service: Service receiving mirrored traffic
            mirror_percent: Percentage of traffic to mirror (1-100)
            namespace: Kubernetes namespace
            port: Service port
            traefik_version: "v3" or "v2"

        Returns:
            Dict with TraefikService YAML
        """
        try:
            if mirror_percent < 1 or mirror_percent > 100:
                raise ValueError('mirror_percent must be between 1 and 100')
            api_version = 'traefik.io/v1alpha1' if traefik_version == 'v3' else 'traefik.containo.us/v1alpha1'
            traefik_service = {
                'apiVersion': api_version,
                'kind': 'TraefikService',
                'metadata': {
                    'name': f'{route_name}-mirror',
                    'namespace': namespace,
                    'labels': {'managed-by': 'traefik-mcp-server'},
                },
                'spec': {
                    'mirroring': {
                        'name': main_service,
                        'port': port,
                        'mirrors': [{'name': mirror_service, 'port': port, 'percent': mirror_percent}],
                    }
                },
            }
            traefik_yaml = yaml.dump(traefik_service, default_flow_style=False)
            return {
                'status': 'success',
                'service_name': f'{route_name}-mirror',
                'namespace': namespace,
                'main_service': main_service,
                'mirror_service': mirror_service,
                'mirror_percent': mirror_percent,
                'traefik_yaml': traefik_yaml,
            }
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    async def create_ingress_route_tcp(
        self,
        route_name: str,
        service_name: str,
        service_port: int,
        namespace: str = 'default',
        entry_points: Optional[List[str]] = None,
        sni_match: Optional[str] = None,
        tls_passthrough: bool = False,
        tls_secret_name: Optional[str] = None,
        middlewares: Optional[List[str]] = None,
        traefik_version: str = 'v3',
    ) -> Dict[str, Any]:
        """Generate an IngressRouteTCP CRD for TCP routing (e.g. PostgreSQL, Redis).

        Args:
            route_name: IngressRouteTCP name
            service_name: Backend K8s Service name
            service_port: Backend service port
            namespace: Kubernetes namespace
            entry_points: TCP entry points (default: ["postgresql"] or ["redis"])
            sni_match: HostSNI match (e.g. "redis.example.com" or "*" for catch-all)
            tls_passthrough: If True, forward TLS to backend without termination
            tls_secret_name: TLS secret for termination (if not passthrough)
            middlewares: MiddlewareTCP names to attach
            traefik_version: "v3" or "v2"

        Returns:
            Dict with IngressRouteTCP YAML
        """
        try:
            if entry_points is None:
                entry_points = ['postgresql']
            api_version = 'traefik.io/v1alpha1' if traefik_version == 'v3' else 'traefik.containo.us/v1alpha1'
            match_rule = f'HostSNI(`{sni_match or "*"}`)'
            route_spec: Dict[str, Any] = {
                'match': match_rule,
                'kind': 'Rule',
                'services': [{'name': service_name, 'port': service_port}],
            }
            if middlewares:
                route_spec['middlewares'] = [{'name': mw, 'namespace': namespace} for mw in middlewares]
            spec: Dict[str, Any] = {'entryPoints': entry_points, 'routes': [route_spec]}
            if tls_passthrough:
                spec['tls'] = {'passthrough': True}
            elif tls_secret_name:
                spec['tls'] = {'secretName': tls_secret_name}
            ingress_route_tcp = {
                'apiVersion': api_version,
                'kind': 'IngressRouteTCP',
                'metadata': {
                    'name': route_name,
                    'namespace': namespace,
                    'labels': {'managed-by': 'traefik-mcp-server'},
                },
                'spec': spec,
            }
            yaml_out = yaml.dump(ingress_route_tcp, default_flow_style=False)
            return {
                'status': 'success',
                'route_name': route_name,
                'namespace': namespace,
                'service_name': service_name,
                'service_port': service_port,
                'sni_match': sni_match or '*',
                'ingress_route_tcp_yaml': yaml_out,
            }
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    async def create_middleware_tcp_ip_allowlist(
        self,
        middleware_name: str,
        source_ranges: List[str],
        namespace: str = 'default',
        traefik_version: str = 'v3',
    ) -> Dict[str, Any]:
        """Generate a MiddlewareTCP with ipAllowList for TCP IP restriction.

        Args:
            middleware_name: MiddlewareTCP name
            source_ranges: Allowed IPs/CIDRs (e.g. ["192.168.1.0/24", "10.0.0.1"])
            namespace: Kubernetes namespace
            traefik_version: "v3" or "v2"

        Returns:
            Dict with MiddlewareTCP YAML
        """
        try:
            if not source_ranges:
                raise ValueError('source_ranges is required')
            api_version = 'traefik.io/v1alpha1' if traefik_version == 'v3' else 'traefik.containo.us/v1alpha1'
            middleware_tcp = {
                'apiVersion': api_version,
                'kind': 'MiddlewareTCP',
                'metadata': {
                    'name': middleware_name,
                    'namespace': namespace,
                    'labels': {'managed-by': 'traefik-mcp-server'},
                },
                'spec': {'ipAllowList': {'sourceRange': source_ranges}},
            }
            yaml_out = yaml.dump(middleware_tcp, default_flow_style=False)
            return {
                'status': 'success',
                'middleware_name': middleware_name,
                'namespace': namespace,
                'source_ranges': source_ranges,
                'middleware_tcp_yaml': yaml_out,
            }
        except Exception as e:
            return {'status': 'error', 'error': str(e)}