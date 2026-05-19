"""Prometheus exporter lifecycle management tools.

Provides granular tools for recommending, installing,
uninstalling, and verifying Prometheus exporters.

Note: The exporter catalog listing has moved to the
``prom://exporters/catalog`` resource (v4 refactor).
"""

from typing import Any, Dict, List, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from prometheus_mcp_server.config import SUPPORTED_EXPORTERS
from prometheus_mcp_server.exceptions import PrometheusOperationError
from prometheus_mcp_server.tools.base import BaseTool
from prometheus_mcp_server.utils.exporter_catalog import build_exporter_manifests
from prometheus_mcp_server.utils.json_coerce import coerce_dict, coerce_list


class ExporterTools(BaseTool):
    """Exporter lifecycle management tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service
        prometheus_service = self.prometheus_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Recommend Exporter",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def prom_recommend_exporter(
            service_type: str = Field(
                ..., description="Service type (e.g. postgres, redis, nginx)"
            ),
            environment: str = Field(
                default="kubernetes", description="Environment: kubernetes or vm"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Get exporter recommendations for a specific service type.

            Use this to find the best exporter for monitoring a third-party
            service. Read-only.

            Returns:
            - {\"exporters\": [{\"name\": str, \"description\": str, ...}], \"notes\": str}

            When NOT to use: For browsing the full exporter catalog, use
            the prom://exporters/catalog resource. For deploying, use prom_install_exporter.
            """
            try:
                matches = []
                svc = service_type.lower()
                for name, info in SUPPORTED_EXPORTERS.items():
                    if svc in name.lower() or svc in info.description.lower():
                        if environment in info.supported_environments:
                            matches.append({
                                "name": info.type,
                                "description": info.description,
                                "default_ports": info.default_ports,
                                "image": info.image,
                            })
                return {
                    "exporters": matches,
                    "notes": f"Found {len(matches)} exporter(s) for '{service_type}' in {environment}.",
                }
            except Exception as e:
                raise PrometheusOperationError(f"Recommendation failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Install Exporter",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def prom_install_exporter(
            exporter_type: str = Field(
                ..., description="Exporter type (e.g. postgres_exporter)"
            ),
            namespace: str = Field(
                default="monitoring", description="Kubernetes namespace"
            ),
            service_name: Optional[str] = Field(
                default=None, description="Custom service name override"
            ),
            config: Optional[Dict[str, Any]] = Field(
                default=None, description="Extra config: port, image, replicas, env vars"
            ),
            environment: str = Field(
                default="kubernetes", description="Environment: kubernetes or vm"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Deploy an exporter to Kubernetes (creates Deployment/DaemonSet + Service).

            Use this to install a Prometheus exporter for monitoring third-party
            systems. MUTATES CLUSTER STATE.

            **WARNING: This creates Kubernetes resources (Deployments/DaemonSets
            and Services) in the target namespace.**

            Returns:
            - {\"applied_resources\": [str], \"manifest_yaml\": str, \"notes\": str}

            When NOT to use: For browsing available exporters, use
            the prom://exporters/catalog resource.

            Prerequisites:
            - Kubernetes cluster must be reachable
            - Target namespace must exist

            Common errors:
            - Unknown exporter_type: Use prom_list_exporters to see supported exporters.
            - Install fails: Ensure K8s cluster is reachable and namespace exists.
            """
            try:
                extra = coerce_dict(config)
                manifests = build_exporter_manifests(
                    exporter_type, namespace,
                    service_name=service_name,
                    config=extra,
                )

                applied = []
                for manifest in manifests:
                    kind = manifest.get("kind", "")
                    if kind == "Deployment":
                        await kubernetes_service.apply_deployment(namespace, manifest)
                        applied.append(f"Deployment/{manifest['metadata']['name']}")
                    elif kind == "DaemonSet":
                        await kubernetes_service.apply_daemonset(namespace, manifest)
                        applied.append(f"DaemonSet/{manifest['metadata']['name']}")
                    elif kind == "Service":
                        await kubernetes_service.apply_service(namespace, manifest)
                        applied.append(f"Service/{manifest['metadata']['name']}")
                    elif kind == "ServiceAccount":
                        await kubernetes_service.apply_serviceaccount(namespace, manifest)
                        applied.append(f"ServiceAccount/{manifest['metadata']['name']}")
                    elif kind == "ClusterRole":
                        await kubernetes_service.apply_clusterrole(manifest)
                        applied.append(f"ClusterRole/{manifest['metadata']['name']}")
                    elif kind == "ClusterRoleBinding":
                        await kubernetes_service.apply_clusterrolebinding(manifest)
                        applied.append(f"ClusterRoleBinding/{manifest['metadata']['name']}")
                    elif kind == "ConfigMap":
                        await kubernetes_service.apply_configmap(namespace, manifest)
                        applied.append(f"ConfigMap/{manifest['metadata']['name']}")

                import yaml
                manifest_yaml = yaml.dump_all(manifests, default_flow_style=False)

                return {
                    "applied_resources": applied,
                    "manifest_yaml": manifest_yaml,
                    "notes": f"Deployed {exporter_type} to {namespace}",
                }
            except Exception as e:
                raise PrometheusOperationError(f"Install failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Uninstall Exporter",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def prom_uninstall_exporter(
            exporter_type: str = Field(
                ..., description="Exporter type to uninstall (e.g. postgres_exporter)"
            ),
            namespace: str = Field(
                default="monitoring", description="Kubernetes namespace"
            ),
            service_name: Optional[str] = Field(
                default=None, description="Custom service name override"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Remove an exporter from Kubernetes (deletes Deployment/DaemonSet + Service).

            DESTRUCTIVE — removes running workloads.

            **WARNING: This deletes Kubernetes resources. Running exporter
            pods will be terminated.**

            Returns:
            - {\"removed_resources\": [str]}

            Common errors:
            - Resource not found: Exporter may not be installed in the namespace.
            """
            try:
                info = SUPPORTED_EXPORTERS.get(exporter_type)
                if not info:
                    raise PrometheusOperationError(
                        f"Unknown exporter_type '{exporter_type}'. "
                        f"Use prom_list_exporters to see supported exporters."
                    )

                resource_name = (service_name or exporter_type).replace("_", "-")
                removed = []

                scope = info.default_scope
                if scope == "daemonset":
                    await kubernetes_service.delete_daemonset(namespace, resource_name)
                    removed.append(f"DaemonSet/{resource_name}")
                else:
                    await kubernetes_service.delete_deployment(namespace, resource_name)
                    removed.append(f"Deployment/{resource_name}")

                await kubernetes_service.delete_service(namespace, resource_name)
                removed.append(f"Service/{resource_name}")

                return {"removed_resources": removed}
            except PrometheusOperationError:
                raise
            except Exception as e:
                raise PrometheusOperationError(f"Uninstall failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Verify Exporter",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_verify_exporter(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            endpoint_url: str = Field(
                ..., description="Exporter metrics endpoint URL"
            ),
            job: Optional[str] = Field(
                default=None, description="Job name for up{} series check"
            ),
            verify_timeout: int = Field(
                default=60, description="Timeout in seconds for verify polling (default: 60)"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """End-to-end health check: scrape endpoint and check Prometheus up{} series.

            Use this after deploying an exporter to verify it's working correctly.
            Makes outbound HTTP requests to the endpoint and queries Prometheus.

            Returns:
            - {\"endpoint_check\": {...}, \"up_series_found\": bool, \"errors\": [str]}

            When NOT to use: For testing raw metrics endpoints without Prometheus
            integration, use prom_test_endpoint instead.

            Common errors:
            - Verify timeout: Exporter pod may not be ready yet. Increase verify_timeout.
            """
            try:
                from prometheus_mcp_server.utils.endpoint_tester import test_metrics_endpoint
                import asyncio

                errors = []

                # Test the endpoint directly
                endpoint_result = await test_metrics_endpoint(endpoint_url)

                # Check if Prometheus has scraped it (up{} series)
                up_found = False
                if job:
                    try:
                        query = f'up{{job="{job}"}}'
                        result = await prometheus_service.instant_query(
                            backend_id, query
                        )
                        up_found = (result.sample_count or 0) > 0
                        if not up_found:
                            errors.append(
                                f"up{{job=\"{job}\"}} not found. "
                                "Prometheus may not have scraped yet."
                            )
                    except Exception as e:
                        errors.append(f"up{{}} query failed: {e}")

                return {
                    "endpoint_check": endpoint_result,
                    "up_series_found": up_found,
                    "errors": errors,
                }
            except Exception as e:
                raise PrometheusOperationError(f"Verification failed: {e}")
