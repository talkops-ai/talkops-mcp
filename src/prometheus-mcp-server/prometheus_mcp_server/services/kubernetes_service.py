"""Kubernetes operations service for Prometheus MCP server."""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

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
            kubeconfig = getattr(self._config, "kubeconfig", None) or os.getenv("K8S_KUBECONFIG")
            if self._config.in_cluster:
                k8s_config.load_incluster_config()
            elif self._config.context_name and kubeconfig:
                k8s_config.load_kube_config(config_file=kubeconfig, context=self._config.context_name)
            elif self._config.context_name:
                k8s_config.load_kube_config(context=self._config.context_name)
            elif kubeconfig:
                k8s_config.load_kube_config(config_file=kubeconfig)
            else:
                k8s_config.load_kube_config()
            self._core = k8s_client.CoreV1Api()
            self._apps = k8s_client.AppsV1Api()
            self._custom = k8s_client.CustomObjectsApi()
            self._rbac = k8s_client.RbacAuthorizationV1Api()
            self._initialized = True
        except Exception as e:
            raise RuntimeError(f"Kubernetes client initialization failed: {e}")

    # ── Service introspection (generic auto-discovery) ────────────────

    # Well-known port names that indicate a Prometheus metrics port.
    _METRICS_PORT_NAMES: List[str] = [
        "metrics", "prometheus", "http-metrics", "prom-metrics",
        "monitoring", "metric", "prometheus-metrics",
    ]

    def _pick_metrics_port(self, ports: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Select the most likely metrics port from a Service's port list.

        Preference order:
        1. Port whose name matches a well-known metrics port name.
        2. Port whose number is a common metrics port (9090, 9100, 8080, 8082, 2112).
        3. None — caller should fall back to user-provided default.
        """
        # 1) Name match
        for p in ports:
            if p.get("name", "").lower() in self._METRICS_PORT_NAMES:
                return p
        # 2) Common metrics port numbers
        common_ports = {9090, 9100, 8080, 8082, 2112, 9091, 9093, 9115}
        for p in ports:
            if p.get("port") in common_ports:
                return p
        return None

    def _sync_discover_service(self, namespace: str, service_name: str) -> Optional[Dict[str, Any]]:
        """Read a K8s Service and extract its labels, selector, and ports.

        Returns None if the service is not found.
        """
        try:
            svc = self._core.read_namespaced_service(service_name, namespace)
        except ApiException as e:
            if e.status == 404:
                return None
            raise

        # Extract metadata labels (ServiceMonitor selector matches on these)
        meta_labels: Dict[str, str] = dict(svc.metadata.labels or {})

        # Extract pod selector labels
        pod_selector: Dict[str, str] = dict(svc.spec.selector or {})

        # Extract ports
        ports: List[Dict[str, Any]] = []
        for p in (svc.spec.ports or []):
            ports.append({
                "name": p.name or "",
                "port": p.port,
                "target_port": str(p.target_port) if p.target_port else "",
                "protocol": p.protocol or "TCP",
            })

        # Auto-pick the best metrics port
        metrics_port = self._pick_metrics_port(ports)

        return {
            "name": svc.metadata.name,
            "namespace": svc.metadata.namespace,
            "labels": meta_labels,
            "selector": pod_selector,
            "ports": ports,
            "metrics_port": metrics_port,
        }

    async def discover_service_details(
        self, namespace: str, service_name: str
    ) -> Optional[Dict[str, Any]]:
        """Read a K8s Service by name and return its labels, selector, and port info.

        This enables generic auto-discovery for ServiceMonitor generation.
        Works for any service regardless of labeling convention (Helm, Kustomize,
        hand-crafted, etc.).

        Returns:
            Dict with keys: name, namespace, labels, selector, ports, metrics_port
            — or None if the service does not exist.
        """
        self._ensure_initialized()
        return await asyncio.to_thread(
            self._sync_discover_service, namespace, service_name
        )

    def _sync_probe_incluster_http(
        self, endpoint_url: str, default_namespace: str = "default"
    ) -> Optional[Dict[str, Any]]:
        """Probe an in-cluster Kubernetes Service URL (`*.svc` / `*.svc.cluster.local`) via K8s API Service Proxy."""
        from urllib.parse import urlparse

        parsed = urlparse(endpoint_url)
        host = (parsed.hostname or "").strip().lower()
        if not host:
            return None
        parts = host.split(".")
        if len(parts) >= 3 and parts[2] == "svc":
            svc_name, ns = parts[0], parts[1]
        elif len(parts) == 2:
            svc_name, ns = parts[0], parts[1]
        elif len(parts) == 1 and host not in ("localhost", "127.0.0.1"):
            svc_name, ns = parts[0], default_namespace
        else:
            return None

        scheme = (parsed.scheme or "http").lower()
        port_str = str(parsed.port) if parsed.port else ("443" if scheme == "https" else "80")
        rel_path = (parsed.path or "/metrics").lstrip("/")
        if parsed.query:
            rel_path = f"{rel_path}?{parsed.query}"

        candidate_svcs = [svc_name]
        if not svc_name.endswith("-envoy"):
            candidate_svcs.append(f"{svc_name}-envoy")

        last_err = ""
        for cand_svc in candidate_svcs:
            proxy_name = f"{scheme}:{cand_svc}:{port_str}"
            raw_path = f"/api/v1/namespaces/{ns}/services/{proxy_name}/proxy/{rel_path}"
            try:
                data, status_code, headers = self._core.api_client.call_api(
                    raw_path,
                    "GET",
                    auth_settings=["BearerToken"],
                    response_type="str",
                    _preload_content=False,
                    _request_timeout=10,
                )
                body_bytes = data.read() if hasattr(data, "read") else bytes(str(data), "utf-8")
                text = body_bytes.decode("utf-8", errors="replace")
                ctype = ""
                if isinstance(headers, dict):
                    for hk, hv in headers.items():
                        if str(hk).lower() == "content-type":
                            ctype = str(hv)
                            break

                errors: List[str] = []
                metrics: List[str] = []
                fmt = "unknown"
                if "application/openmetrics-text" in ctype:
                    fmt = "openmetrics"
                elif "text/plain" in ctype:
                    fmt = "prometheus"
                elif text.lstrip().startswith("#") or "\n# TYPE " in text:
                    fmt = "prometheus"
                else:
                    errors.append(f"Unexpected Content-Type: {ctype}")

                for line in text.splitlines():
                    if not line or line.startswith("#"):
                        continue
                    m_name = line.split("{", 1)[0].split(" ", 1)[0]
                    if m_name and m_name not in metrics:
                        metrics.append(m_name)

                return {
                    "ok": int(status_code) == 200 and bool(metrics),
                    "status_code": int(status_code),
                    "metrics_found": metrics[:50],
                    "format": fmt,
                    "via": "kubernetes_service_proxy",
                    "errors": errors,
                }
            except Exception as exc:
                last_err = str(exc)

        return {
            "ok": False,
            "status_code": 0,
            "metrics_found": [],
            "format": "unknown",
            "via": "kubernetes_service_proxy",
            "errors": [last_err] if last_err else ["Service proxy probe failed"],
        }

    async def probe_incluster_http(
        self, endpoint_url: str, default_namespace: str = "default"
    ) -> Optional[Dict[str, Any]]:
        """Probe an in-cluster Kubernetes Service HTTP metrics URL via the K8s API server proxy."""
        self._ensure_initialized()
        return await asyncio.to_thread(
            self._sync_probe_incluster_http, endpoint_url, default_namespace
        )

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
        """List all PrometheusRule CRDs across the cluster."""
        self._ensure_initialized()
        return await asyncio.to_thread(self._sync_list_prometheus_rules)

    # ── Scrape CRD & Manifest Introspection + Multi-Group Rule Merge ──

    _CRD_KIND_MAP: Dict[str, tuple[str, str, str]] = {
        "servicemonitor": ("monitoring.coreos.com", "v1", "servicemonitors"),
        "podmonitor": ("monitoring.coreos.com", "v1", "podmonitors"),
        "probe": ("monitoring.coreos.com", "v1", "probes"),
        "scrapeconfig": ("monitoring.coreos.com", "v1alpha1", "scrapeconfigs"),
        "prometheusrule": ("monitoring.coreos.com", "v1", "prometheusrules"),
    }

    def _resolve_crd_coords(self, kind: str) -> tuple[str, str, str]:
        norm = kind.strip().lower()
        if norm not in self._CRD_KIND_MAP:
            raise ValueError(
                f"Unsupported CRD kind '{kind}'. Supported kinds: "
                "ServiceMonitor, PodMonitor, Probe, ScrapeConfig, PrometheusRule."
            )
        return self._CRD_KIND_MAP[norm]

    def _sync_get_crd_manifest(
        self, kind: str, namespace: str, name: str
    ) -> Optional[Dict[str, Any]]:
        group, version, plural = self._resolve_crd_coords(kind)
        try:
            obj = self._custom.get_namespaced_custom_object(
                group, version, namespace, plural, name
            )
            from prometheus_mcp_server.utils.redaction import redact_sensitive_data

            redacted = redact_sensitive_data(obj)
            if isinstance(redacted, dict) and isinstance(redacted.get("metadata"), dict):
                redacted["metadata"].pop("managedFields", None)
            return redacted
        except ApiException as e:
            if e.status == 404:
                return None
            raise

    async def get_crd_manifest(
        self, kind: str, namespace: str, name: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch a single namespaced CRD manifest with sensitive fields redacted."""
        self._ensure_initialized()
        return await asyncio.to_thread(
            self._sync_get_crd_manifest, kind, namespace, name
        )

    def _sync_list_scrape_crds(
        self, namespace: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        kinds = ["ServiceMonitor", "PodMonitor", "Probe", "ScrapeConfig"]
        out: Dict[str, List[Dict[str, Any]]] = {}
        for kind in kinds:
            group, version, plural = self._resolve_crd_coords(kind)
            items: List[Dict[str, Any]] = []
            try:
                if namespace:
                    res = self._custom.list_namespaced_custom_object(
                        group, version, namespace, plural
                    )
                else:
                    res = self._custom.list_cluster_custom_object(
                        group, version, plural
                    )
                for item in res.get("items", []):
                    meta = item.get("metadata", {})
                    items.append(
                        {
                            "kind": kind,
                            "name": meta.get("name", ""),
                            "namespace": meta.get("namespace", ""),
                            "labels": meta.get("labels", {}),
                        }
                    )
            except Exception:
                pass
            out[kind] = items
        return out

    async def list_scrape_crds(
        self, namespace: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """List deployed ServiceMonitor, PodMonitor, Probe, and ScrapeConfig CRDs."""
        self._ensure_initialized()
        return await asyncio.to_thread(self._sync_list_scrape_crds, namespace)

    def _sync_list_operator_context(
        self, target_namespaces: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Collect Prometheus Operator selector labels plus compact Service/Pod port & label inventory."""
        skip_ns = {"kube-system", "kube-public", "kube-node-lease"}
        allowed_ns = set(target_namespaces or []) | {"observability", "monitoring"}
        selectors = {
            "serviceMonitorSelector": self._sync_get_servicemonitor_selector_labels(),
            "ruleSelector": self._sync_get_rule_selector_labels(),
            "probeSelector": self._sync_get_probe_selector_labels(),
        }
        prom_instances: List[Dict[str, Any]] = []
        try:
            res = self._custom.list_cluster_custom_object(
                "monitoring.coreos.com", "v1", "prometheuses"
            )
            for item in res.get("items", []):
                meta = item.get("metadata", {})
                spec = item.get("spec", {})
                prom_instances.append(
                    {
                        "name": meta.get("name", ""),
                        "namespace": meta.get("namespace", ""),
                        "serviceMonitorSelector": spec.get("serviceMonitorSelector", {}),
                        "ruleSelector": spec.get("ruleSelector", {}),
                        "probeSelector": spec.get("probeSelector", {}),
                    }
                )
        except Exception:
            pass

        services_out: List[Dict[str, Any]] = []
        try:
            svcs = self._core.list_service_for_all_namespaces()
            for svc in getattr(svcs, "items", []) or []:
                ns = getattr(svc.metadata, "namespace", "") or ""
                if ns in skip_ns or (target_namespaces is not None and ns not in allowed_ns):
                    continue
                ports = [
                    {
                        "name": getattr(p, "name", None),
                        "port": getattr(p, "port", None),
                        "targetPort": str(getattr(p, "target_port", "")),
                    }
                    for p in (getattr(svc.spec, "ports", None) or [])
                ]
                services_out.append(
                    {
                        "name": getattr(svc.metadata, "name", ""),
                        "namespace": ns,
                        "labels": dict(getattr(svc.metadata, "labels", None) or {}),
                        "selector": dict(getattr(svc.spec, "selector", None) or {}),
                        "ports": ports,
                    }
                )
        except Exception:
            pass

        workloads_out: List[Dict[str, Any]] = []
        for kind_label, list_fn in (
            ("Deployment", self._apps.list_deployment_for_all_namespaces),
            ("DaemonSet", self._apps.list_daemon_set_for_all_namespaces),
        ):
            try:
                wl_list = list_fn()
                for wl in getattr(wl_list, "items", []) or []:
                    ns = getattr(wl.metadata, "namespace", "") or ""
                    if ns in skip_ns or (target_namespaces is not None and ns not in allowed_ns):
                        continue
                    tmpl = getattr(wl.spec, "template", None)
                    pod_labels = dict(getattr(getattr(tmpl, "metadata", None), "labels", None) or {})
                    c_ports: List[Dict[str, Any]] = []
                    for c in getattr(getattr(tmpl, "spec", None), "containers", None) or []:
                        for cp in getattr(c, "ports", None) or []:
                            c_ports.append(
                                {
                                    "container": getattr(c, "name", ""),
                                    "name": getattr(cp, "name", None),
                                    "containerPort": getattr(cp, "container_port", None),
                                }
                            )
                    if c_ports:
                        workloads_out.append(
                            {
                                "kind": kind_label,
                                "name": getattr(wl.metadata, "name", ""),
                                "namespace": ns,
                                "pod_labels": pod_labels,
                                "container_ports": c_ports,
                            }
                        )
            except Exception:
                pass

        return {
            "operator_selectors": selectors,
            "prometheus_instances": prom_instances,
            "discovered_services": services_out,
            "discovered_workloads": workloads_out,
        }

    async def list_operator_context(
        self, target_namespaces: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Collect Prometheus Operator selector labels and cluster Service/Workload port & label metadata."""
        self._ensure_initialized()
        return await asyncio.to_thread(self._sync_list_operator_context, target_namespaces)

    def _sync_find_owning_rule_crd(
        self, namespace: str, group_name: str
    ) -> Optional[Dict[str, Any]]:
        """Find an existing PrometheusRule CRD in `namespace` that contains `group_name`."""
        group, version, plural = self._resolve_crd_coords("PrometheusRule")
        try:
            res = self._custom.list_namespaced_custom_object(
                group, version, namespace, plural
            )
            for item in res.get("items", []):
                groups = item.get("spec", {}).get("groups", [])
                for g in groups:
                    if g.get("name") == group_name:
                        return item
        except Exception:
            pass
        return None

    def _sync_upsert_rule_group_crd(
        self,
        namespace: str,
        rule_group: Dict[str, Any],
        crd_name: Optional[str] = None,
        extra_labels: Optional[Dict[str, str]] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Create or update a rule group inside a PrometheusRule CRD without clobbering sibling groups."""
        import re as _re

        group_api, version, plural = self._resolve_crd_coords("PrometheusRule")
        group_name = rule_group.get("name", "default-group")

        existing_crd: Optional[Dict[str, Any]] = None
        if crd_name:
            try:
                existing_crd = self._custom.get_namespaced_custom_object(
                    group_api, version, namespace, plural, crd_name
                )
            except ApiException as e:
                if e.status != 404:
                    raise
        else:
            existing_crd = self._sync_find_owning_rule_crd(namespace, group_name)
            if existing_crd:
                crd_name = existing_crd.get("metadata", {}).get("name")

        if not crd_name:
            sanitized = _re.sub(r"[^a-z0-9-]", "-", group_name.lower()).strip("-")
            crd_name = (
                sanitized if sanitized.endswith("-rules") else f"{sanitized}-rules"
            )
            try:
                existing_crd = self._custom.get_namespaced_custom_object(
                    group_api, version, namespace, plural, crd_name
                )
            except ApiException as e:
                if e.status != 404:
                    raise

        required_labels = self._sync_get_rule_selector_labels()
        merged_labels: Dict[str, str] = {
            "app.kubernetes.io/managed-by": "prometheus-mcp-server"
        }
        merged_labels.update(required_labels)
        if existing_crd:
            merged_labels.update(existing_crd.get("metadata", {}).get("labels") or {})
        if extra_labels:
            merged_labels.update(extra_labels)

        existing_groups: List[Dict[str, Any]] = []
        if existing_crd:
            existing_groups = list(existing_crd.get("spec", {}).get("groups", []))

        replaced = False
        new_groups: List[Dict[str, Any]] = []
        for g in existing_groups:
            if g.get("name") == group_name:
                new_groups.append(rule_group)
                replaced = True
            else:
                new_groups.append(g)
        if not replaced:
            new_groups.append(rule_group)

        manifest: Dict[str, Any] = {
            "apiVersion": f"{group_api}/{version}",
            "kind": "PrometheusRule",
            "metadata": {
                "name": crd_name,
                "namespace": namespace,
                "labels": merged_labels,
            },
            "spec": {"groups": new_groups},
        }

        action = "updated" if existing_crd else "created"
        if not dry_run:
            if existing_crd:
                self._custom.patch_namespaced_custom_object(
                    group_api, version, namespace, plural, crd_name, manifest
                )
            else:
                self._custom.create_namespaced_custom_object(
                    group_api, version, namespace, plural, manifest
                )

        return {
            "action": action,
            "crd_name": crd_name,
            "namespace": namespace,
            "group_name": group_name,
            "sibling_group_count": len(new_groups) - 1,
            "manifest": manifest,
        }

    async def upsert_rule_group_crd(
        self,
        namespace: str,
        rule_group: Dict[str, Any],
        crd_name: Optional[str] = None,
        extra_labels: Optional[Dict[str, str]] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Non-destructively upsert a rule group in a Kubernetes PrometheusRule CRD."""
        self._ensure_initialized()
        return await asyncio.to_thread(
            self._sync_upsert_rule_group_crd,
            namespace,
            rule_group,
            crd_name,
            extra_labels,
            dry_run,
        )

    def _sync_delete_rule_group_crd(
        self,
        namespace: str,
        group_name: str,
        crd_name: Optional[str] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Remove a rule group from a PrometheusRule CRD, or delete the CRD if it is the last group."""
        import re as _re

        group_api, version, plural = self._resolve_crd_coords("PrometheusRule")
        existing_crd: Optional[Dict[str, Any]] = None

        if crd_name:
            try:
                existing_crd = self._custom.get_namespaced_custom_object(
                    group_api, version, namespace, plural, crd_name
                )
            except ApiException as e:
                if e.status != 404:
                    raise
        else:
            existing_crd = self._sync_find_owning_rule_crd(namespace, group_name)
            if existing_crd:
                crd_name = existing_crd.get("metadata", {}).get("name")
            else:
                sanitized = _re.sub(r"[^a-z0-9-]", "-", group_name.lower()).strip("-")
                crd_name = (
                    sanitized if sanitized.endswith("-rules") else f"{sanitized}-rules"
                )
                try:
                    existing_crd = self._custom.get_namespaced_custom_object(
                        group_api, version, namespace, plural, crd_name
                    )
                except ApiException as e:
                    if e.status != 404:
                        raise

        if not existing_crd:
            return {
                "found": False,
                "action": "not_found",
                "crd_name": crd_name,
                "namespace": namespace,
                "group_name": group_name,
            }

        existing_groups = list(existing_crd.get("spec", {}).get("groups", []))
        remaining_groups = [
            g for g in existing_groups if g.get("name") != group_name
        ]

        if len(remaining_groups) == 0:
            action = "deleted_crd"
            if not dry_run:
                self._custom.delete_namespaced_custom_object(
                    group_api, version, namespace, plural, crd_name
                )
        else:
            action = "removed_group_from_crd"
            if not dry_run:
                patch_body = {"spec": {"groups": remaining_groups}}
                self._custom.patch_namespaced_custom_object(
                    group_api, version, namespace, plural, crd_name, patch_body
                )

        return {
            "found": True,
            "action": action,
            "crd_name": crd_name,
            "namespace": namespace,
            "group_name": group_name,
            "remaining_group_count": len(remaining_groups),
        }

    async def delete_rule_group_crd(
        self,
        namespace: str,
        group_name: str,
        crd_name: Optional[str] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Delete a rule group from a PrometheusRule CRD without destroying sibling groups."""
        self._ensure_initialized()
        return await asyncio.to_thread(
            self._sync_delete_rule_group_crd,
            namespace,
            group_name,
            crd_name,
            dry_run,
        )
