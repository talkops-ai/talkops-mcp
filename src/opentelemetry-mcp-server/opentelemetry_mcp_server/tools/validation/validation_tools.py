"""Pipeline validation and safety-check tools.

Read-only tools that validate collector configurations against
known best practices and common pitfalls.
"""

from typing import Any, Dict, List, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from opentelemetry_mcp_server.exceptions import OtelOperationError
from opentelemetry_mcp_server.tools.base import BaseTool


# Recommended processor ordering per the OTel Collector best practices
_RECOMMENDED_PROCESSOR_ORDER = [
    "memory_limiter",
    "k8sattributes",
    "resourcedetection",
    "resource",
    "transform",
    "filter",
    "attributes",
    "tail_sampling",
    "batch",
]


class ValidationTools(BaseTool):
    """Pipeline validation and filelog safety tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Validate k8sattributes Processor Order",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_validate_k8sattributes_order(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            pipeline_name: Optional[str] = Field(
                default=None,
                description="Specific pipeline to validate (all pipelines if omitted)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Validate processor ordering in collector pipelines.

            Checks that processors follow the recommended order:
            memory_limiter → k8sattributes → resourcedetection →
            transform → filter → tail_sampling → batch.

            Misordered processors can cause data loss or attribute
            enrichment failures. Read-only.

            Returns:
            - {"collector": str, "validations": [{"pipeline": str, "valid": bool, "issues": [...]}]}

            When NOT to use: For checking filelog-specific safety issues,
            use otel_check_filelog_safety.

            Common errors:
            - Collector not found: Verify name and namespace.
            """
            try:
                raw = await kubernetes_service.get_otel_collector(
                    namespace, name
                )
                cfg = collector_config_service.parse_collector_config(raw)

                from opentelemetry_mcp_server.utils.yaml_helpers import (
                    extract_pipelines,
                )

                pipelines = extract_pipelines(cfg)
                validations = []

                target_pipelines = (
                    {pipeline_name: pipelines.get(pipeline_name, {})}
                    if pipeline_name
                    else pipelines
                )

                for pname, pcfg in target_pipelines.items():
                    if not isinstance(pcfg, dict):
                        continue
                    result = collector_config_service.validate_processor_order(
                        cfg, pname, _RECOMMENDED_PROCESSOR_ORDER
                    )
                    validations.append(result)

                all_valid = all(v.get("valid", False) for v in validations)

                return {
                    "collector": f"{namespace}/{name}",
                    "all_valid": all_valid,
                    "validations": validations,
                    "recommended_order": _RECOMMENDED_PROCESSOR_ORDER,
                }
            except Exception as e:
                raise OtelOperationError(
                    f"Failed to validate processor order: {e}"
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Check Filelog Safety",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_check_filelog_safety(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Check filelog receiver configuration for safety issues.

            Detects common log collection pitfalls:
            - Missing storage checkpoint (data loss on restart)
            - Self-collection feedback loops
            - Missing resource detection enrichment

            Read-only — returns warnings and recommendations.

            Returns:
            - {"collector": str, "safe": bool, "warnings": [...], "profile": {...}}

            When NOT to use: For general pipeline validation, use
            otel_validate_k8sattributes_order.

            Common errors:
            - No filelog receiver: Returns safe=True with no warnings.
            """
            try:
                raw = await kubernetes_service.get_otel_collector(
                    namespace, name
                )
                cfg = collector_config_service.parse_collector_config(raw)

                profile = collector_config_service.extract_logs_profile(
                    cfg, name, namespace
                )

                return {
                    "collector": f"{namespace}/{name}",
                    "safe": len(profile.warnings) == 0,
                    "warnings": profile.warnings,
                    "profile": profile.model_dump(),
                }
            except Exception as e:
                raise OtelOperationError(
                    f"Failed to check filelog safety: {e}"
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Inspect Target Allocator State",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_inspect_target_allocator_state(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Inspect Target Allocator state and scrape target assignments.

            Shows the TA configuration, allocation strategy, and
            discovered targets. Useful for debugging unbalanced scrape
            assignments or missing metrics. Read-only.

            Returns:
            - {"collector": str, "target_allocator": {"enabled": bool, "strategy": str, "targets": int, ...}}

            When NOT to use: For PromQL-based metric investigation,
            use the Prometheus MCP server.

            Common errors:
            - TA not enabled: Returns enabled=False.
            """
            try:
                raw = await kubernetes_service.get_otel_collector(
                    namespace, name
                )
                spec = raw.get("spec", {})
                ta_spec = spec.get("targetAllocator", {})

                if not ta_spec.get("enabled", False):
                    return {
                        "collector": f"{namespace}/{name}",
                        "target_allocator": {
                            "enabled": False,
                            "message": "Target Allocator is not enabled for this collector",
                        },
                    }

                return {
                    "collector": f"{namespace}/{name}",
                    "target_allocator": {
                        "enabled": True,
                        "allocation_strategy": ta_spec.get(
                            "allocationStrategy", "consistent-hashing"
                        ),
                        "filter_strategy": ta_spec.get("filterStrategy"),
                        "service_monitor_selector": ta_spec.get(
                            "serviceMonitorSelector", {}
                        ),
                        "pod_monitor_selector": ta_spec.get(
                            "podMonitorSelector", {}
                        ),
                        "replicas": ta_spec.get("replicas", 1),
                        "image": ta_spec.get("image"),
                        "prometheus_cr": ta_spec.get("prometheusCR", {}).get(
                            "enabled", False
                        ),
                    },
                }
            except Exception as e:
                raise OtelOperationError(
                    f"Failed to inspect target allocator: {e}"
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Recommend Collector Topology",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def otel_recommend_collector_topology(
            signals: List[str] = Field(
                ...,
                min_length=1,
                description="Signals to collect: 'traces', 'metrics', 'logs'",
            ),
            workload_count: int = Field(
                default=10,
                ge=1,
                description="Approximate number of workloads to instrument",
            ),
            has_prometheus_targets: bool = Field(
                default=False,
                description="Whether Prometheus scrape targets need to be collected",
            ),
            cluster_size: str = Field(
                default="medium",
                description="Cluster size: 'small' (<20 nodes), 'medium' (20-100), 'large' (100+)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Recommend an OTel Collector deployment topology.

            Analyzes workload requirements and suggests the optimal
            collector deployment mode (DaemonSet, Deployment, Gateway),
            pipeline topology, and resource sizing. Read-only, no
            external calls — pure recommendation engine.

            Returns:
            - {"recommendation": {"mode": str, "pipelines": [...], "sizing": {...}, "notes": [...]}}

            When NOT to use: For inspecting existing collector topology,
            use otel_get_collector or otel_list_collectors.
            """
            recommendations = []
            pipelines = []

            # Determine collector mode
            needs_daemonset = "logs" in signals or has_prometheus_targets
            mode = "daemonset" if needs_daemonset else "deployment"

            if "logs" in signals:
                recommendations.append(
                    "Use DaemonSet mode for log collection (filelog receiver needs host access)"
                )
                pipelines.append({
                    "name": "logs",
                    "signal": "logs",
                    "receivers": ["filelog"],
                    "processors": ["memory_limiter", "k8sattributes", "resourcedetection", "batch"],
                    "exporters": ["otlp"],
                })

            if "traces" in signals:
                pipelines.append({
                    "name": "traces",
                    "signal": "traces",
                    "receivers": ["otlp"],
                    "processors": ["memory_limiter", "k8sattributes", "batch"],
                    "exporters": ["otlp"],
                })
                if workload_count > 50:
                    recommendations.append(
                        "Consider a separate Gateway deployment for traces "
                        "with tail sampling to reduce downstream volume"
                    )

            if "metrics" in signals:
                receivers = ["otlp"]
                if has_prometheus_targets:
                    receivers.append("prometheus")
                    recommendations.append(
                        "Enable Target Allocator for balanced Prometheus scraping across collectors"
                    )

                pipelines.append({
                    "name": "metrics",
                    "signal": "metrics",
                    "receivers": receivers,
                    "processors": ["memory_limiter", "k8sattributes", "batch"],
                    "exporters": ["otlp"],
                })

            # Sizing
            sizing = {
                "small": {"cpu_request": "100m", "memory_request": "256Mi", "memory_limit": "512Mi"},
                "medium": {"cpu_request": "250m", "memory_request": "512Mi", "memory_limit": "1Gi"},
                "large": {"cpu_request": "500m", "memory_request": "1Gi", "memory_limit": "2Gi"},
            }

            # Additional recommendations
            if cluster_size == "large":
                recommendations.append(
                    "Use Gateway pattern: DaemonSet collectors forward to a "
                    "central Gateway Deployment for cross-node processing (tail sampling, spanmetrics)"
                )

            if len(signals) > 1 and cluster_size != "small":
                recommendations.append(
                    "Consider separate collectors per signal type for "
                    "independent scaling and resource isolation"
                )

            return {
                "recommendation": {
                    "mode": mode,
                    "pipelines": pipelines,
                    "sizing": sizing.get(cluster_size, sizing["medium"]),
                    "target_allocator_recommended": has_prometheus_targets,
                    "gateway_recommended": cluster_size == "large" or workload_count > 50,
                    "notes": recommendations,
                },
            }
