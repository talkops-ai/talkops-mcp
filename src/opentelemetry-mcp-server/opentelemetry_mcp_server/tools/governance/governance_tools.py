"""Metric cardinality governance and attribute management tools.

Read-only tools for detecting cardinality issues and generating
transform processor YAML to remediate them.
"""

from typing import Any, Dict, List, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from opentelemetry_mcp_server.exceptions import OtelOperationError
from opentelemetry_mcp_server.tools.base import BaseTool


class GovernanceTools(BaseTool):
    """Metric cardinality governance tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Detect Metric Cardinality Issues",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_detect_cardinality(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Detect potential metric cardinality issues in a collector.

            Analyzes the collector's pipeline topology and spanmetrics
            connector config to estimate metric series counts and flag
            high-cardinality dimensions. Read-only.

            Returns:
            - {"collector": str, "issues": [{"metric_name": str, "severity": str, ...}], "total_estimated_series": int}

            When NOT to use: For actual live cardinality metrics, use
            the Prometheus MCP server with PromQL queries.

            Common errors:
            - No spanmetrics: Returns empty issues if no spanmetrics connector found.
            """
            try:
                raw = await kubernetes_service.get_otel_collector(
                    namespace, name
                )
                cfg = collector_config_service.parse_collector_config(raw)

                sm_profile = collector_config_service.extract_spanmetrics_profile(
                    cfg, name, namespace
                )

                issues = []
                total_series = 0

                if sm_profile.enabled:
                    # Analyze spanmetrics dimensions
                    dims = sm_profile.dimensions
                    if len(dims) > 5:
                        issues.append({
                            "metric_name": "span.metrics.*",
                            "estimated_series": sm_profile.estimated_series_per_service or 0,
                            "high_cardinality_labels": [
                                d.get("name", "unknown") for d in dims
                            ],
                            "source": "spanmetrics",
                            "recommendation": (
                                f"Reduce dimensions from {len(dims)} to ≤5. "
                                "Use exclude_dimensions or transform processor."
                            ),
                            "severity": "critical" if len(dims) > 10 else "warning",
                        })

                    if sm_profile.estimated_series_per_service:
                        total_series += sm_profile.estimated_series_per_service

                    # Check histogram bucket count
                    if sm_profile.histogram.explicit_buckets:
                        bucket_count = len(sm_profile.histogram.explicit_buckets)
                        if bucket_count > 20:
                            issues.append({
                                "metric_name": "span.metrics.duration_histogram",
                                "estimated_series": bucket_count * max(1, len(dims)) * 10,
                                "high_cardinality_labels": ["le (histogram bucket)"],
                                "source": "spanmetrics",
                                "recommendation": (
                                    f"Reduce histogram buckets from {bucket_count} to ≤15. "
                                    "Consider exponential histograms for automatic bucketing."
                                ),
                                "severity": "warning",
                            })

                # Check for transform processors that might indicate existing remediation
                from opentelemetry_mcp_server.utils.yaml_helpers import (
                    find_processors_of_type,
                )

                transform_procs = find_processors_of_type(cfg, "transform")
                has_remediation = len(transform_procs) > 0

                return {
                    "collector": f"{namespace}/{name}",
                    "total_estimated_series": total_series,
                    "issues": issues,
                    "total_issues": len(issues),
                    "existing_remediation": has_remediation,
                    "transform_processors": transform_procs,
                    "spanmetrics_enabled": sm_profile.enabled,
                }
            except Exception as e:
                raise OtelOperationError(
                    f"Failed to detect cardinality issues: {e}"
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Generate Transform Rules to Drop Attributes",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def otel_gen_drop_attribute_rules(
            attributes: List[str] = Field(
                ...,
                min_length=1,
                description="List of attribute names to drop (e.g., ['http.user_agent', 'url.full'])",
            ),
            signal: str = Field(
                default="metrics",
                description="Signal type: 'metrics', 'traces', or 'logs'",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Generate a transform processor YAML snippet to drop attributes.

            Use this after detecting cardinality issues to generate the
            config patch needed to drop high-cardinality attributes.
            Read-only — returns YAML text, does not apply it.

            Returns:
            - {"yaml_snippet": str, "attributes_to_drop": [...], "signal": str, "instructions": str}

            When NOT to use: For detecting which attributes to drop, use
            otel_detect_cardinality first.
            """
            from opentelemetry_mcp_server.utils.yaml_helpers import config_to_yaml

            # Build signal-specific transform config
            context_map = {
                "metrics": "datapoint",
                "traces": "span",
                "logs": "log",
            }
            context = context_map.get(signal, "datapoint")
            statement_key = f"{signal}_statements"

            config = {
                "processors": {
                    f"transform/drop_{signal}_attributes": {
                        statement_key: [
                            {
                                "context": context,
                                "statements": [
                                    f'delete_key(attributes, "{attr}")'
                                    for attr in attributes
                                ],
                            }
                        ]
                    }
                }
            }
            yaml_snippet = config_to_yaml(config)

            return {
                "yaml_snippet": yaml_snippet,
                "attributes_to_drop": attributes,
                "signal": signal,
                "instructions": (
                    "1. Add this processor to your collector config under 'processors:'\n"
                    f"2. Add 'transform/drop_{signal}_attributes' to the {signal} "
                    "pipeline's processors list\n"
                    "3. Place it BEFORE the batch processor\n"
                    f"4. Apply the config change and verify {signal} attributes are dropping"
                ),
            }

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Analyze eBPF Instrumentation Footprint",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_analyze_ebpf_footprint(
            namespace: Optional[str] = Field(
                default=None,
                description="Namespace to scan (all namespaces if omitted)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Analyze eBPF instrumentation pods for security posture.

            Scans for eBPF-based observability agents (OpenTelemetry eBPF,
            Grafana Beyla) and audits their security context: privileged
            mode, host PID, Linux capabilities, and host volume mounts.
            Read-only.

            Returns:
            - {"namespace": str, "total_ebpf_pods": int, "risk_level": str, "pods": [...], "recommendations": [...]}

            When NOT to use: For SDK-based (non-eBPF) instrumentation
            status, use otel_list_instrumented_services.

            Common errors:
            - No eBPF pods found: Returns empty list with risk_level='low'.
            """
            try:
                from opentelemetry_mcp_server.utils.k8s_labels import EBPF_AGENT_LABELS

                all_ebpf_pods = []
                for label in EBPF_AGENT_LABELS:
                    pods = await kubernetes_service.list_pods(
                        namespace=namespace, label_selector=label
                    )
                    all_ebpf_pods.extend(pods)

                # Deduplicate by pod name
                seen = set()
                unique_pods = []
                for p in all_ebpf_pods:
                    key = f"{p['namespace']}/{p['name']}"
                    if key not in seen:
                        seen.add(key)
                        unique_pods.append(p)

                # Analyze security context
                pod_details = []
                total_privileged = 0
                total_host_pid = 0
                all_capabilities = set()
                all_host_mounts = set()

                for pod in unique_pods[:50]:  # Limit to first 50
                    is_privileged = False
                    pod_caps = []
                    pod_mounts = []

                    for c in pod.get("containers", []):
                        sc = c.get("security_context", {})
                        if sc.get("privileged"):
                            is_privileged = True
                        caps = sc.get("capabilities", [])
                        pod_caps.extend(caps)

                        for vm in c.get("volume_mounts", []):
                            if "/sys" in vm.get("mount_path", "") or "/proc" in vm.get("mount_path", ""):
                                pod_mounts.append(vm["mount_path"])

                    for hv in pod.get("host_volumes", []):
                        all_host_mounts.add(hv.get("host_path", ""))
                        pod_mounts.append(hv.get("host_path", ""))

                    if is_privileged:
                        total_privileged += 1
                    if pod.get("host_pid"):
                        total_host_pid += 1

                    all_capabilities.update(pod_caps)

                    pod_details.append({
                        "pod_name": pod["name"],
                        "namespace": pod["namespace"],
                        "node_name": pod.get("node_name"),
                        "privileged": is_privileged,
                        "host_pid": pod.get("host_pid", False),
                        "capabilities": pod_caps,
                        "volume_mounts": list(set(pod_mounts)),
                    })

                # Risk assessment
                risk_level = "low"
                recommendations = []
                if total_privileged > 0:
                    risk_level = "high"
                    recommendations.append(
                        "Replace privileged mode with minimal capabilities (BPF, PERFMON, SYS_PTRACE)"
                    )
                if total_host_pid > 0:
                    risk_level = max(risk_level, "medium", key=["low", "medium", "high", "critical"].index)
                    recommendations.append(
                        "Review hostPID requirement — newer eBPF agents may not need it"
                    )
                if "SYS_ADMIN" in all_capabilities:
                    risk_level = "critical"
                    recommendations.append(
                        "Replace SYS_ADMIN with fine-grained capabilities (BPF, PERFMON)"
                    )

                if not recommendations:
                    recommendations.append("No security concerns detected")

                return {
                    "namespace": namespace or "all",
                    "total_ebpf_pods": len(unique_pods),
                    "risk_level": risk_level,
                    "total_privileged": total_privileged,
                    "total_host_pid": total_host_pid,
                    "unique_capabilities": sorted(all_capabilities),
                    "unique_host_mounts": sorted(all_host_mounts),
                    "pods": pod_details,
                    "recommendations": recommendations,
                }
            except Exception as e:
                raise OtelOperationError(
                    f"Failed to analyze eBPF footprint: {e}"
                )
