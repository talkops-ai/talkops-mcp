"""SpanMetrics connector inspection and enablement tools."""

from typing import Any, Dict, List, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from opentelemetry_mcp_server.exceptions import OtelOperationError
from opentelemetry_mcp_server.tools.base import BaseTool


class SpanMetricsTools(BaseTool):
    """SpanMetrics connector tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Inspect SpanMetrics Config",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_inspect_spanmetrics_config(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Inspect the SpanMetrics connector configuration.

            Shows dimensions, histogram config, pipeline wiring, and
            cardinality estimates for the spanmetrics connector. Read-only.

            Returns:
            - {"collector": str, "profile": {"enabled": bool, "dimensions": [...], "histogram": {...}, ...}}

            When NOT to use: For cardinality remediation, use
            otel_detect_cardinality and
            otel_gen_drop_attribute_rules.

            Common errors:
            - No spanmetrics: Returns enabled=False.
            """
            try:
                raw = await kubernetes_service.get_otel_collector(
                    namespace, name
                )
                cfg = collector_config_service.parse_collector_config(raw)

                profile = collector_config_service.extract_spanmetrics_profile(
                    cfg, name, namespace
                )

                return {
                    "collector": f"{namespace}/{name}",
                    "profile": profile.model_dump(),
                }
            except Exception as e:
                raise OtelOperationError(
                    f"Failed to inspect spanmetrics config: {e}"
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Enable SpanMetrics for Service",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def otel_enable_spanmetrics_for_service(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            collector_name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            dimensions: Optional[List[str]] = Field(
                default=None,
                description="Custom dimensions to extract (e.g., ['http.method', 'http.status_code'])",
            ),
            histogram_buckets: Optional[List[str]] = Field(
                default=None,
                description=(
                    "Custom histogram bucket boundaries as OTel duration strings "
                    "(e.g., ['2ms', '100ms', '1s', '15s'])"
                ),
            ),
            dry_run: bool = Field(
                default=True,
                description="If True, returns the config snippet without applying. Set False after review.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Generate configuration to enable the SpanMetrics connector.

            Creates the YAML config snippet for adding a spanmetrics
            connector to an existing collector. Includes the connector
            definition and pipeline wiring instructions.

            **WARNING: SpanMetrics generates new metric series. Review
            dimension count to avoid cardinality explosion.**

            Returns:
            - {"config_snippet": str, "dimensions": [...], "instructions": str, "dry_run": bool}

            When NOT to use: For inspecting existing spanmetrics, use
            otel_inspect_spanmetrics_config.

            Prerequisites: The collector must have a traces pipeline.
            """
            try:
                from opentelemetry_mcp_server.utils.yaml_helpers import config_to_yaml

                dims = dimensions or [
                    "service.name",
                    "http.method",
                    "http.status_code",
                    "rpc.method",
                ]

                buckets = histogram_buckets or [
                    "2ms", "4ms", "6ms", "8ms", "10ms", "50ms", "100ms",
                    "200ms", "400ms", "800ms", "1s", "1400ms", "2s",
                    "5s", "10s", "15s",
                ]

                connector_config = {
                    "connectors": {
                        "spanmetrics": {
                            "histogram": {
                                "explicit": {
                                    "buckets": buckets,
                                }
                            },
                            "dimensions": [
                                {"name": d} for d in dims
                            ],
                            "metrics_flush_interval": "15s",
                        }
                    }
                }

                config_snippet = config_to_yaml(connector_config)

                pipeline_wiring = (
                    "# Add to service.pipelines:\n"
                    "service:\n"
                    "  pipelines:\n"
                    "    traces:\n"
                    "      exporters: [spanmetrics, otlp]  # Add spanmetrics as exporter\n"
                    "    metrics/spanmetrics:\n"
                    "      receivers: [spanmetrics]  # Spanmetrics output feeds into metrics pipeline\n"
                    "      processors: [batch]\n"
                    "      exporters: [otlp]"
                )

                estimated_series = 100 * len(dims)
                warnings = []
                if len(dims) > 5:
                    warnings.append(
                        f"High dimension count ({len(dims)}) may cause "
                        "cardinality issues. Monitor closely after enabling."
                    )

                if not dry_run:
                    # Apply: fetch collector config, merge connector, patch CRD
                    from opentelemetry_mcp_server.utils.config_merger import merge_connector
                    from opentelemetry_mcp_server.utils.yaml_helpers import (
                        extract_pipelines,
                    )

                    raw = await kubernetes_service.get_otel_collector(
                        namespace, collector_name
                    )
                    current_cfg = collector_config_service.parse_collector_config(raw)

                    # Detect the metrics exporter from existing pipelines
                    current_pipelines = extract_pipelines(current_cfg)
                    metrics_exporters = None
                    for pname, pcfg in current_pipelines.items():
                        if pname.startswith("metrics") and isinstance(pcfg, dict):
                            metrics_exporters = pcfg.get("exporters", [])
                            break
                    # Fall back to traces pipeline exporters (excluding spanmetrics itself)
                    if not metrics_exporters:
                        traces_pipe = current_pipelines.get("traces", {})
                        if isinstance(traces_pipe, dict):
                            metrics_exporters = [
                                e for e in traces_pipe.get("exporters", [])
                                if e != "spanmetrics"
                            ]

                    merged_cfg, changes = merge_connector(
                        current_cfg,
                        "spanmetrics",
                        connector_config["connectors"]["spanmetrics"],
                        source_pipeline="traces",
                        target_pipeline="metrics/spanmetrics",
                        target_pipeline_exporters=metrics_exporters or None,
                        target_pipeline_processors=["batch"],
                    )

                    spec = dict(raw.get("spec", {}))
                    spec["config"] = merged_cfg

                    result = await kubernetes_service.create_or_patch_collector(
                        namespace=namespace,
                        name=collector_name,
                        spec=spec,
                        dry_run=False,
                    )

                    return {
                        "collector": f"{namespace}/{collector_name}",
                        "dry_run": False,
                        "action": "applied",
                        "changes": changes,
                        "dimensions": dims,
                        "histogram_buckets": buckets,
                        "estimated_series_per_service": estimated_series,
                        "warnings": warnings,
                        "message": (
                            f"SpanMetrics connector applied to collector '{collector_name}'. "
                            "Monitor cardinality using otel_detect_cardinality."
                        ),
                    }

                return {
                    "collector": f"{namespace}/{collector_name}",
                    "config_snippet": config_snippet,
                    "pipeline_wiring": pipeline_wiring,
                    "dimensions": dims,
                    "histogram_buckets": buckets,
                    "estimated_series_per_service": estimated_series,
                    "warnings": warnings,
                    "dry_run": dry_run,
                    "instructions": (
                        "1. Add the spanmetrics connector config to your collector YAML\n"
                        "2. Wire the pipeline: traces → spanmetrics → metrics/spanmetrics\n"
                        "3. Deploy and verify metrics appear in your backend\n"
                        "4. Monitor cardinality using otel_detect_cardinality"
                    ),
                    "message": (
                        "Dry run — review the config_snippet above. "
                        "Set dry_run=False to apply."
                    ),
                }
            except OtelOperationError:
                raise
            except Exception as e:
                raise OtelOperationError(
                    f"Failed to generate/apply spanmetrics config: {e}"
                )
