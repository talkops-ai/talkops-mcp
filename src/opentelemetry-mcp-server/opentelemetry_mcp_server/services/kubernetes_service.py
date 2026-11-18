"""Kubernetes API service for OpenTelemetry MCP server.

Wraps the synchronous ``kubernetes`` Python client with ``asyncio.to_thread()``
for non-blocking async operation in the FastMCP event loop.
"""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from opentelemetry_mcp_server.config import KubernetesConfig, OtelOperatorConfig
from opentelemetry_mcp_server.exceptions import (
    OtelConnectionError,
    OtelResourceNotFoundError,
    OtelValidationError,
)
from opentelemetry_mcp_server.utils.redaction import (
    REDACTED_VALUE,
    redact_log_text,
)

logger = logging.getLogger(__name__)

VALID_WORKLOAD_KINDS = ("Deployment", "StatefulSet", "DaemonSet")
VALID_CR_KINDS = (
    "OpenTelemetryCollector",
    "Instrumentation",
    "TargetAllocator",
    "OpAMPBridge",
)


class KubernetesService:
    """Async-wrapped Kubernetes API client for OTel CRD and workload operations.

    Handles both in-cluster and out-of-cluster (kubeconfig) authentication.
    Bound to a single cluster context per server instance (`--context` /
    `KUBE_CONTEXT`). All K8s API calls are wrapped in ``asyncio.to_thread()``
    to avoid blocking the FastMCP event loop.
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

        if k8s_config.enabled:
            self._init_client()

    def _init_client(self) -> None:
        """Initialize the Kubernetes client bound to the configured context."""
        try:
            from kubernetes import client, config as k8s_config_loader

            if self._k8s_config.in_cluster:
                k8s_config_loader.load_incluster_config()
            else:
                load_kwargs: Dict[str, Any] = {}
                if self._k8s_config.kubeconfig:
                    load_kwargs["config_file"] = self._k8s_config.kubeconfig
                if self._k8s_config.context_name:
                    load_kwargs["context"] = self._k8s_config.context_name
                k8s_config_loader.load_kube_config(**load_kwargs)

            self._core_v1 = client.CoreV1Api()
            self._apps_v1 = client.AppsV1Api()
            self._custom_api = client.CustomObjectsApi()
            self._initialized = True

            logger.info(
                "Kubernetes client initialized successfully (context=%s)",
                self._k8s_config.context_name or "default",
            )
        except Exception as e:
            logger.warning(f"Kubernetes client initialization failed: {e}")
            self._initialized = False

    async def list_available_contexts(self) -> List[Dict[str, Any]]:
        """List all available kubeconfig contexts.

        Returns context names and which one is the active context for this server.
        """
        try:
            from kubernetes import config as k8s_config_loader

            kwargs: Dict[str, Any] = {}
            cfg_kubeconfig = getattr(self._k8s_config, "kubeconfig", None)
            if isinstance(cfg_kubeconfig, str) and cfg_kubeconfig:
                kwargs["config_file"] = cfg_kubeconfig
            contexts, current = k8s_config_loader.list_kube_config_contexts(**kwargs)

            result = []
            cfg_ctx = getattr(self._k8s_config, "context_name", None)
            if not isinstance(cfg_ctx, str):
                cfg_ctx = None
            current_name = (
                cfg_ctx
                or (current.get("name", "") if isinstance(current, dict) else "")
            )

            for ctx in contexts:
                ctx_dict: Dict[str, Any] = (
                    dict(ctx) if not isinstance(ctx, dict) else ctx
                )
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
                "name": self._k8s_config.context_name or "default",
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
        """List OpenTelemetryCollector CRDs."""
        self._ensure_available()

        kwargs: Dict[str, Any] = {
            "group": self._otel_config.crd_group,
            "version": self._otel_config.crd_api_version,
            "plural": self._otel_config.collector_plural,
        }
        if label_selector:
            kwargs["label_selector"] = label_selector

        try:
            if namespace:
                kwargs["namespace"] = namespace
                return await asyncio.to_thread(
                    self._custom_api.list_namespaced_custom_object, **kwargs
                )
            return await asyncio.to_thread(
                self._custom_api.list_cluster_custom_object, **kwargs
            )
        except Exception as e:
            if getattr(e, "status", None) == 404 or "404" in str(e) or "NotFound" in str(e):
                logger.debug("OpenTelemetryCollector CRD not installed or namespace not found: %s", e)
                return {"items": [], "crd_installed": False}
            raise

    async def get_otel_collector(
        self, namespace: str, name: str
    ) -> Dict[str, Any]:
        """Get a single OpenTelemetryCollector CRD."""
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
        """List Instrumentation CRDs."""
        self._ensure_available()

        kwargs: Dict[str, Any] = {
            "group": self._otel_config.crd_group,
            "version": self._otel_config.instrumentation_api_version,
            "plural": self._otel_config.instrumentation_plural,
        }
        if label_selector:
            kwargs["label_selector"] = label_selector

        try:
            if namespace:
                kwargs["namespace"] = namespace
                return await asyncio.to_thread(
                    self._custom_api.list_namespaced_custom_object, **kwargs
                )
            return await asyncio.to_thread(
                self._custom_api.list_cluster_custom_object, **kwargs
            )
        except Exception as e:
            if getattr(e, "status", None) == 404 or "404" in str(e) or "NotFound" in str(e):
                logger.debug("Instrumentation CRD not installed or namespace not found: %s", e)
                return {"items": [], "crd_installed": False}
            raise

    async def get_instrumentation(
        self, namespace: str, name: str
    ) -> Dict[str, Any]:
        """Get a single Instrumentation CRD."""
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
    # TargetAllocator & OpAMPBridge CRD operations
    # ──────────────────────────────────────────────

    async def list_target_allocators(
        self,
        namespace: Optional[str] = None,
        label_selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List TargetAllocator CRDs across v1beta1 and v1alpha1."""
        self._ensure_available()
        candidate_versions = [self._otel_config.target_allocator_api_version]
        for fallback_ver in ("v1beta1", "v1alpha1"):
            if fallback_ver not in candidate_versions:
                candidate_versions.append(fallback_ver)

        for ver in candidate_versions:
            kwargs: Dict[str, Any] = {
                "group": self._otel_config.crd_group,
                "version": ver,
                "plural": self._otel_config.target_allocator_plural,
            }
            if label_selector:
                kwargs["label_selector"] = label_selector
            try:
                if namespace:
                    kwargs["namespace"] = namespace
                    return await asyncio.to_thread(
                        self._custom_api.list_namespaced_custom_object, **kwargs
                    )
                return await asyncio.to_thread(
                    self._custom_api.list_cluster_custom_object, **kwargs
                )
            except Exception as e:
                logger.debug("TargetAllocator CRD list (%s) returned error: %s", ver, e)
                continue
        return {"items": []}

    async def get_target_allocator(
        self, namespace: str, name: str
    ) -> Dict[str, Any]:
        """Get a single TargetAllocator CRD across v1beta1 and v1alpha1."""
        self._ensure_available()
        candidate_versions = [self._otel_config.target_allocator_api_version]
        for fallback_ver in ("v1beta1", "v1alpha1"):
            if fallback_ver not in candidate_versions:
                candidate_versions.append(fallback_ver)

        last_err: Optional[Exception] = None
        for ver in candidate_versions:
            try:
                return await asyncio.to_thread(
                    self._custom_api.get_namespaced_custom_object,
                    group=self._otel_config.crd_group,
                    version=ver,
                    namespace=namespace,
                    plural=self._otel_config.target_allocator_plural,
                    name=name,
                )
            except Exception as e:
                last_err = e
                if "404" in str(e) or "NotFound" in str(e):
                    continue
                raise OtelConnectionError(f"Failed to get TargetAllocator: {e}")

        raise OtelResourceNotFoundError(
            f"TargetAllocator '{name}' not found in namespace '{namespace}'"
            + (f" ({last_err})" if last_err and "404" not in str(last_err) else "")
        )

    async def list_opamp_bridges(
        self,
        namespace: Optional[str] = None,
        label_selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List OpAMPBridge CRDs (read-only visibility per D6)."""
        self._ensure_available()
        kwargs: Dict[str, Any] = {
            "group": self._otel_config.crd_group,
            "version": self._otel_config.opamp_bridge_api_version,
            "plural": self._otel_config.opamp_bridge_plural,
        }
        if label_selector:
            kwargs["label_selector"] = label_selector

        try:
            if namespace:
                kwargs["namespace"] = namespace
                return await asyncio.to_thread(
                    self._custom_api.list_namespaced_custom_object, **kwargs
                )
            return await asyncio.to_thread(
                self._custom_api.list_cluster_custom_object, **kwargs
            )
        except Exception as e:
            logger.debug("OpAMPBridge CRD list returned error: %s", e)
            return {"items": []}

    async def get_opamp_bridge(
        self, namespace: str, name: str
    ) -> Dict[str, Any]:
        """Get a single OpAMPBridge CRD."""
        self._ensure_available()
        try:
            return await asyncio.to_thread(
                self._custom_api.get_namespaced_custom_object,
                group=self._otel_config.crd_group,
                version=self._otel_config.opamp_bridge_api_version,
                namespace=namespace,
                plural=self._otel_config.opamp_bridge_plural,
                name=name,
            )
        except Exception as e:
            if "404" in str(e) or "NotFound" in str(e):
                raise OtelResourceNotFoundError(
                    f"OpAMPBridge '{name}' not found in namespace '{namespace}'"
                )
            raise OtelConnectionError(f"Failed to get OpAMPBridge: {e}")

    async def delete_custom_resource(
        self,
        kind: str,
        namespace: str,
        name: str,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Delete an OpenTelemetry Custom Resource.

        Supports OpenTelemetryCollector, Instrumentation, TargetAllocator,
        and OpAMPBridge.
        """
        self._ensure_available()
        kind_map = {
            "OpenTelemetryCollector": (
                self._otel_config.crd_api_version,
                self._otel_config.collector_plural,
                self.get_otel_collector,
            ),
            "Instrumentation": (
                self._otel_config.instrumentation_api_version,
                self._otel_config.instrumentation_plural,
                self.get_instrumentation,
            ),
            "TargetAllocator": (
                self._otel_config.target_allocator_api_version,
                self._otel_config.target_allocator_plural,
                self.get_target_allocator,
            ),
            "OpAMPBridge": (
                self._otel_config.opamp_bridge_api_version,
                self._otel_config.opamp_bridge_plural,
                self.get_opamp_bridge,
            ),
        }
        if kind not in kind_map:
            raise OtelValidationError(
                f"Unsupported custom resource kind '{kind}'. "
                f"Valid kinds: {list(VALID_CR_KINDS)}"
            )

        version, plural, getter = kind_map[kind]
        existing = await getter(namespace, name)
        api_ver = str(existing.get("apiVersion", "") or "")
        if "/" in api_ver:
            version = api_ver.split("/", 1)[1] or version

        if dry_run:
            return {
                "kind": kind,
                "name": name,
                "namespace": namespace,
                "dry_run": True,
                "action": "would_delete",
                "existing_metadata": {
                    "labels": existing.get("metadata", {}).get("labels", {}),
                    "annotations": existing.get("metadata", {}).get("annotations", {}),
                },
            }

        await asyncio.to_thread(
            self._custom_api.delete_namespaced_custom_object,
            group=self._otel_config.crd_group,
            version=version,
            namespace=namespace,
            plural=plural,
            name=name,
        )
        return {
            "kind": kind,
            "name": name,
            "namespace": namespace,
            "dry_run": False,
            "action": "deleted",
        }

    # ──────────────────────────────────────────────
    # Workload operations (Deployments, StatefulSets, DaemonSets)
    # ──────────────────────────────────────────────

    @staticmethod
    def _normalize_workload_kind(kind: str) -> str:
        """Normalize workload kind casing."""
        normalized = (kind or "Deployment").strip().lower()
        mapping = {
            "deployment": "Deployment",
            "deployments": "Deployment",
            "statefulset": "StatefulSet",
            "statefulsets": "StatefulSet",
            "daemonset": "DaemonSet",
            "daemonsets": "DaemonSet",
        }
        if normalized not in mapping:
            raise OtelValidationError(
                f"Invalid workload_kind '{kind}'. "
                f"Supported kinds: {list(VALID_WORKLOAD_KINDS)}"
            )
        return mapping[normalized]

    async def list_workloads(
        self,
        namespace: str,
        kinds: Optional[List[str]] = None,
        label_selector: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List workloads (Deployments, StatefulSets, DaemonSets) in a namespace."""
        self._ensure_available()
        target_kinds = (
            [self._normalize_workload_kind(k) for k in kinds]
            if kinds
            else ["Deployment", "StatefulSet", "DaemonSet"]
        )
        kwargs: Dict[str, Any] = {"namespace": namespace}
        if label_selector:
            kwargs["label_selector"] = label_selector

        workloads: List[Dict[str, Any]] = []
        for kind in target_kinds:
            try:
                if kind == "Deployment":
                    res = await asyncio.to_thread(
                        self._apps_v1.list_namespaced_deployment, **kwargs
                    )
                elif kind == "StatefulSet":
                    res = await asyncio.to_thread(
                        self._apps_v1.list_namespaced_stateful_set, **kwargs
                    )
                elif kind == "DaemonSet":
                    res = await asyncio.to_thread(
                        self._apps_v1.list_namespaced_daemon_set, **kwargs
                    )
                else:
                    continue
                for item in getattr(res, "items", []) or []:
                    workloads.append(self._workload_to_dict(item, kind=kind))
            except Exception as e:
                logger.debug("Failed listing %s in %s: %s", kind, namespace, e)

        return workloads

    async def get_workload(
        self,
        namespace: str,
        name: str,
        kind: str = "Deployment",
    ) -> Dict[str, Any]:
        """Get a single Deployment, StatefulSet, or DaemonSet."""
        self._ensure_available()
        norm_kind = self._normalize_workload_kind(kind)
        try:
            if norm_kind == "Deployment":
                result = await asyncio.to_thread(
                    self._apps_v1.read_namespaced_deployment,
                    name=name,
                    namespace=namespace,
                )
            elif norm_kind == "StatefulSet":
                result = await asyncio.to_thread(
                    self._apps_v1.read_namespaced_stateful_set,
                    name=name,
                    namespace=namespace,
                )
            else:
                result = await asyncio.to_thread(
                    self._apps_v1.read_namespaced_daemon_set,
                    name=name,
                    namespace=namespace,
                )
            return self._workload_to_dict(result, kind=norm_kind)
        except Exception as e:
            if "404" in str(e) or "NotFound" in str(e):
                raise OtelResourceNotFoundError(
                    f"{norm_kind} '{name}' not found in namespace '{namespace}'"
                )
            raise OtelConnectionError(f"Failed to get {norm_kind.lower()}: {e}")

    async def patch_workload_annotations(
        self,
        namespace: str,
        name: str,
        annotations: Dict[str, Optional[str]],
        kind: str = "Deployment",
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Patch annotations on a workload's pod template.

        Passing ``None`` as an annotation value removes that annotation key
        via Kubernetes strategic merge patch.
        """
        self._ensure_available()
        norm_kind = self._normalize_workload_kind(kind)
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

        try:
            if norm_kind == "Deployment":
                result = await asyncio.to_thread(
                    self._apps_v1.patch_namespaced_deployment, **kwargs
                )
            elif norm_kind == "StatefulSet":
                result = await asyncio.to_thread(
                    self._apps_v1.patch_namespaced_stateful_set, **kwargs
                )
            else:
                result = await asyncio.to_thread(
                    self._apps_v1.patch_namespaced_daemon_set, **kwargs
                )
            return self._workload_to_dict(result, kind=norm_kind)
        except Exception as e:
            if "404" in str(e) or "NotFound" in str(e):
                raise OtelResourceNotFoundError(
                    f"{norm_kind} '{name}' not found in namespace '{namespace}'"
                )
            raise OtelConnectionError(f"Failed to patch {norm_kind.lower()}: {e}")

    async def restart_workload(
        self,
        namespace: str,
        name: str,
        kind: str = "Deployment",
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Trigger a rolling restart of a Deployment, StatefulSet, or DaemonSet."""
        restarted_at = datetime.now(timezone.utc).isoformat()
        return await self.patch_workload_annotations(
            namespace=namespace,
            name=name,
            annotations={"kubectl.kubernetes.io/restartedAt": restarted_at},
            kind=kind,
            dry_run=dry_run,
        )

    async def list_deployments(
        self,
        namespace: str,
        label_selector: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List Deployments in a namespace."""
        self._ensure_available()
        kwargs: Dict[str, Any] = {"namespace": namespace}
        if label_selector:
            kwargs["label_selector"] = label_selector

        result = await asyncio.to_thread(
            self._apps_v1.list_namespaced_deployment, **kwargs
        )
        return [self._deployment_to_dict(d) for d in result.items]

    async def get_deployment(
        self, namespace: str, name: str
    ) -> Dict[str, Any]:
        """Get a single Deployment."""
        return await self.get_workload(namespace, name, kind="Deployment")

    async def patch_deployment_annotations(
        self,
        namespace: str,
        name: str,
        annotations: Dict[str, Optional[str]],
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Patch annotations on a Deployment's pod template."""
        return await self.patch_workload_annotations(
            namespace=namespace,
            name=name,
            annotations=annotations,
            kind="Deployment",
            dry_run=dry_run,
        )

    # ──────────────────────────────────────────────
    # Pod operations
    # ──────────────────────────────────────────────

    async def list_pods(
        self,
        namespace: Optional[str] = None,
        label_selector: Optional[str] = None,
        field_selector: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List pods."""
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
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Create or patch an Instrumentation CRD."""
        self._ensure_available()
        body: Dict[str, Any] = {
            "apiVersion": f"{self._otel_config.crd_group}/{self._otel_config.instrumentation_api_version}",
            "kind": "Instrumentation",
            "metadata": {
                "name": name,
                "namespace": namespace,
            },
            "spec": spec,
        }

        base_kwargs: Dict[str, Any] = {
            "group": self._otel_config.crd_group,
            "version": self._otel_config.instrumentation_api_version,
            "namespace": namespace,
            "plural": self._otel_config.instrumentation_plural,
        }
        if dry_run:
            base_kwargs["dry_run"] = "All"

        try:
            existing = await self.get_instrumentation(namespace, name)
            if overwrite:
                existing_rv = existing.get("metadata", {}).get("resourceVersion")
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
            return await asyncio.to_thread(
                self._custom_api.create_namespaced_custom_object,
                **base_kwargs,
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
        """Create or patch an OpenTelemetryCollector CRD."""
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
            existing = await self.get_otel_collector(namespace, name)

            if not dry_run:
                self._store_config_snapshot(existing, body)

            if overwrite:
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
            return await asyncio.to_thread(
                self._custom_api.create_namespaced_custom_object,
                **base_kwargs,
                body=body,
            )

    # ──────────────────────────────────────────────
    # RBAC for k8sattributes & Infrastructure Receivers
    # ──────────────────────────────────────────────

    @staticmethod
    def build_receiver_rbac_manifests(
        namespace: str,
        collector_name: str,
        receivers: Optional[List[str]] = None,
        include_k8sattributes: bool = True,
        target_allocator_enabled: bool = False,
    ) -> Dict[str, Any]:
        """Build least-privilege ClusterRole and ClusterRoleBinding manifests.

        Supports RBAC rules for:
        - k8sattributes processor
        - kubeletstats receiver
        - k8s_cluster receiver
        - k8sobjects / k8s_events receiver
        - prometheus Target Allocator (monitoring.coreos.com CRDs)
        """
        sa_name = f"{collector_name}-collector"
        role_name = f"otel-k8sattr-{collector_name}"
        receiver_set = set(receivers or [])

        rules: List[Dict[str, Any]] = []

        if include_k8sattributes:
            rules.extend([
                {
                    "apiGroups": [""],
                    "resources": ["pods", "namespaces", "nodes"],
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
            ])

        if "kubeletstats" in receiver_set:
            rules.append({
                "apiGroups": [""],
                "resources": [
                    "nodes",
                    "nodes/stats",
                    "nodes/metrics",
                    "nodes/proxy",
                ],
                "verbs": ["get", "list", "watch"],
            })

        if "k8s_cluster" in receiver_set:
            rules.extend([
                {
                    "apiGroups": [""],
                    "resources": [
                        "events",
                        "namespaces",
                        "nodes",
                        "pods",
                        "replicationcontrollers",
                        "resourcequotas",
                        "services",
                    ],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["apps"],
                    "resources": [
                        "daemonsets",
                        "deployments",
                        "replicasets",
                        "statefulsets",
                    ],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["batch"],
                    "resources": ["jobs", "cronjobs"],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["autoscaling"],
                    "resources": ["horizontalpodautoscalers"],
                    "verbs": ["get", "list", "watch"],
                },
            ])

        if "k8sobjects" in receiver_set or "k8s_events" in receiver_set:
            rules.extend([
                {
                    "apiGroups": [""],
                    "resources": ["events"],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["events.k8s.io"],
                    "resources": ["events"],
                    "verbs": ["get", "list", "watch"],
                },
            ])

        if "prometheus_ta" in receiver_set or target_allocator_enabled:
            rules.extend([
                {
                    "apiGroups": [""],
                    "resources": [
                        "nodes",
                        "nodes/metrics",
                        "services",
                        "endpoints",
                        "pods",
                        "namespaces",
                    ],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["networking.k8s.io"],
                    "resources": ["ingresses"],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["discovery.k8s.io"],
                    "resources": ["endpointslices"],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["monitoring.coreos.com"],
                    "resources": [
                        "servicemonitors",
                        "podmonitors",
                        "scrapeconfigs",
                        "probes",
                    ],
                    "verbs": ["get", "list", "watch"],
                },
            ])

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
            "rules": rules,
        }

        subjects: List[Dict[str, str]] = [
            {
                "kind": "ServiceAccount",
                "name": sa_name,
                "namespace": namespace,
            },
        ]
        if "prometheus_ta" in receiver_set or target_allocator_enabled:
            subjects.append(
                {
                    "kind": "ServiceAccount",
                    "name": f"{collector_name}-targetallocator",
                    "namespace": namespace,
                }
            )

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
            "subjects": subjects,
        }

        return {
            "cluster_role": cluster_role,
            "cluster_role_binding": cluster_role_binding,
        }

    @staticmethod
    def build_k8sattributes_rbac_manifests(
        namespace: str,
        collector_name: str,
    ) -> Dict[str, Any]:
        """Build ClusterRole and ClusterRoleBinding manifests for k8sattributes."""
        return KubernetesService.build_receiver_rbac_manifests(
            namespace=namespace,
            collector_name=collector_name,
            receivers=[],
            include_k8sattributes=True,
        )

    async def create_receiver_rbac(
        self,
        namespace: str,
        collector_name: str,
        receivers: Optional[List[str]] = None,
        include_k8sattributes: bool = True,
        target_allocator_enabled: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Create or update RBAC resources required by k8sattributes and receivers."""
        manifests = self.build_receiver_rbac_manifests(
            namespace=namespace,
            collector_name=collector_name,
            receivers=receivers,
            include_k8sattributes=include_k8sattributes,
            target_allocator_enabled=target_allocator_enabled,
        )
        role_name = manifests["cluster_role"]["metadata"]["name"]
        if dry_run:
            return {
                "cluster_role": {"name": role_name, "action": "dry_run"},
                "cluster_role_binding": {"name": role_name, "action": "dry_run"},
                "manifests": manifests,
            }

        self._ensure_available()
        from kubernetes import client as k8s_client

        rbac_api = k8s_client.RbacAuthorizationV1Api()
        results: Dict[str, Any] = {}

        # Create or update ClusterRole
        try:
            await asyncio.to_thread(
                rbac_api.read_cluster_role, name=role_name
            )
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
            await asyncio.to_thread(
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

        return results

    async def create_k8sattributes_rbac(
        self,
        namespace: str,
        collector_name: str,
    ) -> Dict[str, Any]:
        """Create RBAC resources required by the k8sattributes processor."""
        return await self.create_receiver_rbac(
            namespace=namespace,
            collector_name=collector_name,
            include_k8sattributes=True,
            dry_run=False,
        )

    async def check_cluster_role_binding_exists(
        self,
        collector_name: str,
        namespace: Optional[str] = None,
    ) -> bool:
        """Check if a ClusterRoleBinding exists for a collector's ServiceAccount."""
        self._ensure_available()
        from kubernetes import client as k8s_client

        rbac_api = k8s_client.RbacAuthorizationV1Api()
        role_name = f"otel-k8sattr-{collector_name}"
        try:
            await asyncio.to_thread(
                rbac_api.read_cluster_role_binding, name=role_name
            )
            return True
        except Exception:
            pass

        # Fallback: scan ClusterRoleBindings for subject matching {collector_name}-collector
        sa_name = f"{collector_name}-collector"
        try:
            bindings = await asyncio.to_thread(rbac_api.list_cluster_role_binding)
            for item in getattr(bindings, "items", []) or []:
                for subj in getattr(item, "subjects", []) or []:
                    if getattr(subj, "name", "") == sa_name:
                        if namespace is None or getattr(subj, "namespace", None) == namespace:
                            return True
        except Exception:
            pass

        return False

    async def list_otel_cluster_roles(
        self, namespace: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List ClusterRoles associated with OpenTelemetry collectors or agents.

        Excludes the OpenTelemetry Operator's own system controller/webhook roles
        so cluster operator installation does not produce false-positive collector
        RBAC findings, and scopes to bound ServiceAccounts in ``namespace`` when
        provided.
        """
        self._ensure_available()
        from kubernetes import client as k8s_client

        rbac_api = k8s_client.RbacAuthorizationV1Api()
        roles: List[Dict[str, Any]] = []
        bound_role_names_for_ns: Optional[set[str]] = None
        if namespace:
            bound_role_names_for_ns = set()
            try:
                bindings = await asyncio.to_thread(rbac_api.list_cluster_role_binding)
                for b in getattr(bindings, "items", []) or []:
                    role_ref = getattr(b, "role_ref", None)
                    ref_name = getattr(role_ref, "name", "") if role_ref else ""
                    for subj in getattr(b, "subjects", []) or []:
                        if getattr(subj, "namespace", None) == namespace and ref_name:
                            bound_role_names_for_ns.add(ref_name)
            except Exception:
                bound_role_names_for_ns = None

        try:
            res = await asyncio.to_thread(rbac_api.list_cluster_role)
            for item in getattr(res, "items", []) or []:
                name = getattr(item.metadata, "name", "") or ""
                labels = getattr(item.metadata, "labels", None) or {}
                name_low = name.lower()
                # Skip OpenTelemetry Operator's own controller/webhook/metrics ClusterRoles
                # and GitOps/Kargo/ArgoCD project roles that merely match a namespace substring
                if (
                    name_low.startswith(
                        ("opentelemetry-operator-", "kargo-", "argocd-")
                    )
                    or labels.get("app.kubernetes.io/name") == "opentelemetry-operator"
                    or labels.get("app.kubernetes.io/part-of") == "opentelemetry-operator"
                    or labels.get("app.kubernetes.io/part-of") in ("kargo", "argocd")
                ):
                    continue
                is_otel = (
                    "otel" in name_low
                    or "opentelemetry" in name_low
                    or labels.get("app.kubernetes.io/managed-by") == "talkops-mcp"
                    or "talkops.ai/collector" in labels
                    or (bound_role_names_for_ns is not None and name in bound_role_names_for_ns and "otel" in name_low)
                )
                if not is_otel:
                    continue
                if bound_role_names_for_ns is not None and bound_role_names_for_ns:
                    if name not in bound_role_names_for_ns and labels.get("talkops.ai/namespace") not in (None, namespace):
                        continue
                    if name not in bound_role_names_for_ns and namespace not in name_low and "talkops.ai/collector" not in labels:
                        continue
                rules_list = []
                for r in getattr(item, "rules", []) or []:
                    rules_list.append({
                        "api_groups": list(getattr(r, "api_groups", None) or []),
                        "resources": list(getattr(r, "resources", None) or []),
                        "verbs": list(getattr(r, "verbs", None) or []),
                    })
                roles.append({
                    "name": name,
                    "labels": labels,
                    "rules": rules_list,
                })
        except Exception as e:
            logger.debug("Failed to list ClusterRoles: %s", e)

        return roles

    async def check_secret_key_exists(
        self,
        namespace: str,
        secret_name: str,
        key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify Secret and optional key existence without returning secret data."""
        self._ensure_available()
        try:
            secret = await asyncio.to_thread(
                self._core_v1.read_namespaced_secret,
                name=secret_name,
                namespace=namespace,
            )
            data_keys = list((getattr(secret, "data", None) or {}).keys())
            key_exists = True if key is None else (key in data_keys)
            return {
                "exists": True,
                "secret_name": secret_name,
                "namespace": namespace,
                "key": key,
                "key_exists": key_exists,
                "available_keys": data_keys,
            }
        except Exception as e:
            if "404" in str(e) or "NotFound" in str(e):
                return {
                    "exists": False,
                    "secret_name": secret_name,
                    "namespace": namespace,
                    "key": key,
                    "key_exists": False,
                    "available_keys": [],
                }
            raise OtelConnectionError(f"Failed to verify Secret '{secret_name}': {e}")

    # ──────────────────────────────────────────────
    # Service, Event, Log, and Namespace discovery
    # ──────────────────────────────────────────────

    async def list_services(
        self,
        namespace: str,
        label_selector: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List Kubernetes Services in a namespace."""
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
        """List all namespace names in the cluster."""
        self._ensure_available()
        result = await asyncio.to_thread(
            self._core_v1.list_namespace
        )
        return [ns.metadata.name for ns in result.items]

    async def count_nodes(self) -> int:
        """Count the number of nodes in the cluster."""
        self._ensure_available()
        result = await asyncio.to_thread(
            self._core_v1.list_node
        )
        return len(result.items)

    async def list_namespace_events(
        self,
        namespace: str,
        involved_object_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List recent Kubernetes Events in a namespace."""
        self._ensure_available()
        try:
            res = await asyncio.to_thread(
                self._core_v1.list_namespaced_event,
                namespace=namespace,
                limit=limit,
            )
            events: List[Dict[str, Any]] = []
            for ev in getattr(res, "items", []) or []:
                involved = getattr(ev, "involved_object", None)
                obj_name = getattr(involved, "name", "") if involved else ""
                obj_kind = getattr(involved, "kind", "") if involved else ""
                if involved_object_name and not (
                    obj_name == involved_object_name
                    or obj_name.startswith(f"{involved_object_name}-")
                ):
                    continue
                last_ts = getattr(ev, "last_timestamp", None) or getattr(
                    ev, "event_time", None
                )
                events.append({
                    "type": getattr(ev, "type", "Normal") or "Normal",
                    "reason": getattr(ev, "reason", "") or "",
                    "message": redact_log_text(getattr(ev, "message", "") or ""),
                    "count": getattr(ev, "count", 1) or 1,
                    "involved_object": {
                        "kind": obj_kind,
                        "name": obj_name,
                    },
                    "last_timestamp": (
                        last_ts.isoformat()
                        if hasattr(last_ts, "isoformat")
                        else str(last_ts or "")
                    ),
                })
            return events
        except Exception as e:
            logger.debug("Failed to list events in %s: %s", namespace, e)
            return []

    async def get_collector_pod_logs(
        self,
        namespace: str,
        collector_name: str,
        tail_lines: int = 50,
    ) -> Dict[str, Any]:
        """Fetch and classify redacted tail logs from a collector's pods."""
        self._ensure_available()
        selectors = [
            f"app.kubernetes.io/instance={namespace}.{collector_name}",
            f"app.kubernetes.io/name={collector_name}-collector",
        ]
        pods: List[Dict[str, Any]] = []
        for selector in selectors:
            try:
                pods = await self.list_pods(
                    namespace=namespace, label_selector=selector
                )
                if pods:
                    break
            except Exception:
                continue

        if not pods:
            # Fallback: match pod name prefix
            all_pods = await self.list_pods(namespace=namespace)
            pods = [
                p for p in all_pods
                if p.get("name", "").startswith(f"{collector_name}-collector")
                or p.get("name", "").startswith(collector_name)
            ]

        if not pods:
            return {
                "pod_name": None,
                "lines": [],
                "error_lines": [],
                "auth_errors": [],
                "tls_errors": [],
                "dns_errors": [],
            }

        target_pod = pods[0]["name"]
        try:
            raw_logs = await asyncio.to_thread(
                self._core_v1.read_namespaced_pod_log,
                name=target_pod,
                namespace=namespace,
                tail_lines=tail_lines,
            )
        except Exception as e:
            return {
                "pod_name": target_pod,
                "lines": [],
                "error_lines": [f"Failed to read pod logs: {e}"],
                "auth_errors": [],
                "tls_errors": [],
                "dns_errors": [],
            }

        redacted_logs = redact_log_text(raw_logs or "")
        lines = [ln.strip() for ln in redacted_logs.splitlines() if ln.strip()]
        error_lines: List[str] = []
        auth_errors: List[str] = []
        tls_errors: List[str] = []
        dns_errors: List[str] = []

        for line in lines:
            lower = line.lower()
            if any(k in lower for k in ("error", "failed", "fatal", "panic", "warn")):
                error_lines.append(line)
            if any(
                k in lower
                for k in (
                    "401",
                    "403",
                    "unauthorized",
                    "forbidden",
                    "unauthenticated",
                    "invalid api key",
                    "permission denied",
                )
            ):
                auth_errors.append(line)
            if any(
                k in lower
                for k in (
                    "x509:",
                    "certificate signed by unknown authority",
                    "tls: failed to verify certificate",
                    "bad certificate",
                    "certificate has expired",
                )
            ):
                tls_errors.append(line)
            if any(
                k in lower
                for k in (
                    "no such host",
                    "connection refused",
                    "context deadline exceeded",
                    "dial tcp",
                    "i/o timeout",
                    "name resolution",
                )
            ):
                dns_errors.append(line)

        return {
            "pod_name": target_pod,
            "lines": lines[-tail_lines:],
            "error_lines": error_lines[-20:],
            "auth_errors": auth_errors[-10:],
            "tls_errors": tls_errors[-10:],
            "dns_errors": dns_errors[-10:],
        }

    # ──────────────────────────────────────────────
    # Health check
    # ──────────────────────────────────────────────

    async def health_check(self) -> Dict[str, Any]:
        """Check K8s API connectivity and OTel CRD availability."""
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
                "context": self._k8s_config.context_name or "default",
            }
        except Exception as e:
            return {"status": "error", "message": f"API unreachable: {e}"}

    # ──────────────────────────────────────────────
    # Config snapshot and rollback
    # ──────────────────────────────────────────────

    _SNAPSHOT_ANNOTATION = "otel.mcp/last-known-good"
    _SNAPSHOT_TIMESTAMP_ANNOTATION = "otel.mcp/last-mutation"
    _SNAPSHOT_TOOL_ANNOTATION = "otel.mcp/last-mutation-tool"

    @staticmethod
    def _compress_config(config_str: str) -> str:
        """Gzip + base64 encode a config string for annotation storage."""
        import base64
        import gzip

        compressed = gzip.compress(config_str.encode("utf-8"))
        return base64.b64encode(compressed).decode("ascii")

    @staticmethod
    def _decompress_config(compressed: str) -> str:
        """Decompress a base64+gzip config string."""
        import base64
        import gzip

        raw = base64.b64decode(compressed)
        return gzip.decompress(raw).decode("utf-8")

    def _store_config_snapshot(
        self,
        existing_crd: Dict[str, Any],
        new_body: Dict[str, Any],
    ) -> None:
        """Store the current config as a snapshot annotation on the new body."""
        import json

        existing_config = existing_crd.get("spec", {}).get("config", "")
        if not existing_config:
            return

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
            logger.warning(f"Failed to store config snapshot: {e}")

    async def revert_collector_config(
        self,
        namespace: str,
        name: str,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Revert a collector to its pre-mutation config."""
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

        spec = dict(raw.get("spec", {}))
        existing_cfg_raw = raw.get("spec", {}).get("config", "")
        restored_cfg: Any = previous_config
        if isinstance(existing_cfg_raw, dict):
            import yaml as _yaml

            try:
                parsed_prev = _yaml.safe_load(previous_config)
                if isinstance(parsed_prev, dict):
                    restored_cfg = parsed_prev
            except Exception:
                pass
        spec["config"] = restored_cfg
        meta = raw.get("metadata", {}) or {}

        await self.create_or_patch_collector(
            namespace=namespace,
            name=name,
            spec=spec,
            labels=meta.get("labels") if isinstance(existing_cfg_raw, dict) else None,
            annotations=meta.get("annotations") if isinstance(existing_cfg_raw, dict) else None,
            overwrite=isinstance(existing_cfg_raw, dict),
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
    # Operator diagnostics
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
        """Scan the OTel Operator pod for recent errors and diagnostics."""
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

        try:
            logs = await asyncio.to_thread(
                self._core_v1.read_namespaced_pod_log,
                name=operator_pod.metadata.name,
                namespace=operator_ns,
                tail_lines=tail_lines,
            )
            logs = redact_log_text(logs or "")

            recent_errors = []
            for line in logs.splitlines():
                line_lower = line.lower()
                if any(kw in line_lower for kw in self._ERROR_KEYWORDS):
                    recent_errors.append(line.strip())

            result["recent_errors"] = recent_errors[-20:]

            log_text = logs.lower()
            if "multiple" in log_text and "instrumentation" in log_text:
                result["warnings"].append(
                    "DETECTED: 'multiple OpenTelemetry Instrumentation instances' error. "
                    "The operator cannot inject auto-instrumentation when multiple "
                    "Instrumentation CRDs exist in the same namespace. "
                    "Delete duplicate Instrumentation CRDs."
                )
            if "webhook" in log_text and ("fail" in log_text or "error" in log_text):
                result["warnings"].append(
                    "DETECTED: Webhook errors in operator logs. "
                    "The mutating webhook may be failing to inject init containers. "
                    "Check cert-manager or webhook certificate expiry."
                )

        except Exception as e:
            result["warnings"].append(f"Failed to read operator logs: {e}")

        try:
            namespaces = await self.list_namespaces()
            for ns in namespaces[:20]:
                try:
                    instrs = await self.list_instrumentations(namespace=ns)
                    count = len(instrs.get("items", []))
                    if count > 0:
                        result["instrumentation_cr_counts"][ns] = count
                        if count > 1:
                            result["warnings"].append(
                                f"Namespace '{ns}' has {count} Instrumentation CRDs. "
                                "The operator requires exactly 1 per namespace for injection."
                            )
                except Exception:
                    continue
        except Exception:
            pass

        return result

    # ──────────────────────────────────────────────
    # Env var remediation
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
        kind: str = "Deployment",
    ) -> Dict[str, Any]:
        """Remove conflicting OTEL_* env vars from a workload."""
        self._ensure_available()
        norm_kind = self._normalize_workload_kind(kind)

        target_vars = env_vars or self._OTEL_CONFLICT_ENV_VARS

        if norm_kind == "Deployment" and "get_deployment" in self.__dict__:
            workload = await self.get_deployment(namespace, deployment_name)
        else:
            workload = await self.get_workload(namespace, deployment_name, kind=norm_kind)
        found_vars: Dict[str, List[str]] = {}

        for c in workload.get("containers", []):
            if c.get("is_init_container"):
                continue
            env = c.get("env", {})
            matches = [v for v in target_vars if v in env]
            if matches:
                found_vars[c["name"]] = matches

        if not found_vars:
            return {
                "deployment": f"{namespace}/{deployment_name}",
                "workload_kind": norm_kind,
                "dry_run": dry_run,
                "action": "no_change",
                "message": "No conflicting OTEL_* env vars found.",
            }

        if dry_run:
            return {
                "deployment": f"{namespace}/{deployment_name}",
                "workload_kind": norm_kind,
                "dry_run": True,
                "action": "dry_run",
                "would_remove": found_vars,
                "message": (
                    f"Would remove {sum(len(v) for v in found_vars.values())} "
                    "OTEL_* env var(s). Set dry_run=False to apply."
                ),
            }

        containers_patch = []
        for container_name, vars_to_remove in found_vars.items():
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

        if norm_kind == "Deployment":
            await asyncio.to_thread(
                self._apps_v1.patch_namespaced_deployment,
                name=deployment_name,
                namespace=namespace,
                body=patch_body,
            )
        elif norm_kind == "StatefulSet":
            await asyncio.to_thread(
                self._apps_v1.patch_namespaced_stateful_set,
                name=deployment_name,
                namespace=namespace,
                body=patch_body,
            )
        else:
            await asyncio.to_thread(
                self._apps_v1.patch_namespaced_daemon_set,
                name=deployment_name,
                namespace=namespace,
                body=patch_body,
            )

        return {
            "deployment": f"{namespace}/{deployment_name}",
            "workload_kind": norm_kind,
            "dry_run": False,
            "action": "applied",
            "removed": found_vars,
            "message": (
                f"Removed {sum(len(v) for v in found_vars.values())} "
                f"OTEL_* env var(s). {norm_kind} will rolling-restart."
            ),
        }

    # ──────────────────────────────────────────────
    # Service endpoint health
    # ──────────────────────────────────────────────

    async def get_collector_service_health(
        self,
        namespace: str,
        collector_name: str,
    ) -> Dict[str, Any]:
        """Validate the K8s Service and Endpoints backing a collector."""
        self._ensure_available()
        result: Dict[str, Any] = {
            "service_found": False,
            "service_name": None,
            "selector": None,
            "ready_endpoints": 0,
            "not_ready_endpoints": 0,
            "warnings": [],
        }

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
                        f"CRITICAL: Service '{svc_name}' has {not_ready} "
                        "endpoint(s) but NONE are ready. Collector pods may "
                        "be crashing or failing health checks."
                    )
                else:
                    result["warnings"].append(
                        f"CRITICAL: Service '{svc_name}' has NO endpoints. "
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

    _SENSITIVE_ENV_TOKENS = (
        "secret",
        "token",
        "password",
        "passwd",
        "api_key",
        "apikey",
        "authorization",
        "headers",
        "private_key",
    )

    @classmethod
    def _sanitize_env_value(cls, env_name: str, env_val: str) -> str:
        """Redact sensitive env var values while preserving normal configuration."""
        lower = (env_name or "").lower()
        if any(tok in lower for tok in cls._SENSITIVE_ENV_TOKENS):
            return REDACTED_VALUE
        return redact_log_text(env_val)

    @classmethod
    def _workload_to_dict(
        cls,
        workload: Any,
        kind: str = "Deployment",
    ) -> Dict[str, Any]:
        """Convert a V1Deployment, V1StatefulSet, or V1DaemonSet to a simplified dict."""
        metadata = workload.metadata
        spec = workload.spec
        status = workload.status

        pod_annotations = {}
        pod_labels = {}
        if spec and getattr(spec, "template", None) and spec.template.metadata:
            pod_annotations = spec.template.metadata.annotations or {}
            pod_labels = spec.template.metadata.labels or {}

        containers = []
        if spec and getattr(spec, "template", None) and spec.template.spec:
            for c in spec.template.spec.containers or []:
                env_vars = {}
                if c.env:
                    for e in c.env:
                        if e.value:
                            env_vars[e.name] = cls._sanitize_env_value(
                                e.name, e.value
                            )
                        elif e.value_from:
                            env_vars[e.name] = "<from-ref>"
                containers.append({
                    "name": c.name,
                    "image": c.image,
                    "env": env_vars,
                })

            for ic in spec.template.spec.init_containers or []:
                containers.append({
                    "name": ic.name,
                    "image": ic.image,
                    "is_init_container": True,
                })

        if kind == "DaemonSet":
            replicas = (
                getattr(status, "desired_number_scheduled", 0) or 0
                if status
                else 0
            )
            ready_replicas = (
                getattr(status, "number_ready", 0) or 0 if status else 0
            )
        else:
            replicas = getattr(spec, "replicas", 0) or 0 if spec else 0
            ready_replicas = (
                getattr(status, "ready_replicas", 0) or 0 if status else 0
            )

        created_ts = getattr(metadata, "creation_timestamp", None)

        return {
            "name": metadata.name,
            "namespace": metadata.namespace,
            "labels": metadata.labels or {},
            "annotations": metadata.annotations or {},
            "pod_annotations": pod_annotations,
            "pod_labels": pod_labels,
            "replicas": replicas,
            "ready_replicas": ready_replicas,
            "containers": containers,
            "kind": kind,
            "creation_timestamp": (
                created_ts.isoformat()
                if hasattr(created_ts, "isoformat")
                else (str(created_ts) if created_ts else None)
            ),
        }

    @classmethod
    def _deployment_to_dict(cls, deployment: Any) -> Dict[str, Any]:
        """Convert a V1Deployment object to a simplified dict."""
        return cls._workload_to_dict(deployment, kind="Deployment")

    @classmethod
    def _pod_to_dict(cls, pod: Any) -> Dict[str, Any]:
        """Convert a V1Pod object to a simplified dict."""
        metadata = pod.metadata
        spec = pod.spec
        status = pod.status

        pod_security_context: Dict[str, Any] = {}
        if getattr(spec, "security_context", None):
            psc = spec.security_context
            pod_security_context = {
                "run_as_non_root": getattr(psc, "run_as_non_root", None),
                "run_as_user": getattr(psc, "run_as_user", None),
                "fs_group": getattr(psc, "fs_group", None),
            }

        containers = []
        if spec and spec.containers:
            for c in spec.containers:
                security_context = {}
                if c.security_context:
                    sc = c.security_context
                    security_context = {
                        "privileged": bool(getattr(sc, "privileged", False)),
                        "run_as_non_root": getattr(sc, "run_as_non_root", None),
                        "run_as_user": getattr(sc, "run_as_user", None),
                        "read_only_root_filesystem": getattr(
                            sc, "read_only_root_filesystem", None
                        ),
                        "allow_privilege_escalation": getattr(
                            sc, "allow_privilege_escalation", None
                        ),
                        "capabilities": (
                            [cap for cap in (sc.capabilities.add or [])]
                            if getattr(sc, "capabilities", None)
                            else []
                        ),
                    }
                volume_mounts = []
                if c.volume_mounts:
                    for vm in c.volume_mounts:
                        volume_mounts.append({
                            "name": vm.name,
                            "mount_path": vm.mount_path,
                            "read_only": bool(getattr(vm, "read_only", False)),
                        })
                env_vars = {}
                if getattr(c, "env", None):
                    for e in c.env:
                        if getattr(e, "value", None):
                            env_vars[e.name] = cls._sanitize_env_value(
                                e.name, e.value
                            )
                        elif getattr(e, "value_from", None):
                            env_vars[e.name] = "<from-ref>"

                containers.append({
                    "name": c.name,
                    "image": c.image,
                    "security_context": security_context,
                    "volume_mounts": volume_mounts,
                    "env": env_vars,
                })

        init_containers = []
        if spec and getattr(spec, "init_containers", None):
            for ic in spec.init_containers or []:
                init_containers.append({
                    "name": ic.name,
                    "image": ic.image,
                })

        host_volumes = []
        if spec and spec.volumes:
            for v in spec.volumes:
                if v.host_path:
                    host_volumes.append({
                        "name": v.name,
                        "host_path": v.host_path.path,
                    })

        container_statuses = []
        if status and getattr(status, "container_statuses", None):
            for cs in status.container_statuses or []:
                state_obj = getattr(cs, "state", None)
                last_state_obj = getattr(cs, "last_state", None)
                state_name = "unknown"
                reason = None
                exit_code = None
                message = None
                if state_obj:
                    if getattr(state_obj, "running", None):
                        state_name = "running"
                    elif getattr(state_obj, "waiting", None):
                        state_name = "waiting"
                        reason = getattr(state_obj.waiting, "reason", None)
                        message = getattr(state_obj.waiting, "message", None)
                    elif getattr(state_obj, "terminated", None):
                        state_name = "terminated"
                        reason = getattr(state_obj.terminated, "reason", None)
                        exit_code = getattr(
                            state_obj.terminated, "exit_code", None
                        )
                        message = getattr(state_obj.terminated, "message", None)

                last_termination_reason = None
                if last_state_obj and getattr(last_state_obj, "terminated", None):
                    last_termination_reason = getattr(
                        last_state_obj.terminated, "reason", None
                    )
                    if exit_code is None:
                        exit_code = getattr(
                            last_state_obj.terminated, "exit_code", None
                        )

                container_statuses.append({
                    "name": getattr(cs, "name", ""),
                    "ready": bool(getattr(cs, "ready", False)),
                    "restart_count": getattr(cs, "restart_count", 0) or 0,
                    "state": state_name,
                    "reason": reason,
                    "exit_code": exit_code,
                    "last_termination_reason": last_termination_reason,
                    "message": redact_log_text(message) if message else None,
                })

        created_ts = getattr(metadata, "creation_timestamp", None)

        return {
            "name": metadata.name,
            "namespace": metadata.namespace,
            "node_name": getattr(spec, "node_name", None),
            "service_account": getattr(spec, "service_account_name", None),
            "labels": metadata.labels or {},
            "annotations": metadata.annotations or {},
            "host_pid": bool(getattr(spec, "host_pid", False)),
            "pod_security_context": pod_security_context,
            "containers": containers,
            "init_containers": init_containers,
            "container_statuses": container_statuses,
            "host_volumes": host_volumes,
            "phase": status.phase if status else "Unknown",
            "creation_timestamp": (
                created_ts.isoformat()
                if hasattr(created_ts, "isoformat")
                else (str(created_ts) if created_ts else None)
            ),
        }
