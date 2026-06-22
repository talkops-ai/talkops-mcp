"""Intent-driven collector provisioning tool.

Provides ``otel_provision_collector`` — the smart, intent-driven entry
point for creating OpenTelemetry collectors. Unlike ``otel_patch_collector``
which requires full config YAML, this tool accepts high-level intents
("I want traces and metrics") and auto-discovers everything else from
the cluster.

This is the TalkOps differentiator: non-DevOps users describe what
they want, and the tool figures out the rest.
"""

from typing import Any, Dict, List, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from opentelemetry_mcp_server.exceptions import (
    OtelOperationError,
    OtelValidationError,
)
from opentelemetry_mcp_server.tools.base import BaseTool

# Valid signals
_VALID_SIGNALS = {"traces", "metrics", "logs"}


class ProvisionTools(BaseTool):
    """Intent-driven collector provisioning tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Provision OpenTelemetry Collector (Smart)",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def otel_provision_collector(
            namespace: str = Field(
                ...,
                min_length=1,
                description=(
                    "Target Kubernetes namespace where the collector "
                    "will be deployed"
                ),
            ),
            signals: List[str] = Field(
                ...,
                min_length=1,
                description=(
                    "Telemetry signals to collect: 'traces', 'metrics', "
                    "'logs'. Example: ['traces', 'metrics']"
                ),
            ),
            name: Optional[str] = Field(
                default=None,
                description=(
                    "Collector name. If omitted, auto-generated as "
                    "'{namespace}-collector'"
                ),
            ),
            exporter_targets: Optional[Dict[str, str]] = Field(
                default=None,
                description=(
                    "Where to send telemetry per signal. "
                    "Example: {'traces': 'jaeger:4317', "
                    "'metrics': 'prometheus:9090'}. "
                    "If omitted, auto-discovered from cluster."
                ),
            ),
            scan_namespaces: Optional[List[str]] = Field(
                default=None,
                description=(
                    "Additional namespaces to scan for backend "
                    "services. If omitted, scans the target namespace "
                    "plus well-known ones (monitoring, observability)."
                ),
            ),
            exporter_overrides: Optional[Dict[str, Dict[str, Any]]] = Field(
                default=None,
                description=(
                    "Per-exporter configuration overrides (headers, TLS, "
                    "auth). Keys are exporter type names (e.g. 'loki', "
                    "'opensearch', 'otlphttp'). Values are config dicts "
                    "deep-merged into the generated exporter config. "
                    "Example for multi-tenant Loki: "
                    "{'loki': {'headers': {'X-Scope-OrgID': 'my-tenant'}}}"
                ),
            ),
            mode: Optional[str] = Field(
                default=None,
                description=(
                    "Deployment mode: 'daemonset', 'deployment', "
                    "'statefulset'. If omitted, auto-selected based "
                    "on signal requirements."
                ),
            ),
            enable_spanmetrics: bool = Field(
                default=False,
                description=(
                    "Enable spanmetrics connector to generate RED "
                    "metrics (Rate, Errors, Duration) from traces"
                ),
            ),
            enable_filelog: bool = Field(
                default=False,
                description=(
                    "Enable filelog receiver for container log "
                    "collection (forces DaemonSet mode)"
                ),
            ),
            prometheus_scrape: bool = Field(
                default=False,
                description=(
                    "Enable Prometheus receiver for scraping Pod/"
                    "ServiceMonitor targets (recommends StatefulSet "
                    "with Target Allocator)"
                ),
            ),
            dry_run: bool = Field(
                default=True,
                description=(
                    "If True, returns the generated spec without "
                    "applying. Set False only after reviewing the "
                    "dry_run output."
                ),
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Provision an OpenTelemetry Collector from intent.

            Smart, intent-driven collector creation that auto-discovers
            backend endpoints, generates best-practice configs, and
            recommends deployment modes. Non-DevOps users only need to
            specify WHAT signals to collect — the tool handles HOW.

            **What this tool does automatically:**
            - Scans the cluster for existing backends (Jaeger, Tempo,
              Prometheus, OpenSearch, Loki)
            - Generates best-practice processor chain with correct
              ordering (memory_limiter → k8sattributes → batch)
            - Selects the right deployment mode from signal requirements
            - Sizes resources from cluster scale
            - Prevents common pitfalls (filelog self-collection, missing
              checkpoints, wrong processor order)

            **WARNING: With dry_run=False, this creates a Kubernetes CRD
            that deploys collector pods.**

            Returns:
            - Complete provisioning result with auto-discovered context,
              generated config, and deployment spec.

            When NOT to use:
            - For expert-level CRD control, use otel_patch_collector.
            - For read-only inspection, use otel_get_collector.

            Prerequisites: OTel Operator must be installed.
            """
            try:
                # ── Validate signals ──
                invalid = set(signals) - _VALID_SIGNALS
                if invalid:
                    raise OtelValidationError(
                        f"Invalid signals: {invalid}. "
                        f"Supported: {sorted(_VALID_SIGNALS)}"
                    )

                # ── Validate exporter_targets keys ──
                if exporter_targets:
                    invalid_targets = set(exporter_targets.keys()) - _VALID_SIGNALS
                    if invalid_targets:
                        raise OtelValidationError(
                            f"Invalid keys in exporter_targets: {invalid_targets}. "
                            f"Keys must be signals: {sorted(_VALID_SIGNALS)}"
                        )

                # ── Initialize config builder ──
                from opentelemetry_mcp_server.services.collector_config_builder import (
                    CollectorConfigBuilder,
                )

                builder = CollectorConfigBuilder(kubernetes_service)

                # ── Auto-generate name if not provided ──
                collector_name = name or f"{namespace}-collector"

                # ── Step 1: Auto-discover cluster context ──
                cluster_size, node_count = await builder.discover_cluster_size()

                # Count workloads in target namespace
                try:
                    deployments = await kubernetes_service.list_deployments(
                        namespace=namespace
                    )
                    workload_count = len(deployments)
                except Exception:
                    workload_count = 0

                # ── Step 2: Auto-discover exporter targets ──
                if exporter_targets:
                    # User provided targets — use them directly
                    discovered_targets = dict(exporter_targets)
                    discovery_meta: Dict[str, Any] = {
                        "scanned_namespaces": [],
                        "existing_collectors": [],
                        "discovered_services": [],
                        "fallbacks_used": [],
                        "user_provided": True,
                    }
                else:
                    # Auto-discover from cluster
                    discovered_targets, discovery_meta = (
                        await builder.discover_exporter_targets(
                            namespace=namespace,
                            signals=signals,
                            scan_namespaces=scan_namespaces,
                        )
                    )

                # ── Step 3: Determine deployment mode ──
                if mode:
                    selected_mode = mode.lower().strip()
                    mode_rationale = f"Mode '{selected_mode}' specified by user"
                else:
                    selected_mode, mode_rationale = builder.recommend_mode(
                        signals, enable_filelog, prometheus_scrape
                    )

                # ── Step 4: Size resources ──
                resources = builder.recommend_resources(cluster_size)

                # ── Step 5: Build the config ──
                generated_config = builder.build_config(
                    signals=signals,
                    exporter_targets=discovered_targets,
                    namespace=namespace,
                    enable_spanmetrics=enable_spanmetrics,
                    enable_filelog=enable_filelog,
                    prometheus_scrape=prometheus_scrape,
                    collector_name=collector_name,
                    exporter_overrides=exporter_overrides,
                )

                # ── Step 6: Convert config to YAML string ──
                from opentelemetry_mcp_server.utils.yaml_helpers import (
                    config_to_yaml,
                )

                config_yaml_str = config_to_yaml(generated_config)

                # ── Step 7: Build CRD spec ──
                crd_group = self.config.otel_operator.crd_group
                crd_version = self.config.otel_operator.crd_api_version

                spec: Dict[str, Any] = {
                    "mode": selected_mode,
                    "image": "otel/opentelemetry-collector-contrib:0.152.1",
                    "config": generated_config,
                    "resources": resources,
                }

                labels = {
                    "app.kubernetes.io/managed-by": "talkops-mcp",
                    "app.kubernetes.io/part-of": "opentelemetry",
                    "talkops.ai/provisioned": "true",
                }

                # Build Target Allocator config for prometheus scraping
                target_allocator = None
                if prometheus_scrape:
                    target_allocator = {
                        "enabled": True,
                        "allocationStrategy": "consistent-hashing",
                        "prometheusCR": {
                            "enabled": True,
                            "serviceMonitorSelector": {},
                            "podMonitorSelector": {},
                        },
                    }
                    spec["targetAllocator"] = target_allocator

                # Add volumes/mounts for filelog
                if enable_filelog:
                    spec["volumes"] = [
                        {
                            "name": "varlogpods",
                            "hostPath": {"path": "/var/log/pods"},
                        },
                        {
                            "name": "file-storage",
                            "emptyDir": {},
                        },
                    ]
                    spec["volumeMounts"] = [
                        {
                            "name": "varlogpods",
                            "mountPath": "/var/log/pods",
                            "readOnly": True,
                        },
                        {
                            "name": "file-storage",
                            "mountPath": "/var/lib/otelcol/file_storage",
                        },
                    ]

                preview_manifest = {
                    "apiVersion": f"{crd_group}/{crd_version}",
                    "kind": "OpenTelemetryCollector",
                    "metadata": {
                        "name": collector_name,
                        "namespace": namespace,
                        "labels": labels,
                    },
                    "spec": spec,
                }

                # ── Summarize pipelines ──
                pipeline_summary = {}
                pipelines = generated_config.get("service", {}).get(
                    "pipelines", {}
                )
                for pname, pcfg in pipelines.items():
                    if isinstance(pcfg, dict):
                        pipeline_summary[pname] = {
                            "receivers": pcfg.get("receivers", []),
                            "processors": pcfg.get("processors", []),
                            "exporters": pcfg.get("exporters", []),
                        }

                # ── Step 7b: Build RBAC for k8sattributes ──
                # The k8sattributes processor requires ClusterRole
                # permissions that the OTel Operator does NOT create.
                rbac_manifests = (
                    kubernetes_service.build_k8sattributes_rbac_manifests(
                        namespace=namespace,
                        collector_name=collector_name,
                    )
                )
                rbac_yaml = config_to_yaml([
                    rbac_manifests["cluster_role"],
                    rbac_manifests["cluster_role_binding"],
                ])

                # ── Build warnings and recommendations ──
                warnings = []
                recommendations = []

                # Warnings for debug exporters
                for signal, target in discovered_targets.items():
                    if target == "__debug__":
                        warnings.append(
                            f"⚠️ No backend found for '{signal}' — "
                            f"using debug exporter (stdout only). "
                            f"Specify exporter_targets to route to "
                            f"a real backend."
                        )

                # Smart recommendations
                if "traces" in signals and not enable_spanmetrics:
                    recommendations.append(
                        "💡 Consider enable_spanmetrics=True to get "
                        "automatic RED metrics (Rate, Errors, Duration) "
                        "from your traces"
                    )
                if (
                    "logs" in signals
                    and not enable_filelog
                ):
                    recommendations.append(
                        "💡 Consider enable_filelog=True if you want "
                        "container log collection via filelog receiver "
                        "(will switch to DaemonSet mode)"
                    )
                if workload_count > 30 and cluster_size == "small":
                    recommendations.append(
                        "💡 High workload density on a small cluster — "
                        "consider separate collectors per signal type"
                    )
                if prometheus_scrape and selected_mode != "statefulset":
                    recommendations.append(
                        "⚠️ Prometheus scraping works best with "
                        "StatefulSet mode for stable Target Allocator "
                        "assignments"
                    )

                # ── Step 8: Apply or return dry run ──
                if dry_run:
                    return {
                        "action": "dry_run",
                        "dry_run": True,
                        "name": collector_name,
                        "namespace": namespace,
                        "mode": selected_mode,
                        "mode_rationale": mode_rationale,
                        "cluster_context": {
                            "cluster_size": cluster_size,
                            "node_count": node_count,
                            "workload_count": workload_count,
                        },
                        "auto_discovered": discovery_meta,
                        "exporter_targets": discovered_targets,
                        "generated_config_yaml": config_yaml_str,
                        "pipeline_summary": pipeline_summary,
                        "resource_sizing": resources,
                        "spec_yaml": config_to_yaml(preview_manifest),
                        "rbac_resources": {
                            "description": (
                                "RBAC resources required by the "
                                "k8sattributes processor. These will "
                                "be auto-created when dry_run=False."
                            ),
                            "cluster_role": rbac_manifests["cluster_role"]["metadata"]["name"],
                            "service_account": f"{collector_name}-collector",
                            "rbac_yaml": rbac_yaml,
                        },
                        "warnings": warnings,
                        "recommendations": recommendations,
                        "message": (
                            "🔍 Review the generated config and spec "
                            "above. Set dry_run=False to apply to the "
                            "cluster."
                        ),
                    }

                # ── Apply to cluster ──
                result = (
                    await kubernetes_service.create_or_patch_collector(
                        namespace=namespace,
                        name=collector_name,
                        spec=spec,
                        labels=labels,
                        overwrite=False,
                        dry_run=False,
                    )
                )

                # ── Create RBAC for k8sattributes ──
                rbac_result = (
                    await kubernetes_service.create_k8sattributes_rbac(
                        namespace=namespace,
                        collector_name=collector_name,
                    )
                )

                return {
                    "action": "applied",
                    "dry_run": False,
                    "name": collector_name,
                    "namespace": namespace,
                    "mode": selected_mode,
                    "mode_rationale": mode_rationale,
                    "cluster_context": {
                        "cluster_size": cluster_size,
                        "node_count": node_count,
                        "workload_count": workload_count,
                    },
                    "auto_discovered": discovery_meta,
                    "exporter_targets": discovered_targets,
                    "pipeline_summary": pipeline_summary,
                    "resource_sizing": resources,
                    "result": {
                        "name": result.get("metadata", {}).get("name"),
                        "namespace": result.get("metadata", {}).get(
                            "namespace"
                        ),
                        "uid": result.get("metadata", {}).get("uid"),
                        "resource_version": result.get(
                            "metadata", {}
                        ).get("resourceVersion"),
                    },
                    "rbac_result": rbac_result,
                    "warnings": warnings,
                    "recommendations": recommendations,
                    "message": (
                        "✅ Collector provisioned successfully! "
                        f"'{collector_name}' is now deploying in "
                        f"namespace '{namespace}'. "
                        "RBAC for k8sattributes processor has been "
                        "created automatically."
                    ),
                }

            except (OtelValidationError, OtelOperationError):
                raise
            except Exception as e:
                raise OtelOperationError(
                    f"Failed to provision collector: {e}"
                )
