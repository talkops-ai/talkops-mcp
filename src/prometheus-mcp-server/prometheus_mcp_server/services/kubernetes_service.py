"""Kubernetes operations service for Prometheus MCP server."""

import asyncio
from typing import Any, Dict

from kubernetes import client as k8s_client, config as k8s_config
from kubernetes.client.exceptions import ApiException

from prometheus_mcp_server.config import KubernetesConfig


class KubernetesService:
    """Wrapper over the official Kubernetes Python client.

    All K8s API calls are wrapped with asyncio.to_thread() to avoid
    blocking the event loop, since the kubernetes client is synchronous.
    """

    def __init__(self, config: KubernetesConfig) -> None:
        self._config = config
        self._core: Any = None
        self._apps: Any = None
        self._custom: Any = None
        self._rbac: Any = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazily initialize the Kubernetes client."""
        if self._initialized:
            return
        try:
            if self._config.in_cluster:
                k8s_config.load_incluster_config()
            elif self._config.context_name:
                k8s_config.load_kube_config(context=self._config.context_name)
            else:
                k8s_config.load_kube_config()
            self._core = k8s_client.CoreV1Api()
            self._apps = k8s_client.AppsV1Api()
            self._custom = k8s_client.CustomObjectsApi()
            self._rbac = k8s_client.RbacAuthorizationV1Api()
            self._initialized = True
        except Exception as e:
            raise RuntimeError(f"Kubernetes client initialization failed: {e}")

    def _sync_apply_deployment(self, namespace: str, manifest: Dict[str, Any]) -> None:
        """Synchronous deployment apply (runs in thread)."""
        name = manifest["metadata"]["name"]
        try:
            self._apps.read_namespaced_deployment(name, namespace)
            self._apps.patch_namespaced_deployment(name, namespace, manifest)
        except ApiException as e:
            if e.status == 404:
                self._apps.create_namespaced_deployment(namespace, manifest)
            else:
                raise

    async def apply_deployment(self, namespace: str, manifest: Dict[str, Any]) -> None:
        self._ensure_initialized()
        await asyncio.to_thread(self._sync_apply_deployment, namespace, manifest)

    def _sync_apply_daemonset(self, namespace: str, manifest: Dict[str, Any]) -> None:
        """Synchronous daemonset apply (runs in thread)."""
        name = manifest["metadata"]["name"]
        try:
            self._apps.read_namespaced_daemon_set(name, namespace)
            self._apps.patch_namespaced_daemon_set(name, namespace, manifest)
        except ApiException as e:
            if e.status == 404:
                self._apps.create_namespaced_daemon_set(namespace, manifest)
            else:
                raise

    async def apply_daemonset(self, namespace: str, manifest: Dict[str, Any]) -> None:
        self._ensure_initialized()
        await asyncio.to_thread(self._sync_apply_daemonset, namespace, manifest)

    def _sync_apply_service(self, namespace: str, manifest: Dict[str, Any]) -> None:
        """Synchronous service apply (runs in thread)."""
        name = manifest["metadata"]["name"]
        try:
            self._core.read_namespaced_service(name, namespace)
            self._core.patch_namespaced_service(name, namespace, manifest)
        except ApiException as e:
            if e.status == 404:
                self._core.create_namespaced_service(namespace, manifest)
            else:
                raise

    async def apply_service(self, namespace: str, manifest: Dict[str, Any]) -> None:
        self._ensure_initialized()
        await asyncio.to_thread(self._sync_apply_service, namespace, manifest)

    def _sync_apply_serviceaccount(self, namespace: str, manifest: Dict[str, Any]) -> None:
        name = manifest["metadata"]["name"]
        try:
            self._core.read_namespaced_service_account(name, namespace)
            self._core.patch_namespaced_service_account(name, namespace, manifest)
        except ApiException as e:
            if e.status == 404:
                self._core.create_namespaced_service_account(namespace, manifest)
            else:
                raise

    async def apply_serviceaccount(self, namespace: str, manifest: Dict[str, Any]) -> None:
        self._ensure_initialized()
        await asyncio.to_thread(self._sync_apply_serviceaccount, namespace, manifest)

    def _sync_apply_clusterrole(self, manifest: Dict[str, Any]) -> None:
        name = manifest["metadata"]["name"]
        try:
            self._rbac.read_cluster_role(name)
            self._rbac.patch_cluster_role(name, manifest)
        except ApiException as e:
            if e.status == 404:
                self._rbac.create_cluster_role(manifest)
            else:
                raise

    async def apply_clusterrole(self, manifest: Dict[str, Any]) -> None:
        self._ensure_initialized()
        await asyncio.to_thread(self._sync_apply_clusterrole, manifest)

    def _sync_apply_clusterrolebinding(self, manifest: Dict[str, Any]) -> None:
        name = manifest["metadata"]["name"]
        try:
            self._rbac.read_cluster_role_binding(name)
            self._rbac.patch_cluster_role_binding(name, manifest)
        except ApiException as e:
            if e.status == 404:
                self._rbac.create_cluster_role_binding(manifest)
            else:
                raise

    async def apply_clusterrolebinding(self, manifest: Dict[str, Any]) -> None:
        self._ensure_initialized()
        await asyncio.to_thread(self._sync_apply_clusterrolebinding, manifest)

    def _sync_apply_configmap(self, namespace: str, manifest: Dict[str, Any]) -> None:
        name = manifest["metadata"]["name"]
        try:
            self._core.read_namespaced_config_map(name, namespace)
            self._core.patch_namespaced_config_map(name, namespace, manifest)
        except ApiException as e:
            if e.status == 404:
                self._core.create_namespaced_config_map(namespace, manifest)
            else:
                raise

    async def apply_configmap(self, namespace: str, manifest: Dict[str, Any]) -> None:
        self._ensure_initialized()
        await asyncio.to_thread(self._sync_apply_configmap, namespace, manifest)

    def _sync_delete_deployment(self, namespace: str, name: str) -> None:
        """Synchronous deployment delete (runs in thread)."""
        try:
            self._apps.delete_namespaced_deployment(name, namespace)
        except ApiException as e:
            if e.status != 404:
                raise

    async def delete_deployment(self, namespace: str, name: str) -> None:
        self._ensure_initialized()
        await asyncio.to_thread(self._sync_delete_deployment, namespace, name)

    def _sync_delete_daemonset(self, namespace: str, name: str) -> None:
        """Synchronous daemonset delete (runs in thread)."""
        try:
            self._apps.delete_namespaced_daemon_set(name, namespace)
        except ApiException as e:
            if e.status != 404:
                raise

    async def delete_daemonset(self, namespace: str, name: str) -> None:
        self._ensure_initialized()
        await asyncio.to_thread(self._sync_delete_daemonset, namespace, name)

    def _sync_delete_service(self, namespace: str, name: str) -> None:
        """Synchronous service delete (runs in thread)."""
        try:
            self._core.delete_namespaced_service(name, namespace)
        except ApiException as e:
            if e.status != 404:
                raise

    async def delete_service(self, namespace: str, name: str) -> None:
        self._ensure_initialized()
        await asyncio.to_thread(self._sync_delete_service, namespace, name)

    def _sync_apply_custom_resource(self, namespace: str, manifest: Dict[str, Any]) -> None:
        """Synchronous generic custom resource apply (runs in thread)."""
        # Determine group and version from apiVersion
        api_version = manifest.get("apiVersion", "")
        if "/" in api_version:
            group, version = api_version.split("/", 1)
        else:
            group = ""
            version = api_version

        # Determine plural from kind (rudimentary pluralization)
        kind = manifest.get("kind", "")
        if kind.endswith("s"):
            plural = kind.lower() + "es"
        elif kind.endswith("y"):
            plural = kind[:-1].lower() + "ies"
        else:
            plural = kind.lower() + "s"

        name = manifest["metadata"]["name"]
        try:
            self._custom.get_namespaced_custom_object(group, version, namespace, plural, name)
            self._custom.patch_namespaced_custom_object(group, version, namespace, plural, name, manifest)
        except ApiException as e:
            if e.status == 404:
                self._custom.create_namespaced_custom_object(group, version, namespace, plural, manifest)
            else:
                raise

    async def apply_custom_resource(self, namespace: str, manifest: Dict[str, Any]) -> None:
        self._ensure_initialized()
        await asyncio.to_thread(self._sync_apply_custom_resource, namespace, manifest)

    def _sync_delete_custom_resource(self, namespace: str, group: str, version: str, plural: str, name: str) -> None:
        """Synchronous generic custom resource delete (runs in thread)."""
        try:
            self._custom.delete_namespaced_custom_object(group, version, namespace, plural, name)
        except ApiException as e:
            if e.status != 404:
                raise

    async def delete_custom_resource(self, namespace: str, group: str, version: str, plural: str, name: str) -> None:
        self._ensure_initialized()
        await asyncio.to_thread(self._sync_delete_custom_resource, namespace, group, version, plural, name)

    def _sync_apply_servicemonitor(self, namespace: str, manifest: Dict[str, Any]) -> None:
        """Synchronous ServiceMonitor apply (runs in thread)."""
        group = "monitoring.coreos.com"
        version = "v1"
        plural = "servicemonitors"
        name = manifest["metadata"]["name"]
        try:
            self._custom.get_namespaced_custom_object(group, version, namespace, plural, name)
            self._custom.patch_namespaced_custom_object(group, version, namespace, plural, name, manifest)
        except ApiException as e:
            if e.status == 404:
                self._custom.create_namespaced_custom_object(group, version, namespace, plural, manifest)
            else:
                raise

    async def apply_servicemonitor(self, namespace: str, manifest: Dict[str, Any]) -> None:
        self._ensure_initialized()
        await asyncio.to_thread(self._sync_apply_servicemonitor, namespace, manifest)

    def _sync_get_servicemonitor_selector_labels(self) -> Dict[str, str]:
        """Query all Prometheus CRDs to discover the serviceMonitorSelector matchLabels.

        Returns the matchLabels dict from the first Prometheus instance found,
        or an empty dict if no Prometheus CRD exists or the selector is empty
        (meaning all ServiceMonitors are accepted).
        """
        group = "monitoring.coreos.com"
        version = "v1"
        plural = "prometheuses"
        try:
            result = self._custom.list_cluster_custom_object(group, version, plural)
            for item in result.get("items", []):
                selector = item.get("spec", {}).get("serviceMonitorSelector", {})
                match_labels = selector.get("matchLabels", {})
                if match_labels:
                    return dict(match_labels)
            return {}
        except ApiException:
            return {}
        except Exception:
            return {}

    async def get_servicemonitor_required_labels(self) -> Dict[str, str]:
        """Discover the labels required for ServiceMonitors to be picked up by Prometheus Operator.

        Reads the Prometheus CRD's spec.serviceMonitorSelector.matchLabels
        to determine what labels must be present on ServiceMonitor metadata.

        Returns:
            Dict of required labels (e.g. {"release": "kube-prometheus-stack"}),
            or empty dict if no selector is configured (all SMs are accepted).
        """
        self._ensure_initialized()
        return await asyncio.to_thread(self._sync_get_servicemonitor_selector_labels)

    def _sync_get_rule_selector_labels(self) -> Dict[str, str]:
        """Query all Prometheus CRDs to discover the ruleSelector matchLabels.

        Returns the matchLabels dict from the first Prometheus instance found,
        or an empty dict if no Prometheus CRD exists or the selector is empty
        (meaning all PrometheusRules are accepted).
        """
        group = "monitoring.coreos.com"
        version = "v1"
        plural = "prometheuses"
        try:
            result = self._custom.list_cluster_custom_object(group, version, plural)
            for item in result.get("items", []):
                selector = item.get("spec", {}).get("ruleSelector", {})
                match_labels = selector.get("matchLabels", {})
                if match_labels:
                    return dict(match_labels)
            return {}
        except Exception:
            return {}

    async def get_rule_required_labels(self) -> Dict[str, str]:
        """Discover the labels required for PrometheusRules to be picked up by Prometheus Operator.

        Reads the Prometheus CRD's spec.ruleSelector.matchLabels
        to determine what labels must be present on PrometheusRule metadata.

        Returns:
            Dict of required labels, or empty dict if no selector is configured.
        """
        self._ensure_initialized()
        return await asyncio.to_thread(self._sync_get_rule_selector_labels)

    def _sync_get_probe_selector_labels(self) -> Dict[str, str]:
        """Query all Prometheus CRDs to discover the probeSelector matchLabels.

        Returns the matchLabels dict from the first Prometheus instance found,
        or an empty dict if no Prometheus CRD exists or the selector is empty
        (meaning all Probes are accepted).
        """
        group = "monitoring.coreos.com"
        version = "v1"
        plural = "prometheuses"
        try:
            result = self._custom.list_cluster_custom_object(group, version, plural)
            for item in result.get("items", []):
                selector = item.get("spec", {}).get("probeSelector", {})
                match_labels = selector.get("matchLabels", {})
                if match_labels:
                    return dict(match_labels)
            return {}
        except Exception:
            return {}

    async def get_probe_required_labels(self) -> Dict[str, str]:
        """Discover the labels required for Probes to be picked up by Prometheus Operator.

        Reads the Prometheus CRD's spec.probeSelector.matchLabels
        to determine what labels must be present on Probe metadata.

        Returns:
            Dict of required labels, or empty dict if no selector is configured.
        """
        self._ensure_initialized()
        return await asyncio.to_thread(self._sync_get_probe_selector_labels)

    def _sync_list_prometheus_rules(self) -> dict:
        """List all PrometheusRule CRDs across the cluster (runs in thread)."""
        group = "monitoring.coreos.com"
        version = "v1"
        plural = "prometheusrules"
        return self._custom.list_cluster_custom_object(group, version, plural)

    async def list_prometheus_rules(self) -> dict:
        """List all PrometheusRule CRDs across the cluster.

        Queries the Kubernetes API for all PrometheusRule custom resources,
        returning the raw cluster-wide listing including metadata and specs.

        Returns:
            Raw Kubernetes API response with all PrometheusRule items.

        Raises:
            RuntimeError: If Kubernetes client is not initialized.
            ApiException: If the Kubernetes API call fails.
        """
        self._ensure_initialized()
        return await asyncio.to_thread(self._sync_list_prometheus_rules)
