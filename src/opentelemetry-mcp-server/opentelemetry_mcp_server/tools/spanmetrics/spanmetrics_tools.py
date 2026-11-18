"""Trace-to-metrics connector configuration tool.

Provides ``otel_configure_connectors`` for enabling ``spanmetrics`` (RED
metrics from spans) and ``servicegraph`` (service dependency topology
metrics) connectors with high-cardinality dimension guards.
"""

from typing import Any, Dict, List, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from opentelemetry_mcp_server.exceptions import (
    OtelOperationError,
    OtelValidationError,
)
from opentelemetry_mcp_server.models.findings import Finding, FindingCode
from opentelemetry_mcp_server.services.config_linter import (
    _HIGH_CARDINALITY_DIMENSIONS,
)
from opentelemetry_mcp_server.tools.base import BaseTool
from opentelemetry_mcp_server.utils.config_merger import (
    ensure_presampling_connector_split,
    merge_connector,
)
from opentelemetry_mcp_server.utils.yaml_helpers import (
    config_to_yaml,
    extract_pipelines,
)

_VALID_CONNECTORS = {"spanmetrics", "servicegraph"}


class SpanMetricsTools(BaseTool):
    """Trace-to-metrics connector configuration tools."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register_tool("pipeline", is_write=True):
            return

        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Configure Trace-to-Metrics Connectors",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def otel_configure_connectors(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            collector_name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            connectors: List[str] = Field(
                ...,
                min_length=1,
                description=(
                    "Connectors to enable: 'spanmetrics' (RED metrics from spans) "
                    "and/or 'servicegraph' (service topology edges)"
                ),
            ),
            connector_options: Optional[Dict[str, Any]] = Field(
                default=None,
                description=(
                    "Optional connector settings dict supporting keys: "
                    "'dimensions' (list of attribute names), "
                    "'histogram_type' ('explicit' or 'exponential'), "
                    "'histogram_buckets' (list of duration strings for spanmetrics), "
                    "'metrics_flush_interval' (str, default '15s'), "
                    "'latency_histogram_buckets' (list for servicegraph), "
                    "'store_ttl' (str, default '2s' for servicegraph), "
                    "'store_max_items' (int, default 1000 for servicegraph)"
                ),
            ),
            dry_run: bool = Field(
                default=True,
                description=(
                    "If True, returns the connector YAML snippet and cardinality "
                    "estimates without applying. Set False after reviewing."
                ),
            ),
            confirm: bool = Field(
                default=False,
                description=(
                    "Set True to confirm applying connector changes when dry_run=False"
                ),
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Configure spanmetrics and/or servicegraph connectors on a collector.

            Wires each connector as an exporter in the ``traces`` pipeline and
            as a receiver in a dedicated ``metrics/{connector}`` pipeline, while
            checking for high-cardinality dimension configurations.
            """
            try:
                if not dry_run:
                    self.require_write_access("otel_configure_connectors")

                invalid = set(connectors) - _VALID_CONNECTORS
                if invalid:
                    raise OtelValidationError(
                        f"Unsupported connectors: {invalid}. "
                        f"Supported: {sorted(_VALID_CONNECTORS)}"
                    )

                opts = dict(connector_options or {})
                dims: List[str] = list(
                    opts.get("dimensions")
                    or [
                        "service.name",
                        "http.method",
                        "http.status_code",
                        "rpc.method",
                    ]
                )
                histogram_type = str(
                    opts.get("histogram_type", "explicit")
                ).lower()
                buckets: List[str] = list(
                    opts.get("histogram_buckets")
                    or [
                        "2ms",
                        "4ms",
                        "6ms",
                        "8ms",
                        "10ms",
                        "50ms",
                        "100ms",
                        "200ms",
                        "400ms",
                        "800ms",
                        "1s",
                        "1400ms",
                        "2s",
                        "5s",
                        "10s",
                        "15s",
                    ]
                )
                flush_interval = str(
                    opts.get("metrics_flush_interval", "15s")
                )

                findings: List[Finding] = []
                warnings: List[str] = []

                bad_dims = [
                    d
                    for d in dims
                    if d.lower() in _HIGH_CARDINALITY_DIMENSIONS
                ]
                if len(dims) > 5 or bad_dims:
                    msg = (
                        f"High-cardinality connector configuration: {len(dims)} "
                        f"dimensions configured"
                        + (
                            f", including unbounded dimension(s) {bad_dims}"
                            if bad_dims
                            else ""
                        )
                        + "."
                    )
                    warnings.append(msg)
                    findings.append(
                        Finding.create(
                            FindingCode.CFG_SPANMETRICS_HIGH_CARDINALITY,
                            message=msg,
                            field_path="connectors.spanmetrics.dimensions",
                            remediation=(
                                "Keep connector dimensions <= 5 and avoid unbounded "
                                "identifiers (user.id, session.id, request.id, trace.id)."
                            ),
                        )
                    )

                connectors_block: Dict[str, Any] = {}
                if "spanmetrics" in connectors:
                    hist_cfg: Dict[str, Any] = (
                        {"exponential": {"max_size": 160}}
                        if histogram_type == "exponential"
                        else {"explicit": {"buckets": buckets}}
                    )
                    connectors_block["spanmetrics"] = {
                        "histogram": hist_cfg,
                        "dimensions": [{"name": d} for d in dims],
                        "metrics_flush_interval": flush_interval,
                    }

                if "servicegraph" in connectors:
                    sg_buckets = list(
                        opts.get("latency_histogram_buckets")
                        or [
                            "2ms",
                            "10ms",
                            "50ms",
                            "100ms",
                            "250ms",
                            "500ms",
                            "1s",
                            "2.5s",
                            "5s",
                            "10s",
                        ]
                    )
                    sg_dims = [
                        d
                        for d in dims
                        if d != "service.name"
                    ]
                    connectors_block["servicegraph"] = {
                        "latency_histogram_buckets": sg_buckets,
                        "dimensions": sg_dims,
                        "store": {
                            "ttl": str(opts.get("store_ttl", "2s")),
                            "max_items": int(
                                opts.get("store_max_items", 1000)
                            ),
                        },
                    }

                config_snippet = config_to_yaml(
                    {"connectors": connectors_block}
                )
                estimated_series = 100 * max(1, len(dims)) * len(connectors)

                if dry_run:
                    return {
                        "collector": f"{namespace}/{collector_name}",
                        "dry_run": True,
                        "action": "dry_run",
                        "connectors": connectors,
                        "config_snippet": config_snippet,
                        "dimensions": dims,
                        "histogram_buckets": buckets,
                        "estimated_series_per_service": estimated_series,
                        "warnings": warnings,
                        "findings": [f.model_dump() for f in findings],
                        "message": (
                            "Dry run — review the connector config_snippet above. "
                            "Set dry_run=False to apply."
                        ),
                    }

                raw = await kubernetes_service.get_otel_collector(
                    namespace, collector_name
                )
                current_cfg = collector_config_service.parse_collector_config(
                    raw
                )

                current_pipelines = extract_pipelines(current_cfg)
                metrics_exporters = None
                for pname, pcfg in current_pipelines.items():
                    if pname.startswith("metrics") and isinstance(pcfg, dict):
                        metrics_exporters = [
                            e
                            for e in pcfg.get("exporters", [])
                            if e not in _VALID_CONNECTORS
                        ]
                        if metrics_exporters:
                            break

                merged_cfg = dict(current_cfg)
                if not metrics_exporters:
                    defined_exps = merged_cfg.get("exporters", {}) or {}
                    cand_metric_exps = [
                        ename
                        for ename in defined_exps
                        if ename.startswith(("prometheus", "otlphttp/metrics", "otlphttp/prometheus"))
                    ]
                    if cand_metric_exps:
                        metrics_exporters = [cand_metric_exps[0]]
                    else:
                        from opentelemetry_mcp_server.services.collector_config_builder import (
                            CollectorConfigBuilder,
                        )

                        builder = CollectorConfigBuilder(kubernetes_service)
                        disc_targets, _ = await builder.discover_exporter_targets(
                            namespace=namespace,
                            signals=["metrics"],
                        )
                        built_exps = builder._build_exporters(disc_targets)
                        merged_exps = dict(merged_cfg.get("exporters") or {})
                        for ek, ev in built_exps.items():
                            merged_exps.setdefault(ek, ev)
                        merged_cfg["exporters"] = merged_exps
                        metrics_exporters = list(built_exps.keys()) or ["debug"]

                defined_procs = merged_cfg.get("processors", {}) or {}
                metric_pipe_procs = (
                    ["memory_limiter", "batch"]
                    if "memory_limiter" in defined_procs
                    else ["batch"]
                )
                if "batch" not in defined_procs:
                    merged_procs = dict(defined_procs)
                    merged_procs["batch"] = {}
                    merged_cfg["processors"] = merged_procs

                all_changes: List[str] = []
                for conn_name, conn_cfg in connectors_block.items():
                    merged_cfg, changes = merge_connector(
                        merged_cfg,
                        conn_name,
                        conn_cfg,
                        source_pipeline="traces",
                        target_pipeline=f"metrics/{conn_name}",
                        target_pipeline_exporters=metrics_exporters or None,
                        target_pipeline_processors=metric_pipe_procs,
                    )
                    all_changes.extend(changes)

                merged_cfg, split_changes = ensure_presampling_connector_split(
                    merged_cfg
                )
                all_changes.extend(split_changes)

                spec = dict(raw.get("spec", {}) or {})
                spec["config"] = merged_cfg

                await kubernetes_service.create_or_patch_collector(
                    namespace=namespace,
                    name=collector_name,
                    spec=spec,
                    dry_run=False,
                )

                return {
                    "collector": f"{namespace}/{collector_name}",
                    "dry_run": False,
                    "action": "applied",
                    "connectors": connectors,
                    "changes": all_changes,
                    "dimensions": dims,
                    "histogram_buckets": buckets,
                    "estimated_series_per_service": estimated_series,
                    "warnings": warnings,
                    "findings": [f.model_dump() for f in findings],
                    "message": (
                        f"Configured connector(s) {connectors} on collector "
                        f"'{collector_name}'."
                    ),
                }
            except (OtelValidationError, OtelOperationError):
                raise
            except Exception as e:
                self.handle_error(
                    e,
                    tool_name="otel_configure_connectors",
                    namespace=namespace,
                    resource_name=collector_name,
                )
                raise
