"""Cluster health, namespaces, kubeconfig contexts, and server capability resources."""

import asyncio
import json
import logging

from argo_rollout_mcp_server.resources.base import BaseResource

logger = logging.getLogger(__name__)


class ClusterResources(BaseResource):
    """Cluster-level and server capability resources."""

    def register(self, mcp_instance) -> None:
        """Register cluster and server resources with FastMCP."""

        @mcp_instance.resource("argorollout://cluster/health")
        async def cluster_health() -> str:
            """Get overall cluster node readiness and capacity."""
            try:
                if not self.argo_service:
                    return json.dumps({"error": "Services not available", "healthScore": 0}, indent=2)

                def _fetch_nodes():
                    from kubernetes import client

                    if getattr(self.argo_service, "_lazy_init_enabled", False):
                        try:
                            self.argo_service._ensure_initialized()
                        except Exception:
                            pass
                    core_v1 = getattr(self.argo_service, "_core_v1", None) or client.CoreV1Api()
                    return core_v1.list_node()

                nodes = await asyncio.to_thread(_fetch_nodes)
                node_items = getattr(nodes, "items", []) or []
                node_count = len(node_items)
                nodes_ready = 0
                total_cpu = 0.0
                total_memory = 0

                for node in node_items:
                    conditions = (node.status.conditions if node.status else None) or []
                    for condition in conditions:
                        if condition.type == "Ready" and condition.status == "True":
                            nodes_ready += 1
                            break

                    if node.status and node.status.capacity:
                        cpu_str = node.status.capacity.get("cpu", "0")
                        try:
                            total_cpu += float(cpu_str)
                        except ValueError:
                            pass
                        memory_str = node.status.capacity.get("memory", "0Ki")
                        try:
                            if memory_str.endswith("Ki"):
                                total_memory += int(memory_str[:-2])
                            elif memory_str.endswith("Mi"):
                                total_memory += int(memory_str[:-2]) * 1024
                            elif memory_str.endswith("Gi"):
                                total_memory += int(memory_str[:-2]) * 1024 * 1024
                        except ValueError:
                            pass

                memory_gi = total_memory / (1024 * 1024)
                health_score = int((nodes_ready / node_count) * 100) if node_count > 0 else 0

                return json.dumps(
                    {
                        "nodeCount": node_count,
                        "nodesReady": nodes_ready,
                        "cpuCapacityCores": round(total_cpu, 2),
                        "memoryCapacity": f"{round(memory_gi, 2)}Gi",
                        "healthScore": health_score,
                    },
                    indent=2,
                )
            except Exception as e:
                logger.error(f"Error getting cluster health: {e}")
                return json.dumps({"error": str(e), "healthScore": 0}, indent=2)

        @mcp_instance.resource("argorollout://cluster/namespaces")
        async def cluster_namespaces() -> str:
            """Get list of namespaces in the cluster."""
            try:
                if not self.argo_service:
                    return json.dumps({"error": "Services not available", "namespaces": []}, indent=2)

                def _fetch_namespaces():
                    from kubernetes import client

                    if getattr(self.argo_service, "_lazy_init_enabled", False):
                        try:
                            self.argo_service._ensure_initialized()
                        except Exception:
                            pass
                    core_v1 = getattr(self.argo_service, "_core_v1", None) or client.CoreV1Api()
                    return core_v1.list_namespace()

                namespaces = await asyncio.to_thread(_fetch_namespaces)
                namespace_list = []
                for ns in getattr(namespaces, "items", []) or []:
                    namespace_list.append(
                        {
                            "name": ns.metadata.name,
                            "status": ns.status.phase if ns.status else "Active",
                            "creationTimestamp": (
                                ns.metadata.creation_timestamp.isoformat()
                                if getattr(ns.metadata, "creation_timestamp", None)
                                else None
                            ),
                        }
                    )
                return json.dumps(
                    {"namespaces": namespace_list, "totalNamespaces": len(namespace_list)},
                    indent=2,
                )
            except Exception as e:
                logger.error(f"Error getting namespaces: {e}")
                return json.dumps({"error": str(e), "namespaces": []}, indent=2)

        @mcp_instance.resource("argorollout://cluster/contexts")
        async def cluster_contexts() -> str:
            """Get active and available kubeconfig contexts (no credentials)."""
            try:
                if not self.argo_service:
                    return json.dumps({"error": "Argo service not available", "contexts": []}, indent=2)
                result = await asyncio.to_thread(self.argo_service.get_kube_contexts)
                return json.dumps(result, indent=2)
            except Exception as e:
                logger.error(f"Error getting kubeconfig contexts: {e}")
                return json.dumps({"error": str(e), "contexts": []}, indent=2)

        @mcp_instance.resource("argorollout://server/capabilities")
        async def server_capabilities() -> str:
            """Get server capabilities, write mode, enabled toolsets, and CRD availability."""
            try:
                if not self.argo_service:
                    return json.dumps(
                        {
                            "allow_write": getattr(self.config, "allow_write", False) if self.config else False,
                            "toolsets": getattr(self.config, "toolsets", ["all"]) if self.config else ["all"],
                            "cluster_connected": False,
                        },
                        indent=2,
                    )
                result = await asyncio.to_thread(self.argo_service.get_server_capabilities)
                return json.dumps(result, indent=2)
            except Exception as e:
                logger.error(f"Error getting server capabilities: {e}")
                return json.dumps({"error": str(e)}, indent=2)
