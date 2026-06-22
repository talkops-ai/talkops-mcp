"""Kubernetes API service for OpenTelemetry MCP server.

Wraps the synchronous ``kubernetes`` Python client with ``asyncio.to_thread()``
for non-blocking async operation in the FastMCP event loop.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from opentelemetry_mcp_server.config import KubernetesConfig, OtelOperatorConfig
from opentelemetry_mcp_server.exceptions import (
    OtelConnectionError,
    OtelResourceNotFoundError,
)

logger = logging.getLogger(__name__)


class KubernetesService:
    """Async-wrapped Kubernetes API client for OTel CRD operations.

    Handles both in-cluster and out-of-cluster (kubeconfig) authentication.
    All K8s API calls are wrapped in ``asyncio.to_thread()`` to avoid
    blocking the FastMCP event loop.

    Supports multi-cluster via a client pool: each kubeconfig context
    gets its own set of API clients, created lazily on first use.
    The default context is used.
    """

    def __init__(
        self,
        k8s_config: KubernetesConfig,
        otel_config: Optional[OtelOperatorConfig] = None,
    ) -> None:
        self._k8s_config = k8s_config
        self._otel_config = otel_config or OtelOperatorConfig()
        self._core_v1: Any = None
        self._apps_v1: Any = None
        self._custom_api: Any = None
        self._initialized = False

        # Multi-context client pool: context_name -> (core_v1, apps_v1, custom_api)
        self._client_pool: Dict[Optional[str], Any] = {}

        if k8s_config.enabled:
            self._init_client()

    def _init_client(self) -> None:
        """Initialize the Kubernetes client."""
        try:
            from kubernetes import client, config as k8s_config_loader

            if self._k8s_config.in_cluster:
                k8s_config_loader.load_incluster_config()
            else:
                k8s_config_loader.load_kube_config()

            self._core_v1 = client.CoreV1Api()
            self._apps_v1 = client.AppsV1Api()
            self._custom_api = client.CustomObjectsApi()
            self._initialized = True

            # Cache default context clients in pool
            self._client_pool[None] = (
                self._core_v1, self._apps_v1, self._custom_api
            )

            logger.info("Kubernetes client initialized successfully")
        except Exception as e:
            logger.warning(f"Kubernetes client initialization failed: {e}")
            self._initialized = False



    async def list_available_contexts(self) -> List[Dict[str, Any]]:
        """List all available kubeconfig contexts.

        Returns context names and which one is the current default.
        Used by agents to discover which clusters they can access.

        Returns:
            List of context dicts with name, cluster, and is_current.
        """
        try:
            from kubernetes import config as k8s_config_loader

            contexts, current = k8s_config_loader.list_kube_config_contexts()

            result = []
            current_name = current.get("name", "") if current else ""

            for ctx in contexts:
                ctx_dict: Dict[str, Any] = dict(ctx) if not isinstance(ctx, dict) else ctx
                cluster_info: Dict[str, Any] = ctx_dict.get("context", {})
                if isinstance(cluster_info, dict):
                    cluster = cluster_info.get("cluster", "")
                    user = cluster_info.get("user", "")
                    ns = cluster_info.get("namespace", "default")
                else:
                    cluster, user, ns = "", "", "default"
                result.append({
                    "name": ctx_dict.get("name", ""),
                    "cluster": cluster,
                    "user": user,
                    "namespace": ns,
                    "is_current": ctx_dict.get("name") == current_name,
                })

            return result

        except Exception as e:
            logger.warning(f"Failed to list kubeconfig contexts: {e}")
            return [{
                "name": "default",
                "cluster": "unknown",
                "is_current": True,
                "error": str(e),
            }]

    @property
    def is_available(self) -> bool:
        """Whether the Kubernetes client is initialized and available."""
        return self._initialized and self._k8s_config.enabled

    def _ensure_available(self) -> None:
        """Raise if K8s client is not available."""
        if not self.is_available:
            raise OtelConnectionError(
                "Kubernetes client is not available. "
                "Set K8S_ENABLED=true and ensure cluster connectivity."
            )

    # ──────────────────────────────────────────────
    # OpenTelemetryCollector CRD operations
    # ──────────────────────────────────────────────

    async def list_otel_collectors(
        self,
        namespace: Optional[str] = None,
        label_selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List OpenTelemetryCollector CRDs.

        Args:
            namespace: Namespace to query, or None for all namespaces.
            label_selector: Optional K8s label selector string.

        Returns:
            Raw K8s API response dict with ``items`` list.
        """
        self._ensure_available()

        kwargs: Dict[str, Any] = {
            "group": self._otel_config.crd_group,
            "version": self._otel_config.crd_api_version,
            "plural": self._otel_config.collector_plural,
        }
        if label_selector:
            kwargs["label_selector"] = label_selector

        if namespace:
            kwargs["namespace"] = namespace
            return await asyncio.to_thread(
                self._custom_api.list_namespaced_custom_object, **kwargs
            )
        return await asyncio.to_thread(
            self._custom_api.list_cluster_custom_object, **kwargs
        )

    async def get_otel_collector(
        self, namespace: str, name: str
    ) -> Dict[str, Any]:
        """Get a single OpenTelemetryCollector CRD.

        Args:
            namespace: CRD namespace.
            name: CRD name.

        Returns:
            Raw K8s API response dict.

        Raises:
            OtelResourceNotFoundError: If the CRD is not found.
        """
        self._ensure_available()
        try:
            return await asyncio.to_thread(
                self._custom_api.get_namespaced_custom_object,
                group=self._otel_config.crd_group,
                version=self._otel_config.crd_api_version,
                namespace=namespace,
                plural=self._otel_config.collector_plural,
                name=name,
            )
        except Exception as e:
            if "404" in str(e) or "NotFound" in str(e):
                raise OtelResourceNotFoundError(
                    f"OpenTelemetryCollector '{name}' not found in namespace '{namespace}'"
                )
            raise OtelConnectionError(f"Failed to get collector: {e}")

    # ──────────────────────────────────────────────
    # Instrumentation CRD operations
    # ──────────────────────────────────────────────

    async def list_instrumentations(
        self,
        namespace: Optional[str] = None,
        label_selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List Instrumentation CRDs.

        Args:
            namespace: Namespace to query, or None for all namespaces.
            label_selector: Optional label selector.

        Returns:
            Raw K8s API response dict.
        """
        self._ensure_available()

        kwargs: Dict[str, Any] = {
            "group": self._otel_config.crd_group,
            "version": self._otel_config.instrumentation_api_version,
            "plural": self._otel_config.instrumentation_plural,
        }
        if label_selector:
            kwargs["label_selector"] = label_selector

        if namespace:
            kwargs["namespace"] = namespace
            return await asyncio.to_thread(
                self._custom_api.list_namespaced_custom_object, **kwargs
            )
        return await asyncio.to_thread(
            self._custom_api.list_cluster_custom_object, **kwargs
        )

    async def get_instrumentation(
        self, namespace: str, name: str
    ) -> Dict[str, Any]:
        """Get a single Instrumentation CRD.

        Args:
            namespace: CRD namespace.
            name: CRD name.

        Returns:
            Raw K8s API response dict.

        Raises:
            OtelResourceNotFoundError: If the CRD is not found.
        """
        self._ensure_available()
        try:
            return await asyncio.to_thread(
                self._custom_api.get_namespaced_custom_object,
                group=self._otel_config.crd_group,
                version=self._otel_config.instrumentation_api_version,
                namespace=namespace,
                plural=self._otel_config.instrumentation_plural,
                name=name,
            )
        except Exception as e:
            if "404" in str(e) or "NotFound" in str(e):
                raise OtelResourceNotFoundError(
                    f"Instrumentation '{name}' not found in namespace '{namespace}'"
                )
            raise OtelConnectionError(f"Failed to get instrumentation: {e}")

    # ──────────────────────────────────────────────
    # Workload operations (Deployments, StatefulSets)
    # ──────────────────────────────────────────────

    async def list_deployments(
        self,
        namespace: str,
        label_selector: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List Deployments in a namespace.

        Args:
            namespace: Target namespace.
            label_selector: Optional label selector.

        Returns:
            List of deployment dicts.
        """
        self._ensure_available()
        kwargs: Dict[str, Any] = {"namespace": namespace}
        if label_selector:
            kwargs["label_selector"] = label_selector

        result = await asyncio.to_thread(
            self._apps_v1.list_namespaced_deployment, **kwargs
        )
        return [
            self._deployment_to_dict(d)
            for d in result.items
        ]

    async def get_deployment(
        self, namespace: str, name: str
    ) -> Dict[str, Any]:
        """Get a single Deployment.

        Args:
            namespace: Deployment namespace.
            name: Deployment name.

        Returns:
            Deployment dict.

        Raises:
            OtelResourceNotFoundError: If not found.
        """
        self._ensure_available()
        try:
            result = await asyncio.to_thread(
                self._apps_v1.read_namespaced_deployment,
                name=name,
                namespace=namespace,
            )
            return self._deployment_to_dict(result)
        except Exception as e:
            if "404" in str(e) or "NotFound" in str(e):
                raise OtelResourceNotFoundError(
                    f"Deployment '{name}' not found in namespace '{namespace}'"
                )
            raise OtelConnectionError(f"Failed to get deployment: {e}")

    async def patch_deployment_annotations(
        self,
        namespace: str,
        name: str,
        annotations: Dict[str, str],
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Patch annotations on a Deployment's pod template.

        Used for applying auto-instrumentation annotations.

        Args:
            namespace: Deployment namespace.
            name: Deployment name.
            annotations: Annotations to merge into the pod template.
            dry_run: If True, performs a server-side dry run without persisting.

        Returns:
            Updated deployment dict.
        """
        self._ensure_available()
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": annotations,
                    }
                }
            }
        }

        kwargs: Dict[str, Any] = {
            "name": name,
            "namespace": namespace,
            "body": body,
        }
        if dry_run:
            kwargs["dry_run"] = "All"

        result = await asyncio.to_thread(
            self._apps_v1.patch_namespaced_deployment, **kwargs
        )
        return self._deployment_to_dict(result)

    # ──────────────────────────────────────────────
    # Pod operations
    # ──────────────────────────────────────────────

    async def list_pods(
        self,
        namespace: Optional[str] = None,
        label_selector: Optional[str] = None,
        field_selector: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List pods.

        Args:
            namespace: Namespace, or None for all namespaces.
            label_selector: Optional label selector.
            field_selector: Optional field selector.

        Returns:
            List of pod dicts.
        """
        self._ensure_available()
        kwargs: Dict[str, Any] = {}
        if label_selector:
            kwargs["label_selector"] = label_selector
        if field_selector:
            kwargs["field_selector"] = field_selector

        if namespace:
            kwargs["namespace"] = namespace
            result = await asyncio.to_thread(
                self._core_v1.list_namespaced_pod, **kwargs
            )
        else:
            result = await asyncio.to_thread(
                self._core_v1.list_pod_for_all_namespaces, **kwargs
            )

        return [self._pod_to_dict(p) for p in result.items]

    # ──────────────────────────────────────────────
    # Instrumentation CRD mutation
    # ──────────────────────────────────────────────

    async def create_or_patch_instrumentation(
        self,
        namespace: str,
        name: str,
        spec: Dict[str, Any],
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """Create or patch an Instrumentation CRD.

        Args:
            namespace: Target namespace.
            name: Instrumentation CR name.
            spec: CRD spec dict.
            overwrite: If True, replaces existing; if False, merges.

        Returns:
            Created/updated CRD dict.
        """
        self._ensure_available()
        body = {
            "apiVersion": f"{self._otel_config.crd_group}/{self._otel_config.instrumentation_api_version}",
            "kind": "Instrumentation",
            "metadata": {
                "name": name,
                "namespace": namespace,
            },
            "spec": spec,
        }

        try:
            # Try to get existing
            await self.get_instrumentation(namespace, name)
            # Exists — patch or replace
            if overwrite:
                return await asyncio.to_thread(
                    self._custom_api.replace_namespaced_custom_object,
                    group=self._otel_config.crd_group,
                    version=self._otel_config.instrumentation_api_version,
                    namespace=namespace,
                    plural=self._otel_config.instrumentation_plural,
                    name=name,
                    body=body,
                )
            return await asyncio.to_thread(
                self._custom_api.patch_namespaced_custom_object,
                group=self._otel_config.crd_group,
                version=self._otel_config.instrumentation_api_version,
                namespace=namespace,
                plural=self._otel_config.instrumentation_plural,
                name=name,
                body=body,
            )
        except OtelResourceNotFoundError:
            # Does not exist — create
            return await asyncio.to_thread(
                self._custom_api.create_namespaced_custom_object,
                group=self._otel_config.crd_group,
                version=self._otel_config.instrumentation_api_version,
                namespace=namespace,
                plural=self._otel_config.instrumentation_plural,
                body=body,
            )

    # ──────────────────────────────────────────────
    # OpenTelemetryCollector CRD mutation
    # ──────────────────────────────────────────────

    async def create_or_patch_collector(
        self,
        namespace: str,
        name: str,
        spec: Dict[str, Any],
        labels: Optional[Dict[str, str]] = None,
        annotations: Optional[Dict[str, str]] = None,
        overwrite: bool = False,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Create or patch an OpenTelemetryCollector CRD.

        Args:
            namespace: Target namespace.
            name: Collector CR name.
            spec: CRD spec dict (mode, config, image, replicas, etc.).
            labels: Optional metadata labels to apply.
            annotations: Optional metadata annotations to apply.
            overwrite: If True, replaces existing; if False, merges.
            dry_run: If True, performs a server-side dry run without
                persisting changes.

        Returns:
            Created/updated CRD dict.
        """
        self._ensure_available()

        metadata: Dict[str, Any] = {
            "name": name,
            "namespace": namespace,
        }
        if labels:
            metadata["labels"] = labels
        if annotations:
            metadata["annotations"] = annotations

        body = {
            "apiVersion": f"{self._otel_config.crd_group}/{self._otel_config.crd_api_version}",
            "kind": "OpenTelemetryCollector",
            "metadata": metadata,
            "spec": spec,
        }

        base_kwargs: Dict[str, Any] = {
            "group": self._otel_config.crd_group,
            "version": self._otel_config.crd_api_version,
            "namespace": namespace,
            "plural": self._otel_config.collector_plural,
        }
        if dry_run:
            base_kwargs["dry_run"] = "All"

        try:
            # Try to get existing
            existing = await self.get_otel_collector(namespace, name)

            # Snapshot current config before mutation (non-dry-run only)
            if not dry_run:
                self._store_config_snapshot(existing, body)

            # Exists — patch or replace
            if overwrite:
                # replace (PUT) requires metadata.resourceVersion
                existing_rv = (
                    existing.get("metadata", {}).get("resourceVersion")
                )
                if existing_rv:
                    body["metadata"]["resourceVersion"] = existing_rv
                return await asyncio.to_thread(
                    self._custom_api.replace_namespaced_custom_object,
                    **base_kwargs,
                    name=name,
                    body=body,
                )
            return await asyncio.to_thread(
                self._custom_api.patch_namespaced_custom_object,
                **base_kwargs,
                name=name,
                body=body,
            )
        except OtelResourceNotFoundError:
            # Does not exist — create
            return await asyncio.to_thread(
                self._custom_api.create_namespaced_custom_object,
                **base_kwargs,
                body=body,
            )

    # ──────────────────────────────────────────────
    # RBAC for k8sattributes processor
    # ──────────────────────────────────────────────

    @staticmethod
    def build_k8sattributes_rbac_manifests(
        namespace: str,
        collector_name: str,
    ) -> Dict[str, Any]:
        """Build ClusterRole and ClusterRoleBinding manifests for k8sattributes.

        The k8sattributes processor needs permissions to watch Pods,
        ReplicaSets, Namespaces, Nodes, and Jobs. The OTel Operator
        does NOT auto-create these RBAC resources.

        Args:
            namespace: Namespace where the collector runs.
            collector_name: Collector CR name (used to derive the
                ServiceAccount name created by the Operator).

        Returns:
            Dict with ``cluster_role`` and ``cluster_role_binding``
            manifest dicts ready for YAML serialization or K8s apply.
        """
        # The OTel Operator creates a ServiceAccount named
        # "{collector_name}-collector" in the target namespace
        sa_name = f"{collector_name}-collector"
        role_name = f"otel-k8sattr-{collector_name}"

        cluster_role = {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRole",
            "metadata": {
                "name": role_name,
                "labels": {
                    "app.kubernetes.io/managed-by": "talkops-mcp",
                    "app.kubernetes.io/component": "rbac",
                    "talkops.ai/collector": collector_name,
                },
            },
            "rules": [
                {
                    "apiGroups": [""],
                    "resources": [
                        "pods", "namespaces", "nodes",
                    ],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["apps"],
                    "resources": ["replicasets"],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["batch"],
                    "resources": ["jobs"],
                    "verbs": ["get", "list", "watch"],
                },
            ],
        }

        cluster_role_binding = {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRoleBinding",
            "metadata": {
                "name": role_name,
                "labels": {
                    "app.kubernetes.io/managed-by": "talkops-mcp",
                    "app.kubernetes.io/component": "rbac",
                    "talkops.ai/collector": collector_name,
                },
            },
            "roleRef": {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "ClusterRole",
                "name": role_name,
            },
            "subjects": [
                {
                    "kind": "ServiceAccount",
                    "name": sa_name,
                    "namespace": namespace,
                },
            ],
        }

        return {
            "cluster_role": cluster_role,
            "cluster_role_binding": cluster_role_binding,
        }

    async def create_k8sattributes_rbac(
        self,
        namespace: str,
        collector_name: str,
    ) -> Dict[str, Any]:
        """Create RBAC resources required by the k8sattributes processor.

        Creates a ClusterRole and ClusterRoleBinding so the collector's
        ServiceAccount can list/watch Pods, ReplicaSets, Namespaces,
        Nodes, and Jobs.

        Args:
            namespace: Namespace where the collector runs.
            collector_name: Collector CR name.

        Returns:
            Dict with created resource metadata.
        """
        self._ensure_available()

        from kubernetes import client as k8s_client

        rbac_api = k8s_client.RbacAuthorizationV1Api()
        manifests = self.build_k8sattributes_rbac_manifests(
            namespace, collector_name
        )

        results: Dict[str, Any] = {}

        # Create or update ClusterRole
        role_name = manifests["cluster_role"]["metadata"]["name"]
        try:
            existing = await asyncio.to_thread(
                rbac_api.read_cluster_role, name=role_name
            )
            # Exists — patch it
            await asyncio.to_thread(
                rbac_api.patch_cluster_role,
                name=role_name,
                body=manifests["cluster_role"],
            )
            results["cluster_role"] = {
                "name": role_name, "action": "updated"
            }
        except Exception as e:
            if "404" in str(e) or "NotFound" in str(e):
                await asyncio.to_thread(
                    rbac_api.create_cluster_role,
                    body=manifests["cluster_role"],
                )
                results["cluster_role"] = {
                    "name": role_name, "action": "created"
                }
            else:
                raise OtelConnectionError(
                    f"Failed to create ClusterRole '{role_name}': {e}"
                )

        # Create or update ClusterRoleBinding
        try:
            existing = await asyncio.to_thread(
                rbac_api.read_cluster_role_binding, name=role_name
            )
            await asyncio.to_thread(
                rbac_api.patch_cluster_role_binding,
                name=role_name,
                body=manifests["cluster_role_binding"],
            )
            results["cluster_role_binding"] = {
                "name": role_name, "action": "updated"
            }
        except Exception as e:
            if "404" in str(e) or "NotFound" in str(e):
                await asyncio.to_thread(
                    rbac_api.create_cluster_role_binding,
                    body=manifests["cluster_role_binding"],
                )
                results["cluster_role_binding"] = {
                    "name": role_name, "action": "created"
                }
            else:
                raise OtelConnectionError(
                    f"Failed to create ClusterRoleBinding '{role_name}': {e}"
                )

        logger.info(
            f"RBAC for k8sattributes created: ClusterRole={role_name}, "
            f"ClusterRoleBinding={role_name}, "
            f"ServiceAccount={namespace}/{collector_name}-collector"
        )
        return results

    # ──────────────────────────────────────────────
    # Service and namespace discovery
    # ──────────────────────────────────────────────

    async def list_services(
        self,
        namespace: str,
        label_selector: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List Kubernetes Services in a namespace.

        Used by the provisioning engine to auto-discover backend
        endpoints (Jaeger, Tempo, Prometheus, OpenSearch, etc.).

        Args:
            namespace: Target namespace.
            label_selector: Optional label selector.

        Returns:
            List of simplified service dicts with name, ports, and type.
        """
        self._ensure_available()
        kwargs: Dict[str, Any] = {"namespace": namespace}
        if label_selector:
            kwargs["label_selector"] = label_selector

        result = await asyncio.to_thread(
            self._core_v1.list_namespaced_service, **kwargs
        )
        services = []
        for svc in result.items:
            ports = []
            if svc.spec and svc.spec.ports:
                for p in svc.spec.ports:
                    ports.append({
                        "name": p.name,
                        "port": p.port,
                        "target_port": (
                            p.target_port
                            if isinstance(p.target_port, int)
                            else str(p.target_port)
                        ),
                        "protocol": p.protocol or "TCP",
                    })
            services.append({
                "name": svc.metadata.name,
                "namespace": svc.metadata.namespace,
                "type": svc.spec.type if svc.spec else "ClusterIP",
                "cluster_ip": svc.spec.cluster_ip if svc.spec else None,
                "ports": ports,
                "labels": svc.metadata.labels or {},
            })
        return services

    async def list_namespaces(self) -> List[str]:
        """List all namespace names in the cluster.

        Returns:
            List of namespace name strings.
        """
        self._ensure_available()
        result = await asyncio.to_thread(
            self._core_v1.list_namespace
        )
        return [ns.metadata.name for ns in result.items]

    async def count_nodes(self) -> int:
        """Count the number of nodes in the cluster.

        Used by the provisioning engine to auto-size collectors.

        Returns:
            Node count.
        """
        self._ensure_available()
        result = await asyncio.to_thread(
            self._core_v1.list_node
        )
        return len(result.items)

    # ──────────────────────────────────────────────
    # Health check
    # ──────────────────────────────────────────────

    async def health_check(self) -> Dict[str, Any]:
        """Check K8s API connectivity and OTel CRD availability.

        Returns:
            Health status dict with connectivity info.
        """
        if not self._k8s_config.enabled:
            return {"status": "disabled", "message": "Kubernetes integration is disabled"}

        if not self._initialized:
            return {"status": "error", "message": "Kubernetes client failed to initialize"}

        try:
            from kubernetes import client as k8s_client

            version_api = k8s_client.VersionApi()
            version_info: Any = await asyncio.to_thread(version_api.get_code)
            return {
                "status": "healthy",
                "server_version": f"{version_info.major}.{version_info.minor}",
                "git_version": version_info.git_version,
                "context": "default",
            }
        except Exception as e:
            return {"status": "error", "message": f"API unreachable: {e}"}

    # ──────────────────────────────────────────────
    # Config snapshot and rollback (Critique 2)
    # ──────────────────────────────────────────────

    _SNAPSHOT_ANNOTATION = "otel.mcp/last-known-good"
    _SNAPSHOT_TIMESTAMP_ANNOTATION = "otel.mcp/last-mutation"
    _SNAPSHOT_TOOL_ANNOTATION = "otel.mcp/last-mutation-tool"

    @staticmethod
    def _compress_config(config_str: str) -> str:
        """Gzip + base64 encode a config string for annotation storage.

        Args:
            config_str: Raw config YAML/JSON string.

        Returns:
            Base64-encoded gzipped string.
        """
        import base64
        import gzip

        compressed = gzip.compress(config_str.encode("utf-8"))
        return base64.b64encode(compressed).decode("ascii")

    @staticmethod
    def _decompress_config(compressed: str) -> str:
        """Decompress a base64+gzip config string.

        Args:
            compressed: Base64-encoded gzipped string.

        Returns:
            Original config string.
        """
        import base64
        import gzip

        raw = base64.b64decode(compressed)
        return gzip.decompress(raw).decode("utf-8")

    def _store_config_snapshot(
        self,
        existing_crd: Dict[str, Any],
        new_body: Dict[str, Any],
    ) -> None:
        """Store the current config as a snapshot annotation on the new body.

        Called automatically by ``create_or_patch_collector`` before
        applying a real (non-dry-run) mutation. Stores the existing
        config YAML in a gzip+base64 annotation.

        Args:
            existing_crd: Current CRD dict (pre-mutation).
            new_body: The body about to be applied (modified in-place).
        """
        import json
        from datetime import datetime, timezone

        existing_config = existing_crd.get("spec", {}).get("config", "")
        if not existing_config:
            return

        # If config is a dict, serialize to JSON for storage
        if isinstance(existing_config, dict):
            existing_config = json.dumps(existing_config, sort_keys=True)

        try:
            compressed = self._compress_config(existing_config)

            metadata: Dict[str, Any] = new_body.setdefault("metadata", {})
            annotations: Dict[str, str] = metadata.setdefault("annotations", {})

            annotations[self._SNAPSHOT_ANNOTATION] = compressed
            annotations[self._SNAPSHOT_TIMESTAMP_ANNOTATION] = (
                datetime.now(timezone.utc).isoformat()
            )

            logger.info(
                f"Stored config snapshot ({len(compressed)} chars compressed)"
            )
        except Exception as e:
            # Non-blocking — don't fail the mutation because snapshot failed
            logger.warning(f"Failed to store config snapshot: {e}")

    async def revert_collector_config(
        self,
        namespace: str,
        name: str,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Revert a collector to its pre-mutation config.

        Reads the ``otel.mcp/last-known-good`` annotation from the
        collector CRD and restores the config. This is a one-level undo.

        Args:
            namespace: Collector namespace.
            name: Collector CRD name.
            dry_run: If True, returns the diff without applying.

        Returns:
            Dict with current vs. snapshot config and action taken.
        """
        self._ensure_available()

        raw = await self.get_otel_collector(namespace, name)
        crd_annotations = raw.get("metadata", {}).get("annotations", {})

        snapshot_data = crd_annotations.get(self._SNAPSHOT_ANNOTATION)
        if not snapshot_data:
            return {
                "collector": f"{namespace}/{name}",
                "action": "no_snapshot",
                "dry_run": dry_run,
                "message": (
                    "No config snapshot found. The collector has not been "
                    "modified by MCP tools, or the snapshot annotation was "
                    "removed. For multi-step rollback, use GitOps (git revert)."
                ),
            }

        snapshot_timestamp = crd_annotations.get(
            self._SNAPSHOT_TIMESTAMP_ANNOTATION, "unknown"
        )

        try:
            previous_config = self._decompress_config(snapshot_data)
        except Exception as e:
            return {
                "collector": f"{namespace}/{name}",
                "action": "error",
                "message": f"Failed to decompress snapshot: {e}",
            }

        current_config = raw.get("spec", {}).get("config", "")
        if isinstance(current_config, dict):
            import json
            current_config = json.dumps(current_config, sort_keys=True)

        if dry_run:
            return {
                "collector": f"{namespace}/{name}",
                "action": "dry_run",
                "dry_run": True,
                "snapshot_timestamp": snapshot_timestamp,
                "current_config_preview": current_config[:500] + ("..." if len(current_config) > 500 else ""),
                "snapshot_config_preview": previous_config[:500] + ("..." if len(previous_config) > 500 else ""),
                "message": (
                    f"Would revert to config snapshot from {snapshot_timestamp}. "
                    "Set dry_run=False to apply. NOTE: This is a one-level undo. "
                    "For multi-step rollback, use GitOps."
                ),
            }

        # Apply the revert
        spec = dict(raw.get("spec", {}))
        spec["config"] = previous_config

        # Remove the snapshot annotation (consumed)
        result = await self.create_or_patch_collector(
            namespace=namespace,
            name=name,
            spec=spec,
            dry_run=False,
        )

        return {
            "collector": f"{namespace}/{name}",
            "action": "reverted",
            "dry_run": False,
            "snapshot_timestamp": snapshot_timestamp,
            "message": (
                f"Reverted to config snapshot from {snapshot_timestamp}. "
                "The collector will reconcile with the restored config."
            ),
        }

    # ──────────────────────────────────────────────
    # Operator diagnostics (Gap 2)
    # ──────────────────────────────────────────────

    _OPERATOR_NAMESPACES = [
        "opentelemetry-operator-system",
        "opentelemetry",
        "otel-system",
        "default",
    ]

    _OPERATOR_LABEL_SELECTORS = [
        "app.kubernetes.io/name=opentelemetry-operator",
        "app=opentelemetry-operator",
        "control-plane=controller-manager",
    ]

    _ERROR_KEYWORDS = frozenset({
        "error", "fatal", "panic", "fail", "denied", "forbidden",
        "webhook", "timeout", "crash", "multiple",
    })

    async def get_operator_diagnostics(
        self,
        tail_lines: int = 100,
    ) -> Dict[str, Any]:
        """Scan the OTel Operator pod for recent errors and diagnostics.

        Searches common operator namespaces and label selectors to find
        the operator pod, then reads its logs and extracts error-level
        entries. Also counts Instrumentation CRDs per namespace to detect
        the common "multiple Instrumentation instances" problem.

        Args:
            tail_lines: Number of log lines to read from the tail.

        Returns:
            Diagnostics dict with operator status, errors, and warnings.
        """
        self._ensure_available()
        result: Dict[str, Any] = {
            "operator_found": False,
            "operator_pod": None,
            "operator_namespace": None,
            "operator_status": None,
            "recent_errors": [],
            "instrumentation_cr_counts": {},
            "warnings": [],
        }

        # Find operator pod
        operator_pod = None
        operator_ns = None
        for ns in self._OPERATOR_NAMESPACES:
            for selector in self._OPERATOR_LABEL_SELECTORS:
                try:
                    pods = await asyncio.to_thread(
                        self._core_v1.list_namespaced_pod,
                        namespace=ns,
                        label_selector=selector,
                        limit=1,
                    )
                    if pods.items:
                        operator_pod = pods.items[0]
                        operator_ns = ns
                        break
                except Exception:
                    continue
            if operator_pod:
                break

        if not operator_pod:
            result["warnings"].append(
                "OTel Operator pod not found in common namespaces: "
                f"{self._OPERATOR_NAMESPACES}. Check if the operator is installed."
            )
            return result

        result["operator_found"] = True
        result["operator_pod"] = operator_pod.metadata.name
        result["operator_namespace"] = operator_ns
        result["operator_status"] = (
            operator_pod.status.phase if operator_pod.status else "Unknown"
        )

        # Read operator logs
        try:
            logs = await asyncio.to_thread(
                self._core_v1.read_namespaced_pod_log,
                name=operator_pod.metadata.name,
                namespace=operator_ns,
                tail_lines=tail_lines,
            )

            recent_errors = []
            for line in logs.splitlines():
                line_lower = line.lower()
                if any(kw in line_lower for kw in self._ERROR_KEYWORDS):
                    recent_errors.append(line.strip())

            result["recent_errors"] = recent_errors[-20:]  # Cap at 20

            # Detect specific known issues
            log_text = logs.lower()
            if "multiple" in log_text and "instrumentation" in log_text:
                result["warnings"].append(
                    "⚠️ DETECTED: 'multiple OpenTelemetry Instrumentation instances' error. "
                    "The operator cannot inject auto-instrumentation when multiple "
                    "Instrumentation CRDs exist in the same namespace. "
                    "Delete duplicate Instrumentation CRDs."
                )
            if "webhook" in log_text and ("fail" in log_text or "error" in log_text):
                result["warnings"].append(
                    "⚠️ DETECTED: Webhook errors in operator logs. "
                    "The mutating webhook may be failing to inject init containers. "
                    "Check cert-manager or webhook certificate expiry."
                )

        except Exception as e:
            result["warnings"].append(f"Failed to read operator logs: {e}")

        # Count Instrumentation CRDs per namespace (multi-instance detection)
        try:
            namespaces = await self.list_namespaces()
            for ns in namespaces[:20]:  # Cap at 20 namespaces
                try:
                    instrs = await self.list_instrumentations(namespace=ns)
                    count = len(instrs.get("items", []))
                    if count > 0:
                        result["instrumentation_cr_counts"][ns] = count
                        if count > 1:
                            result["warnings"].append(
                                f"⚠️ Namespace '{ns}' has {count} Instrumentation CRDs. "
                                "The operator requires exactly 1 per namespace for injection."
                            )
                except Exception:
                    continue
        except Exception:
            pass

        return result

    # ──────────────────────────────────────────────
    # Env var remediation (Gap 3)
    # ──────────────────────────────────────────────

    _OTEL_CONFLICT_ENV_VARS = [
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
        "OTEL_COLLECTOR_NAME",
    ]

    async def strip_otel_env_vars(
        self,
        namespace: str,
        deployment_name: str,
        env_vars: Optional[List[str]] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Remove conflicting OTEL_* env vars from a deployment.

        Uses a strategic merge patch to null out specified env vars
        from all containers in the deployment's pod template.

        Args:
            namespace: Deployment namespace.
            deployment_name: Deployment name.
            env_vars: Specific env var names to remove. Defaults to
                the standard OTEL_* conflict set.
            dry_run: If True, returns what would be removed without applying.

        Returns:
            Dict with removed vars, affected containers, and dry_run status.
        """
        self._ensure_available()

        target_vars = env_vars or self._OTEL_CONFLICT_ENV_VARS

        # Read the deployment to find which vars exist
        dep = await self.get_deployment(namespace, deployment_name)
        found_vars: Dict[str, List[str]] = {}  # container_name -> [env_var_names]

        for c in dep.get("containers", []):
            if c.get("is_init_container"):
                continue
            env = c.get("env", {})
            matches = [v for v in target_vars if v in env]
            if matches:
                found_vars[c["name"]] = matches

        if not found_vars:
            return {
                "deployment": f"{namespace}/{deployment_name}",
                "dry_run": dry_run,
                "action": "no_change",
                "message": "No conflicting OTEL_* env vars found.",
            }

        if dry_run:
            return {
                "deployment": f"{namespace}/{deployment_name}",
                "dry_run": True,
                "action": "dry_run",
                "would_remove": found_vars,
                "message": (
                    f"Would remove {sum(len(v) for v in found_vars.values())} "
                    "OTEL_* env var(s). Set dry_run=False to apply."
                ),
            }

        # Build strategic merge patch to remove env vars
        # The K8s API removes an env var when its value is set to null
        # in a strategic merge patch with $patch: delete
        from kubernetes import client as k8s_client

        containers_patch = []
        for container_name, vars_to_remove in found_vars.items():
            env_patch = [
                k8s_client.V1EnvVar(name=v, value=None)
                for v in vars_to_remove
            ]
            containers_patch.append({
                "name": container_name,
                "env": [{"name": v, "$patch": "delete"} for v in vars_to_remove],
            })

        patch_body = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": containers_patch,
                    }
                }
            }
        }

        await asyncio.to_thread(
            self._apps_v1.patch_namespaced_deployment,
            name=deployment_name,
            namespace=namespace,
            body=patch_body,
        )

        return {
            "deployment": f"{namespace}/{deployment_name}",
            "dry_run": False,
            "action": "applied",
            "removed": found_vars,
            "message": (
                f"Removed {sum(len(v) for v in found_vars.values())} "
                "OTEL_* env var(s). Deployment will rolling-restart."
            ),
        }

    # ──────────────────────────────────────────────
    # Service endpoint health (Gap 4)
    # ──────────────────────────────────────────────

    async def get_collector_service_health(
        self,
        namespace: str,
        collector_name: str,
    ) -> Dict[str, Any]:
        """Validate the K8s Service and Endpoints backing a collector.

        The OTel Operator creates Services matching the collector name
        pattern ``{collector_name}-collector``. This method checks
        whether the Service exists and has ready Endpoints.

        Args:
            namespace: Collector namespace.
            collector_name: Collector CRD name.

        Returns:
            Service health dict with selector, endpoint counts, and warnings.
        """
        self._ensure_available()
        result: Dict[str, Any] = {
            "service_found": False,
            "service_name": None,
            "selector": None,
            "ready_endpoints": 0,
            "not_ready_endpoints": 0,
            "warnings": [],
        }

        # The OTel Operator uses the naming pattern: {name}-collector
        candidate_names = [
            f"{collector_name}-collector",
            collector_name,
        ]

        svc = None
        svc_name = None
        for name in candidate_names:
            try:
                svc = await asyncio.to_thread(
                    self._core_v1.read_namespaced_service,
                    name=name,
                    namespace=namespace,
                )
                svc_name = name
                break
            except Exception:
                continue

        if not svc:
            result["warnings"].append(
                f"No K8s Service found for collector '{collector_name}' "
                f"in namespace '{namespace}'. Tried: {candidate_names}"
            )
            return result

        result["service_found"] = True
        result["service_name"] = svc_name
        result["selector"] = svc.spec.selector if svc.spec else None

        # Check endpoints
        try:
            endpoints = await asyncio.to_thread(
                self._core_v1.read_namespaced_endpoints,
                name=svc_name,
                namespace=namespace,
            )

            ready = 0
            not_ready = 0
            if endpoints.subsets:
                for subset in endpoints.subsets:
                    if subset.addresses:
                        ready += len(subset.addresses)
                    if subset.not_ready_addresses:
                        not_ready += len(subset.not_ready_addresses)

            result["ready_endpoints"] = ready
            result["not_ready_endpoints"] = not_ready

            if ready == 0:
                if not_ready > 0:
                    result["warnings"].append(
                        f"⚠️ CRITICAL: Service '{svc_name}' has {not_ready} "
                        "endpoint(s) but NONE are ready. Collector pods may "
                        "be crashing or failing health checks."
                    )
                else:
                    result["warnings"].append(
                        f"⚠️ CRITICAL: Service '{svc_name}' has NO endpoints. "
                        "The selector may be orphaned (pointing to deleted pods) "
                        "or no collector pods are running. "
                        f"Selector: {svc.spec.selector if svc.spec else 'none'}"
                    )
        except Exception as e:
            result["warnings"].append(f"Failed to read endpoints: {e}")

        return result

    # ──────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────

    @staticmethod
    def _deployment_to_dict(deployment: Any) -> Dict[str, Any]:
        """Convert a V1Deployment object to a simplified dict."""
        metadata = deployment.metadata
        spec = deployment.spec
        status = deployment.status

        # Extract pod template annotations
        pod_annotations = {}
        if spec.template and spec.template.metadata:
            pod_annotations = spec.template.metadata.annotations or {}

        # Extract container info
        containers = []
        if spec.template and spec.template.spec:
            for c in spec.template.spec.containers or []:
                env_vars = {}
                if c.env:
                    for e in c.env:
                        if e.value:
                            env_vars[e.name] = e.value
                        elif e.value_from:
                            # Track the env var name even for valueFrom sources.
                            # Use a sentinel so OTEL_* key detection still fires.
                            env_vars[e.name] = "<from-ref>"
                containers.append({
                    "name": c.name,
                    "image": c.image,
                    "env": env_vars,
                })

            # Check for init containers (OTel agent injection)
            for ic in spec.template.spec.init_containers or []:
                containers.append({
                    "name": ic.name,
                    "image": ic.image,
                    "is_init_container": True,
                })

        return {
            "name": metadata.name,
            "namespace": metadata.namespace,
            "labels": metadata.labels or {},
            "annotations": metadata.annotations or {},
            "pod_annotations": pod_annotations,
            "replicas": spec.replicas or 0,
            "ready_replicas": status.ready_replicas or 0 if status else 0,
            "containers": containers,
            "kind": "Deployment",
        }

    @staticmethod
    def _pod_to_dict(pod: Any) -> Dict[str, Any]:
        """Convert a V1Pod object to a simplified dict."""
        metadata = pod.metadata
        spec = pod.spec
        status = pod.status

        containers = []
        if spec.containers:
            for c in spec.containers:
                security_context = {}
                if c.security_context:
                    sc = c.security_context
                    security_context = {
                        "privileged": sc.privileged or False,
                        "capabilities": (
                            [cap for cap in (sc.capabilities.add or [])]
                            if sc.capabilities else []
                        ),
                    }
                volume_mounts = []
                if c.volume_mounts:
                    for vm in c.volume_mounts:
                        volume_mounts.append({
                            "name": vm.name,
                            "mount_path": vm.mount_path,
                        })
                containers.append({
                    "name": c.name,
                    "image": c.image,
                    "security_context": security_context,
                    "volume_mounts": volume_mounts,
                })

        # Extract host volumes
        host_volumes = []
        if spec.volumes:
            for v in spec.volumes:
                if v.host_path:
                    host_volumes.append({
                        "name": v.name,
                        "host_path": v.host_path.path,
                    })

        return {
            "name": metadata.name,
            "namespace": metadata.namespace,
            "node_name": spec.node_name,
            "labels": metadata.labels or {},
            "annotations": metadata.annotations or {},
            "host_pid": spec.host_pid or False,
            "containers": containers,
            "host_volumes": host_volumes,
            "phase": status.phase if status else "Unknown",
        }
