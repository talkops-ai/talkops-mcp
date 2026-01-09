"""Traefik middleware tools - Middleware management for traffic policies."""

from typing import Dict, Any, Optional
from pydantic import Field
from fastmcp import Context

from argoflow_mcp_server.tools.base import BaseTool
from argoflow_mcp_server.exceptions.custom import (
    TraefikOperationError,
    TraefikMiddlewareError,
    TraefikCircuitBreakerError,
    TraefikMirroringError,
    TraefikAnomalyError,
)


class MiddlewareTools(BaseTool):
    """Tools for creating and managing Traefik middleware."""
    
    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""
        
        @mcp_instance.tool()
        async def traefik_add_rate_limiting(
            middleware_name: str = Field(..., min_length=1, description='Middleware name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            average: int = Field(default=100, ge=1, le=10000, description='Average requests per period'),
            burst: int = Field(default=200, ge=1, le=20000, description='Maximum burst size'),
            period: str = Field(default='1s', description='Time period (e.g., "1s", "1m", "1h")'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Create rate limiting middleware for canary protection.
            
            Protect canary service from being overwhelmed by limiting the rate
            of incoming requests. This is especially useful during initial
            canary phases when capacity is limited.
            
            Args:
                middleware_name: Name of the middleware
                namespace: Kubernetes namespace
                average: Average requests allowed per period
                burst: Maximum burst of simultaneous requests
                period: Time period for rate calculation
            
            Returns:
                Creation result with rate limit details
            
            Raises:
                TraefikMiddlewareError: If creation fails
            
            Example configurations:
                - Light protection: average=100, burst=200, period="1s"
                - Medium protection: average=50, burst=100, period="1s"
                - Heavy protection: average=20, burst=40, period="1s"
            """
            await ctx.info(
                f"Creating rate limiting middleware '{middleware_name}': {average} req/{period}, burst {burst}",
                extra={
                    'middleware_name': middleware_name,
                    'namespace': namespace,
                    'average': average,
                    'burst': burst,
                    'period': period
                }
            )
            
            try:
                result = await self.traefik_service.add_rate_limiting(
                    middleware_name=middleware_name,
                    namespace=namespace,
                    average=average,
                    burst=burst,
                    period=period
                )
                
                await ctx.info(
                    f"Successfully created rate limiting middleware '{middleware_name}'",
                    extra={
                        'middleware_name': middleware_name,
                        'rate': f"{average} req/{period}"
                    }
                )
                
                return result
            
            except TraefikMiddlewareError as e:
                await ctx.error(f"Failed to create rate limiting: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(
                    f"Failed to create rate limiting middleware: {str(e)}",
                    extra={'middleware_name': middleware_name, 'error': str(e)}
                )
                raise TraefikOperationError(f'Rate limiting creation failed: {str(e)}')
        
        @mcp_instance.tool()
        async def traefik_add_circuit_breaker(
            middleware_name: str = Field(..., min_length=1, description='Middleware name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            trigger_type: str = Field(
                default='error-rate',
                description='Trigger type: "error-rate", "latency", or "network-error"'
            ),
            threshold: float = Field(
                default=0.30,
                ge=0.0,
                le=1.0,
                description='Threshold value (0.30 = 30% for error-rate, milliseconds for latency)'
            ),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Create circuit breaker middleware for auto-rollback.
            
            Automatically stop sending traffic to canary if error rates,
            latency, or network errors exceed thresholds. This provides
            automatic protection and rollback capability.
            
            Args:
                middleware_name: Name of the middleware
                namespace: Kubernetes namespace
                trigger_type: Type of circuit breaker trigger
                threshold: Threshold value for activation
            
            Returns:
                Creation result with circuit breaker configuration
            
            Raises:
                TraefikCircuitBreakerError: If creation fails or invalid trigger type
            
            Trigger types:
                - "error-rate": Activate when 5xx errors > threshold% (e.g., 0.30 = 30%)
                - "latency": Activate when p50 latency > threshold ms (e.g., 100 = 100ms)
                - "network-error": Activate when network errors > threshold% (e.g., 0.10 = 10%)
            
            Example configurations:
                - Conservative: error-rate, threshold=0.50 (50% errors)
                - Standard: error-rate, threshold=0.30 (30% errors)
                - Aggressive: error-rate, threshold=0.10 (10% errors)
            """
            await ctx.info(
                f"Creating circuit breaker middleware '{middleware_name}': {trigger_type} > {threshold}",
                extra={
                    'middleware_name': middleware_name,
                    'namespace': namespace,
                    'trigger_type': trigger_type,
                    'threshold': threshold
                }
            )
            
            # Validate trigger type
            valid_triggers = ['error-rate', 'latency', 'network-error']
            if trigger_type not in valid_triggers:
                error_msg = f"Invalid trigger type '{trigger_type}'. Must be one of: {', '.join(valid_triggers)}"
                await ctx.error(error_msg)
                raise TraefikCircuitBreakerError(error_msg)
            
            try:
                result = await self.traefik_service.add_circuit_breaker(
                    middleware_name=middleware_name,
                    namespace=namespace,
                    trigger_type=trigger_type,
                    threshold=threshold
                )
                
                description = result.get('description', '')
                await ctx.info(
                    f"Successfully created circuit breaker '{middleware_name}': {description}",
                    extra={
                        'middleware_name': middleware_name,
                        'trigger': trigger_type,
                        'threshold': threshold
                    }
                )
                
                return result
            
            except TraefikCircuitBreakerError as e:
                await ctx.error(f"Circuit breaker creation failed: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(
                    f"Failed to create circuit breaker: {str(e)}",
                    extra={'middleware_name': middleware_name, 'error': str(e)}
                )
                raise TraefikOperationError(f'Circuit breaker creation failed: {str(e)}')
        
        @mcp_instance.tool()
        async def traefik_enable_traffic_mirroring(
            route_name: str = Field(..., min_length=1, description='Route name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            main_service: Optional[str] = Field(
                default=None,
                description='Main service name (default: {route_name}-stable)'
            ),
            mirror_service: Optional[str] = Field(
                default=None,
                description='Mirror service name (default: {route_name}-staging)'
            ),
            mirror_percent: int = Field(
                default=20,
                ge=1,
                le=100,
                description='Percentage of traffic to mirror (1-100)'
            ),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Enable traffic mirroring for shadow testing.
            
            Copy a percentage of production traffic to a shadow/staging service
            for validation before sending real user traffic. Responses from
            mirrored service are discarded, so there's no user impact.
            
            Use cases:
            - A/B testing without affecting users
            - Canary validation before traffic shift
            - Staging environment load testing with real patterns
            
            Args:
                route_name: Name of the route
                namespace: Kubernetes namespace
                main_service: Main service receiving real traffic
                mirror_service: Service receiving mirrored traffic
                mirror_percent: Percentage of traffic to mirror
            
            Returns:
                Creation result with mirroring configuration
            
            Raises:
                TraefikMirroringError: If mirroring setup fails
            
            Example:
                Mirror 20% of production traffic to staging for validation
            """
            await ctx.info(
                f"Enabling traffic mirroring for route '{route_name}': {mirror_percent}% to mirror",
                extra={
                    'route_name': route_name,
                    'namespace': namespace,
                    'mirror_percent': mirror_percent,
                    'main_service': main_service,
                    'mirror_service': mirror_service
                }
            )
            
            try:
                result = await self.traefik_service.enable_traffic_mirroring(
                    route_name=route_name,
                    namespace=namespace,
                    main_service=main_service,
                    mirror_service=mirror_service,
                    mirror_percent=mirror_percent
                )
                
                await ctx.info(
                    f"Successfully enabled traffic mirroring for '{route_name}'",
                    extra={
                        'route_name': route_name,
                        'mirror_percent': mirror_percent,
                        'mirror_service': result.get('mirror_service')
                    }
                )
                
                return result
            
            except TraefikMirroringError as e:
                await ctx.error(f"Failed to enable traffic mirroring: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(
                    f"Failed to enable traffic mirroring: {str(e)}",
                    extra={'route_name': route_name, 'error': str(e)}
                )
                raise TraefikOperationError(f'Traffic mirroring configuration failed: {str(e)}')
        
        @mcp_instance.tool()
        async def traefik_detect_anomalies(
            route_name: str = Field(..., min_length=1, description='Route name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            threshold: float = Field(
                default=2.0,
                ge=1.0,
                le=5.0,
                description='Standard deviations for anomaly detection'
            ),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Detect traffic anomalies (Prometheus integration).
            
            Analyze traffic patterns to detect anomalies such as:
            - Sudden traffic spikes or drops
            - Unusual error rate patterns
            - Latency degradation
            
            Note: This requires Prometheus integration for full functionality.
            Currently returns a placeholder response.
            
            Args:
                route_name: Name of the route
                namespace: Kubernetes namespace
                threshold: Standard deviations for anomaly detection
            
            Returns:
                Anomaly detection results
            
            Note:
                Full implementation requires Prometheus metrics collection.
                This is a placeholder for future metrics-based detection.
            """
            await ctx.info(
                f"Detecting traffic anomalies for route '{route_name}'",
                extra={
                    'route_name': route_name,
                    'namespace': namespace,
                    'threshold': threshold
                }
            )
            
            try:
                result = await self.traefik_service.detect_traffic_anomalies(
                    route_name=route_name,
                    namespace=namespace,
                    threshold=threshold
                )
                
                anomalies_detected = result.get('anomalies_detected', False)
                if anomalies_detected:
                    await ctx.warning(
                        f"Anomalies detected for route '{route_name}'",
                        extra={'route_name': route_name, 'result': result}
                    )
                else:
                    await ctx.info(
                        f"No anomalies detected for route '{route_name}'",
                        extra={'route_name': route_name}
                    )
                
                return result
            
            except Exception as e:
                await ctx.error(
                    f"Failed to detect anomalies: {str(e)}",
                    extra={'route_name': route_name, 'error': str(e)}
                )
                raise TraefikOperationError(f'Anomaly detection failed: {str(e)}')
