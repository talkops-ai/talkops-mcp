"""Prometheus Exporter Kubernetes Lifecycle MCP tools (`exporter` toolset)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from prometheus_mcp_server.config import SUPPORTED_EXPORTERS
from prometheus_mcp_server.exceptions import (
    PrometheusOperationError,
    PrometheusValidationError,
)
from prometheus_mcp_server.tools.base import BaseTool
from prometheus_mcp_server.utils.exporter_catalog import (
    build_exporter_manifests,
    build_servicemonitor_manifest,
)
from prometheus_mcp_server.utils.param_coercion import JsonDict
from prometheus_mcp_server.utils.redaction import redact_sensitive_data


class ExporterTools(BaseTool):
    """Kubernetes exporter deployment and removal tools (`exporter` toolset)."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register("exporter", is_write=True):
            return

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Install Prometheus Exporter to Kubernetes",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_install_exporter(
            exporter_type: str = Field(
                ...,
                min_length=1,
                description="Exporter type (e.g. 'postgres_exporter', 'redis_exporter', 'node_exporter')",
            ),
            namespace: str = Field(
                default="monitoring",
                description="Kubernetes namespace to deploy the exporter into",
            ),
            release_name: Optional[str] = Field(
                default=None,
                description="Optional K8s resource name override (defaults to exporter_type with hyphens)",
            ),
            exporter_config: Optional[JsonDict] = Field(
                default=None,
                description="Exporter environment/secret/flag config (e.g. {'REDIS_ADDR': 'redis://redis:6379'} or {'secret_env': {'DATA_SOURCE_NAME': {'name': 'pg-dsn', 'key': 'dsn'}}})",
            ),
            create_servicemonitor: bool = Field(
                default=True,
                description="Automatically create a matching ServiceMonitor CRD",
            ),
            dry_run: bool = Field(
                default=True,
                description="When True (default), renders and redacts manifests without applying to Kubernetes",
            ),
            confirm: bool = Field(
                default=False,
                description="Set True to confirm live deployment when dry_run=False",
            ),
            ctx: Optional[Context] = None,
        ) -> Dict[str, Any]:
            """Deploy a Prometheus exporter (`Deployment`/`DaemonSet`, `Service`, and `ServiceMonitor`) to Kubernetes.

            **MUTATES CLUSTER STATE when `dry_run=False`.** Redacts sensitive credentials in returned manifests.

            Returns:
            - {"status": str, "dry_run": bool, "exporter_type": str, "applied_resources": [...], "manifests": [...]}
            """
            self.ensure_write_allowed("default", "prom_install_exporter")

            if exporter_type not in SUPPORTED_EXPORTERS:
                supported = sorted(SUPPORTED_EXPORTERS.keys())
                raise PrometheusValidationError(
                    f"Unknown exporter_type '{exporter_type}'. Supported exporters: {supported}"
                )

            raw_cfg = dict(exporter_config or {})
            reserved_keys = {"env", "secret_env", "scope", "port", "image", "replicas", "config_data"}
            if any(k in raw_cfg for k in reserved_keys):
                merged_env = dict(raw_cfg.get("env") or {})
                for k, v in raw_cfg.items():
                    if k not in reserved_keys:
                        merged_env[k] = v
                builder_cfg: Dict[str, Any] = {k: raw_cfg[k] for k in reserved_keys if k in raw_cfg}
                builder_cfg["env"] = merged_env
            else:
                builder_cfg = {"env": raw_cfg}

            name = release_name or exporter_type.replace("_", "-")
            manifests = build_exporter_manifests(
                exporter_type=exporter_type,
                namespace=namespace,
                service_name=name,
                config=builder_cfg,
            )
            if create_servicemonitor:
                sm_labels = (
                    await self.kubernetes_service.get_servicemonitor_required_labels()
                    if self.kubernetes_service is not None
                    else {}
                )
                manifests.append(
                    build_servicemonitor_manifest(
                        name=name,
                        namespace=namespace,
                        service_name=name,
                        labels=sm_labels,
                    )
                )

            applied_resources: List[str] = []
            if not dry_run:
                if self.kubernetes_service is None:
                    raise PrometheusOperationError(
                        "Kubernetes service is not configured (set K8S_ENABLED=true)."
                    )
                await self.confirm_or_elicit(
                    ctx,
                    confirm=confirm,
                    prompt_message=(
                        f"Deploy exporter '{exporter_type}' ('{namespace}/{name}', "
                        f"{len(manifests)} resources) to Kubernetes?"
                    ),
                    backend_id="default",
                    operation="prom_install_exporter",
                    details={
                        "exporter_type": exporter_type,
                        "name": name,
                        "namespace": namespace,
                    },
                )
                for m in manifests:
                    kind = m.get("kind", "")
                    m_name = m.get("metadata", {}).get("name", name)
                    if kind == "Deployment":
                        await self.kubernetes_service.apply_deployment(namespace, m)
                    elif kind == "DaemonSet":
                        await self.kubernetes_service.apply_daemonset(namespace, m)
                    elif kind == "Service":
                        await self.kubernetes_service.apply_service(namespace, m)
                    elif kind == "ServiceAccount":
                        await self.kubernetes_service.apply_serviceaccount(namespace, m)
                    elif kind == "ClusterRole":
                        await self.kubernetes_service.apply_clusterrole(m)
                    elif kind == "ClusterRoleBinding":
                        await self.kubernetes_service.apply_clusterrolebinding(m)
                    elif kind == "ConfigMap":
                        await self.kubernetes_service.apply_configmap(namespace, m)
                    elif kind == "ServiceMonitor":
                        await self.kubernetes_service.apply_servicemonitor(namespace, m)
                    else:
                        await self.kubernetes_service.apply_custom_resource(namespace, m)
                    applied_resources.append(f"{kind}/{m_name}")
            else:
                applied_resources = [
                    f"{m.get('kind', 'Resource')}/{m.get('metadata', {}).get('name', name)}"
                    for m in manifests
                ]

            self.record_audit(
                backend_id="default",
                operation="prom_install_exporter",
                summary=f"{'Dry-run install' if dry_run else 'Installed'} exporter '{exporter_type}' ({namespace}/{name})",
                outcome="dry_run" if dry_run else "succeeded",
                details={
                    "exporter_type": exporter_type,
                    "name": name,
                    "namespace": namespace,
                    "resources": applied_resources,
                },
            )

            return {
                "status": "dry_run_preview" if dry_run else "installed",
                "dry_run": dry_run,
                "exporter_type": exporter_type,
                "name": name,
                "namespace": namespace,
                "applied_resources": applied_resources,
                "manifests": redact_sensitive_data(manifests),
            }

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Uninstall Prometheus Exporter from Kubernetes",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_uninstall_exporter(
            exporter_type: str = Field(
                ...,
                min_length=1,
                description="Exporter type to uninstall (e.g. 'postgres_exporter', 'redis_exporter')",
            ),
            namespace: str = Field(
                default="monitoring",
                description="Kubernetes namespace of the deployed exporter",
            ),
            release_name: Optional[str] = Field(
                default=None,
                description="Optional K8s resource name override (defaults to exporter_type with hyphens)",
            ),
            dry_run: bool = Field(
                default=True,
                description="When True (default), previews resources to remove without mutating the cluster",
            ),
            confirm: bool = Field(
                default=False,
                description="Set True to confirm deletion when dry_run=False",
            ),
            ctx: Optional[Context] = None,
        ) -> Dict[str, Any]:
            """Remove a deployed Prometheus exporter (`Deployment`/`DaemonSet`, `Service`, and `ServiceMonitor`) from Kubernetes.

            **DESTRUCTIVE when `dry_run=False`.** Always preview with `dry_run=True` first.

            Returns:
            - {"status": str, "dry_run": bool, "exporter_type": str, "removed_resources": [...]}
            """
            self.ensure_write_allowed("default", "prom_uninstall_exporter")

            if exporter_type not in SUPPORTED_EXPORTERS:
                supported = sorted(SUPPORTED_EXPORTERS.keys())
                raise PrometheusValidationError(
                    f"Unknown exporter_type '{exporter_type}'. Supported exporters: {supported}"
                )

            info = SUPPORTED_EXPORTERS[exporter_type]
            name = release_name or exporter_type.replace("_", "-")
            workload_kind = (
                "DaemonSet" if info.default_scope == "daemonset" else "Deployment"
            )
            planned_removals = [
                f"{workload_kind}/{name}",
                f"Service/{name}",
                f"ServiceMonitor/{name}",
            ]

            if not dry_run:
                if self.kubernetes_service is None:
                    raise PrometheusOperationError(
                        "Kubernetes service is not configured (set K8S_ENABLED=true)."
                    )
                await self.confirm_or_elicit(
                    ctx,
                    confirm=confirm,
                    prompt_message=(
                        f"Uninstall exporter '{exporter_type}' ({planned_removals}) from namespace '{namespace}'?"
                    ),
                    backend_id="default",
                    operation="prom_uninstall_exporter",
                    details={
                        "exporter_type": exporter_type,
                        "name": name,
                        "namespace": namespace,
                    },
                )
                if workload_kind == "DaemonSet":
                    await self.kubernetes_service.delete_daemonset(namespace, name)
                else:
                    await self.kubernetes_service.delete_deployment(namespace, name)
                await self.kubernetes_service.delete_service(namespace, name)
                await self.kubernetes_service.delete_custom_resource(
                    namespace, "monitoring.coreos.com", "v1", "servicemonitors", name
                )

            self.record_audit(
                backend_id="default",
                operation="prom_uninstall_exporter",
                summary=f"{'Dry-run uninstall' if dry_run else 'Uninstalled'} exporter '{exporter_type}' ({namespace}/{name})",
                outcome="dry_run" if dry_run else "succeeded",
                details={
                    "exporter_type": exporter_type,
                    "name": name,
                    "namespace": namespace,
                    "removed_resources": planned_removals,
                },
            )

            return {
                "status": "dry_run_preview" if dry_run else "uninstalled",
                "dry_run": dry_run,
                "exporter_type": exporter_type,
                "name": name,
                "namespace": namespace,
                "removed_resources": planned_removals,
            }
