"""Kubernetes discovery and CRD management service for Tempo backends.

Discovers Tempo services via:
1. Service labels (app.kubernetes.io/name=tempo)
2. Tempo Operator CRDs (TempoStack, TempoMonolithic)

Manages Tempo Operator CRDs:
3. List/Get TempoStack and TempoMonolithic resources
4. Create/Patch TempoStack and TempoMonolithic resources

Follows the OTel MCP server's CRD management pattern: all K8s client calls
are wrapped in asyncio.to_thread() because the kubernetes client is synchronous.
"""

import asyncio
from typing import Any, Dict, List, Literal, Optional

from tempo_mcp_server.config import BackendConfig, KubernetesConfig, TempoOperatorConfig

# CRD kind → plural mapping
_KIND_PLURAL_MAP = {
    "TempoStack": "tempostacks",
    "TempoMonolithic": "tempomonolithics",
}

# CRD kind → default deployment mode
_KIND_MODE_MAP: Dict[str, Literal["monolithic", "microservices", "unknown"]] = {
    "TempoStack": "microservices",
    "TempoMonolithic": "monolithic",
}


class KubernetesService:
    """Kubernetes discovery and CRD management for Tempo backends."""

    def __init__(
        self,
        config: KubernetesConfig,
        operator_config: Optional[TempoOperatorConfig] = None,
    ) -> None:
        self._config = config
        self._operator_config = operator_config or TempoOperatorConfig()
        self._api_client = None
        self._custom_api = None
        self._k8s_loaded = False

    def _ensure_k8s(self) -> bool:
        """Load kubeconfig once, initialize API clients."""
        if not self._config.enabled:
            return False

        if self._k8s_loaded:
            return True

        try:
            from kubernetes import client, config as k8s_config

            if self._config.in_cluster:
                k8s_config.load_incluster_config()
            else:
                k8s_config.load_kube_config(
                    context=self._config.context_name
                )
            self._api_client = client.CoreV1Api()
            self._custom_api = client.CustomObjectsApi()
            self._k8s_loaded = True
            return True
        except Exception as e:
            # K8s client init failure — return False (non-fatal)
            return False

    def _get_client(self) -> Any:
        """Lazy-load Kubernetes CoreV1Api client."""
        if self._ensure_k8s():
            return self._api_client
        return None

    def _get_custom_api(self) -> Any:
        """Lazy-load Kubernetes CustomObjectsApi client."""
        if self._ensure_k8s():
            return self._custom_api
        return None

    def _get_plural(self, kind: str) -> str:
        """Get the CRD plural name for a given kind."""
        plural = _KIND_PLURAL_MAP.get(kind)
        if not plural:
            raise ValueError(
                f"Unknown CRD kind: '{kind}'. "
                f"Supported: {sorted(_KIND_PLURAL_MAP.keys())}"
            )
        return plural

    # ──────────────────────────────────────────────────────────
    # Discovery (existing, refactored to use cached clients)
    # ──────────────────────────────────────────────────────────

    async def discover_tempo_services(
        self, namespace: Optional[str] = None,
    ) -> List[BackendConfig]:
        """Discover Tempo services by labels."""
        k8s = self._get_client()
        if not k8s:
            return []

        discovered: List[BackendConfig] = []
        try:
            label_selector = "app.kubernetes.io/name=tempo"

            # H-03: The kubernetes client is synchronous — run in a thread pool
            # to avoid blocking the asyncio event loop during K8s API calls.
            if namespace:
                services = await asyncio.to_thread(
                    k8s.list_namespaced_service,
                    namespace=namespace,
                    label_selector=label_selector,
                )
            else:
                services = await asyncio.to_thread(
                    k8s.list_service_for_all_namespaces,
                    label_selector=label_selector,
                )

            for svc in services.items:
                name = svc.metadata.name
                ns = svc.metadata.namespace
                labels = svc.metadata.labels or {}

                # Find query-frontend port
                port = 3200  # default Tempo port
                for svc_port in svc.spec.ports or []:
                    if svc_port.name in ("http", "http-query", "tempo-query"):
                        port = svc_port.port
                        break

                # Determine deployment mode from labels
                component = labels.get("app.kubernetes.io/component", "")
                if component == "query-frontend":
                    mode = "microservices"
                else:
                    mode = "monolithic"

                backend = BackendConfig(
                    id=f"k8s-{ns}-{name}",
                    base_url=f"http://{name}.{ns}.svc.cluster.local:{port}",
                    type="tempo",
                    display_name=f"K8s: {ns}/{name}",
                    labels=labels,
                    deployment_mode=mode,
                )
                discovered.append(backend)


        except Exception:
            pass  # Non-fatal — discovery best-effort

        return discovered

    async def discover_tempo_operator_crs(
        self, namespace: Optional[str] = None,
    ) -> List[BackendConfig]:
        """Discover TempoStack and TempoMonolithic CRDs."""
        custom_api = self._get_custom_api()
        if not custom_api:
            return []

        discovered: List[BackendConfig] = []
        group = self._operator_config.crd_group
        version = self._operator_config.crd_api_version

        for kind, mode in _KIND_MODE_MAP.items():
            plural = self._get_plural(kind)
            try:
                if namespace:
                    crs = await asyncio.to_thread(
                        custom_api.list_namespaced_custom_object,
                        group=group,
                        version=version,
                        namespace=namespace,
                        plural=plural,
                    )
                else:
                    crs = await asyncio.to_thread(
                        custom_api.list_cluster_custom_object,
                        group=group,
                        version=version,
                        plural=plural,
                    )

                for cr in crs.get("items", []):
                    name = cr["metadata"]["name"]
                    ns = cr["metadata"]["namespace"]

                    # For microservices, route to query-frontend
                    if mode == "microservices":
                        svc_name = f"tempo-{name}-query-frontend"
                    else:
                        svc_name = f"tempo-{name}"

                    backend = BackendConfig(
                        id=f"operator-{ns}-{name}",
                        base_url=f"http://{svc_name}.{ns}.svc.cluster.local:3200",
                        type="tempo",
                        display_name=f"Operator: {ns}/{name} ({mode})",
                        deployment_mode=mode,
                    )
                    discovered.append(backend)


            except Exception:
                pass  # CRD kind may not be installed

        return discovered

    # ──────────────────────────────────────────────────────────
    # CRD Management (new — following OTel MCP server pattern)
    # ──────────────────────────────────────────────────────────

    async def get_tempo_operator_cr(
        self, namespace: str, name: str, kind: str
    ) -> Dict[str, Any]:
        """Get a single TempoStack or TempoMonolithic CR.

        Args:
            namespace: K8s namespace.
            name: CR name.
            kind: "TempoStack" or "TempoMonolithic".

        Returns:
            Full CR dict including metadata, spec, and status.

        Raises:
            ValueError: If kind is not recognized.
            Exception: If the CR is not found or API fails.
        """
        custom_api = self._get_custom_api()
        if not custom_api:
            raise RuntimeError("Kubernetes not available (K8S_ENABLED=false)")

        plural = self._get_plural(kind)
        return await asyncio.to_thread(
            custom_api.get_namespaced_custom_object,
            group=self._operator_config.crd_group,
            version=self._operator_config.crd_api_version,
            namespace=namespace,
            plural=plural,
            name=name,
        )

    async def list_tempo_operator_crs(
        self,
        namespace: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List Tempo Operator CRDs, optionally filtered by namespace and kind.

        Args:
            namespace: Filter to a single namespace (None = all namespaces).
            kind: Filter to "TempoStack" or "TempoMonolithic" (None = both).

        Returns:
            List of CR dicts.
        """
        custom_api = self._get_custom_api()
        if not custom_api:
            return []

        kinds_to_scan = (
            [kind] if kind else list(_KIND_PLURAL_MAP.keys())
        )
        group = self._operator_config.crd_group
        version = self._operator_config.crd_api_version

        results: List[Dict[str, Any]] = []
        for k in kinds_to_scan:
            plural = self._get_plural(k)
            try:
                if namespace:
                    resp = await asyncio.to_thread(
                        custom_api.list_namespaced_custom_object,
                        group=group,
                        version=version,
                        namespace=namespace,
                        plural=plural,
                    )
                else:
                    resp = await asyncio.to_thread(
                        custom_api.list_cluster_custom_object,
                        group=group,
                        version=version,
                        plural=plural,
                    )
                for item in resp.get("items", []):
                    item["_kind"] = k  # Tag for downstream
                    results.append(item)
            except Exception:
                pass  # CRD kind may not be installed

        return results

    async def create_or_patch_tempo_cr(
        self,
        namespace: str,
        name: str,
        kind: str,
        spec: Dict[str, Any],
        labels: Optional[Dict[str, str]] = None,
        overwrite: bool = False,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Create or patch a TempoStack/TempoMonolithic CR.

        Follows the OTel MCP server pattern:
        1. Try get existing → if exists, patch (or replace if overwrite=True)
        2. If not found → create
        3. dry_run=True → server-side dry run, no persist

        Args:
            namespace: Target namespace.
            name: CR name.
            kind: "TempoStack" or "TempoMonolithic".
            spec: The CR spec dict.
            labels: Optional labels to merge into metadata.
            overwrite: If True, replaces entire spec. If False, merges.
            dry_run: If True, performs a server-side dry run.

        Returns:
            The created/patched CR dict.
        """
        custom_api = self._get_custom_api()
        if not custom_api:
            raise RuntimeError("Kubernetes not available (K8S_ENABLED=false)")

        plural = self._get_plural(kind)
        group = self._operator_config.crd_group
        version = self._operator_config.crd_api_version

        merged_labels = {
            "app.kubernetes.io/managed-by": "talkops-mcp",
            "app.kubernetes.io/part-of": "tempo",
        }
        if labels:
            merged_labels.update(labels)

        body = {
            "apiVersion": f"{group}/{version}",
            "kind": kind,
            "metadata": {
                "name": name,
                "namespace": namespace,
                "labels": merged_labels,
            },
            "spec": spec,
        }

        dry_run_param = ["All"] if dry_run else None

        # Try to get existing
        try:
            existing = await asyncio.to_thread(
                custom_api.get_namespaced_custom_object,
                group=group,
                version=version,
                namespace=namespace,
                plural=plural,
                name=name,
            )
            # Exists → patch or replace
            if overwrite:
                body["metadata"]["resourceVersion"] = (
                    existing.get("metadata", {}).get("resourceVersion")
                )
                result = await asyncio.to_thread(
                    custom_api.replace_namespaced_custom_object,
                    group=group,
                    version=version,
                    namespace=namespace,
                    plural=plural,
                    name=name,
                    body=body,
                    dry_run=dry_run_param,
                )
            else:
                # Strategic merge patch
                patch_body = {"spec": spec, "metadata": {"labels": merged_labels}}
                result = await asyncio.to_thread(
                    custom_api.patch_namespaced_custom_object,
                    group=group,
                    version=version,
                    namespace=namespace,
                    plural=plural,
                    name=name,
                    body=patch_body,
                    dry_run=dry_run_param,
                )
            return result

        except Exception as e:
            if "404" in str(e) or "NotFound" in str(e):
                # Does not exist → create
                result = await asyncio.to_thread(
                    custom_api.create_namespaced_custom_object,
                    group=group,
                    version=version,
                    namespace=namespace,
                    plural=plural,
                    body=body,
                    dry_run=dry_run_param,
                )
                return result
            raise
