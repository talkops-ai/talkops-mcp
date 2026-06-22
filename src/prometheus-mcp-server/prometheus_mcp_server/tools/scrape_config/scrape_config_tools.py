"""Prometheus scrape configuration tools.

Provides granular tools for managing scrape targets via
ServiceMonitor CRDs or file_sd_configs.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from prometheus_mcp_server.exceptions import PrometheusOperationError
from prometheus_mcp_server.tools.base import BaseTool
from prometheus_mcp_server.services.kubernetes_service import KubernetesService
from prometheus_mcp_server.utils.json_coerce import coerce_dict, coerce_list


class ScrapeConfigTools(BaseTool):
    """Scrape target configuration tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        kubernetes_service: "KubernetesService" = self.kubernetes_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Apply ServiceMonitor",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def prom_apply_servicemonitor(
            service_name: str = Field(
                ..., description="Service name to monitor (the actual K8s Service name)"
            ),
            namespace: str = Field(
                default="default",
                description=(
                    "Namespace where the ServiceMonitor CRD will be created. "
                    "This is where Prometheus Operator looks for ServiceMonitors. "
                    "Usually the same as the Prometheus namespace (e.g. 'monitoring'). "
                    "If the target service is in a different namespace, set "
                    "target_namespace instead of changing this."
                ),
            ),
            target_namespace: Optional[str] = Field(
                default=None,
                description=(
                    "Namespace where the target Service lives. Use when the service "
                    "is in a different namespace than the ServiceMonitor itself "
                    "(cross-namespace scraping). For example: ServiceMonitor in "
                    "'monitoring', service in 'otel-demo' → set namespace='monitoring', "
                    "target_namespace='otel-demo'. When omitted, the ServiceMonitor "
                    "selects services in its own namespace."
                ),
            ),
            monitor_name: Optional[str] = Field(
                default=None, description="ServiceMonitor name (auto-generated if omitted)"
            ),
            port_name: str = Field(
                default="metrics",
                description=(
                    "Port *name* (not number) to scrape, e.g. 'metrics', 'prometheus', "
                    "'http-metrics'. Used as fallback when auto_discover=False or "
                    "when no well-known port is found."
                ),
            ),
            path: str = Field(
                default="/metrics", description="Metrics path"
            ),
            interval: str = Field(
                default="30s", description="Scrape interval"
            ),
            labels: Optional[Dict[str, str]] = Field(
                default=None, description="Extra labels for ServiceMonitor metadata"
            ),
            metric_relabelings: Optional[List[Dict[str, Any]]] = Field(
                default=None, description="Metric relabelings to apply to the endpoint"
            ),
            auto_discover: bool = Field(
                default=True,
                description=(
                    "Auto-discover the target Service's labels and ports from the "
                    "Kubernetes API. When True (default), the tool reads the actual "
                    "Service (in target_namespace or namespace) to build a correct "
                    "selector and port configuration. Set to False to use the "
                    "provided port_name and a simple {app: service_name} selector."
                ),
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Generate and apply a ServiceMonitor CRD for Prometheus Operator.

            Use this to wire applications to Prometheus without manual YAML editing.
            MUTATES CLUSTER — creates a K8s custom resource.

            **WARNING: Creates a ServiceMonitor CRD in the Kubernetes cluster.**

            Supports cross-namespace scraping via the `target_namespace` parameter.
            When `target_namespace` differs from `namespace`, the generated
            ServiceMonitor includes a ``spec.namespaceSelector`` so Prometheus can
            discover services in the target namespace from the SM in `namespace`.

            By default, auto-discovers the target Service's metadata labels and
            port names from the Kubernetes API so the generated ServiceMonitor
            correctly matches any labeling convention (Helm, Kustomize, etc.).
            If the Service is not found, falls back to a simple ``{app: service_name}``
            selector with a warning.

            **Cross-namespace example**:
            ServiceMonitor in 'monitoring', service 'otel-demo-collector-collector'
            in 'otel-demo':
            >>> prom_apply_servicemonitor(
            ...     service_name="otel-demo-collector-collector",
            ...     namespace="monitoring",
            ...     target_namespace="otel-demo",
            ... )

            Returns:
            - {"applied": str, "namespace": str, "target_namespace": str,
               "manifest_yaml": str, "notes": str,
               "auto_discovered": bool, "discovered_details": dict | None}

            Prerequisites:
            - Prometheus Operator must be installed in the cluster

            When NOT to use: For deploying exporter workloads, use
            prom_install_exporter. This tool only configures scrape targets.

            Common errors:
            - CRD not installed: Ensure Prometheus Operator is deployed.
            - Service not found: Use the exact K8s Service name, not the app name.
              Run `kubectl get svc -n <namespace>` to list available services.
            - Target not appearing: Check that the port_name matches the K8s port
              name on the Service (must be a named port, not a bare number).
            """
            try:
                extra_labels = coerce_dict(labels) or {}
                operator_labels = await kubernetes_service.get_servicemonitor_required_labels()
                if operator_labels:
                    extra_labels.update(operator_labels)

                name = monitor_name or f"{service_name}-monitor"

                # Determine which namespace to look up the service in for discovery
                discover_in_ns = target_namespace or namespace

                # ── Auto-discovery: read the real K8s Service ────────────
                discovered = None
                selector_labels: Dict[str, str] = {"app": service_name}
                effective_port = port_name
                discovery_notes: List[str] = []

                if auto_discover:
                    discovered = await kubernetes_service.discover_service_details(
                        discover_in_ns, service_name
                    )

                if discovered:
                    # Use the service's metadata labels as the selector.
                    # Strip Helm housekeeping labels that shouldn't be used
                    # as selectors (they change on upgrades and are not stable).
                    svc_labels = dict(discovered["labels"])
                    _HELM_NOISE = {
                        "helm.sh/chart",
                        "app.kubernetes.io/managed-by",
                        "app.kubernetes.io/version",
                        "operator.opentelemetry.io/collector-service-type",
                    }
                    for key in _HELM_NOISE:
                        svc_labels.pop(key, None)

                    if svc_labels:
                        selector_labels = svc_labels
                        discovery_notes.append(
                            f"Auto-discovered selector labels from "
                            f"Service/{service_name} in {discover_in_ns}: "
                            f"{selector_labels}"
                        )
                    else:
                        discovery_notes.append(
                            f"Service/{service_name} has no usable labels after "
                            "filtering Helm noise; falling back to {{app: service_name}}"
                        )

                    # Auto-detect the best metrics port
                    metrics_port = discovered.get("metrics_port")
                    if metrics_port and metrics_port.get("name"):
                        effective_port = metrics_port["name"]
                        discovery_notes.append(
                            f"Auto-discovered metrics port: "
                            f"{effective_port} (:{metrics_port.get('port')})"
                        )
                    else:
                        discovery_notes.append(
                            f"No well-known metrics port detected; "
                            f"using provided port_name='{port_name}'"
                        )
                elif auto_discover:
                    discovery_notes.append(
                        f"Service/{service_name} not found in namespace {discover_in_ns}; "
                        f"falling back to default selector {{app: {service_name}}}"
                    )

                # ── Build the manifest ───────────────────────────────────
                endpoint: Dict[str, Any] = {
                    "port": effective_port,
                    "path": path,
                    "interval": interval,
                }
                if metric_relabelings:
                    endpoint["metricRelabelings"] = coerce_list(metric_relabelings)

                spec: Dict[str, Any] = {
                    "selector": {
                        "matchLabels": selector_labels,
                    },
                    "endpoints": [endpoint],
                }

                # Add namespaceSelector for cross-namespace scraping
                if target_namespace and target_namespace != namespace:
                    spec["namespaceSelector"] = {
                        "matchNames": [target_namespace]
                    }
                    discovery_notes.append(
                        f"Cross-namespace scraping enabled: namespaceSelector targets '{target_namespace}'"
                    )

                manifest = {
                    "apiVersion": "monitoring.coreos.com/v1",
                    "kind": "ServiceMonitor",
                    "metadata": {
                        "name": name,
                        "namespace": namespace,
                        "labels": extra_labels,
                    },
                    "spec": spec,
                }

                await kubernetes_service.apply_servicemonitor(namespace, manifest)

                import yaml
                manifest_yaml = yaml.dump(manifest, default_flow_style=False)

                notes_str = (
                    f"ServiceMonitor for {service_name} applied to {namespace}. "
                    + " | ".join(discovery_notes)
                )

                return {
                    "applied": f"ServiceMonitor/{name}",
                    "namespace": namespace,
                    "target_namespace": discover_in_ns,
                    "manifest_yaml": manifest_yaml,
                    "notes": notes_str,
                    "auto_discovered": discovered is not None,
                    "discovered_details": discovered,
                }
            except Exception as e:
                raise PrometheusOperationError(f"ServiceMonitor apply failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Delete ServiceMonitor",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_delete_servicemonitor(
            monitor_name: str = Field(
                ..., description="Name of the ServiceMonitor CRD to delete"
            ),
            namespace: str = Field(
                default="monitoring", description="Namespace where the ServiceMonitor lives"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Delete a ServiceMonitor CRD from the cluster.

            Use this to remove stale or incorrectly configured ServiceMonitors.
            MUTATES CLUSTER — deletes a K8s custom resource. Idempotent: safe
            to call even if the resource does not exist.

            **WARNING: Permanently deletes the ServiceMonitor from the cluster.**

            Returns:
            - {"deleted": str, "namespace": str, "status": "deleted" | "not_found"}

            Common errors:
            - Permission denied: Ensure the MCP server has RBAC rights to delete
              ServiceMonitor CRDs in the target namespace.
            """
            try:
                await kubernetes_service.delete_custom_resource(
                    namespace=namespace,
                    group="monitoring.coreos.com",
                    version="v1",
                    plural="servicemonitors",
                    name=monitor_name,
                )
                return {
                    "deleted": f"ServiceMonitor/{monitor_name}",
                    "namespace": namespace,
                    "status": "deleted",
                }
            except Exception as e:
                # delete_custom_resource swallows 404 — only real errors reach here
                raise PrometheusOperationError(f"ServiceMonitor delete failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Apply Probe",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def prom_apply_probe(
            targets: List[str] = Field(
                ..., description="URLs to probe (e.g. ['https://talkops.ai'])"
            ),
            probe_name: Optional[str] = Field(
                default=None, description="Name for the Probe CRD"
            ),
            namespace: str = Field(
                default="monitoring", description="Namespace for the Probe CRD"
            ),
            module: str = Field(
                default="http_2xx", description="Blackbox module to use"
            ),
            prober_url: str = Field(
                default="blackbox-exporter.monitoring.svc.cluster.local:9115", description="Blackbox exporter address"
            ),
            interval: str = Field(
                default="60s", description="Scrape interval"
            ),
            labels: Optional[Dict[str, str]] = Field(
                default=None, description="Extra labels for Probe"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Generate and apply a Probe CRD for Prometheus Operator.

            Use this to configure blackbox monitoring for external endpoints.
            MUTATES CLUSTER — creates a K8s custom resource.

            **WARNING: Creates a Probe CRD in the Kubernetes cluster.**

            Returns:
            - {\"applied\": str, \"namespace\": str, \"manifest_yaml\": str, \"notes\": str}

            Prerequisites:
            - Prometheus Operator must be installed in the cluster
            - Blackbox exporter must be deployed
            """
            try:
                target_list = coerce_list(targets)
                if not target_list:
                    raise ValueError("At least one target URL must be provided")

                extra_labels = coerce_dict(labels) or {}
                operator_labels = await kubernetes_service.get_probe_required_labels()
                if operator_labels:
                    extra_labels.update(operator_labels)

                # Generate a safe name if not provided
                if not probe_name:
                    safe_target = target_list[0].replace("https://", "").replace("http://", "").split("/")[0].replace(".", "-")
                    name = f"probe-{safe_target}"
                else:
                    name = probe_name

                manifest = {
                    "apiVersion": "monitoring.coreos.com/v1",
                    "kind": "Probe",
                    "metadata": {
                        "name": name,
                        "namespace": namespace,
                        "labels": extra_labels,
                    },
                    "spec": {
                        "interval": interval,
                        "module": module,
                        "prober": {
                            "url": prober_url,
                        },
                        "targets": {
                            "staticConfig": {
                                "static": target_list,
                            }
                        }
                    },
                }

                await kubernetes_service.apply_custom_resource(namespace, manifest)

                import yaml
                manifest_yaml = yaml.dump(manifest, default_flow_style=False)

                return {
                    "applied": f"Probe/{name}",
                    "namespace": namespace,
                    "manifest_yaml": manifest_yaml,
                    "notes": f"Probe for {len(target_list)} targets applied to {namespace}",
                }
            except Exception as e:
                raise PrometheusOperationError(f"Probe apply failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Manage File SD Targets",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=False,
            )
        )
        async def prom_manage_file_sd(
            file_sd_path: str = Field(
                ..., description="Path to file_sd JSON file"
            ),
            targets: List[str] = Field(
                ..., description="Target addresses (e.g. ['host:9100'])"
            ),
            file_sd_action: str = Field(
                default="add", description="Sub-action: add or remove"
            ),
            target_labels: Optional[Dict[str, str]] = Field(
                default=None, description="Labels for file_sd targets"
            ),
            backend_id: Optional[str] = Field(
                default=None, description="Backend ID for triggering reload after changes"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Add or remove static targets in a file_sd_configs JSON file.

            MUTATES FILESYSTEM — writes to the specified file path and may
            trigger a Prometheus /-/reload.

            **WARNING: Modifies the file_sd JSON file on disk.**

            Returns:
            - {\"action\": str, \"targets_added|removed\": [str], \"file\": str, \"reload_triggered\": bool}

            Prerequisites:
            - Requires --web.enable-lifecycle flag on Prometheus for reload support.

            Common errors:
            - File not found: Ensure the file_sd_path exists.
            """
            try:
                target_list = coerce_list(targets)
                extra_labels = coerce_dict(target_labels) or {}
                sd_path = Path(file_sd_path)

                # Read existing entries
                existing: List[Dict[str, Any]] = []
                if sd_path.exists():
                    content = sd_path.read_text()
                    if content.strip():
                        existing = json.loads(content)

                if file_sd_action == "add":
                    existing.append({
                        "targets": target_list,
                        "labels": extra_labels,
                    })
                    sd_path.write_text(json.dumps(existing, indent=2))
                    return {
                        "action": "add",
                        "targets_added": target_list,
                        "file": str(sd_path),
                        "reload_triggered": False,
                    }

                elif file_sd_action == "remove":
                    target_set = set(target_list)
                    filtered = [
                        entry for entry in existing
                        if not target_set.intersection(set(entry.get("targets", [])))
                    ]
                    sd_path.write_text(json.dumps(filtered, indent=2))
                    return {
                        "action": "remove",
                        "targets_removed": target_list,
                        "file": str(sd_path),
                        "reload_triggered": False,
                    }
                else:
                    raise PrometheusOperationError(
                        f"Invalid file_sd_action: {file_sd_action}. Must be 'add' or 'remove'."
                    )
            except PrometheusOperationError:
                raise
            except Exception as e:
                raise PrometheusOperationError(f"File SD operation failed: {e}")
