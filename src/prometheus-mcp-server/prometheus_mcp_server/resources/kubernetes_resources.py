"""Kubernetes CRD resources for Prometheus MCP server."""

import json
from typing import Any, Dict, List

from prometheus_mcp_server.exceptions import (
    PrometheusResourceError,
    PrometheusResourceNotFoundError,
)
from prometheus_mcp_server.resources.base import BaseResource
from prometheus_mcp_server.services.kubernetes_service import KubernetesService


class KubernetesResources(BaseResource):
    """Kubernetes CRD MCP resources (`prom://kubernetes/scrape-crds` and `prom://kubernetes/manifests/...`)."""

    def __init__(self, service_locator: Dict[str, Any]):
        super().__init__(service_locator)
        self.kubernetes_service: KubernetesService = service_locator.get("kubernetes_service")  # type: ignore[assignment]

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "prom://kubernetes/scrape-crds",
            name="prom_kubernetes_scrape_crds",
            description=(
                "Inventory of deployed Prometheus Operator CRDs across the cluster: "
                "ServiceMonitor, PodMonitor, Probe, ScrapeConfig, and PrometheusRule"
            ),
            mime_type="application/json",
        )
        async def kubernetes_scrape_crds_resource() -> str:
            try:
                if self.kubernetes_service is None:
                    return json.dumps(
                        {
                            "error": "Kubernetes service not configured",
                            "hint": "Set K8S_ENABLED=true in your environment",
                        }
                    )

                scrape_crds = await self.kubernetes_service.list_scrape_crds()
                rules_list: List[Dict[str, Any]] = []
                try:
                    raw_rules = await self.kubernetes_service.list_prometheus_rules()
                    for item in raw_rules.get("items", []):
                        meta = item.get("metadata", {})
                        groups = item.get("spec", {}).get("groups", [])
                        rules_list.append(
                            {
                                "kind": "PrometheusRule",
                                "name": meta.get("name", ""),
                                "namespace": meta.get("namespace", ""),
                                "labels": meta.get("labels", {}),
                                "group_names": [g.get("name", "") for g in groups],
                            }
                        )
                except Exception:
                    pass

                crd_namespaces = sorted(
                    {
                        item.get("namespace", "")
                        for items in scrape_crds.values()
                        for item in items
                        if item.get("namespace")
                    }
                    | {
                        r.get("namespace", "")
                        for r in rules_list
                        if r.get("namespace")
                    }
                )
                payload: Dict[str, Any] = {}
                try:
                    import inspect

                    op_ctx_fn = getattr(self.kubernetes_service, "list_operator_context", None)
                    if callable(op_ctx_fn):
                        maybe_ctx = op_ctx_fn(crd_namespaces or None)
                        if inspect.isawaitable(maybe_ctx):
                            maybe_ctx = await maybe_ctx
                        if isinstance(maybe_ctx, dict):
                            payload["operator_selectors"] = maybe_ctx.get("operator_selectors", {})
                            payload["prometheus_instances"] = maybe_ctx.get("prometheus_instances", [])
                            extra_ctx = {
                                k: v
                                for k, v in maybe_ctx.items()
                                if k not in ("operator_selectors", "prometheus_instances")
                            }
                        else:
                            extra_ctx = {}
                    else:
                        extra_ctx = {}
                except Exception:
                    extra_ctx = {}

                payload["scrape_crds"] = scrape_crds
                payload["prometheus_rules"] = rules_list
                payload.update(extra_ctx)

                return json.dumps(payload, default=str, separators=(",", ":"))
            except Exception as e:
                raise PrometheusResourceError(f"Failed to list Kubernetes CRDs: {e}")

        @mcp_instance.resource(
            "prom://kubernetes/manifests/{kind}/{namespace}/{name}",
            name="prom_kubernetes_manifest_detail",
            description=(
                "Live redacted Kubernetes CRD manifest for a specific ServiceMonitor, "
                "PodMonitor, Probe, ScrapeConfig, or PrometheusRule"
            ),
            mime_type="application/json",
        )
        async def kubernetes_manifest_detail_resource(
            kind: str, namespace: str, name: str
        ) -> str:
            try:
                if self.kubernetes_service is None:
                    raise PrometheusResourceError(
                        "Kubernetes service is not enabled (set K8S_ENABLED=true)."
                    )
                manifest = await self.kubernetes_service.get_crd_manifest(
                    kind, namespace, name
                )
                if manifest is None:
                    raise PrometheusResourceNotFoundError(
                        f"{kind} '{namespace}/{name}' not found. "
                        "Read prom://kubernetes/scrape-crds to list available CRDs."
                    )
                return json.dumps(manifest, default=str, indent=2)
            except (PrometheusResourceError, PrometheusResourceNotFoundError):
                raise
            except Exception as e:
                raise PrometheusResourceError(
                    f"Failed to fetch {kind} '{namespace}/{name}': {e}"
                )
