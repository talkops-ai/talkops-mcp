"""Kubernetes discovery and CRD management service for Tempo backends.

Discovers Tempo services via:
1. Service labels (app.kubernetes.io/name=tempo)
2. Tempo Operator CRDs (TempoStack, TempoMonolithic)

Manages Tempo Operator CRDs:
3. List/Get TempoStack and TempoMonolithic resources
4. Apply TempoStack and TempoMonolithic manifests with Server-Side Dry-Run validation
5. Read installed CRD OpenAPI schema for TempoStack and TempoMonolithic
"""

import asyncio
from typing import Any, Dict, List, Literal, Optional

import yaml

from tempo_mcp_server.config import BackendConfig, KubernetesConfig, TempoOperatorConfig
from tempo_mcp_server.utils.redaction import compute_unified_diff, sanitize_k8s_manifest

# CRD kind -> plural mapping
_KIND_PLURAL_MAP = {
    "TempoStack": "tempostacks",
    "TempoMonolithic": "tempomonolithics",
}

# CRD kind -> default deployment mode
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
        self._apiext_api = None
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
                    config_file=self._config.kubeconfig,
                    context=self._config.context_name,
                )
            self._api_client = client.CoreV1Api()
            self._custom_api = client.CustomObjectsApi()
            self._apiext_api = client.ApiextensionsV1Api()
            self._k8s_loaded = True
            return True
        except Exception:
            return False

    def _get_client(self) -> Any:
        if self._ensure_k8s():
            return self._api_client
        return None

    def _get_custom_api(self) -> Any:
        if self._ensure_k8s():
            return self._custom_api
        return None

    def _get_apiext_api(self) -> Any:
        if self._ensure_k8s():
            return self._apiext_api
        return None

    def _get_plural(self, kind: str) -> str:
        plural = _KIND_PLURAL_MAP.get(kind)
        if not plural:
            raise ValueError(
                f"Unknown CRD kind: '{kind}'. "
                f"Supported: {sorted(_KIND_PLURAL_MAP.keys())}"
            )
        return plural

    # ──────────────────────────────────────────────────────────
    # Discovery
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

                port = 3200
                for svc_port in svc.spec.ports or []:
                    if svc_port.name in ("http", "http-query", "tempo-query"):
                        port = svc_port.port
                        break

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
            pass

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
                pass

        return discovered

    # ──────────────────────────────────────────────────────────
    # CRD Inspection & Schema Discovery
    # ──────────────────────────────────────────────────────────

    async def get_tempo_operator_cr(
        self, namespace: str, name: str, kind: str
    ) -> Dict[str, Any]:
        """Get a single TempoStack or TempoMonolithic CR (sanitized)."""
        custom_api = self._get_custom_api()
        if not custom_api:
            raise RuntimeError("Kubernetes not available (K8S_ENABLED=false)")

        plural = self._get_plural(kind)
        raw = await asyncio.to_thread(
            custom_api.get_namespaced_custom_object,
            group=self._operator_config.crd_group,
            version=self._operator_config.crd_api_version,
            namespace=namespace,
            plural=plural,
            name=name,
        )
        return sanitize_k8s_manifest(raw)

    async def list_tempo_operator_crs(
        self,
        namespace: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List Tempo Operator CRDs, optionally filtered by namespace and kind."""
        custom_api = self._get_custom_api()
        if not custom_api:
            return []

        kinds_to_scan = [kind] if kind else list(_KIND_PLURAL_MAP.keys())
        group = self._operator_config.crd_group
        version = self._operator_config.crd_api_version

        results: List[Dict[str, Any]] = []
        for k in kinds_to_scan:
            plural = self._get_plural(k)
            try:
                if namespace and namespace != "_all":
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
                    sanitized = sanitize_k8s_manifest(item)
                    sanitized["_kind"] = k
                    results.append(sanitized)
            except Exception:
                pass

        return results

    async def get_crd_schema(self, kind: str) -> Dict[str, Any]:
        """Retrieve the installed OpenAPI v3 spec schema for TempoStack or TempoMonolithic."""
        plural = self._get_plural(kind)
        group = self._operator_config.crd_group
        version = self._operator_config.crd_api_version
        crd_name = f"{plural}.{group}"

        apiext = self._get_apiext_api()
        if apiext:
            try:
                crd_obj = await asyncio.to_thread(
                    apiext.read_custom_resource_definition,
                    name=crd_name,
                )
                crd_dict = crd_obj.to_dict() if hasattr(crd_obj, "to_dict") else crd_obj
                versions = crd_dict.get("spec", {}).get("versions", [])
                for v in versions:
                    if v.get("name") == version or v.get("served"):
                        schema = (
                            v.get("schema", {})
                            .get("open_apiv3_schema", v.get("schema", {}).get("openAPIV3Schema", {}))
                        )
                        spec_props = (
                            schema.get("properties", {})
                            .get("spec", {})
                            .get("properties", {})
                        )
                        return {
                            "kind": kind,
                            "crd_name": crd_name,
                            "api_version": f"{group}/{v.get('name', version)}",
                            "source": "cluster_crd",
                            "spec_top_level_fields": sorted(list(spec_props.keys())),
                            "spec_schema": spec_props,
                        }
            except Exception:
                pass

        # Fallback minimal structural summary when cluster CRD is unreachable
        fallback_fields = (
            [
                "storage",
                "storageSize",
                "replicationFactor",
                "retention",
                "resources",
                "search",
                "tenants",
                "template",
                "observability",
                "extraConfig",
            ]
            if kind == "TempoStack"
            else [
                "storage",
                "resources",
                "multitenancy",
                "jaegerui",
                "observability",
                "extraConfig",
            ]
        )
        return {
            "kind": kind,
            "crd_name": crd_name,
            "api_version": f"{group}/{version}",
            "source": "offline_descriptor",
            "kubernetes_enabled": self._config.enabled,
            "spec_top_level_fields": fallback_fields,
        }

    # ──────────────────────────────────────────────────────────
    # CRD Apply & Mutation
    # ──────────────────────────────────────────────────────────

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
        """Create or patch a TempoStack/TempoMonolithic CR (with server-side dryRun support)."""
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

        dry_run_param = "All" if dry_run else None
        kwargs: Dict[str, Any] = {}
        if dry_run_param:
            kwargs["dry_run"] = dry_run_param

        try:
            existing = await asyncio.to_thread(
                custom_api.get_namespaced_custom_object,
                group=group,
                version=version,
                namespace=namespace,
                plural=plural,
                name=name,
            )
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
                    **kwargs,
                )
            else:
                patch_body = {"spec": spec, "metadata": {"labels": merged_labels}}
                result = await asyncio.to_thread(
                    custom_api.patch_namespaced_custom_object,
                    group=group,
                    version=version,
                    namespace=namespace,
                    plural=plural,
                    name=name,
                    body=patch_body,
                    **kwargs,
                )
            return sanitize_k8s_manifest(result)

        except Exception as e:
            if "404" in str(e) or "NotFound" in str(e) or getattr(e, "status", None) == 404:
                result = await asyncio.to_thread(
                    custom_api.create_namespaced_custom_object,
                    group=group,
                    version=version,
                    namespace=namespace,
                    plural=plural,
                    body=body,
                    **kwargs,
                )
                return sanitize_k8s_manifest(result)
            raise

    async def apply_tempo_cr_manifest(
        self,
        manifest: Dict[str, Any],
        dry_run: bool = True,
        field_manager: str = "talkops-tempo-mcp",
    ) -> Dict[str, Any]:
        """Validate and apply a TempoStack or TempoMonolithic manifest with unified diff."""
        kind = manifest.get("kind", "")
        if kind not in _KIND_PLURAL_MAP:
            raise ValueError(
                f"Invalid manifest kind '{kind}'. Only 'TempoStack' and 'TempoMonolithic' are permitted."
            )

        meta = manifest.get("metadata") or {}
        name = meta.get("name")
        namespace = meta.get("namespace") or "default"
        spec = manifest.get("spec")
        if not name or not isinstance(spec, dict):
            raise ValueError(
                "Manifest must contain metadata.name and a non-empty spec object."
            )

        labels = dict(meta.get("labels") or {})
        labels.setdefault("app.kubernetes.io/managed-by", field_manager)
        labels.setdefault("app.kubernetes.io/part-of", "tempo")

        desired_obj = {
            "apiVersion": manifest.get(
                "apiVersion",
                f"{self._operator_config.crd_group}/{self._operator_config.crd_api_version}",
            ),
            "kind": kind,
            "metadata": {
                "name": name,
                "namespace": namespace,
                "labels": labels,
            },
            "spec": spec,
        }

        existing: Optional[Dict[str, Any]] = None
        custom_api = self._get_custom_api()
        if custom_api:
            try:
                existing = await self.get_tempo_operator_cr(
                    namespace=namespace, name=name, kind=kind
                )
            except Exception:
                existing = None

        diff_text = compute_unified_diff(
            existing,
            desired_obj,
            fromfile=f"{kind}/{namespace}/{name} (current)",
            tofile=f"{kind}/{namespace}/{name} (desired)",
        )
        sanitized_desired = sanitize_k8s_manifest(desired_obj)
        manifest_yaml = yaml.safe_dump(sanitized_desired, sort_keys=False)

        if not custom_api:
            if dry_run:
                return {
                    "action": "dry_run",
                    "dry_run": True,
                    "server_validated": False,
                    "server_dry_run_validated": False,
                    "name": name,
                    "namespace": namespace,
                    "kind": kind,
                    "diff": diff_text,
                    "manifest_yaml": manifest_yaml,
                }
            raise RuntimeError("Kubernetes not available (K8S_ENABLED=false)")

        applied = await self.create_or_patch_tempo_cr(
            namespace=namespace,
            name=name,
            kind=kind,
            spec=spec,
            labels=labels,
            overwrite=False,
            dry_run=dry_run,
        )

        action = "dry_run" if dry_run else ("patched" if existing else "created")
        return {
            "action": action,
            "dry_run": dry_run,
            "server_validated": True,
            "server_dry_run_validated": True,
            "name": name,
            "namespace": namespace,
            "kind": kind,
            "diff": diff_text,
            "manifest_yaml": manifest_yaml,
            "resource_version": applied.get("metadata", {}).get("resourceVersion"),
            "uid": applied.get("metadata", {}).get("uid"),
        }
