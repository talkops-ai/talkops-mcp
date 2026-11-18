"""Deployment overview and Kubernetes Tempo Operator CRD resources."""

import json
from typing import Any, Dict, List

from tempo_mcp_server.exceptions import TempoResourceError
from tempo_mcp_server.resources.base import BaseResource


class DeploymentResources(BaseResource):
    """Dynamic deployment topology and Tempo Operator CRD resources."""

    def register(self, mcp_instance: Any) -> None:
        config = self.config
        kubernetes_service = self.kubernetes_service

        @mcp_instance.resource(
            "tempo://deployment/overview",
            name="tempo_deployment_overview",
            description="Deployment topology: configured backends and Kubernetes-discovered Tempo installs",
            mime_type="application/json",
        )
        async def tempo_deployment_overview() -> str:
            overview: Dict[str, Any] = {
                "total_backends": len(config.backends),
                "backends": [],
                "kubernetes_enabled": config.kubernetes.enabled,
                "discovered_services": [],
                "discovered_operator_crs": [],
            }
            for backend in config.backends:
                overview["backends"].append({
                    "id": backend.id,
                    "type": backend.type,
                    "deployment_mode": backend.deployment_mode,
                    "multi_tenant": backend.multi_tenant,
                    "base_url": backend.base_url,
                })

            if config.kubernetes.enabled and kubernetes_service:
                try:
                    svcs = await kubernetes_service.discover_tempo_services()
                    overview["discovered_services"] = [
                        {"id": s.id, "base_url": s.base_url, "deployment_mode": s.deployment_mode}
                        for s in svcs
                    ]
                    crs = await kubernetes_service.discover_tempo_operator_crs()
                    overview["discovered_operator_crs"] = [
                        {"id": c.id, "base_url": c.base_url, "deployment_mode": c.deployment_mode}
                        for c in crs
                    ]
                except Exception:
                    pass

            return json.dumps(overview, indent=2)

        @mcp_instance.resource(
            "tempo://operator/crs/{namespace}",
            name="tempo_operator_crs",
            description="Inventory of TempoStack and TempoMonolithic CRs in a namespace (use '_all' for cluster-wide)",
            mime_type="application/json",
        )
        async def tempo_operator_crs(namespace: str) -> str:
            if not kubernetes_service or not config.kubernetes.enabled:
                return json.dumps({
                    "namespace": namespace,
                    "kubernetes_enabled": False,
                    "items": [],
                    "total": 0,
                }, indent=2)

            try:
                ns_filter = None if namespace == "_all" else namespace
                crs = await kubernetes_service.list_tempo_operator_crs(namespace=ns_filter)
                items: List[Dict[str, Any]] = []
                for cr in crs:
                    meta = cr.get("metadata", {})
                    spec = cr.get("spec", {})
                    status = cr.get("status", {})
                    conditions = status.get("conditions", [])

                    ready = None
                    status_phase = None
                    for cond in conditions:
                        if cond.get("type") == "Ready":
                            ready = cond.get("status") == "True"
                            status_phase = "Ready" if ready else "NotReady"
                            break

                    storage = spec.get("storage", {})
                    storage_type = (
                        storage.get("secret", {}).get("type")
                        or storage.get("tls", {}).get("type")
                    )
                    retention = spec.get("retention", {}).get("global", {}).get("traces")
                    mg_enabled = (
                        spec.get("template", {})
                        .get("metricsGenerator", {})
                        .get("enabled", False)
                    )

                    items.append({
                        "name": meta.get("name", ""),
                        "namespace": meta.get("namespace", ""),
                        "kind": cr.get("_kind", cr.get("kind", "unknown")),
                        "storage_type": storage_type,
                        "retention": retention,
                        "metrics_generator_enabled": bool(mg_enabled),
                        "status_phase": status_phase,
                        "ready": ready,
                    })

                return json.dumps({
                    "namespace": namespace,
                    "kubernetes_enabled": True,
                    "items": items,
                    "total": len(items),
                }, indent=2)
            except Exception as e:
                raise TempoResourceError(
                    f"Failed to list Tempo Operator CRs in '{namespace}': {e}"
                ) from e

        @mcp_instance.resource(
            "tempo://operator/manifests/{kind}/{namespace}/{name}",
            name="tempo_operator_manifest",
            description="Sanitized and secret-redacted TempoStack or TempoMonolithic manifest",
            mime_type="application/json",
        )
        async def tempo_operator_manifest(kind: str, namespace: str, name: str) -> str:
            if not kubernetes_service:
                raise TempoResourceError("Kubernetes service not initialized")
            try:
                cr = await kubernetes_service.get_tempo_operator_cr(
                    namespace=namespace, name=name, kind=kind
                )
                return json.dumps(cr, indent=2)
            except Exception as e:
                raise TempoResourceError(
                    f"Failed to read {kind} '{namespace}/{name}': {e}"
                ) from e

        @mcp_instance.resource(
            "tempo://operator/crd-schema/{kind}",
            name="tempo_operator_crd_schema",
            description="Installed CRD OpenAPI v3 spec schema for TempoStack or TempoMonolithic",
            mime_type="application/json",
        )
        async def tempo_operator_crd_schema(kind: str) -> str:
            if not kubernetes_service:
                raise TempoResourceError("Kubernetes service not initialized")
            try:
                schema = await kubernetes_service.get_crd_schema(kind=kind)
                return json.dumps(schema, indent=2)
            except Exception as e:
                raise TempoResourceError(
                    f"Failed to read CRD schema for '{kind}': {e}"
                ) from e
