"""Cluster health resources.

Provides overall cluster health and capacity information.
"""

import json
import logging
from mcp.types import Resource, TextContent
from argoflow_mcp_server.resources.base import BaseResource

logger = logging.getLogger(__name__)


class ClusterResources(BaseResource):
    """Cluster health resources.
    
    Provides overall cluster health and capacity.
    Update frequency: Every 30 seconds.
    """
    
    def register(self, mcp_instance) -> None:
        """Register cluster resources with FastMCP.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        
        @mcp_instance.resource("argoflow://cluster/health")
        async def cluster_health() -> str:
            """Get overall cluster health and capacity.
            
            Returns:
                JSON string with cluster health information
            
            Note:
                This requires direct Kubernetes API access to query nodes and metrics.
                Currently returns placeholder data.
            """
            try:
                if not self.argo_service:
                    return json.dumps({
                        "error": "Services not available",
                        "healthScore": 0
                    }, indent=2)
                
                # Access the Kubernetes API client from argo_service
                # Note: This uses the initialized client from the service
                try:
                    from kubernetes import client
                    
                    # Get core API instance
                    core_v1 = client.CoreV1Api()
                    
                    # List all nodes
                    nodes = core_v1.list_node()
                    
                    node_count = len(nodes.items)
                    nodes_ready = 0
                    
                    # Check node status
                    for node in nodes.items:
                        conditions = node.status.conditions or []
                        for condition in conditions:
                            if condition.type == 'Ready' and condition.status == 'True':
                                nodes_ready += 1
                                break
                    
                    # Get node capacity
                    total_cpu = 0.0
                    total_memory = 0
                    
                    for node in nodes.items:
                        if node.status.capacity:
                            # Parse CPU (in cores)
                            cpu_str = node.status.capacity.get('cpu', '0')
                            try:
                                total_cpu += float(cpu_str)
                            except ValueError:
                                logger.warning(f"Could not parse CPU capacity: {cpu_str}")
                            
                            # Parse memory (in Ki)
                            memory_str = node.status.capacity.get('memory', '0Ki')
                            try:
                                if memory_str.endswith('Ki'):
                                    total_memory += int(memory_str[:-2])
                                elif memory_str.endswith('Mi'):
                                    total_memory += int(memory_str[:-2]) * 1024
                                elif memory_str.endswith('Gi'):
                                    total_memory += int(memory_str[:-2]) * 1024 * 1024
                            except ValueError:
                                logger.warning(f"Could not parse memory capacity: {memory_str}")
                    
                    # Convert memory to human-readable format
                    memory_gi = total_memory / (1024 * 1024)
                    
                    # Calculate health score
                    health_score = 0
                    if node_count > 0:
                        ready_ratio = nodes_ready / node_count
                        health_score = int(ready_ratio * 100)
                    
                    # Placeholder for resource usage (requires metrics-server)
                    cpu_used = 0.0
                    memory_used_gi = 0.0
                    
                    resource_data = {
                        "nodeCount": node_count,
                        "nodesReady": nodes_ready,
                        "cpuCapacity": round(total_cpu, 2),
                        "cpuUsed": round(cpu_used, 2),
                        "cpuUsagePercent": 0,  # Requires metrics-server
                        "memoryCapacity": f"{round(memory_gi, 2)}Gi",
                        "memoryUsed": f"{round(memory_used_gi, 2)}Gi",
                        "memoryUsagePercent": 0,  # Requires metrics-server
                        "healthScore": health_score,
                        "note": "Resource usage requires metrics-server integration"
                    }
                    
                    return json.dumps(resource_data, indent=2)
                    
                except ImportError:
                    logger.error("Kubernetes client not available")
                    return json.dumps({
                        "error": "Kubernetes client not available",
                        "healthScore": 0
                    }, indent=2)
                except Exception as e:
                    logger.error(f"Error querying cluster: {e}")
                    return json.dumps({
                        "error": f"Error querying cluster: {str(e)}",
                        "healthScore": 0
                    }, indent=2)
                    
            except Exception as e:
                logger.error(f"Error getting cluster health: {e}")
                return json.dumps({
                    "error": str(e),
                    "healthScore": 0
                }, indent=2)
        
        @mcp_instance.resource("argoflow://cluster/namespaces")
        async def cluster_namespaces() -> str:
            """Get list of namespaces in the cluster.
            
            Returns:
                JSON string with namespace information
            """
            try:
                if not self.argo_service:
                    return json.dumps({
                        "error": "Services not available",
                        "namespaces": []
                    }, indent=2)
                
                try:
                    from kubernetes import client
                    
                    # Get core API instance
                    core_v1 = client.CoreV1Api()
                    
                    # List all namespaces
                    namespaces = core_v1.list_namespace()
                    
                    namespace_list = []
                    for ns in namespaces.items:
                        namespace_list.append({
                            "name": ns.metadata.name,
                            "status": ns.status.phase,
                            "creationTimestamp": ns.metadata.creation_timestamp.isoformat() if ns.metadata.creation_timestamp else None
                        })
                    
                    resource_data = {
                        "namespaces": namespace_list,
                        "totalNamespaces": len(namespace_list)
                    }
                    
                    return json.dumps(resource_data, indent=2)
                    
                except ImportError:
                    logger.error("Kubernetes client not available")
                    return json.dumps({
                        "error": "Kubernetes client not available",
                        "namespaces": []
                    }, indent=2)
                except Exception as e:
                    logger.error(f"Error listing namespaces: {e}")
                    return json.dumps({
                        "error": f"Error listing namespaces: {str(e)}",
                        "namespaces": []
                    }, indent=2)
                    
            except Exception as e:
                logger.error(f"Error getting namespaces: {e}")
                return json.dumps({
                    "error": str(e),
                    "namespaces": []
                }, indent=2)
