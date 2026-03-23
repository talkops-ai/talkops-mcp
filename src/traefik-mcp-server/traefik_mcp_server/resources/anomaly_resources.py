"""Anomaly detection resources.

Provides real-time anomaly alerts for detected issues during deployments.
"""

import json
from typing import List
from datetime import datetime
from mcp.types import Resource, TextContent
from traefik_mcp_server.resources.base import BaseResource



class AnomalyResources(BaseResource):
    """Anomaly detection resources.
    
    Provides alert stream for detected anomalies.
    Update frequency: Real-time (event-driven).
    """
    
    def register(self, mcp_instance) -> None:
        """Register anomaly resources with FastMCP.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        
        @mcp_instance.resource("traefik://anomalies/detected")
        async def detected_anomalies() -> str:
            """Get currently detected anomalies.
            
            Returns:
                JSON string with detected anomalies
            
            Note:
                This is a basic implementation. Full anomaly detection requires
                metrics-based analysis from Prometheus and custom detection logic.
            """
            try:
                if not self.argo_service:
                    return json.dumps({
                        "anomalies": [],
                        "error": "Argo service not available"
                    }, indent=2)
                
                # Get namespace from config
                namespace = getattr(self.config, 'namespace', 'default') if self.config else 'default'
                
                # List all rollouts
                rollouts_result = await self.argo_service.list_rollouts(namespace=namespace)
                rollout_list = rollouts_result.get("rollouts", []) if isinstance(rollouts_result, dict) else []
                
                anomalies = []
                
                for rollout in rollout_list:
                    name = rollout.get('name', 'unknown')
                    ns = rollout.get('namespace', namespace)
                    
                    try:
                        # Get detailed status
                        status_data = await self.argo_service.get_rollout_status(
                            name=name,
                            namespace=ns
                        )
                        
                        # get_rollout_status returns flat structure
                        phase = status_data.get('phase', 'Unknown')
                        
                        # Detect anomalies based on rollout state
                        
                        # 1. Degraded state
                        if phase == 'Degraded':
                            anomalies.append({
                                "type": "DEGRADED_ROLLOUT",
                                "service": name,
                                "namespace": ns,
                                "severity": "HIGH",
                                "message": status_data.get('message', 'Rollout is in degraded state'),
                                "timestamp": datetime.utcnow().isoformat() + 'Z'
                            })
                        
                        # 2. Aborted rollout
                        if status_data.get('abort', False):
                            anomalies.append({
                                "type": "ROLLOUT_ABORTED",
                                "service": name,
                                "namespace": ns,
                                "severity": "HIGH",
                                "message": "Rollout was aborted",
                                "timestamp": datetime.utcnow().isoformat() + 'Z'
                            })
                        
                        # 3. Unhealthy replicas — replicas is a dict {total, ready, available}
                        replicas_info = status_data.get('replicas', {})
                        if isinstance(replicas_info, dict):
                            replicas_desired = replicas_info.get('total', 0) or status_data.get('desired_replicas', 0)
                            replicas_ready = replicas_info.get('ready', 0)
                        else:
                            replicas_desired = replicas_info if isinstance(replicas_info, int) else 0
                            replicas_ready = 0
                        
                        if replicas_desired > 0:
                            unhealthy_ratio = (replicas_desired - replicas_ready) / replicas_desired
                            
                            if unhealthy_ratio > 0.5:  # More than 50% unhealthy
                                anomalies.append({
                                    "type": "HIGH_UNHEALTHY_REPLICAS",
                                    "service": name,
                                    "namespace": ns,
                                    "severity": "HIGH",
                                    "current": replicas_ready,
                                    "desired": replicas_desired,
                                    "unhealthyRatio": round(unhealthy_ratio, 2),
                                    "message": f"{int(unhealthy_ratio * 100)}% of replicas are not ready",
                                    "timestamp": datetime.utcnow().isoformat() + 'Z'
                                })
                            elif unhealthy_ratio > 0.2:  # More than 20% unhealthy
                                anomalies.append({
                                    "type": "ELEVATED_UNHEALTHY_REPLICAS",
                                    "service": name,
                                    "namespace": ns,
                                    "severity": "MEDIUM",
                                    "current": replicas_ready,
                                    "desired": replicas_desired,
                                    "unhealthyRatio": round(unhealthy_ratio, 2),
                                    "message": f"{int(unhealthy_ratio * 100)}% of replicas are not ready",
                                    "timestamp": datetime.utcnow().isoformat() + 'Z'
                                })
                        
                        # 4. Long-running progression (stuck rollout)
                        # This would require timestamp tracking - placeholder for now
                        if phase == 'Progressing':
                            # In a full implementation, track how long it's been progressing
                            pass
                        
                    except Exception:
                        pass
                resource_data = {
                    "anomalies": anomalies,
                    "totalAnomolies": len(anomalies),
                    "timestamp": datetime.utcnow().isoformat() + 'Z'
                }
                
                return json.dumps(resource_data, indent=2)
                
            except Exception as e:
                return json.dumps({
                    "error": str(e),
                    "anomalies": []
                }, indent=2)
        
        @mcp_instance.resource("traefik://anomalies/history/{namespace}")
        async def anomaly_history(namespace: str) -> str:
            """Get anomaly history for a namespace.
            
            Args:
                namespace: Kubernetes namespace
            
            Returns:
                JSON string with anomaly history
            
            Note:
                This is a placeholder. Full implementation requires persistent storage
                of detected anomalies.
            """
            try:
                # Placeholder - would query anomaly database/store
                resource_data = {
                    "namespace": namespace,
                    "history": [],
                    "note": "Anomaly history requires persistent storage implementation"
                }
                
                return json.dumps(resource_data, indent=2)
                
            except Exception as e:
                return json.dumps({"error": str(e)}, indent=2)
