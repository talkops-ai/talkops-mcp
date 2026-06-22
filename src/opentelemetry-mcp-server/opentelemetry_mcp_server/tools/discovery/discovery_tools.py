"""OpenTelemetry collector and service discovery tools.

Provides read-only tools for listing collectors, getting collector details,
and listing instrumented services across the Kubernetes cluster.
"""

from typing import Any, Dict, List, Optional
import datetime

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from opentelemetry_mcp_server.exceptions import OtelOperationError
from opentelemetry_mcp_server.tools.base import BaseTool
from opentelemetry_mcp_server.utils.pagination import paginate


class DiscoveryTools(BaseTool):
    """Collector and service discovery tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="List OTel Collectors",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_list_collectors(
            namespace: Optional[str] = Field(
                default=None,
                description="Kubernetes namespace filter (all namespaces if omitted)",
            ),
            label_selector: Optional[str] = Field(
                default=None,
                description="K8s label selector (e.g., 'app=my-collector')",
            ),
            page_size: int = Field(
                default=50,
                ge=1,
                le=200,
                description="Items per page (default 50, max 200)",
            ),
            cursor: Optional[str] = Field(
                default=None,
                description="Pagination cursor from previous response",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """List OpenTelemetryCollector CRDs with filtering and pagination.

            Use this to discover all OTel collectors in the cluster.
            Returns summary-level data for each collector. Read-only.

            Returns:
            - {"items": [{"name": str, "namespace": str, "mode": str, "summary": str, ...}], "total_count": int, "next_cursor": str|null}

            When NOT to use: For detailed config of a specific collector,
            use otel_get_collector instead.

            Common errors:
            - K8s unreachable: Check otel://system/health resource.
            - No CRDs found: Ensure OTel Operator is installed.
            """
            try:
                raw = await kubernetes_service.list_otel_collectors(
                    namespace=namespace, label_selector=label_selector
                )
                items = raw.get("items", [])

                collectors = []
                for item in items:
                    try:
                        cfg = collector_config_service.parse_collector_config(item)
                        instance = collector_config_service.build_collector_instance(
                            item, cfg, detail_level="summary"
                        )
                        collectors.append(instance.model_dump(exclude={"raw_config_yaml"}))
                    except Exception as e:
                        # Include failed collectors with error info
                        metadata = item.get("metadata", {})
                        collectors.append({
                            "name": metadata.get("name", "unknown"),
                            "namespace": metadata.get("namespace", "unknown"),
                            "error": f"Failed to parse config: {e}",
                        })

                page_items, next_cursor = paginate(collectors, page_size, cursor)

                return {
                    "items": page_items,
                    "total_count": len(collectors),
                    "next_cursor": next_cursor,
                    "page_size": page_size,
                }
            except Exception as e:
                raise OtelOperationError(f"Failed to list collectors: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get OTel Collector Details",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_get_collector(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            detail_level: str = Field(
                default="summary",
                description="Detail level: 'summary' (compact) or 'full' (includes raw YAML config)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Get detailed information about a specific OTel collector.

            Use this for deep inspection of a collector's config, pipelines,
            and status. Use detail_level='full' to include raw YAML. Read-only.

            Returns:
            - {"name": str, "namespace": str, "mode": str, "pipelines": [...], "status": {...}, ...}

            When NOT to use: For listing multiple collectors, use
            otel_list_collectors. For enrichment/logs/spanmetrics profiles,
            use the corresponding otel:// resources.

            Common errors:
            - Collector not found: Verify name and namespace.
            """
            try:
                raw = await kubernetes_service.get_otel_collector(
                    namespace, name
                )
                cfg = collector_config_service.parse_collector_config(raw)
                instance = collector_config_service.build_collector_instance(
                    raw, cfg, detail_level=detail_level
                )
                result = instance.model_dump()

                # Attach service endpoint health (Gap 4)
                try:
                    svc_health = await kubernetes_service.get_collector_service_health(
                        namespace=namespace,
                        collector_name=name,
                    )
                    result["service_health"] = svc_health
                except Exception:
                    # Non-blocking — don't fail the main response
                    result["service_health"] = {
                        "service_found": False,
                        "warnings": ["Service health check unavailable"],
                    }

                return result
            except Exception as e:
                raise OtelOperationError(f"Failed to get collector: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="List Instrumented Services",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_list_instrumented_services(
            namespace: str = Field(
                ..., min_length=1, description="Namespace to scan"
            ),
            page_size: int = Field(
                default=50,
                ge=1,
                le=200,
                description="Items per page",
            ),
            cursor: Optional[str] = Field(
                default=None,
                description="Pagination cursor from previous response",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """List workloads and their OpenTelemetry instrumentation status.

            Scans Deployments in a namespace and reports whether each has
            auto-instrumentation annotations, init containers, and OTEL_*
            env vars. Read-only.

            Returns:
            - {"items": [{"name": str, "kind": str, "language": str|null, "init_container_injected": bool, ...}], "total_count": int}

            When NOT to use: For Instrumentation CRD details, use
            the otel://instrumentation/{ns}/{name} resource.

            Common errors:
            - Empty results: Ensure deployments exist in the namespace.
            """
            try:
                from opentelemetry_mcp_server.utils.k8s_labels import (
                    detect_language_from_annotations,
                    detect_language_from_images,
                    detect_language_from_name,
                    detect_language_from_runtime_env,
                    detect_signals_from_env,
                    get_instrumentation_cr_from_annotations,
                    has_otel_sdk_env,
                )

                deployments = await kubernetes_service.list_deployments(namespace)

                services = []
                for dep in deployments:
                    pod_annotations = dep.get("pod_annotations", {})
                    lang = detect_language_from_annotations(pod_annotations)
                    cr_name = get_instrumentation_cr_from_annotations(pod_annotations)

                    # Fallback 1: detect language from container image names
                    if lang is None:
                        container_images = [
                            c.get("image", "")
                            for c in dep.get("containers", [])
                            if not c.get("is_init_container")
                        ]
                        lang = detect_language_from_images(container_images)

                    # Fallback 2: detect from container or deployment names
                    # (lower confidence — only when images didn't match)
                    if lang is None:
                        for c in dep.get("containers", []):
                            if not c.get("is_init_container"):
                                lang = detect_language_from_name(c.get("name", ""))
                                if lang:
                                    break
                        if lang is None:
                            lang = detect_language_from_name(dep.get("name", ""))

                    # Fallback 3: detect from runtime env vars
                    # (JAVA_HOME, PYTHONPATH, NODE_VERSION, etc.)
                    if lang is None:
                        for c in dep.get("containers", []):
                            if not c.get("is_init_container"):
                                lang = detect_language_from_runtime_env(
                                    c.get("env", {})
                                )
                                if lang:
                                    break

                    # Check for OTel init container
                    init_injected = any(
                        c.get("is_init_container", False)
                        and "opentelemetry" in (c.get("image", "") or "").lower()
                        for c in dep.get("containers", [])
                    )

                    # Check for OTEL_ env vars and detect signals
                    otel_env = False
                    all_signals: list = []
                    for c in dep.get("containers", []):
                        if not c.get("is_init_container"):
                            env = c.get("env", {})
                            if has_otel_sdk_env(env):
                                otel_env = True
                            signals = detect_signals_from_env(env)
                            all_signals.extend(signals)

                    endpoint = None
                    for c in dep.get("containers", []):
                        env = c.get("env", {})
                        endpoint = env.get(
                            "OTEL_EXPORTER_OTLP_ENDPOINT", endpoint
                        )

                    warnings = []
                    if lang and not init_injected and cr_name is None:
                        # Annotation present but init container missing
                        warnings.append(
                            f"Auto-instrumentation annotation for '{lang}' found "
                            "but init container not injected. Check Instrumentation CR."
                        )
                    if otel_env and not cr_name and not detect_language_from_annotations(pod_annotations):
                        # Manual SDK — has OTEL_ env vars but no operator annotation
                        annotation_hint = (
                            f"inject-{lang}" if lang else "inject-<language>"
                        )
                        warnings.append(
                            "Service has OTEL_* env vars but no auto-instrumentation "
                            f"annotation. Consider adding '{annotation_hint}' annotation "
                            "for operator-managed instrumentation."
                        )

                    services.append({
                        "name": dep["name"],
                        "namespace": dep["namespace"],
                        "kind": dep.get("kind", "Deployment"),
                        "language": lang,
                        "instrumentation_cr_name": cr_name,
                        "init_container_injected": init_injected,
                        "sdk_env_vars_present": otel_env,
                        "signals_detected": list(set(all_signals)),
                        "endpoint_configured": endpoint,
                        "ready_replicas": dep.get("ready_replicas", 0),
                        "total_replicas": dep.get("replicas", 0),
                        "warnings": warnings,
                    })

                page_items, next_cursor = paginate(services, page_size, cursor)

                return {
                    "items": page_items,
                    "total_count": len(services),
                    "next_cursor": next_cursor,
                    "page_size": page_size,
                }
            except Exception as e:
                raise OtelOperationError(
                    f"Failed to list instrumented services: {e}"
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Verify Pipeline Health",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_verify_pipeline_health(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            collector_name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            metrics_port: int = Field(
                default=8888,
                description="Internal metrics port (default 8888)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Verify telemetry is actually flowing through a collector's pipeline.

            Use this to confirm data is reaching backends, not just that
            the collector pod is running. Reads the collector's internal
            Prometheus metrics (:8888/metrics) to check exporter
            success/failure counts, receiver acceptance, and queue health.
            Read-only — does not modify any state.

            Returns:
            - {"healthy": bool, "exporters": {...}, "receivers": {...},
               "queue_health": {...}, "warnings": [...]}

            When NOT to use: For K8s-level collector status (pod readiness,
            service endpoints), use otel_get_collector. For config inspection,
            read the otel://collector/* resources.

            Prerequisites: Collector must have internal telemetry enabled
            (service.telemetry.metrics.address, default :8888).

            Common errors:
            - Cannot fetch metrics: Ensure service.telemetry.metrics is configured.
            - No otelcol_* metrics: Collector may be using a custom build without
              internal telemetry support.
            """
            try:
                from opentelemetry_mcp_server.services.collector_metrics_service import (
                    CollectorMetricsService,
                )

                metrics_service = CollectorMetricsService(kubernetes_service)
                report = await metrics_service.fetch_pipeline_health(
                    namespace=namespace,
                    collector_name=collector_name,
                    metrics_port=metrics_port,
                )
                return report.to_dict()
            except OtelOperationError:
                raise
            except Exception as e:
                raise OtelOperationError(
                    f"Failed to verify pipeline health: {e}"
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="List K8s Contexts",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def otel_list_k8s_contexts(
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """List available kubeconfig contexts for multi-cluster operations.

            Use this to discover which Kubernetes clusters are accessible.
            Returns context names from the kubeconfig file with cluster and
            user info. Read-only — does not modify any state.

            Returns:
            - {"contexts": [{"name": str, "cluster": str, "user": str,
               "namespace": str, "is_current": bool}]}

            When NOT to use: For listing OTel collectors or services within
            a cluster, use otel_list_collectors or otel_list_instrumented_services.

            Common errors:
            - Empty list: No kubeconfig file found or running in-cluster mode.
            """
            try:
                contexts = await kubernetes_service.list_available_contexts()
                return {
                    "contexts": contexts,
                    "count": len(contexts),
                    "current": next(
                        (c["name"] for c in contexts if c.get("is_current")),
                        "unknown",
                    ),
                }
            except Exception as e:
                raise OtelOperationError(
                    f"Failed to list K8s contexts: {e}"
                )

        @mcp_instance.tool(
            name="otel_query_a2ui",
            annotations=ToolAnnotations(
                title="OpenTelemetry A2UI Pipelines",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_query_a2ui(
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Retrieve the status of all OpenTelemetry Collectors and their pipelines.
            
            This tool aggregates collector configurations and deep pipeline metrics
            across the cluster and formats the result precisely for the frontend
            A2UI Status Datatable schema.

            Returns:
            - Dict[str, Any]: A JSON object matching the A2UI `kind: "otel"` schema (title, columns, rows).

            When NOT to use:
            - Do not use for general collector discovery or programmatic state checks; use `otel_list_collectors` instead.
            - Do not use to patch or modify collector state.

            Side effects:
            - None — read-only operation.

            Common errors:
            - Kubernetes API errors if cluster access is unavailable.
            """
            try:
                from opentelemetry_mcp_server.services.collector_metrics_service import CollectorMetricsService
                
                # Fetch all collectors
                raw = await kubernetes_service.list_otel_collectors()
                items = raw.get("items", [])
                
                rows = []
                metrics_service = CollectorMetricsService(kubernetes_service)
                
                now = datetime.datetime.now(datetime.timezone.utc)
                
                overall_status_degraded = False

                for item in items:
                    name = item.get("metadata", {}).get("name", "unknown")
                    namespace = item.get("metadata", {}).get("namespace", "unknown")
                    
                    # Calculate Uptime from creationTimestamp
                    creation_str = item.get("metadata", {}).get("creationTimestamp")
                    uptime_str = "Unknown"
                    if creation_str:
                        try:
                            # Example: 2024-03-10T10:15:30Z
                            if creation_str.endswith("Z"):
                                creation_str = creation_str[:-1] + "+00:00"
                            created_dt = datetime.datetime.fromisoformat(creation_str)
                            diff = now - created_dt
                            days, remainder = divmod(diff.total_seconds(), 86400)
                            hours, _ = divmod(remainder, 3600)
                            if days > 0:
                                uptime_str = f"{int(days)}d"
                            else:
                                uptime_str = f"{int(hours)}h"
                        except Exception:
                            pass
                    
                    # Parse config to find pipelines
                    try:
                        cfg = collector_config_service.parse_collector_config(item)
                        instance = collector_config_service.build_collector_instance(item, cfg, detail_level="summary")
                        pipelines = ", ".join(p.name for p in instance.pipelines)
                        if not pipelines:
                            pipelines = "None"
                        phase = instance.status.phase
                    except Exception:
                        pipelines = "Unknown"
                        phase = "Error"
                        
                    # Fetch deep pipeline health
                    status = phase
                    try:
                        # Will check internal metrics
                        report = await metrics_service.fetch_pipeline_health(
                            namespace=namespace,
                            collector_name=name,
                            metrics_port=8888
                        )
                        if report.healthy:
                            status = "Healthy"
                        else:
                            status = "Degraded"
                            overall_status_degraded = True
                    except Exception:
                        # If we can't reach the metrics endpoint, we just use the CRD phase
                        # Phase might be "Running" but we append (No Metrics) if we want, or keep it standard.
                        pass
                        
                    rows.append({
                        "name": name,
                        "status": status,
                        "pipeline": pipelines,
                        "uptime": uptime_str
                    })

                return {
                    "title": "OpenTelemetry Pipelines",
                    "overallSeverity": "warning" if overall_status_degraded else "success",
                    "overallStatusLabel": "Health",
                    "overallStatusValue": "Degraded" if overall_status_degraded else "Healthy",
                    "columns": [
                        {"key": "name", "label": "Collector Name", "sortable": True},
                        {"key": "status", "label": "Status", "sortable": True},
                        {"key": "pipeline", "label": "Pipeline Type", "sortable": False},
                        {"key": "uptime", "label": "Uptime", "sortable": True}
                    ],
                    "rows": rows
                }
            except Exception as e:
                raise OtelOperationError(f"Failed to query OpenTelemetry A2UI pipelines: {e}")
