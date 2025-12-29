"""Metrics summary resources.

Provides key performance metrics from Prometheus (when available).
"""

import json
import logging
from typing import Optional, Dict, Any
from mcp.types import Resource, TextContent
from argoflow_mcp_server.resources.base import BaseResource

logger = logging.getLogger(__name__)


class MetricsResources(BaseResource):
    """Metrics summary resources.
    
    Provides key performance metrics (requires Prometheus).
    Update frequency: Every 10 seconds.
    """
    
    def register(self, mcp_instance) -> None:
        """Register metrics resources with FastMCP.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        
        @mcp_instance.resource("argoflow://metrics/{namespace}/{service}/summary")
        async def metrics_summary(namespace: str, service: str) -> str:
            """Get metrics summary for a service.
            
            Args:
                namespace: Kubernetes namespace
                service: Service name
            
            Returns:
                JSON string with key performance metrics
            
            Note:
                This is a placeholder implementation. Full implementation requires
                Prometheus client integration for actual metric queries.
            """
            try:
                # TODO: Integrate with Prometheus
                # For now, return mock data structure
                resource_data = {
                    "service": service,
                    "namespace": namespace,
                    "requestRate": 0.0,
                    "errorRate": 0.0,
                    "latency": {
                        "p50": 0.0,
                        "p95": 0.0,
                        "p99": 0.0
                    },
                    "resources": {
                        "cpu": 0.0,
                        "memory": 0
                    },
                    "note": "Prometheus integration required for actual metrics"
                }
                
                logger.info(f"Metrics requested for {service} in {namespace} (Prometheus not configured)")
                
                return json.dumps(resource_data, indent=2)
                
            except Exception as e:
                logger.error(f"Error getting metrics summary: {e}")
                return json.dumps({"error": str(e)}, indent=2)
        
        @mcp_instance.resource("argoflow://metrics/prometheus/status")
        async def prometheus_status() -> str:
            """Get Prometheus integration status.
            
            Returns:
                JSON string with Prometheus connection status
            """
            try:
                # Check if Prometheus configuration exists
                prometheus_url = None
                if self.config:
                    prometheus_url = getattr(self.config, 'prometheus_url', None)
                
                resource_data = {
                    "configured": prometheus_url is not None,
                    "url": prometheus_url or "Not configured",
                    "status": "unavailable",
                    "message": "Prometheus integration not yet implemented"
                }
                
                return json.dumps(resource_data, indent=2)
                
            except Exception as e:
                logger.error(f"Error checking Prometheus status: {e}")
                return json.dumps({
                    "error": str(e),
                    "configured": False,
                    "status": "error"
                }, indent=2)
